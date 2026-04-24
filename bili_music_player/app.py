from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .audio_player import AudioPlayer, AudioPlayerError
from .downloader import AudioDownloadError, AudioStream, BiliAudioDownloader
from .library import MusicLibrary, Track


class BiliMusicPlayerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Bili Music Player")
        self.geometry("820x500")
        self.minsize(680, 420)

        self.library = MusicLibrary()
        self.downloader = BiliAudioDownloader()
        self.player = AudioPlayer()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_url_task_running = False

        self.url_var = tk.StringVar()
        self.cache_after_stream_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="准备就绪。")
        self.pause_text = tk.StringVar(value="暂停")

        self._build_ui()
        self._load_playlist()
        self.after(150, self._process_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        input_frame = ttk.LabelFrame(root, text="Bilibili 链接", padding=10)
        input_frame.grid(row=0, column=0, sticky="ew")
        input_frame.columnconfigure(0, weight=1)

        self.url_entry = ttk.Entry(input_frame, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.url_entry.bind("<Return>", lambda _event: self._start_stream())

        self.stream_button = ttk.Button(input_frame, text="播放/串流", command=self._start_stream)
        self.stream_button.grid(row=0, column=1, padx=(0, 8))

        self.cache_button = ttk.Button(input_frame, text="保存到本地", command=self._start_cache_only)
        self.cache_button.grid(row=0, column=2)

        self.cache_check = ttk.Checkbutton(
            input_frame,
            text="播放时同时缓存到本地",
            variable=self.cache_after_stream_var,
        )
        self.cache_check.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        playlist_frame = ttk.LabelFrame(root, text="本地缓存/播放列表", padding=10)
        playlist_frame.grid(row=1, column=0, sticky="nsew", pady=12)
        playlist_frame.columnconfigure(0, weight=1)
        playlist_frame.rowconfigure(0, weight=1)

        self.playlist = tk.Listbox(playlist_frame, activestyle="dotbox")
        self.playlist.grid(row=0, column=0, sticky="nsew")
        self.playlist.bind("<Double-Button-1>", lambda _event: self._play_selected())

        scrollbar = ttk.Scrollbar(playlist_frame, orient=tk.VERTICAL, command=self.playlist.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.playlist.configure(yscrollcommand=scrollbar.set)

        controls = ttk.Frame(root)
        controls.grid(row=2, column=0, sticky="ew")
        controls.columnconfigure(4, weight=1)

        ttk.Button(controls, text="播放选中", command=self._play_selected).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(controls, textvariable=self.pause_text, command=self._pause_or_resume).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(controls, text="停止", command=self._stop).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(controls, text="刷新列表", command=self._refresh_playlist).grid(row=0, column=3)

        status = ttk.Label(root, textvariable=self.status_var, anchor="w")
        status.grid(row=3, column=0, sticky="ew", pady=(12, 0))

    def _load_playlist(self) -> None:
        self.playlist.delete(0, tk.END)
        self.library.prune_missing()
        self.library.save()
        for track in self.library.tracks:
            self.playlist.insert(tk.END, track.display_name)

    def _refresh_playlist(self) -> None:
        self._load_playlist()
        self._set_status("播放列表已刷新。")

    def _start_stream(self) -> None:
        if self.is_url_task_running:
            return

        url = self._url_or_error()
        if url is None:
            return

        self._begin_url_task("正在解析音频流...")
        cache_after_stream = self.cache_after_stream_var.get()
        thread = threading.Thread(target=self._stream_worker, args=(url, cache_after_stream), daemon=True)
        thread.start()

    def _start_cache_only(self) -> None:
        if self.is_url_task_running:
            return

        url = self._url_or_error()
        if url is None:
            return

        self._begin_url_task("正在缓存音频到本地...")
        self._start_cache_worker(url, play_after=False)

    def _stream_worker(self, url: str, cache_after_stream: bool) -> None:
        try:
            stream = self.downloader.resolve_stream(url, lambda message: self.events.put(("status", message)))
            self.events.put(("stream_resolved", (stream, cache_after_stream)))
        except AudioDownloadError as exc:
            self.events.put(("error", str(exc)))
        except Exception as exc:  # Defensive UI boundary.
            self.events.put(("error", f"发生未知错误：{exc}"))

    def _start_cache_worker(self, url: str, play_after: bool) -> None:
        thread = threading.Thread(target=self._cache_worker, args=(url, play_after), daemon=True)
        thread.start()

    def _cache_worker(self, url: str, play_after: bool) -> None:
        try:
            track = self.downloader.download(url, lambda message: self.events.put(("status", message)))
            self.events.put(("cached", (track, play_after)))
        except AudioDownloadError as exc:
            self.events.put(("error", str(exc)))
        except Exception as exc:  # Defensive UI boundary.
            self.events.put(("error", f"发生未知错误：{exc}"))

    def _start_temp_play_worker(self, url: str) -> None:
        thread = threading.Thread(target=self._temp_play_worker, args=(url,), daemon=True)
        thread.start()

    def _temp_play_worker(self, url: str) -> None:
        try:
            self.events.put(("status", "正在建立临时音频缓存..."))
            track = self.downloader.download_temporary(url, lambda message: self.events.put(("status", message)))
            self.events.put(("temp_ready", track))
        except AudioDownloadError as exc:
            self.events.put(("error", str(exc)))
        except Exception as exc:  # Defensive UI boundary.
            self.events.put(("error", f"发生未知错误：{exc}"))

    def _process_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "status":
                self._set_status(str(payload))
            elif event == "stream_resolved":
                stream, cache_after_stream = payload
                if isinstance(stream, AudioStream):
                    self._handle_stream_resolved(stream, bool(cache_after_stream))
            elif event == "temp_ready" and isinstance(payload, Track):
                if self._play_track(payload):
                    self.url_var.set("")
                    self._set_status(f"正在播放临时缓存：{payload.title}")
                self._finish_url_task()
            elif event == "cached":
                track, play_after = payload
                if isinstance(track, Track):
                    self.library.add_or_update(track)
                    self.url_var.set("")
                    self._load_playlist()
                    if play_after:
                        if self._play_track(track):
                            self._set_status(f"已缓存并播放：{track.title}")
                    else:
                        self._set_status(f"已缓存：{track.title}")
                self._finish_url_task()
            elif event == "error":
                self._finish_url_task()
                self._show_error(str(payload))

        self.after(150, self._process_events)

    def _handle_stream_resolved(self, stream: AudioStream, cache_after_stream: bool) -> None:
        try:
            self.player.play(stream.stream_url)
        except AudioPlayerError:
            fallback = "本地缓存" if cache_after_stream else "临时音频缓存"
            self._set_status(f"播放器无法直接打开远程音频流，改用{fallback}...")
            if cache_after_stream:
                self._start_cache_worker(stream.url, play_after=True)
            else:
                self._start_temp_play_worker(stream.url)
            return

        self.pause_text.set("暂停")
        if cache_after_stream:
            self._set_status(f"正在串流播放：{stream.title}；后台缓存中...")
            self._start_cache_worker(stream.url, play_after=False)
        else:
            self.url_var.set("")
            self._set_status(f"正在串流播放：{stream.title}")
            self._finish_url_task()

    def _selected_track(self) -> Track | None:
        selection = self.playlist.curselection()
        if not selection:
            self._show_error("请先在播放列表中选择一首音频。")
            return None

        tracks = self.library.tracks
        index = selection[0]
        if index >= len(tracks):
            self._show_error("选中的条目无效，请刷新列表。")
            return None
        return tracks[index]

    def _play_selected(self) -> None:
        track = self._selected_track()
        if track is not None:
            self._play_track(track)

    def _play_track(self, track: Track) -> bool:
        try:
            self.player.play(track.file_path)
        except AudioPlayerError as exc:
            self._show_error(str(exc))
            return False
        self.pause_text.set("暂停")
        self._set_status(f"正在播放：{track.title}")
        return True

    def _pause_or_resume(self) -> None:
        try:
            paused = self.player.pause_or_resume()
        except AudioPlayerError as exc:
            self._show_error(str(exc))
            return
        self.pause_text.set("继续" if paused else "暂停")
        self._set_status("已暂停。" if paused else "继续播放。")

    def _stop(self) -> None:
        self.player.stop()
        self.pause_text.set("暂停")
        self._set_status("已停止。")

    def _url_or_error(self) -> str | None:
        url = self.url_var.get().strip()
        if not url:
            self._show_error("请输入 Bilibili 视频链接。")
            return None
        return url

    def _begin_url_task(self, message: str) -> None:
        self.is_url_task_running = True
        self._set_url_controls_state(tk.DISABLED)
        self._set_status(message)

    def _finish_url_task(self) -> None:
        self.is_url_task_running = False
        self._set_url_controls_state(tk.NORMAL)

    def _set_url_controls_state(self, state: str) -> None:
        self.stream_button.configure(state=state)
        self.cache_button.configure(state=state)
        self.cache_check.configure(state=state)

    def _show_error(self, message: str) -> None:
        self._set_status(message)
        messagebox.showerror("Bili Music Player", message)

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _on_close(self) -> None:
        self.player.close()
        self.downloader.cleanup_temporary_files()
        self.destroy()


def main() -> None:
    app = BiliMusicPlayerApp()
    app.mainloop()
