"""Provider discovery, connection checks, and encrypted multi-model catalog."""
from __future__ import annotations

import base64
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import aiohttp

from api_provider import ApiSettings, UniversalLLM, _dpapi, _endpoint, _settings_path


@dataclass
class ModelProfile:
    id: str
    name: str
    protocol: str
    base_url: str
    api_key: str
    enabled: bool = True
    role: str = "worker"
    capabilities: list[str] | None = None
    tasks: list[str] | None = None

    def validate(self) -> "ModelProfile":
        self.id = self.id.strip()
        self.name = self.name.strip() or self.id
        ApiSettings(self.protocol, self.base_url, self.api_key, self.id).validate()
        self.role = self.role if self.role in {"primary", "worker", "judge"} else "worker"
        allowed_capabilities = {"text", "vision", "audio"}
        raw_capabilities = self.capabilities if isinstance(self.capabilities, list) else ["text"]
        self.capabilities = list(dict.fromkeys(str(value) for value in raw_capabilities if str(value) in allowed_capabilities)) or ["text"]
        allowed_tasks = {"chat", "vision", "scene"}
        defaults = ["chat", "scene"] + (["vision"] if "vision" in self.capabilities else [])
        raw_tasks = self.tasks if isinstance(self.tasks, list) else defaults
        self.tasks = list(dict.fromkeys(str(value) for value in raw_tasks if str(value) in allowed_tasks)) or ["chat"]
        if "vision" in self.tasks and "vision" not in self.capabilities:
            self.tasks.remove("vision")
        return self

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "protocol": self.protocol,
            "base_url": self.base_url,
            "enabled": self.enabled,
            "role": self.role,
            "capabilities": self.capabilities,
            "tasks": self.tasks,
        }


def _catalog_path() -> Path:
    return _settings_path().with_name("models.json")


def _read_catalog() -> tuple[list[ModelProfile], dict[str, Any]]:
    try:
        raw = json.loads(_catalog_path().read_text(encoding="utf-8"))
        profiles = []
        for item in raw.get("models", []):
            encrypted = item.pop("encrypted_key", "")
            item["api_key"] = _dpapi(base64.b64decode(encrypted), True).decode("utf-8") if encrypted else ""
            profiles.append(ModelProfile(**item).validate())
        return profiles, raw.get("collaboration") or {"enabled": False, "strategy": "fallback", "model_ids": []}
    except Exception:
        return [], {"enabled": False, "strategy": "fallback", "model_ids": []}


def _write_catalog(profiles: list[ModelProfile], collaboration: dict[str, Any]) -> None:
    path = _catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for profile in profiles:
        profile.validate()
        row = asdict(profile)
        row.pop("api_key", None)
        row["encrypted_key"] = base64.b64encode(_dpapi(profile.api_key.encode("utf-8"))).decode("ascii")
        rows.append(row)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"models": rows, "collaboration": collaboration}, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


class ModelCatalog:
    def runtime_profiles(self) -> list[ModelProfile]:
        return _read_catalog()[0]

    def public_models(self) -> list[dict[str, Any]]:
        return [p.public() for p in _read_catalog()[0]]

    def save_models(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        old, collaboration = _read_catalog()
        old_by_id = {p.id: p for p in old}
        profiles: list[ModelProfile] = []
        for item in items:
            model_id = str(item.get("id", "")).strip()
            previous = old_by_id.get(model_id)
            key = str(item.get("api_key", "")).strip() or (previous.api_key if previous else "")
            profile = ModelProfile(
                id=model_id,
                name=str(item.get("name", model_id)),
                protocol=str(item.get("protocol", "openai-compatible")),
                base_url=str(item.get("base_url", "")),
                api_key=key,
                enabled=bool(item.get("enabled", True)),
                role=str(item.get("role", "worker")),
                capabilities=item.get("capabilities"),
                tasks=item.get("tasks"),
            ).validate()
            if any(p.id == profile.id for p in profiles):
                raise ValueError(f"模型 ID 重复：{profile.id}")
            profiles.append(profile)
        _write_catalog(profiles, collaboration)
        return [p.public() for p in profiles]

    def collaboration(self) -> dict[str, Any]:
        return _read_catalog()[1]

    def save_collaboration(self, value: dict[str, Any]) -> dict[str, Any]:
        profiles, _ = _read_catalog()
        ids = {p.id for p in profiles}
        strategy = value.get("strategy", "fallback")
        if strategy not in {"fallback", "parallel"}:
            raise ValueError("协作策略必须是 fallback 或 parallel")
        selected = [str(x) for x in value.get("model_ids", []) if str(x) in ids]
        judge = value.get("judge_model_id")
        if judge is not None and str(judge) not in ids:
            raise ValueError("裁决模型不存在")
        result = {"enabled": bool(value.get("enabled", False)), "strategy": strategy, "model_ids": selected}
        if judge is not None:
            result["judge_model_id"] = str(judge)
        _write_catalog(profiles, result)
        return result


async def discover_models(protocol: str, base_url: str, api_key: str) -> dict[str, Any]:
    protocol = protocol.strip()
    base_url = base_url.strip().rstrip("/")
    api_key = api_key.strip()
    if protocol not in {"openai-compatible", "anthropic-messages", "gemini"}:
        raise ValueError("不支持的 API 协议")
    if not base_url.startswith(("http://", "https://")) or not api_key:
        raise ValueError("请输入有效的接口地址和 API Key")
    if protocol == "gemini":
        url = _endpoint(base_url, "models", "v1beta")
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {"key": api_key}
    else:
        url = _endpoint(base_url, "models")
        headers = {"x-api-key": api_key, "Authorization": f"Bearer {api_key}"} if protocol == "anthropic-messages" else {"Authorization": f"Bearer {api_key}"}
        params = None
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, params=params) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    raise RuntimeError(f"HTTP {response.status}: {str(data)[:240]}")
    except Exception as exc:
        return {"connected": False, "protocol": protocol, "base_url": base_url, "models": [], "error": str(exc)}
    rows = data.get("models", []) if protocol == "gemini" else data.get("data", [])
    models = []
    for item in rows if isinstance(rows, list) else []:
        row = item if isinstance(item, dict) else {}
        model_id = str(row.get("name", "") if protocol == "gemini" else row.get("id", "")).replace("models/", "", 1)
        methods = row.get("supportedGenerationMethods", [])
        if not model_id or (protocol == "gemini" and methods and "generateContent" not in methods):
            continue
        architecture = row.get("architecture") if isinstance(row.get("architecture"), dict) else {}
        raw_modalities = row.get("input_modalities") or row.get("modalities") or row.get("supported_modalities") or architecture.get("input_modalities")
        labels = {str(value).lower() for value in raw_modalities} if isinstance(raw_modalities, list) else set()
        capabilities = ["text"]
        if labels & {"image", "vision", "video"}:
            capabilities.append("vision")
        if labels & {"audio", "sound"}:
            capabilities.append("audio")
        models.append({
            "id": model_id,
            "name": str(row.get("displayName") or row.get("id") or model_id),
            "owned_by": row.get("owned_by"),
            "capabilities": capabilities,
            "tasks": ["chat", "scene"] + (["vision"] if "vision" in capabilities else []),
        })
    return {"connected": True, "protocol": protocol, "base_url": base_url, "models": models}


async def test_connection(protocol: str, base_url: str, api_key: str, model: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        settings = ApiSettings(protocol, base_url, api_key, model).validate()
        answer = ""
        async for piece in UniversalLLM(settings).chat_iter([{"role": "user", "content": "请只回复：连接成功"}]):
            answer += piece
        if not answer.strip():
            raise RuntimeError("模型返回空内容")
        return {"connected": True, "latency_ms": round((time.perf_counter() - started) * 1000), "model": model}
    except Exception as exc:
        return {"connected": False, "latency_ms": round((time.perf_counter() - started) * 1000), "model": model, "error": str(exc)[:300]}
