import json
from pathlib import Path
from config import Config


class ActivityCache:
    """
    Caches discovered Moodle course activities by course URL and section ID
    to eliminate redundant DOM discovery on repeated runs.
    """

    def __init__(self, cache_file: Path = None):
        self.cache_file = cache_file or Config.CACHE_FILE
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache = self._load()

    def _load(self) -> dict:
        if self.cache_file.exists():
            try:
                return json.loads(self.cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save(self):
        try:
            self.cache_file.write_text(json.dumps(self.cache, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[Cache Warning] Error saving activity cache: {e}")

    def get_activities(self, course_url: str) -> list[dict] | None:
        """Retrieves cached activities for a course URL or returns None."""
        norm_key = course_url.rstrip("/").strip()
        return self.cache.get(norm_key)

    def save_activities(self, course_url: str, activities: list[dict]):
        """Caches discovered activities for a course URL."""
        norm_key = course_url.rstrip("/").strip()
        self.cache[norm_key] = activities
        self._save()
        print(f"[Activity Cache] Cached {len(activities)} activities for: {norm_key}")

    def clear(self):
        """Clears the activity cache."""
        self.cache = {}
        self._save()
