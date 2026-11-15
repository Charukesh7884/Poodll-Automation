from playwright.sync_api import Page, Locator
from config import Config


class MoodleWaits:
    """
    Condition-based wait manager for Moodle pages and activities.
    Replaces arbitrary fixed sleep() calls with explicit event-driven conditions.
    """

    @staticmethod
    def page_ready(page: Page, timeout: int = None) -> bool:
        """Waits for main Moodle page content to be ready."""
        t = timeout or Config.DEFAULT_TIMEOUT
        try:
            page.wait_for_load_state("domcontentloaded", timeout=t)
            page.locator("#region-main, #page-content, .course-content, body").first.wait_for(
                state="attached", timeout=t
            )
            return True
        except Exception:
            return False

    @staticmethod
    def wait_for_activity(page: Page, timeout: int = None) -> bool:
        """Waits for activity elements to attach to the DOM."""
        t = timeout or Config.DEFAULT_TIMEOUT
        try:
            page.locator(".activityitem, .activity, li.activity, div.activityinstance, #region-main").first.wait_for(
                state="visible", timeout=t
            )
            return True
        except Exception:
            return False

    @staticmethod
    def wait_for_element(locator: Locator, state: str = "visible", timeout: int = None) -> bool:
        """Waits for a specific locator state."""
        t = timeout or Config.DEFAULT_TIMEOUT
        try:
            locator.wait_for(state=state, timeout=t)
            return True
        except Exception:
            return False
