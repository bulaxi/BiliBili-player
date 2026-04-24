# Bili Music Player

一个简单的 Python 桌面音乐播放器。现在采用“串流优先 + 可选缓存”的混合模式：输入 Bilibili 视频链接后，默认先解析独立音频流并尝试直接播放，不再把完整视频下载到本地作为默认流程。

## 功能

- 输入 Bilibili 视频 URL 后点击“播放/串流”，优先播放远程音频流
- 如果当前 pygame/SDL 环境无法直接打开远程音频流，自动改用临时音频缓存：只获取音频流并转换为 mp3 后播放，不保存完整视频文件
- 可勾选“播放时同时缓存到本地”，或点击“保存到本地”单独保存音频
- 保留本地缓存/播放列表，可播放选中音频、暂停/继续、停止、刷新列表
- 本地缓存数据保存在项目内 `downloads/`，临时串流缓存保存在 `downloads/.stream-cache/` 并在退出时清理

## 混合模式说明

程序继续使用 `yt-dlp`、`tkinter` 和 `pygame`：

1. “播放/串流”会先让 `yt-dlp` 解析 Bilibili 的独立音频流地址，避免默认下载完整视频。
2. 程序会把音频流地址交给 `pygame.mixer.music` 尝试直接播放。
3. 由于 pygame/SDL 对 HTTPS、请求头和部分音频容器的支持取决于本机环境，直接串流不一定总能成功。失败时，程序会下载“音频流本身”到临时目录并转换成 mp3，再用 pygame 播放。
4. “保存到本地”会把音频保存为 mp3 并加入本地播放列表，适合离线播放或保留历史。

这个方案的目标是实用稳定：默认不下载完整视频；在 pygame 不能真串流时，也只处理音频，不走旧的“先下载视频再播放”的路径。

## Windows 安装

建议使用 Python 3.10 或更新版本。

1. 创建并启用虚拟环境：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. 安装 Python 依赖：

   ```powershell
   pip install -r requirements.txt
   ```

   `requirements.txt` 已包含 `imageio-ffmpeg`，程序会优先使用它自带的 ffmpeg 二进制做音频转换，因此通常**不需要额外手动安装系统级 ffmpeg**。

3. （可选）安装系统 ffmpeg：

   如果你更希望系统里也能直接运行 `ffmpeg` 命令，可以额外安装：

   - 使用 winget：

     ```powershell
     winget install Gyan.FFmpeg
     ```

   - 或从 ffmpeg 官网/发行包下载 Windows 版本，并把 `bin` 目录加入系统 `PATH`。

   安装后重新打开 PowerShell，运行下面命令确认可用：

   ```powershell
   ffmpeg -version
   ```

## 运行

在项目根目录执行：

```powershell
python -m bili_music_player
```

## 使用方法

1. 复制一个 Bilibili 视频链接到输入框。
2. 点击“播放/串流”直接播放。程序会优先尝试远程音频流；如果本机 pygame 无法打开，会自动改用临时音频缓存。
3. 如需保存，勾选“播放时同时缓存到本地”，或点击“保存到本地”。
4. 已保存的音频会出现在“本地缓存/播放列表”。选择列表项后点击“播放选中”，也可以双击播放。
5. 使用“暂停/继续”和“停止”控制播放。

## 常见问题

- 如果提示需要 `ffmpeg`，先确认已经执行过 `pip install -r requirements.txt`；本项目会优先使用 `imageio-ffmpeg` 自带的 ffmpeg。若你想让命令行也能直接用 `ffmpeg`，再额外安装系统级 ffmpeg。
- 如果 Bilibili 链接需要登录权限、会员权限或地区权限，`yt-dlp` 可能无法直接解析或获取音频。
- 如果“播放/串流”一开始没有立刻出声，可能是 pygame 不能直接打开该远程流，程序正在转入临时音频缓存 fallback。
- 如果播放本地缓存失败，请确认音频文件仍在 `downloads/` 文件夹中，或点击“刷新列表”清理不存在的条目。
