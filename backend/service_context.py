from __future__ import annotations

import asyncio

from api_catalog import ModelCatalog, ModelProfile, discover_models, test_connection
from api_provider import ApiSettings, UniversalLLM, clear_user_settings, load_user_settings, save_user_settings
from asr.asr_factory import build_asr
from config_manager import AppConfig, load_config
from llm.llm_factory import build_llm
from tts.tts_factory import build_tts


class ServiceContext:
    def __init__(self, config: AppConfig | None = None):
        self.config = config or load_config()
        tts_cfg = self.config.tts_configs.get(self.config.default_tts)
        asr_cfg = self.config.asr_configs.get(self.config.default_asr)
        if tts_cfg is None or asr_cfg is None:
            raise RuntimeError("配置缺失：default_tts/asr 必须对应已定义的 configs")
        self.tts = build_tts(self.config.default_tts, tts_cfg)
        self.asr = build_asr(self.config.default_asr, asr_cfg)
        self.history: list[dict] = []
        self.catalog = ModelCatalog()
        self.user_api = load_user_settings()
        self._load_llm()

    def _load_llm(self) -> None:
        if self.user_api:
            self.llm = UniversalLLM(self.user_api)
            return
        cfg = self.config.llm_configs.get(self.config.default_llm)
        if cfg is None:
            raise RuntimeError("配置缺失：default_llm 必须对应已定义的 configs")
        self.llm = build_llm(self.config.default_llm, cfg)

    def _active_profiles(self, task: str = "chat") -> list[ModelProfile]:
        collaboration = self.catalog.collaboration()
        if not collaboration.get("enabled"):
            return []
        profiles = {profile.id: profile for profile in self.catalog.runtime_profiles() if profile.enabled}
        selected = collaboration.get("model_ids") or list(profiles)
        active = [profiles[item] for item in selected if item in profiles]
        routed = [profile for profile in active if task in (profile.tasks or ["chat"])]
        return routed or active

    def api_status(self) -> dict:
        profiles = self._active_profiles()
        if profiles:
            first = profiles[0]
            return {"configured": True, "protocol": first.protocol, "base_url": first.base_url, "model": first.id, "source": "catalog"}
        if self.user_api:
            return {"configured": True, "protocol": self.user_api.protocol, "base_url": self.user_api.base_url, "model": self.user_api.model, "source": "user"}
        cfg = self.config.llm_configs.get(self.config.default_llm)
        configured = bool(cfg and cfg.api_key)
        return {"configured": configured, "protocol": cfg.provider if configured else "openai-compatible", "base_url": cfg.base_url if configured else "", "model": cfg.model if configured else "", "source": "environment" if configured else "local"}

    def save_api(self, protocol: str, base_url: str, api_key: str, model: str) -> dict:
        if not api_key.strip() and self.user_api:
            api_key = self.user_api.api_key
        settings = ApiSettings(protocol, base_url, api_key, model).validate()
        save_user_settings(settings)
        self.user_api = settings
        self.llm = UniversalLLM(settings)
        return self.api_status()

    def clear_api(self) -> dict:
        clear_user_settings()
        self.user_api = None
        self._load_llm()
        return self.api_status()

    def _resolve_api_key(self, protocol: str, base_url: str, model: str = "", provided: str = "") -> str:
        if provided.strip():
            return provided.strip()
        normalized = base_url.strip().rstrip("/")
        if self.user_api and self.user_api.protocol == protocol and self.user_api.base_url.rstrip("/") == normalized:
            return self.user_api.api_key
        for profile in self.catalog.runtime_profiles():
            if profile.protocol == protocol and profile.base_url.rstrip("/") == normalized and profile.api_key:
                return profile.api_key
        return ""

    def public_models(self) -> list[dict]:
        return self.catalog.public_models()

    def save_models(self, items: list[dict]) -> list[dict]:
        prepared = [
            {**item, "api_key": self._resolve_api_key(item.get("protocol", ""), item.get("base_url", ""), item.get("id", ""), item.get("api_key", ""))}
            for item in items
        ]
        return self.catalog.save_models(prepared)

    def collaboration(self) -> dict:
        return self.catalog.collaboration()

    def save_collaboration(self, value: dict) -> dict:
        return self.catalog.save_collaboration(value)

    async def discover(self, protocol: str, base_url: str, api_key: str) -> dict:
        key = self._resolve_api_key(protocol, base_url, provided=api_key)
        return await discover_models(protocol, base_url, key)

    async def test_connection(self, protocol: str, base_url: str, api_key: str, model: str) -> dict:
        key = self._resolve_api_key(protocol, base_url, model, api_key)
        return await test_connection(protocol, base_url, key, model)

    async def _collect(self, profile: ModelProfile, messages: list[dict]) -> str:
        chunks: list[str] = []
        settings = ApiSettings(profile.protocol, profile.base_url, profile.api_key, profile.id)
        async for chunk in UniversalLLM(settings).chat_iter(messages):
            chunks.append(chunk)
        answer = "".join(chunks).strip()
        if not answer:
            raise RuntimeError(f"模型 {profile.id} 返回空内容")
        return answer

    async def chat_iter(self, messages: list[dict], task: str = "chat"):
        profiles = self._active_profiles(task)
        if not profiles:
            async for piece in self.llm.chat_iter(messages):
                yield piece
            return
        strategy = self.catalog.collaboration().get("strategy", "fallback")
        if strategy == "parallel":
            results = await asyncio.gather(*(self._collect(profile, messages) for profile in profiles), return_exceptions=True)
            answers = [item for item in results if isinstance(item, str)]
            if not answers:
                raise RuntimeError("所有协作模型均调用失败")
            yield "\n\n".join(answers)
            return
        last_error: Exception | None = None
        for profile in profiles:
            try:
                yield await self._collect(profile, messages)
                return
            except Exception as exc:
                last_error = exc
        raise last_error or RuntimeError("没有可用的协作模型")


_sc: ServiceContext | None = None


def get_service_context() -> ServiceContext:
    global _sc
    if _sc is None:
        _sc = ServiceContext()
    return _sc
