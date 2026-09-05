# backend/asr/stub_asr.py
# 本地 ASR 占位实现。M3 后续用 sherpa-onnx 本地模型替换（需模型文件 + 音频设备调试）。
# 当前语音通道不可用，前端应走 text-input 文本对话。
import numpy as np
from .asr_interface import ASRInterface


class StubASR(ASRInterface):
    async def transcribe_np(self, audio: np.ndarray) -> str:
        raise NotImplementedError(
            "本地 ASR 未实现（M3 后续：sherpa-onnx）。当前仅支持 text-input 文本对话。"
        )
