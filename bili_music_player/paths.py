from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
STREAM_CACHE_DIR = DOWNLOADS_DIR / ".stream-cache"
LIBRARY_FILE = DOWNLOADS_DIR / "library.json"
SEARCH_CACHE_FILE = DOWNLOADS_DIR / "search-cache.json"


def ensure_app_dirs() -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    STREAM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
