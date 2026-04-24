# Bili Music Player

一个简单的 Python 桌面音乐播放器：输入 Bilibili 视频链接，使用 `yt-dlp` 下载并提取音频，保存到项目内的 `downloads/` 文件夹，然后在应用内播放。

## 功能

- 输入 Bilibili 视频 URL 并下载/提取音频
- 本地播放列表/历史记录
- 播放选中音频、暂停/继续、停止
- 状态与错误提示
- 下载文件与播放列表数据保存在本地，不使用云服务

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

3. 安装 ffmpeg：

   `yt-dlp` 下载 Bilibili 音频后，需要 `ffmpeg` 将音频提取/转换为 mp3。任选一种方式安装：

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
2. 点击“下载/提取音频”。
3. 下载完成后，音频会保存到 `downloads/`，并出现在“本地播放列表”。
4. 选择列表中的音频，点击“播放选中”，也可以双击列表项播放。
5. 使用“暂停/继续”和“停止”控制播放。

## 常见问题

- 如果提示需要 `ffmpeg`，请确认已安装 ffmpeg，并且 `ffmpeg.exe` 所在目录已经加入 `PATH`。
- 如果 Bilibili 链接需要登录权限、会员权限或地区权限，`yt-dlp` 可能无法直接下载。
- 如果播放失败，请确认生成的音频文件仍在 `downloads/` 文件夹中，或点击“刷新列表”清理不存在的条目。
