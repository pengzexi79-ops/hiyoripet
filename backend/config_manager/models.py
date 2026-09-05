# backend/config_manager/models.py
# Pydantic 强校验配置；支持 ${ENV_VAR} 环境变量替换（密钥不入库）。
from pydantic import BaseModel, model_validator
import os
import re

_ENV = re.compile(r"\$\{([^}]+)\}")


def _resolve(value):
    if isinstance(value, str):
        return _ENV.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    return value


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000


class LLMConfig(BaseModel):
    provider: str = "openai-compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = "gpt-5.5"


class TTSConfig(BaseModel):
    provider: str = "edge-tts"
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "+0%"


class ASRConfig(BaseModel):
    provider: str = "stub"


class AppConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    llm_configs: dict[str, LLMConfig] = {}
    default_llm: str = "foxtoken"
    tts_configs: dict[str, TTSConfig] = {}
    default_tts: str = "edge"
    asr_configs: dict[str, ASRConfig] = {}
    default_asr: str = "stub"
    agent: dict = {}

    @model_validator(mode="before")
    @classmethod
    def _resolve_env(cls, data):
        return _resolve(data)
