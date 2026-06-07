<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows%20|%20macOS%20|%20Linux-blue" alt="Platform">
  <img src="https://img.shields.io/badge/GUI-CustomTkinter-3b8ed0" alt="CustomTkinter">
</p>

<h1 align="center">Media Filter / 媒体筛选器</h1>

<p align="center">A desktop GUI tool for scanning media folders (video + audio), analyzing file statistics, and generating batch FFmpeg transcoding commands.<br>
桌面端媒体文件扫描统计工具，支持视频和音频文件的码率/时长/大小查看，批量生成 FFmpeg 转码命令。</p>

<p align="center">
  <a href="#features--功能">Features</a> ·
  <a href="#quick-start--快速开始">Quick Start</a> ·
  <a href="#requirements--环境要求">Requirements</a> ·
  <a href="#usage--使用方式">Usage</a>
</p>

---

## Features / 功能

| Feature | Description |
|---------|-------------|
| Folder scanning | Recursively scan folders for video + audio files, extract size / duration / bitrate via ffprobe |
| 文件夹扫描 | 递归扫描文件夹，支持视频和音频文件，通过 ffprobe 提取大小、时长、码率 |
| Multi-threaded | Configurable thread count for fast scanning of large folders |
| 多线程 | 可配置线程数，快速处理大量媒体文件 |
| Sort & filter | Sort by name / size / duration / bitrate; filter by file format |
| 排序筛选 | 按名称、大小、时长、码率排序；按格式筛选 |
| Selection stats | Multi-select files to view total count, duration, and size |
| 选择统计 | 勾选多个文件实时显示总数量、总时长、总大小 |
| Batch commands | Built-in presets: x265 CRF CPU / NVENC HEVC / NVENC H.264 |
| 批量命令 | 内置转码预设，支持自定义命令和参数 |
| Theme | Dark / Light mode with smooth animated transition |
| 主题切换 | 深色/浅色模式，流畅渐变动画过渡 |
| Bilingual | Chinese / English UI with one-click toggle |
| 双语界面 | 中英文界面一键切换，预设命令同步翻译 |
| Drag-select | Click-and-drag to multi-select rows quickly |
| 拖拽选择 | 点击拖拽即可快速批量选择 |

## Quick Start / 快速开始

```bash
# 1. Clone the repo
git clone https://github.com/yvgui2004/video-filter.git
cd video-filter

# 2. Install dependencies
pip install -r requirements.txt

# 3. Make sure ffprobe is installed (see Requirements below)

# 4. Run
python 3.py
```

## Requirements / 环境要求

### 1. Python 3.10+

Download from [python.org](https://www.python.org/downloads/), check **"Add Python to PATH"** during install.

从 [python.org](https://www.python.org/downloads/) 下载，安装时勾选 **"Add Python to PATH"**。

```bash
python --version   # should be ≥ 3.10
```

### 2. CustomTkinter

```bash
pip install -r requirements.txt
```

Or with mirror (China) / 国内镜像加速：

```bash
pip install customtkinter -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. FFmpeg (includes ffprobe)

The app uses `ffprobe` to read media metadata. FFmpeg must be installed and in PATH.

程序通过 `ffprobe` 读取媒体元数据，必须先安装 FFmpeg 并加入系统 PATH。

**Windows:**

1. Download [ffmpeg-master-latest-win64-gpl.zip](https://github.com/BtbN/FFmpeg-Builds/releases/latest)
1. Extract to a directory (e.g. `C:\ffmpeg`) / 解压到 `C:\ffmpeg`
1. Add `C:\ffmpeg\bin` to system PATH: / 添加到 PATH：
   - Right-click "This PC" → Properties → Advanced system settings → Environment Variables
   - 右键"此电脑" → 属性 → 高级系统设置 → 环境变量
   - Find `Path` in System variables, add `C:\ffmpeg\bin`
   - 在系统变量 `Path` 中添加 `C:\ffmpeg\bin`
1. Restart terminal and verify: / 重启终端验证：

```bash
ffprobe -version
```

**macOS:**

```bash
brew install ffmpeg
```

**Linux (Debian/Ubuntu):**

```bash
sudo apt install ffmpeg
```

### 4. Verify / 验证

```bash
python -c "import customtkinter; print('OK')"
ffprobe -version | head -1
```

## Usage / 使用方式

```bash
python 3.py
```

| Step | Action |
|------|--------|
| 1 | Click **Open Folder** / 点击"选择文件夹" |
| 2 | Sort by name/size/duration, filter by format / 排序、筛选 |
| 3 | Check boxes to select files / 勾选媒体文件 |
| 4 | Optionally apply batch command presets / 可选应用批量命令预设 |
| 5 | Copy file paths or execute commands / 复制路径或执行命令 |

## Batch Command Presets / 批量命令预设

| Preset | Command | Description |
|--------|---------|-------------|
| x265 CRF23 | `ffmpeg -i input -c:v libx265 -crf 23 ...` | Compress ~75%, CPU encode |
| x265 CRF26 | `ffmpeg -i input -c:v libx265 -crf 26 ...` | Compress ~85%, CPU encode |
| NVENC HEVC CQ23 | `ffmpeg -i input -c:v hevc_nvenc -cq 23 ...` | GPU HEVC high quality |
| NVENC HEVC CQ26 | `ffmpeg -i input -c:v hevc_nvenc -cq 26 ...` | GPU HEVC balanced |
| NVENC H.264 | `ffmpeg -i input -c:v h264_nvenc ...` | GPU H.264 compatibility |

All presets can be customized in the Batch Command dialog. / 所有预设可在批量命令对话框中自定义。

## Project Structure / 项目结构

```
video-filter/
├── 3.py              # Main application
├── requirements.txt  # Python dependencies
├── LICENSE           # MIT license
└── README.md         # This file
```

## License / 许可证

MIT — feel free to use, modify, and distribute.
