# Bili Music Player

一个基于 Python + Tkinter 的 Bilibili 音乐播放器客户端。输入关键词即可搜索 Bilibili 的音乐、MV、翻唱视频，并直接提取音频进行在线播放或本地缓存。本应用最初通过爬取 B 站音视频制作，目前支持了 yt-dlp 与 Bilibili 接口双解析。

## ✨ 主要功能

- **🚀 快捷搜歌**：直接输入歌名、歌手名、BV 号进行搜索，自动过滤非音乐内容。
- **🎧 双引擎解析**：优先使用 `yt-dlp` 解析高质量音频，遇到网络限制或解析不稳定时，自动回退到 Bilibili 搜索接口。
- **❤️ 收藏歌单**：遇到喜欢的歌，一键加入“我喜欢”列表，像网易云一样方便下次直接点播，支持顺序播放、随机播放等。
- **📦 导入 CSV 歌单**：支持一键导入 Excel / CSV 格式的歌单，自带自动限速防护策略，防止请求被封禁(412)。
- **💾 本地离线缓存**：支持“边播边存”或直接下载音频到本地，本地缓存列表会记录已保存的内容，可离线播放。
- **🖥️ 现代桌面 UI**：深色模式无边框设计，展示视频封面图、UP 主、播放量等，支持拖动进度条。

## 🛠️ 安装与运行

推荐使用 Python 3.10+，并建议在虚拟环境中运行：

```bash
# 1. 克隆项目
git clone https://github.com/your-username/bili-music-player.git
cd bili-music-player

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行项目
python run_app.py
```

> 提示：项目自带 Windows 打包脚本 `build_exe.ps1`，直接运行即可打包为免安装的独立应用（生成在 `dist/` 目录）。

## 📝 导入“我喜欢”说明

导入歌单时，推荐使用带有以下表头的 CSV 或 Excel (.xlsx) 文件：
- `曲名` 或 `title`
- `链接` 或 `url` 或 `BV号`
系统会自动解析并采集对应数据。

## 🛡️ 免责声明

本项目仅供学习与技术交流使用。所有的音频及视频素材版权均归 Bilibili 及原上传 UP 主所有，请勿用于任何商业用途。

## 📄 许可证

[MIT License](LICENSE)
