import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).resolve().parent / ".env")


class Config:

    # -----------------------------
    # LMS Credentials
    # -----------------------------

    LMS_USERNAME = os.getenv("LMS_USERNAME", "")
    LMS_PASSWORD = os.getenv("LMS_PASSWORD", "")
    TARGET_URL = os.getenv("TARGET_URL", "").strip()
    if not TARGET_URL:
        # Fallback: scan .env for raw URL if user pasted without variable name
        try:
            env_file = Path(__file__).resolve().parent / ".env"
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("http://") or line.startswith("https://"):
                        TARGET_URL = line
                        break
        except Exception:
            pass

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    # Multi-Course URLs support (comma-separated or JSON list in .env)
    _raw_course_urls = os.getenv("COURSE_URLS", "").strip()
    if _raw_course_urls:
        try:
            import json
            _parsed = json.loads(_raw_course_urls)
            COURSE_URLS = _parsed if isinstance(_parsed, list) else [_parsed]
        except Exception:
            COURSE_URLS = [u.strip() for u in _raw_course_urls.split(",") if u.strip()]
    elif TARGET_URL:
        COURSE_URLS = [TARGET_URL]
    else:
        COURSE_URLS = []

    # -----------------------------
    # Activity Passing Score Thresholds
    # -----------------------------

    # Default passing score threshold percentage (0 - 100).
    PASSING_THRESHOLD = int(os.getenv("PASSING_THRESHOLD", os.getenv("QUIZ_MIN_SCORE", "70")))

    # Minimum score/accuracy percentage required for Read-Aloud activities (0 - 100).
    READALOUD_MIN_SCORE = int(os.getenv("READALOUD_MIN_SCORE", "80"))

    # Minimum score/percentage required for Solo Speaking activities (0 - 100).
    SOLO_MIN_SCORE = int(os.getenv("SOLO_MIN_SCORE", "70"))

    # Minimum score percentage for HVP / Interactive Video activities (0 - 100).
    HVP_MIN_SCORE = int(os.getenv("HVP_MIN_SCORE", str(PASSING_THRESHOLD)))

    # Minimum score percentage for WordCards activities (0 - 100).
    WORDCARDS_MIN_SCORE = int(os.getenv("WORDCARDS_MIN_SCORE", str(PASSING_THRESHOLD)))

    # Minimum score percentage for standard Moodle Quiz activities (0 - 100).
    QUIZ_MIN_SCORE = int(os.getenv("QUIZ_MIN_SCORE", str(PASSING_THRESHOLD)))

    @classmethod
    def get_threshold(cls, act_type: str) -> float:
        """Returns the configured passing score threshold for a given activity type."""
        t = (act_type or "").lower()
        if "readaloud" in t:
            return float(cls.READALOUD_MIN_SCORE)
        elif "solo" in t:
            return float(cls.SOLO_MIN_SCORE)
        elif "hvp" in t or "h5p" in t:
            return float(cls.HVP_MIN_SCORE)
        elif "wordcards" in t:
            return float(cls.WORDCARDS_MIN_SCORE)
        elif "quiz" in t:
            return float(cls.QUIZ_MIN_SCORE)
        return float(cls.PASSING_THRESHOLD)

    # -----------------------------
    # VB-CABLE
    # -----------------------------

    CABLE_INPUT_NAME = "CABLE Input"

    CABLE_OUTPUT_NAME = "CABLE Output"


    # -----------------------------
    # TTS
    # -----------------------------

    TTS_RATE = 170

    TTS_VOLUME = 1.0

    TTS_VOICE_ID = None


    # -----------------------------
    # Browser & Performance
    # -----------------------------

    HEADLESS = False

    DEFAULT_TARGET_URL = "http://127.0.0.1:8000"

    PERSISTENT_AUTH = True
    BLOCK_FONTS = False          # Safeguarded: kept False so H5P/YouTube font loaders never hang
    BLOCK_MEDIA = False          # Safeguarded: kept False for Poodll audio & H5P video
    BLOCK_TRACKING = False
    BLOCK_IMAGES = False         # Kept False to preserve instructional visuals
    BLOCK_CSS = False            # Kept False to preserve layouts and buttons

    BENCHMARK = True
    DEFAULT_TIMEOUT = 10000
    NAVIGATION_TIMEOUT = 15000

    # -----------------------------
    # Audio verification
    # -----------------------------

    AUDIO_THRESHOLD_DB = -45.0

    AUDIO_TIMEOUT_SECONDS = 15


    # -----------------------------
    # Paths
    # -----------------------------

    BASE_DIR = Path(__file__).resolve().parent

    TEMP_DIR = BASE_DIR / "temp"
    TEMP_DIR.mkdir(exist_ok=True)

    STORAGE_DIR = BASE_DIR / "storage"
    STORAGE_DIR.mkdir(exist_ok=True)

    AUTH_STATE_FILE = STORAGE_DIR / "auth.json"
    CACHE_FILE = STORAGE_DIR / "cache.json"
