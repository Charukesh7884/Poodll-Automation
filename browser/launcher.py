from pathlib import Path
from typing import Tuple
from playwright.sync_api import Playwright, Browser, BrowserContext

SHIM_PATH = Path(__file__).parent / "media_shim.js"
POODLL_SHIM_PATH = Path(__file__).parent / "cloudpoodll_shim.js"


from config import Config

def launch_browser(
    p: Playwright,
    headless: bool = False
) -> Tuple[Browser, BrowserContext]:
    browser = p.chromium.launch(
        headless=headless,
        args=[
            "--use-fake-ui-for-media-stream",
            "--autoplay-policy=no-user-gesture-required",
        ]
    )

    auth_path = str(Config.AUTH_STATE_FILE) if Config.AUTH_STATE_FILE.exists() and Config.AUTH_STATE_FILE.stat().st_size > 50 else None

    context = browser.new_context(
        permissions=["microphone"],
        storage_state=auth_path
    )

    if POODLL_SHIM_PATH.exists():
        context.add_init_script(path=str(POODLL_SHIM_PATH))
    if SHIM_PATH.exists():
        context.add_init_script(path=str(SHIM_PATH))

    return browser, context
