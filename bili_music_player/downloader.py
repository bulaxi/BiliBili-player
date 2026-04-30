from __future__ import annotations

import html
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlencode, urlparse

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
BILIBILI_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
BILIBILI_HOME_URL = "https://www.bilibili.com/"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(slots=True)
class AudioStream:
    title: str
    url: str
    stream_url: str
    duration: float | None = None


@dataclass(slots=True)
class BiliSearchResult:
    title: str
    url: str
    duration: float | None = None
    uploader: str | None = None
    view_count: int | None = None
    thumbnail_url: str | None = None


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
        self._buvid3 = f"{uuid.uuid4()}infoc"
        ensure_app_dirs()

    def search(
        self,
        keyword: str,
        limit: int = 10,
        progress_callback: ProgressCallback | None = None,
    ) -> list[BiliSearchResult]:
        keyword = self._normalize_search_keyword(keyword)
        if not keyword:
            raise AudioDownloadError("请输入搜索关键词。")

        limit = max(1, min(limit, 30))
        if progress_callback is not None:
            progress_callback(f"正在搜索 Bilibili：{keyword}")

        ytdlp_error: str | None = None
        ytdlp_results: list[BiliSearchResult] = []
        try:
            ytdlp_results = self._search_with_ytdlp(keyword, limit)
        except DownloadError as exc:
            ytdlp_error = self._friendly_error(exc, "yt-dlp 搜索失败")
        else:
            if self._has_useful_search_metadata(ytdlp_results):
                ytdlp_results = self._sort_search_results(ytdlp_results, keyword)
                if progress_callback is not None:
                    progress_callback(f"找到 {len(ytdlp_results)} 条搜索结果。")
                return ytdlp_results

        if progress_callback is not None:
            progress_callback("yt-dlp 搜索结果不可用，正在改用 Bilibili 搜索接口...")

        try:
            results = self._search_with_bilibili_api(keyword, limit)
        except AudioDownloadError as exc:
            if ytdlp_results:
                if progress_callback is not None:
                    progress_callback("Bilibili 搜索接口不可用，使用 yt-dlp 返回的基础结果。")
                return ytdlp_results
            if ytdlp_error is not None:
                raise AudioDownloadError(f"{exc}（{ytdlp_error}）") from exc
            raise

        if not results:
            if ytdlp_results:
                ytdlp_results = self._sort_search_results(ytdlp_results, keyword)
                if progress_callback is not None:
                    progress_callback("Bilibili 搜索接口未返回结果，使用 yt-dlp 返回的基础结果。")
                return ytdlp_results
            suffix = f"（{ytdlp_error}）" if ytdlp_error is not None else ""
            raise AudioDownloadError(f"没有找到可播放的 Bilibili 搜索结果。{suffix}")

        results = self._sort_search_results(results, keyword)
        if progress_callback is not None:
            progress_callback(f"找到 {len(results)} 条搜索结果。")
        return results

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

        if progress_callback is not None:
            progress_callback("阔音频流已就绪，正在交给播放器...")

        return AudioStream(
            title=title,
            url=cleaned_url,
            stream_url=stream_url,
            duration=self._duration_from_info(audio_format) or self._duration_from_info(info),
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
        return BiliAudioDownloader.normalized_video_url(cleaned_url)

    @staticmethod
    def normalized_video_url(value: str) -> str:
        cleaned_value = value.strip()
        if not cleaned_value:
            raise AudioDownloadError("请输入 Bilibili 视频链接。")

        parsed = urlparse(cleaned_value)
        if parsed.scheme in {"http", "https"}:
            return cleaned_value
        if cleaned_value.startswith(("BV", "av")):
            return f"https://www.bilibili.com/video/{cleaned_value}"
        return cleaned_value

    @staticmethod
    def is_video_reference(value: str) -> bool:
        cleaned_value = value.strip()
        if cleaned_value.startswith(("BV", "av")):
            return True
        parsed = urlparse(cleaned_value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _normalize_search_keyword(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).split())

    def _search_with_ytdlp(self, keyword: str, limit: int) -> list[BiliSearchResult]:
        query = f"bilisearch{limit}:{keyword}"
        with YoutubeDL(self._build_search_options(limit, keyword)) as ydl:
            info = ydl.extract_info(query, download=False)

        entries = []
        if isinstance(info, dict):
            entries = [entry for entry in info.get("entries") or [] if isinstance(entry, dict)]
        return [result for entry in entries if (result := self._search_result_from_entry(entry)) is not None]

    def _search_with_bilibili_api(self, keyword: str, limit: int) -> list[BiliSearchResult]:
        page_size = max(20, limit)
        results: list[BiliSearchResult] = []
        seen_urls: set[str] = set()

        for page in range(1, 4):
            payload = self._request_bilibili_search_page(keyword, page, page_size)
            entries = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(entries, list):
                break

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                result = self._search_result_from_entry(entry)
                if result is None or result.url in seen_urls:
                    continue
                seen_urls.add(result.url)
                results.append(result)
                if len(results) >= limit:
                    return results

            if not entries:
                break

        return results

    @staticmethod
    def _has_useful_search_metadata(results: list[BiliSearchResult]) -> bool:
        return any(
            result.title != "未命名视频" or result.uploader or result.duration is not None
            for result in results
        )

    def _request_bilibili_search_page(self, keyword: str, page: int, page_size: int) -> dict:
        params = {
            "Search_key": keyword,
            "keyword": keyword,
            "search_type": "video",
            "page": page,
            "page_size": page_size,
            "context": "",
            "order": "totalrank",
            "duration": 0,
            "tids_2": "",
            "tids": 0,
            "highlight": 1,
            "__refresh__": "true",
        }
        url = f"{BILIBILI_SEARCH_API}?{urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers=self._browser_headers(
                referer=f"https://search.bilibili.com/all?keyword={quote(keyword)}",
                include_cookie=True,
            ),
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw_body = response.read()
        except urllib.error.HTTPError as exc:
            detail = self._read_http_error_detail(exc)
            raise AudioDownloadError(f"Bilibili 搜索接口返回 HTTP {exc.code}。{detail}") from exc
        except urllib.error.URLError as exc:
            raise AudioDownloadError(f"Bilibili 搜索接口连接失败：{exc.reason}") from exc
        except OSError as exc:
            raise AudioDownloadError(f"Bilibili 搜索接口连接失败：{exc}") from exc

        try:
            document = json.loads(raw_body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise AudioDownloadError("Bilibili 搜索接口返回了无法解析的数据。") from exc

        code = document.get("code")
        if code not in (0, None):
            message = document.get("message") or document.get("msg") or "未知错误"
            raise AudioDownloadError(f"Bilibili 搜索接口返回错误 {code}：{message}")

        data = document.get("data")
        if not isinstance(data, dict):
            raise AudioDownloadError("Bilibili 搜索接口没有返回搜索结果。")
        return data

    def _browser_headers(self, referer: str = BILIBILI_HOME_URL, include_cookie: bool = False) -> dict[str, str]:
        headers = {
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,text/plain,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer,
        }
        if include_cookie:
            headers["Cookie"] = f"buvid3={self._buvid3}"
        return headers

    @staticmethod
    def _read_http_error_detail(exc: urllib.error.HTTPError) -> str:
        try:
            raw_body = exc.read()
        except OSError:
            raw_body = b""

        if not raw_body:
            return ""

        text = raw_body.decode("utf-8", errors="replace").strip()
        if not text:
            return ""

        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            return text[:200]

        message = document.get("message") or document.get("msg")
        code = document.get("code")
        if message and code is not None:
            return f"{code}：{message}"
        if message:
            return str(message)
        return text[:200]

    def _build_search_options(self, limit: int, keyword: str) -> dict:
        return {
            "extract_flat": "in_playlist",
            "http_headers": self._browser_headers(
                referer=f"https://search.bilibili.com/all?keyword={quote(keyword)}",
            ),
            "ignoreerrors": True,
            "no_warnings": True,
            "playlistend": limit,
            "quiet": True,
            "skip_download": True,
        }

    def _build_extract_options(self) -> dict:
        return {
            "format": AUDIO_ONLY_FORMAT,
            "http_headers": self._browser_headers(),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }

    def _search_result_from_entry(self, entry: dict) -> BiliSearchResult | None:
        url = self._entry_video_url(entry)
        if url is None:
            return None

        title = self._clean_entry_text(entry.get("title") or entry.get("fulltitle") or "未命名视频")
        if not title:
            title = "未命名视频"

        return BiliSearchResult(
            title=title,
            url=url,
            duration=self._duration_from_info(entry),
            uploader=self._entry_text(entry, "uploader", "channel", "creator", "author"),
            view_count=self._entry_int(entry, "view_count", "views", "play_count", "play"),
            thumbnail_url=self._thumbnail_url_from_entry(entry),
        )

    @staticmethod
    def _thumbnail_url_from_entry(entry: dict) -> str | None:
        for key in ("thumbnail", "thumbnail_url", "pic", "cover", "cover_url", "arcurl_pic"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                continue

            candidate = value.strip()
            if candidate.startswith("//"):
                return f"https:{candidate}"
            parsed = urlparse(candidate)
            if parsed.scheme in {"http", "https"}:
                return candidate
        return None

    def _sort_search_results(self, results: list[BiliSearchResult], keyword: str) -> list[BiliSearchResult]:
        return sorted(results, key=lambda result: self._search_result_score(result, keyword), reverse=True)

    def _search_result_score(self, result: BiliSearchResult, keyword: str) -> float:
        score = 0.0
        normalized_keyword = self._normalize_for_score(keyword)
        normalized_title = self._normalize_for_score(result.title)
        normalized_uploader = self._normalize_for_score(result.uploader or "")

        keyword_tokens = [token for token in normalized_keyword.split() if token]
        if normalized_keyword and normalized_keyword in normalized_title:
            score += 80

        for token in keyword_tokens:
            if token in normalized_title:
                score += 18
            if token in normalized_uploader:
                score += 8

        positive_title_tokens = {
            "官方": 22,
            "mv": 20,
            "m v": 20,
            "music video": 20,
            "官方版": 18,
            "完整版": 8,
            "高音质": 10,
            "hi res": 12,
            "歌词": 4,
        }
        for token, weight in positive_title_tokens.items():
            if token in normalized_title:
                score += weight

        negative_title_tokens = {
            "翻唱": -30,
            "cover": -28,
            "现场": -18,
            "live": -18,
            "伴奏": -24,
            "纯音乐": -20,
            "鬼畜": -30,
            "dj": -20,
            "剪辑": -12,
            "reaction": -20,
            "教学": -18,
        }
        for token, weight in negative_title_tokens.items():
            if token in normalized_title:
                score += weight

        duration = result.duration or 0.0
        if 90 <= duration <= 480:
            score += 12
        elif duration and duration < 45:
            score -= 18
        elif duration > 900:
            score -= 10

        if result.view_count is not None and result.view_count > 0:
            score += min(16.0, result.view_count / 100000.0)

        return score

    @staticmethod
    def _normalize_for_score(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold().replace("_", " ").replace("-", " ")
        return " ".join(normalized.split())

    def _entry_video_url(self, entry: dict) -> str | None:
        for key in ("webpage_url", "original_url", "arcurl", "url", "goto_url"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                continue

            candidate = value.strip()
            if candidate.startswith("//"):
                return f"https:{candidate}"
            parsed = urlparse(candidate)
            if parsed.scheme in {"http", "https"}:
                return candidate
            if candidate.startswith(("BV", "av")):
                return self.normalized_video_url(candidate)

        for key in ("bvid", "id"):
            video_id = entry.get(key)
            if isinstance(video_id, str) and video_id.startswith(("BV", "av")):
                return self.normalized_video_url(video_id)

        aid = entry.get("aid")
        if isinstance(aid, int):
            return self.normalized_video_url(f"av{aid}")
        if isinstance(aid, str) and aid.isdigit():
            return self.normalized_video_url(f"av{aid}")
        return None

    @staticmethod
    def _entry_text(entry: dict, *keys: str) -> str | None:
        for key in keys:
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                cleaned = BiliAudioDownloader._clean_entry_text(value)
                if cleaned:
                    return cleaned
        return None

    @staticmethod
    def _clean_entry_text(value: object) -> str:
        text = html.unescape(str(value))
        text = HTML_TAG_RE.sub("", text)
        return " ".join(text.split())

    @staticmethod
    def _entry_int(entry: dict, *keys: str) -> int | None:
        for key in keys:
            value = entry.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                normalized = value.replace(",", "").replace("+", "").strip()
                if normalized.isdigit():
                    return int(normalized)
                for suffix, multiplier in (("亿", 100_000_000), ("万", 10_000)):
                    if not normalized.endswith(suffix):
                        continue
                    try:
                        return int(float(normalized[: -len(suffix)]) * multiplier)
                    except ValueError:
                        pass
        return None

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
            "http_headers": self._browser_headers(),
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
        if isinstance(duration, (int, float)):
            return float(duration)
        if isinstance(duration, str):
            parsed_duration = BiliAudioDownloader._parse_duration_string(duration)
            if parsed_duration is not None:
                return parsed_duration

        duration_string = info.get("duration_string")
        if isinstance(duration_string, str):
            return BiliAudioDownloader._parse_duration_string(duration_string)
        return None

    @staticmethod
    def _parse_duration_string(value: str) -> float | None:
        parts = value.split(":")
        if not parts or not all(part.isdigit() for part in parts):
            return None

        seconds = 0
        for part in parts:
            seconds = seconds * 60 + int(part)
        return float(seconds)

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
