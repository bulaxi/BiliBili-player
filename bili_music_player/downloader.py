from __future__ import annotations

from pathlib import Path
from typing import Callable

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .library import Track
from .paths import DOWNLOADS_DIR, ensure_app_dirs


ProgressCallback = Callable[[str], None]


class AudioDownloadError(RuntimeError):
    pass


class BiliAudioDownloader:
    def __init__(self, downloads_dir: Path = DOWNLOADS_DIR) -> None:
        self.downloads_dir = downloads_dir
        ensure_app_dirs()

    def download(self, url: str, progress_callback: ProgressCallback | None = None) -> Track:
        cleaned_url = url.strip()
        if not cleaned_url:
            raise AudioDownloadError("请输入 Bilibili 视频链接。")

        options = self._build_options(progress_callback)
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(cleaned_url, download=True)
                if info is None:
                    raise AudioDownloadError("未能获取视频信息。")
                title = str(info.get("title") or "未命名音频")
                file_path = self._resolve_output_path(ydl, info)
        except DownloadError as exc:
            raise AudioDownloadError(self._friendly_error(exc)) from exc
        except OSError as exc:
            raise AudioDownloadError(f"保存文件失败：{exc}") from exc

        return Track(
            title=title,
            url=cleaned_url,
            file_path=str(file_path),
            duration=self._duration_from_info(info),
        )

    def _build_options(self, progress_callback: ProgressCallback | None) -> dict:
        hooks = []
        if progress_callback is not None:
            hooks.append(lambda data: self._handle_progress(data, progress_callback))

        return {
            "format": "bestaudio/best",
            "outtmpl": str(self.downloads_dir / "%(title).200B [%(id)s].%(ext)s"),
            "noplaylist": True,
            "progress_hooks": hooks,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
            "no_warnings": True,
        }

    def _resolve_output_path(self, ydl: YoutubeDL, info: dict) -> Path:
        requested_downloads = info.get("requested_downloads") or []
        for download in requested_downloads:
            candidate = download.get("filepath")
            if candidate:
                path = Path(candidate)
                mp3_path = path.with_suffix(".mp3")
                if mp3_path.exists():
                    return mp3_path
                if path.exists():
                    return path

        prepared_path = Path(ydl.prepare_filename(info))
        mp3_path = prepared_path.with_suffix(".mp3")
        if mp3_path.exists():
            return mp3_path
        if prepared_path.exists():
            return prepared_path

        video_id = str(info.get("id") or "")
        matches = sorted(
            (path for path in self.downloads_dir.iterdir() if video_id and video_id in path.stem),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return matches[0]
        raise AudioDownloadError("下载完成，但没有找到生成的音频文件。")

    @staticmethod
    def _handle_progress(data: dict, progress_callback: ProgressCallback) -> None:
        status = data.get("status")
        if status == "downloading":
            percent = data.get("_percent_str", "").strip()
            speed = data.get("_speed_str", "").strip()
            progress_callback(f"下载中 {percent} {speed}".strip())
        elif status == "finished":
            progress_callback("下载完成，正在提取音频...")

    @staticmethod
    def _duration_from_info(info: dict) -> float | None:
        duration = info.get("duration")
        return float(duration) if isinstance(duration, (int, float)) else None

    @staticmethod
    def _friendly_error(exc: DownloadError) -> str:
        message = str(exc)
        if "ffmpeg" in message.lower():
            return "音频提取需要 ffmpeg。请安装 ffmpeg 并加入 PATH 后重试。"
        return f"下载失败：{message}"
