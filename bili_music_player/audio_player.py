from __future__ import annotations

from pathlib import Path

import pygame


class AudioPlayerError(RuntimeError):
    pass


class AudioPlayer:
    def __init__(self) -> None:
        self._initialized = False
        self._paused = False
        self._current_file: Path | None = None

    @property
    def current_file(self) -> Path | None:
        return self._current_file

    @property
    def is_paused(self) -> bool:
        return self._paused

    def play(self, file_path: str | Path) -> None:
        path = Path(file_path)
        if not path.exists():
            raise AudioPlayerError("音频文件不存在，可能已被删除。")

        self._ensure_initialized()
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
        except pygame.error as exc:
            raise AudioPlayerError(f"播放失败：{exc}") from exc

        self._current_file = path
        self._paused = False

    def pause_or_resume(self) -> bool:
        self._ensure_initialized()
        if self._current_file is None:
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

    def close(self) -> None:
        if self._initialized:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
            self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        try:
            pygame.mixer.init()
        except pygame.error as exc:
            raise AudioPlayerError(f"初始化音频设备失败：{exc}") from exc
        self._initialized = True
