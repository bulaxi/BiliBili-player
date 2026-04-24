from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .audio_player import AudioPlayer, AudioPlayerError
from .downloader import AudioDownloadError, BiliAudioDownloader
from .library import MusicLibrary, Track


class BiliMusicPlayerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Bili Music Player")
        self.geometry("760x460")
        self.minsize(620, 380)

        self.library = MusicLibrary()
        self.downloader = BiliAudioDownloader()
        self.player = AudioPlayer()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_downloading = False

        self.url_var = tk.StringVar()
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
        self.url_entry.bind("<Return>", lambda _event: self._start_download())

        self.download_button = ttk.Button(input_frame, text="下载/提取音频", command=self._start_download)
        self.download_button.grid(row=0, column=1)

        playlist_frame = ttk.LabelFrame(root, text="本地播放列表", padding=10)
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

    def _start_download(self) -> None:
        if self.is_downloading:
            return

        url = self.url_var.get().strip()
        if not url:
            self._show_error("请输入 Bilibili 视频链接。")
            return

        self.is_downloading = True
        self.download_button.configure(state=tk.DISABLED)
        self._set_status("准备下载...")
        thread = threading.Thread(target=self._download_worker, args=(url,), daemon=True)
        thread.start()

    def _download_worker(self, url: str) -> None:
        try:
            track = self.downloader.download(url, lambda message: self.events.put(("status", message)))
            self.events.put(("downloaded", track))
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
            elif event == "downloaded" and isinstance(payload, Track):
                self.library.add_or_update(payload)
                self.url_var.set("")
                self._load_playlist()
                self._set_status(f"已保存：{payload.title}")
                self.is_downloading = False
                self.download_button.configure(state=tk.NORMAL)
            elif event == "error":
                self.is_downloading = False
                self.download_button.configure(state=tk.NORMAL)
                self._show_error(str(payload))

        self.after(150, self._process_events)

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
        if track is None:
            return
        try:
            self.player.play(track.file_path)
        except AudioPlayerError as exc:
            self._show_error(str(exc))
            return
        self.pause_text.set("暂停")
        self._set_status(f"正在播放：{track.title}")

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

    def _show_error(self, message: str) -> None:
        self._set_status(message)
        messagebox.showerror("Bili Music Player", message)

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _on_close(self) -> None:
        self.player.close()
        self.destroy()


def main() -> None:
    app = BiliMusicPlayerApp()
    app.mainloop()
