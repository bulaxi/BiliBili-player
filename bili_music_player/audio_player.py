from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pygame


class AudioPlayerError(RuntimeError):
    pass


class AudioPlayer:
    def __init__(self) -> None:
        self._initialized = False
        self._paused = False
        self._current_source: Path | str | None = None
        self._start_offset = 0.0

    @property
    def current_file(self) -> Path | None:
        return self._current_source if isinstance(self._current_source, Path) else None

    @property
    def current_source(self) -> Path | str | None:
        return self._current_source


    def play(self, source: str | Path, start: float = 0.0) -> None:
        is_url = self._is_url(source)
        playback_source: Path | str = str(source) if is_url else Path(source)
        start = max(0.0, start)

        if isinstance(playback_source, Path) and not playback_source.exists():
            raise AudioPlayerError("音频文件不存在，可能已被删除。")

        self._ensure_initialized()
        try:
            pygame.mixer.music.load(str(playback_source))
            if start > 0 and not is_url:
                pygame.mixer.music.play(start=start)
            else:
                pygame.mixer.music.play()
        except pygame.error as exc:
            raise AudioPlayerError(f"播放失败：{exc}") from exc

        self._current_source = playback_source
        self._start_offset = start if not is_url else 0.0
        self._paused = False

    def pause_or_resume(self) -> bool:
        self._ensure_initialized()
        if self._current_source is None:
            raise AudioPlayerError("请先选择并播放一首音频。")

        if self._paused:
            pygame.mixer.music.unpause()
            self._paused = False
        else:
            pygame.mixer.music.pause()
            self._paused = True
        return self._paused

    def stop(self) -> None:
        if not self._initialized:
            return
        pygame.mixer.music.stop()
        self._paused = False
        self._current_source = None
        self._start_offset = 0.0

    def position_seconds(self) -> float:
        if not self._initialized or self._current_source is None:
            return 0.0

        position_ms = pygame.mixer.music.get_pos()
        if position_ms < 0:
            return self._start_offset
        return self._start_offset + (position_ms / 1000.0)

    def has_finished(self) -> bool:
        if not self._initialized or self._current_source is None or self._paused:
            return False
        return not pygame.mixer.music.get_busy()

    def clear_finished(self) -> None:
        self._current_source = None
        self._start_offset = 0.0
        self._paused = False

    def seek(self, position_seconds: float) -> None:
        if self._current_source is None:
            raise AudioPlayerError("请先选择并播放一首音频。")
        if not isinstance(self._current_source, Path):
            raise AudioPlayerError("远程串流播放不支持拖动进度，请先保存到本地缓存后再拖动。")

        was_paused = self._paused
        self.play(self._current_source, start=position_seconds)
        if was_paused:
            pygame.mixer.music.pause()
            self._paused = True

    def close(self) -> None:
        if self._initialized:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
            self._initialized = False
        self._current_source = None
        self._start_offset = 0.0
        self._paused = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        try:
            pygame.mixer.init()
        except pygame.error as exc:
            raise AudioPlayerError(f"初始化音频设备失败：{exc}") from exc
        self._initialized = True

    @staticmethod
    def _is_url(source: str | Path) -> bool:
        if isinstance(source, Path):
            return False
        return urlparse(str(source)).scheme in {"http", "https"}
