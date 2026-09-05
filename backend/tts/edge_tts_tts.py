# backend/tts/edge_tts_tts.py
# Edge TTS 实现（微软免费在线 TTS，中文音色）。返回 mp3 路径；音量包后续用 RMS 提取。
import os
import tempfile
import edge_tts
from typing import List, Tuple
from .tts_interface import TTSInterface


class EdgeTTSTTS(TTSInterface):
    def __init__(self, voice: str, rate: str = "+0%"):
        self.voice = voice
        self.rate = rate

    async def generate_audio(self, text: str, **kwargs) -> Tuple[str, List[float]]:
        path = os.path.join(tempfile.gettempdir(), f"pet_tts_{abs(hash(text))}.mp3")
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
        await communicate.save(path)
        return path, []  # volumes 后续用 RMS 提取，驱动 ParamMouthOpenY
