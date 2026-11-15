from dataclasses import dataclass
from typing import List, Optional
import sounddevice as sd


@dataclass
class AudioDevice:
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float


def get_audio_devices() -> List[AudioDevice]:
    devices = sd.query_devices()
    result = []
    for index, device in enumerate(devices):
        result.append(
            AudioDevice(
                index=index,
                name=device["name"],
                max_input_channels=device["max_input_channels"],
                max_output_channels=device["max_output_channels"],
                default_samplerate=device["default_samplerate"],
            )
        )
    return result


def find_device(
    name_substring: str,
    kind: Optional[str] = None
) -> Optional[AudioDevice]:
    name_substring = name_substring.lower()
    matches = []

    for device in get_audio_devices():
        name = device.name.lower()
        if name_substring not in name:
            continue

        if kind == "input":
            if device.max_input_channels <= 0:
                continue
        elif kind == "output":
            if device.max_output_channels <= 0:
                continue

        matches.append(device)

    if not matches:
        return None

    # Prefer Windows DirectSound or MME if multiple matches exist, otherwise return first match
    for m in matches:
        if "directsound" in m.name.lower() or "mme" in m.name.lower():
            return m

    return matches[0]


def verify_vb_cable():
    cable_input = find_device(
        "CABLE Input",
        kind="output"
    )
    cable_output = find_device(
        "CABLE Output",
        kind="input"
    )

    if cable_input is None:
        raise RuntimeError(
            "\n"
            "VB-CABLE CABLE Input was not found.\n"
            "Python needs an OUTPUT device named 'CABLE Input'.\n"
            "Run:\n"
            "python -m sounddevice\n"
        )

    if cable_output is None:
        raise RuntimeError(
            "\n"
            "VB-CABLE CABLE Output was not found.\n"
            "Chromium needs an INPUT device named 'CABLE Output'.\n"
            "Run:\n"
            "python -m sounddevice\n"
        )

    return cable_input, cable_output
