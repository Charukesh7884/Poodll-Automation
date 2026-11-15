import sys
import time
import socket
import threading
from typing import Optional
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from playwright.sync_api import sync_playwright
import sounddevice as sd

from config import Config
from audio.devices import verify_vb_cable
from audio.tts import TTSEngine
from audio.router import AudioRouter
from browser.launcher import launch_browser
from browser.automation import BrowserController

TEST_TEXT = "Testing VB-Cable audio injection from Python."


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_local_server(port: int = 8000) -> Optional[HTTPServer]:
    if is_port_in_use(port):
        print(f"Server already active on http://127.0.0.1:{port}")
        return None

    handler = SimpleHTTPRequestHandler
    server = HTTPServer(("127.0.0.1", port), handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"Local test HTTP server started on http://127.0.0.1:{port}")
    return server


def sd_stop():
    try:
        sd.stop()
    except Exception:
        pass


def main():
    print()
    print("=" * 60)
    print("POODLE AUDIO PIPELINE TEST")
    print("=" * 60)

    # ------------------------------------------------
    # 0. Ensure HTTP Server is Running
    # ------------------------------------------------
    server = start_local_server(8000)

    # ------------------------------------------------
    # 1. Detect VB-CABLE
    # ------------------------------------------------
    print()
    print("[1/6] Detecting VB-CABLE...")

    cable_input, cable_output = verify_vb_cable()

    print("Python output :", cable_input.name, f"(index {cable_input.index})")
    print("Browser input :", cable_output.name, f"(index {cable_output.index})")

    # ------------------------------------------------
    # 2. TTS
    # ------------------------------------------------
    print()
    print("[2/6] Initializing TTS...")

    tts = TTSEngine(
        rate=Config.TTS_RATE,
        volume=Config.TTS_VOLUME,
        voice_id=Config.TTS_VOICE_ID,
    )

    router = AudioRouter(
        output_device=cable_input,
        tts_engine=tts,
    )

    wav_path = Config.TEMP_DIR / "pipeline_test.wav"

    # ------------------------------------------------
    # 3. Launch browser
    # ------------------------------------------------
    print()
    print(f"[3/6] Launching Chromium (headless={Config.HEADLESS})...")

    with sync_playwright() as p:
        browser, context = launch_browser(p, headless=Config.HEADLESS)
        controller = BrowserController(context)

        test_url = "http://127.0.0.1:8000/web/static/mic_test.html"
        print(f"Navigating to {test_url}...")
        page = controller.navigate(test_url)

        # Give page a short moment to initialize audio context
        page.wait_for_timeout(1000)

        # ------------------------------------------------
        # 4. Inspect browser devices
        # ------------------------------------------------
        print()
        print("[4/6] Inspecting Chromium audio devices...")

        devices = controller.inspect_audio_devices()
        for device in devices:
            print(f"  {device['kind']}: {device['label']}")

        cable_browser_device = next(
            (
                d for d in devices
                if "cable output" in (d.get("label") or "").lower()
                or ("vb-audio" in (d.get("label") or "").lower() and "cable" in (d.get("label") or "").lower())
            ),
            None,
        )

        if cable_browser_device is None:
            raise RuntimeError("Chromium cannot see CABLE Output.")

        print("FOUND:", cable_browser_device["label"])

        # ------------------------------------------------
        # 5. Verify actual stream
        # ------------------------------------------------
        print()
        print("[5/6] Verifying actual MediaStream device...")

        stream_info = controller.verify_cable_stream()

        print("Device label      :", stream_info.get("label"))
        print("Device ID         :", stream_info.get("deviceId"))
        print("Echo cancellation :", stream_info.get("echoCancellation"))
        print("Noise suppression :", stream_info.get("noiseSuppression"))
        print("Auto gain control :", stream_info.get("autoGainControl"))

        label_lower = (stream_info.get("label") or "").lower()
        if "cable output" not in label_lower and "vb-audio" not in label_lower:
            raise RuntimeError(
                f"MediaStream is NOT using CABLE Output. Got: {stream_info.get('label')}"
            )

        # ------------------------------------------------
        # 6. Play TTS through cable
        # ------------------------------------------------
        print()
        print("[6/6] Playing TTS through CABLE Input...")

        router.play_tts(
            TEST_TEXT,
            wav_path,
            blocking=False,
        )

        # Wait until browser detects signal
        deadline = time.time() + Config.AUDIO_TIMEOUT_SECONDS
        detected = False
        metrics = {"maxDb": float("-inf"), "samples": 0}

        while time.time() < deadline:
            metrics = page.evaluate(
                """
                () => ({
                    maxDb: window.audioMetrics ? window.audioMetrics.maxDb : -Infinity,
                    samples: window.audioMetrics ? window.audioMetrics.sampleCount : 0
                })
                """
            )

            max_db = metrics.get("maxDb", float("-inf"))
            print(f"\rPeak: {max_db:.2f} dB", end="", flush=True)

            if max_db > Config.AUDIO_THRESHOLD_DB:
                detected = True
                break

            time.sleep(0.1)

        print()
        sd_stop()

        # ------------------------------------------------
        # Final result
        # ------------------------------------------------
        print()
        print("=" * 60)

        if detected:
            print("PASS: AUDIO REACHED CHROMIUM")
            print(f"Peak detected: {metrics['maxDb']:.2f} dB")
        else:
            print("FAIL: NO AUDIO DETECTED")
            print(f"Maximum observed: {metrics['maxDb']:.2f} dB")

        print("=" * 60)

        context.close()
        browser.close()

        if server:
            server.shutdown()

        if not detected:
            sys.exit(1)


if __name__ == "__main__":
    main()
