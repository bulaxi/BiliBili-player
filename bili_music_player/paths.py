from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
LIBRARY_FILE = DOWNLOADS_DIR / "library.json"


def ensure_app_dirs() -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
