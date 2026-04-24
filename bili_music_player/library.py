from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .paths import LIBRARY_FILE, ensure_app_dirs


@dataclass(slots=True)
class Track:
    title: str
    url: str
    file_path: str
    duration: float | None = None

    @property
    def display_name(self) -> str:
        suffix = Path(self.file_path).suffix.lower()
        return f"{self.title}{f' ({suffix[1:]})' if suffix else ''}"


class MusicLibrary:
    def __init__(self, library_file: Path = LIBRARY_FILE) -> None:
        self.library_file = library_file
        ensure_app_dirs()
        self._tracks: list[Track] = []
        self.load()

    @property
    def tracks(self) -> list[Track]:
        return list(self._tracks)

    def load(self) -> None:
        if not self.library_file.exists():
            self._tracks = []
            return

        try:
            data = json.loads(self.library_file.read_text(encoding="utf-8"))
            self._tracks = [Track(**item) for item in data if self._is_valid_item(item)]
        except (OSError, json.JSONDecodeError, TypeError):
            self._tracks = []

    def save(self) -> None:
        ensure_app_dirs()
        data = [asdict(track) for track in self._tracks]
        self.library_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_or_update(self, track: Track) -> None:
        existing_index = next(
            (index for index, item in enumerate(self._tracks) if item.file_path == track.file_path),
            None,
        )
        if existing_index is None:
            self._tracks.insert(0, track)
        else:
            self._tracks[existing_index] = track
        self.prune_missing()
        self.save()

    def prune_missing(self) -> None:
        self._tracks = [track for track in self._tracks if Path(track.file_path).exists()]

    def replace_all(self, tracks: Iterable[Track]) -> None:
        self._tracks = list(tracks)
        self.save()

    @staticmethod
    def _is_valid_item(item: object) -> bool:
        if not isinstance(item, dict):
            return False
        return all(key in item for key in ("title", "url", "file_path"))
