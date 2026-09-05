# backend/llm/llm_interface.py
# LLM 能力接口（Protocol 模式，见 CONTRACTS C3）。新增后端只改工厂，不动调用方。
from typing import AsyncIterator, Protocol


class LLMInterface(Protocol):
    async def chat_iter(self, messages: list[dict]) -> AsyncIterator[str]:
        """流式返回回复文本增量（delta）。"""
        ...
