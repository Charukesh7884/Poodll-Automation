import argparse
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

from config import Config
from audio.devices import verify_vb_cable
from audio.tts import TTSEngine
from audio.router import AudioRouter
from browser.launcher import launch_browser
from browser.automation import BrowserController


def main():
    parser = argparse.ArgumentParser(description="Poodle Audio Browser Automation Agent")
    parser.add_argument(
        "--url",
        type=str,
        default=Config.DEFAULT_TARGET_URL,
        help=f"Target URL to automate (default: {Config.DEFAULT_TARGET_URL})"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=Config.HEADLESS,
        help="Run browser in headless mode"
    )
    parser.add_argument(
        "--speak",
        type=str,
        default="Hello! Poodle Audio Automation is active.",
        help="Initial text to synthesize and route to the browser"
    )
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("POODLE AUDIO BROWSER AUTOMATION")
    print("=" * 60)

    # 1. Device Verification
    print("\n[1/4] Verifying VB-CABLE devices...")
    cable_input, cable_output = verify_vb_cable()
    print(f"  Python Output (CABLE Input)  : {cable_input.name} [id={cable_input.index}]")
    print(f"  Browser Input (CABLE Output) : {cable_output.name} [id={cable_output.index}]")

    # 2. TTS & Router Initialization
    print("\n[2/4] Initializing TTS & Audio Router...")
    tts = TTSEngine(
        rate=Config.TTS_RATE,
        volume=Config.TTS_VOLUME,
        voice_id=Config.TTS_VOICE_ID,
    )
    router = AudioRouter(output_device=cable_input, tts_engine=tts)
    wav_path = Config.TEMP_DIR / "agent_speech.wav"

    # 3. Browser Launch & Injection
    print(f"\n[3/4] Launching Chromium (headless={args.headless})...")
    with sync_playwright() as p:
        browser, context = launch_browser(p, headless=args.headless)
        controller = BrowserController(context)

        print(f"  Navigating to: {args.url}")
        page = controller.navigate(args.url)

        # 4. Stream Verification
        print("\n[4/4] Verifying CABLE Output stream...")
        try:
            stream_info = controller.verify_cable_stream()
            print(f"  Bound to: {stream_info.get('label')} (ID: {stream_info.get('deviceId')})")
        except Exception as e:
            print(f"  Note on stream check: {e}")

        # Speak test utterance if requested
        if args.speak:
            print(f"\n[Agent] Routing speech to website: \"{args.speak}\"")
            router.play_tts(args.speak, wav_path, blocking=True)
            print("  Speech playback finished.")

        print("\n[Agent] Automation ready. Target page is open with CABLE Output active.")
        print("Press Ctrl+C to close browser and exit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
