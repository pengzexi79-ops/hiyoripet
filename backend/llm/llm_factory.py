# backend/llm/llm_factory.py
# 按 provider 名实例化 LLM（配置驱动，见 DECISIONS D4）。
from .llm_interface import LLMInterface
from .foxtoken_llm import FoxtokenLLM
from config_manager.models import LLMConfig


def build_llm(provider: str, cfg: LLMConfig) -> LLMInterface:
    # provider 为配置键（如 "foxtoken"）；实际实现由 cfg.provider 决定（如 "openai-compatible"）
    if cfg.provider in ("openai-compatible", "foxtoken"):
        return FoxtokenLLM(cfg.base_url, cfg.api_key, cfg.model)
    raise ValueError(f"未知 LLM provider: {cfg.provider}")
