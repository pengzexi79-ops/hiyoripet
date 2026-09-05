# backend/llm/foxtoken_llm.py
# foxtoken 网关（OpenAI 兼容 / new-api 系）LLM 实现。
# 端点 https://foxtoken.top/v1，模型 gpt-5.5；密钥走环境变量（不入库）。
from openai import AsyncOpenAI
from typing import AsyncIterator
from .llm_interface import LLMInterface


class FoxtokenLLM(LLMInterface):
    def __init__(self, base_url: str, api_key: str, model: str):
        self.model = model
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key or "EMPTY")

    async def chat_iter(self, messages: list[dict]) -> AsyncIterator[str]:
        if not self._client.api_key or self._client.api_key == "EMPTY":
            raise RuntimeError("FOXTOKEN_KEY 未设置：LLM 不可用（见 backend/conf.yaml）")
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
