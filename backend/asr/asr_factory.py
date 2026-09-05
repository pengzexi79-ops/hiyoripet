# backend/asr/asr_factory.py
# 按 provider 名实例化 ASR（配置驱动，见 DECISIONS D4/D5）。
from config_manager.models import ASRConfig
from .asr_interface import ASRInterface
from .stub_asr import StubASR


def build_asr(provider: str, cfg: ASRConfig) -> ASRInterface:
    # provider 为配置键（如 "stub"）；实际实现由 cfg.provider 决定（如 "stub"）
    if cfg.provider == "stub":
        return StubASR()
    raise ValueError(f"未知 ASR provider: {cfg.provider}")
