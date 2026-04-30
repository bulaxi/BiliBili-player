from __future__ import annotations

import json
import time
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


@dataclass(slots=True)
class FavoriteTrack:
    title: str
    url: str
    duration: float | None = None
    uploader: str | None = None
    view_count: int | None = None
    thumbnail_url: str | None = None
    added_at: float | None = None


class MusicLibrary:
    def __init__(self, library_file: Path = LIBRARY_FILE) -> None:
        self.library_file = library_file
        ensure_app_dirs()
        self._tracks: list[Track] = []
        self._favorites: list[FavoriteTrack] = []
        self.load()

    @property
    def tracks(self) -> list[Track]:
        return list(self._tracks)

    @property
    def favorites(self) -> list[FavoriteTrack]:
        return list(self._favorites)

    def load(self) -> None:
        if not self.library_file.exists():
            self._tracks = []
            self._favorites = []
            return

        try:
            data = json.loads(self.library_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            self._tracks = []
            self._favorites = []
            return

        if isinstance(data, list):
            self._tracks = [Track(**item) for item in data if self._is_valid_track_item(item)]
            self._favorites = []
            return

        if not isinstance(data, dict):
            self._tracks = []
            self._favorites = []
            return

        tracks_data = data.get("tracks") or []
        favorites_data = data.get("favorites") or []
        self._tracks = [Track(**item) for item in tracks_data if self._is_valid_track_item(item)]
        self._favorites = [
            FavoriteTrack(**self._normalize_favorite_item(item))
            for item in favorites_data
            if self._is_valid_favorite_item(item)
        ]

    def save(self) -> None:
        ensure_app_dirs()
        data = {
            "tracks": [asdict(track) for track in self._tracks],
            "favorites": [asdict(track) for track in self._favorites],
        }
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

    def add_favorite(self, favorite: FavoriteTrack) -> None:
        normalized = FavoriteTrack(
            title=favorite.title,
            url=favorite.url,
            duration=favorite.duration,
            uploader=favorite.uploader,
            view_count=favorite.view_count,
            thumbnail_url=favorite.thumbnail_url,
            added_at=favorite.added_at or time.time(),
        )
        existing_index = next(
            (index for index, item in enumerate(self._favorites) if item.url == normalized.url),
            None,
        )
        if existing_index is None:
            self._favorites.insert(0, normalized)
        else:
            self._favorites[existing_index] = normalized
            self._favorites.insert(0, self._favorites.pop(existing_index))
        self.save()

    def remove_favorite(self, url: str) -> None:
        self._favorites = [favorite for favorite in self._favorites if favorite.url != url]
        self.save()

    def prune_missing(self) -> None:
        self._tracks = [track for track in self._tracks if Path(track.file_path).exists()]

    @staticmethod
    def _is_valid_track_item(item: object) -> bool:
        if not isinstance(item, dict):
            return False
        return all(key in item for key in ("title", "url", "file_path"))

    @staticmethod
    def _is_valid_favorite_item(item: object) -> bool:
        if not isinstance(item, dict):
            return False
        return all(key in item for key in ("title", "url"))

    @staticmethod
    def _normalize_favorite_item(item: dict) -> dict:
        return {
            "title": item.get("title") or "未命名收藏",
            "url": item.get("url") or "",
            "duration": item.get("duration"),
            "uploader": item.get("uploader"),
            "view_count": item.get("view_count"),
            "thumbnail_url": item.get("thumbnail_url"),
            "added_at": item.get("added_at"),
        }
