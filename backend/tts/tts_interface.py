# backend/tts/tts_interface.py
# TTS 能力接口（Protocol 模式，见 CONTRACTS C3）。
# 返回 (音频文件路径, 逐帧音量包)；音量包用于前端口型同步（数据流 B）。
from typing import Protocol, Tuple
from typing import List


class TTSInterface(Protocol):
    async def generate_audio(self, text: str, **kwargs) -> Tuple[str, List[float]]:
        ...
