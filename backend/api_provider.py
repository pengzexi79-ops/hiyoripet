# Runtime API profiles and protocol adapters for official or relay endpoints.
from __future__ import annotations

import base64
import ctypes
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import AsyncIterator

import aiohttp
from openai import AsyncOpenAI

PROTOCOLS = {"openai-compatible", "anthropic-messages", "gemini"}


@dataclass
class ApiSettings:
    protocol: str
    base_url: str
    api_key: str
    model: str

    def validate(self) -> "ApiSettings":
        self.protocol = self.protocol.strip()
        self.base_url = self.base_url.strip().rstrip("/")
        self.api_key = self.api_key.strip()
        self.model = self.model.strip()
        if self.protocol not in PROTOCOLS:
            raise ValueError("不支持的 API 协议")
        if not self.base_url.startswith(("https://", "http://")):
            raise ValueError("API 地址必须以 http:// 或 https:// 开头")
        if not self.api_key:
            raise ValueError("请输入 API Key")
        if not self.model:
            raise ValueError("请输入模型名称")
        return self


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        return data
    source = ctypes.create_string_buffer(data)
    source_blob = _Blob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    result = _Blob()
    crypt32 = ctypes.windll.crypt32
    if decrypt:
        ok = crypt32.CryptUnprotectData(ctypes.byref(source_blob), None, None, None, None, 0, ctypes.byref(result))
    else:
        ok = crypt32.CryptProtectData(ctypes.byref(source_blob), "HiyoriPet API Key", None, None, None, 0, ctypes.byref(result))
    if not ok:
        raise OSError("Windows DPAPI 加密失败")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.windll.kernel32.LocalFree(result.data)


def _settings_path() -> Path:
    root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return root / "HiyoriPet" / "api.json"


def load_user_settings() -> ApiSettings | None:
    path = _settings_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["api_key"] = _dpapi(base64.b64decode(raw.pop("encrypted_key")), True).decode("utf-8")
        return ApiSettings(**raw).validate()
    except Exception:
        return None


def save_user_settings(settings: ApiSettings) -> None:
    settings.validate()
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = asdict(settings)
    raw["encrypted_key"] = base64.b64encode(_dpapi(raw.pop("api_key").encode("utf-8"))).decode("ascii")
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def clear_user_settings() -> None:
    _settings_path().unlink(missing_ok=True)


def _endpoint(base: str, leaf: str, version: str = "v1") -> str:
    base = base.rstrip("/")
    if base.endswith("/" + leaf):
        return base
    if base.endswith("/" + version) or re.search(r"/v\d+(?:beta\d*)?$", base):
        return f"{base}/{leaf}"
    return f"{base}/{version}/{leaf}"


def _image_data_url(value: str) -> tuple[str, str]:
    match = re.match(r"^data:([^;]+);base64,(.+)$", value, re.DOTALL)
    if not match:
        raise ValueError("multimodal image must be a data URL")
    return match.group(1), match.group(2)


def _provider_content(message: dict, protocol: str):
    text = str(message.get("content", ""))
    image = message.get("image")
    if not image:
        return text
    if protocol == "openai-compatible":
        return [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": str(image)}},
        ]
    media_type, encoded = _image_data_url(str(image))
    if protocol == "anthropic-messages":
        return [
            {"type": "text", "text": text},
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": encoded}},
        ]
    raise ValueError("gemini image parts are converted separately")


class UniversalLLM:
    def __init__(self, settings: ApiSettings):
        self.settings = settings.validate()

    async def chat_iter(self, messages: list[dict]) -> AsyncIterator[str]:
        if self.settings.protocol == "openai-compatible":
            async for text in self._openai(messages):
                yield text
        elif self.settings.protocol == "anthropic-messages":
            yield await self._anthropic(messages)
        else:
            yield await self._gemini(messages)

    async def _openai(self, messages: list[dict]) -> AsyncIterator[str]:
        client = AsyncOpenAI(base_url=self.settings.base_url, api_key=self.settings.api_key)
        request_messages = [{**message, "content": _provider_content(message, "openai-compatible")} for message in messages]
        stream = await client.chat.completions.create(model=self.settings.model, messages=request_messages, stream=True)
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def _anthropic(self, messages: list[dict]) -> str:
        system = "\n".join(str(m["content"]) for m in messages if m.get("role") == "system")
        body = {
            "model": self.settings.model,
            "max_tokens": 512,
            "system": system,
            "messages": [
                {**message, "content": _provider_content(message, "anthropic-messages")}
                for message in messages if message.get("role") in ("user", "assistant")
            ],
        }
        headers = {
            "x-api-key": self.settings.api_key,
            "Authorization": f"Bearer {self.settings.api_key}",
            "anthropic-version": "2023-06-01",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(_endpoint(self.settings.base_url, "messages"), json=body, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
        return "".join(item.get("text", "") for item in data.get("content", []) if item.get("type") == "text")

    async def _gemini(self, messages: list[dict]) -> str:
        system = "\n".join(str(m["content"]) for m in messages if m.get("role") == "system")
        contents = []
        for message in messages:
            if message.get("role") == "system":
                continue
            role = "model" if message.get("role") == "assistant" else "user"
            parts = [{"text": str(message.get("content", ""))}]
            if message.get("image"):
                media_type, encoded = _image_data_url(str(message["image"]))
                parts.append({"inline_data": {"mime_type": media_type, "data": encoded}})
            contents.append({"role": role, "parts": parts})
        body = {"contents": contents}
        if system:
            body["system_instruction"] = {"parts": [{"text": system}]}
        url = _endpoint(self.settings.base_url, f"models/{self.settings.model}:generateContent", "v1beta")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=body,
                headers={
                    "x-goog-api-key": self.settings.api_key,
                    "Authorization": f"Bearer {self.settings.api_key}",
                },
            ) as response:
                response.raise_for_status()
                data = await response.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        return "".join(part.get("text", "") for part in parts)
