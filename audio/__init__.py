"""Audio module for Poodle-Automation."""
from .devices import AudioDevice, get_audio_devices, find_device, verify_vb_cable
from .tts import TTSEngine
from .router import AudioRouter

__all__ = [
    "AudioDevice",
    "get_audio_devices",
    "find_device",
    "verify_vb_cable",
    "TTSEngine",
    "AudioRouter",
]
