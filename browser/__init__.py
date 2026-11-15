"""Browser automation module for Poodle-Automation."""
from .launcher import launch_browser
from .automation import BrowserController

__all__ = ["launch_browser", "BrowserController"]
