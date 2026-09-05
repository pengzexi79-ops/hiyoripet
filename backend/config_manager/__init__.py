from .models import (
    AppConfig,
    ServerConfig,
    LLMConfig,
    TTSConfig,
    ASRConfig,
)
import os
import yaml


def load_config(path: str | None = None) -> AppConfig:
    """加载并校验配置；默认读取仓库内 conf.yaml。密钥经 ${ENV_VAR} 解析。"""
    if path is None:
        path = os.environ.get(
            "PET_CONFIG",
            os.path.join(os.path.dirname(__file__), "..", "conf.yaml"),
        )
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return AppConfig(**raw)


__all__ = [
    "AppConfig",
    "ServerConfig",
    "LLMConfig",
    "TTSConfig",
    "ASRConfig",
    "load_config",
]
