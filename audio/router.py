import wave
from pathlib import Path
from typing import Union
import numpy as np
import sounddevice as sd

from .tts import TTSEngine


class AudioRouter:

    def __init__(
        self,
        output_device,
        tts_engine: TTSEngine
    ):
        self.output_device = output_device
        self.tts = tts_engine

    def play_wav(
        self,
        wav_path: Union[str, Path],
        blocking: bool = True
    ):
        with wave.open(str(wav_path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())

        if sample_width == 2:
            audio = np.frombuffer(frames, dtype=np.int16)
            audio = audio.astype(np.float32) / 32768.0
        elif sample_width == 1:
            audio = np.frombuffer(frames, dtype=np.uint8)
            audio = (audio.astype(np.float32) - 128) / 128.0
        else:
            raise RuntimeError(
                f"Unsupported WAV sample width: {sample_width}"
            )

        if channels > 1:
            audio = audio.reshape(-1, channels)

        sd.play(
            audio,
            samplerate=sample_rate,
            device=self.output_device.index
        )

        if blocking:
            sd.wait()

    def play_tts(
        self,
        text: str,
        output_path: Union[str, Path],
        blocking: bool = True
    ):
        self.tts.synthesize_to_file(
            text,
            output_path
        )
        self.play_wav(
            output_path,
            blocking=blocking
        )
