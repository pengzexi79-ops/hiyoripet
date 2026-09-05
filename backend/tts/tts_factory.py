# backend/tts/tts_factory.py
# 按 provider 名实例化 TTS（配置驱动，见 DECISIONS D4）。
from config_manager.models import TTSConfig
from .tts_interface import TTSInterface
from .edge_tts_tts import EdgeTTSTTS


def build_tts(provider: str, cfg: TTSConfig) -> TTSInterface:
    # provider 为配置键（如 "edge"）；实际实现由 cfg.provider 决定（如 "edge-tts"）
    if cfg.provider == "edge-tts":
        return EdgeTTSTTS(cfg.voice, cfg.rate)
    raise ValueError(f"未知 TTS provider: {cfg.provider}")
