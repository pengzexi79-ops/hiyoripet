# backend/asr/asr_interface.py
# ASR 能力接口（Protocol 模式，见 CONTRACTS C3）。音频为 np.ndarray（16000Hz 单声道）。
from typing import Protocol
import numpy as np


class ASRInterface(Protocol):
    async def transcribe_np(self, audio: np.ndarray) -> str:
        ...
