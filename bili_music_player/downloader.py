from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

try:
    import imageio_ffmpeg
except ImportError:  # Optional at import time; surfaced when download needs ffmpeg.
    imageio_ffmpeg = None

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .library import Track
from .paths import DOWNLOADS_DIR, STREAM_CACHE_DIR, ensure_app_dirs


ProgressCallback = Callable[[str], None]
AUDIO_ONLY_FORMAT = "bestaudio[acodec!=none][vcodec=none]"


@dataclass(slots=True)
class AudioStream:
    title: str
    url: str
    stream_url: str
    duration: float | None = None
    ext: str | None = None
    http_headers: dict[str, str] = field(default_factory=dict)


class AudioDownloadError(RuntimeError):
    pass


class BiliAudioDownloader:
    def __init__(
        self,
        downloads_dir: Path = DOWNLOADS_DIR,
        stream_cache_dir: Path = STREAM_CACHE_DIR,
    ) -> None:
        self.downloads_dir = downloads_dir
        self.stream_cache_dir = stream_cache_dir
        ensure_app_dirs()

    def resolve_stream(self, url: str, progress_callback: ProgressCallback | None = None) -> AudioStream:
        cleaned_url = self._clean_url(url)
        if progress_callback is not None:
            progress_callback("正在解析音频流...")

        try:
            with YoutubeDL(self._build_extract_options()) as ydl:
                info = ydl.extract_info(cleaned_url, download=False)
        except DownloadError as exc:
            raise AudioDownloadError(self._friendly_error(exc, "解析音频流失败")) from exc

        if info is None:
            raise AudioDownloadError("未能获取视频信息。")

        info = self._single_video_info(info)
        audio_format = self._select_audio_format(info)
        title = str(info.get("title") or audio_format.get("title") or "未命名音频")
        stream_url = audio_format.get("url")
        if not isinstance(stream_url, str) or not stream_url:
            raise AudioDownloadError("未找到可播放的音频流地址。")

        headers: dict[str, str] = {}
        for source in (info.get("http_headers"), audio_format.get("http_headers")):
            if isinstance(source, dict):
                headers.update({str(key): str(value) for key, value in source.items()})

        if progress_callback is not None:
            progress_callback("音频流已就绪，正在交给播放器...")

        return AudioStream(
            title=title,
            url=cleaned_url,
            stream_url=stream_url,
            duration=self._duration_from_info(audio_format) or self._duration_from_info(info),
            ext=str(audio_format.get("ext") or info.get("ext") or ""),
            http_headers=headers,
        )

    def download(self, url: str, progress_callback: ProgressCallback | None = None) -> Track:
        return self._download_audio(url, self.downloads_dir, progress_callback)

    def download_temporary(self, url: str, progress_callback: ProgressCallback | None = None) -> Track:
        self._cleanup_old_stream_cache()
        prefix = f"stream-{uuid.uuid4().hex[:8]}-"
        return self._download_audio(url, self.stream_cache_dir, progress_callback, filename_prefix=prefix)

    def cleanup_temporary_files(self) -> None:
        for path in self.stream_cache_dir.glob("*"):
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass

    def _download_audio(
        self,
        url: str,
        output_dir: Path,
        progress_callback: ProgressCallback | None,
        filename_prefix: str = "",
    ) -> Track:
        cleaned_url = self._clean_url(url)
        output_dir.mkdir(parents=True, exist_ok=True)

        options = self._build_download_options(output_dir, progress_callback, filename_prefix)
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(cleaned_url, download=True)
                if info is None:
                    raise AudioDownloadError("未能获取视频信息。")
                title = str(info.get("title") or "未命名音频")
                file_path = self._resolve_output_path(ydl, info, output_dir)
        except DownloadError as exc:
            raise AudioDownloadError(self._friendly_error(exc, "下载失败")) from exc
        except OSError as exc:
            raise AudioDownloadError(f"保存文件失败：{exc}") from exc

        return Track(
            title=title,
            url=cleaned_url,
            file_path=str(file_path),
            duration=self._duration_from_info(info),
        )

    @staticmethod
    def _clean_url(url: str) -> str:
        cleaned_url = url.strip()
        if not cleaned_url:
            raise AudioDownloadError("请输入 Bilibili 视频链接。")
        return cleaned_url

    def _build_extract_options(self) -> dict:
        return {
            "format": AUDIO_ONLY_FORMAT,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }

    def _build_download_options(
        self,
        output_dir: Path,
        progress_callback: ProgressCallback | None,
        filename_prefix: str,
    ) -> dict:
        hooks = []
        if progress_callback is not None:
            hooks.append(lambda data: self._handle_progress(data, progress_callback))

        options = {
            "format": AUDIO_ONLY_FORMAT,
            "outtmpl": str(output_dir / f"{filename_prefix}%(title).200B [%(id)s].%(ext)s"),
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
        ffmpeg_exe = self._find_ffmpeg_executable()
        if ffmpeg_exe is not None:
            options["ffmpeg_location"] = ffmpeg_exe
        return options

    def _resolve_output_path(self, ydl: YoutubeDL, info: dict, output_dir: Path) -> Path:
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
            (path for path in output_dir.iterdir() if video_id and video_id in path.stem),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return matches[0]
        raise AudioDownloadError("处理完成，但没有找到生成的音频文件。")

    @staticmethod
    def _single_video_info(info: dict) -> dict:
        if info.get("_type") != "playlist":
            return info

        entries = info.get("entries") or []
        for entry in entries:
            if isinstance(entry, dict):
                return entry
        raise AudioDownloadError("播放列表中没有可用的视频。")

    def _select_audio_format(self, info: dict) -> dict:
        candidates = []
        for candidate in self._format_candidates(info):
            if not self._is_audio_only(candidate):
                continue
            url = candidate.get("url")
            if not isinstance(url, str) or not url:
                continue
            candidates.append(candidate)

        if not candidates:
            raise AudioDownloadError("未找到可直接播放的音频流，已避免下载完整视频文件。")

        return max(candidates, key=self._audio_quality_score)

    @staticmethod
    def _format_candidates(info: dict) -> list[dict]:
        candidates = []
        for item in (info, *(info.get("requested_formats") or []), *(info.get("formats") or [])):
            if isinstance(item, dict):
                candidates.append(item)
        return candidates

    @staticmethod
    def _is_audio_only(info: dict) -> bool:
        acodec = str(info.get("acodec") or "")
        if not acodec or acodec == "none":
            return False

        vcodec = info.get("vcodec")
        if vcodec == "none":
            return True

        has_video_shape = any(info.get(key) for key in ("width", "height", "fps"))
        return vcodec in (None, "", "unknown") and not has_video_shape

    @staticmethod
    def _audio_quality_score(info: dict) -> float:
        for key in ("abr", "tbr", "filesize", "filesize_approx"):
            value = info.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return 0.0

    def _cleanup_old_stream_cache(self, max_age_seconds: int = 24 * 60 * 60) -> None:
        cutoff = time.time() - max_age_seconds
        for path in self.stream_cache_dir.glob("*"):
            if not path.is_file():
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass

    @staticmethod
    def _handle_progress(data: dict, progress_callback: ProgressCallback) -> None:
        status = data.get("status")
        if status == "downloading":
            percent = data.get("_percent_str", "").strip()
            speed = data.get("_speed_str", "").strip()
            progress_callback(f"音频获取中 {percent} {speed}".strip())
        elif status == "finished":
            progress_callback("音频获取完成，正在转换为 mp3...")

    @staticmethod
    def _duration_from_info(info: dict) -> float | None:
        duration = info.get("duration")
        return float(duration) if isinstance(duration, (int, float)) else None

    @staticmethod
    def _find_ffmpeg_executable() -> str | None:
        if imageio_ffmpeg is None:
            return None
        try:
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None

    @staticmethod
    def _friendly_error(exc: DownloadError, prefix: str) -> str:
        message = str(exc)
        lowered = message.lower()
        if "ffmpeg" in lowered:
            return "音频提取需要 ffmpeg。请安装 ffmpeg，或安装 requirements.txt 里的 imageio-ffmpeg 后重试。"
        if "requested format is not available" in lowered:
            return f"{prefix}：未找到可用的独立音频流，已避免下载完整视频文件。"
        return f"{prefix}：{message}"
