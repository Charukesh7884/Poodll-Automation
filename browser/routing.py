from urllib.parse import urlparse
from playwright.sync_api import Route
from config import Config

BLOCKED_TRACKING_HOSTS = {
    "google-analytics.com",
    "googletagmanager.com",
    "hotjar.com",
    "clarity.ms",
    "doubleclick.net",
    "facebook.net",
}


class ResourceRouter:
    """
    Centralized Playwright resource interceptor.
    Blocks fonts and third-party trackers while strictly preserving
    scripts, documents, images, CSS, and media required by Poodll/H5P.
    """

    def __init__(
        self,
        block_fonts: bool = None,
        block_media: bool = None,
        block_tracking: bool = None,
        block_images: bool = None,
        block_css: bool = None,
    ):
        self.block_fonts = Config.BLOCK_FONTS if block_fonts is None else block_fonts
        self.block_media = Config.BLOCK_MEDIA if block_media is None else block_media
        self.block_tracking = Config.BLOCK_TRACKING if block_tracking is None else block_tracking
        self.block_images = Config.BLOCK_IMAGES if block_images is None else block_images
        self.block_css = Config.BLOCK_CSS if block_css is None else block_css

        self.total_requests = 0
        self.blocked_requests = 0

    def route_handler(self, route: Route):
        self.total_requests += 1
        req = route.request
        res_type = req.resource_type
        url = req.url

        # 1. Tracking domain filtering
        if self.block_tracking:
            host = urlparse(url).netloc.lower()
            if any(blocked in host for blocked in BLOCKED_TRACKING_HOSTS):
                self.blocked_requests += 1
                route.abort()
                return

        # 2. Font blocking (saves high bandwidth & prevents font reflow delay)
        if self.block_fonts and res_type == "font":
            self.blocked_requests += 1
            route.abort()
            return

        # 3. Media blocking (Safeguarded: NEVER block Poodll/H5P audio/video)
        if self.block_media and res_type == "media":
            # Protect audio / poodll / h5p requests
            url_lower = url.lower()
            if "poodll" not in url_lower and "hvp" not in url_lower and "youtube" not in url_lower:
                self.blocked_requests += 1
                route.abort()
                return

        # 4. Experimental image/css blocking (disabled by default)
        if self.block_images and res_type == "image":
            self.blocked_requests += 1
            route.abort()
            return

        if self.block_css and res_type == "stylesheet":
            self.blocked_requests += 1
            route.abort()
            return

        # Allow essential resources (documents, scripts, XHR, fetch)
        try:
            route.continue_()
        except Exception:
            pass

    def attach_to_page(self, page):
        """Attaches the route interceptor to a Playwright page."""
        page.route("**/*", self.route_handler)
