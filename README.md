<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows%20|%20macOS%20|%20Linux-blue" alt="Platform">
  <img src="https://img.shields.io/badge/GUI-CustomTkinter-3b8ed0" alt="CustomTkinter">
</p>

<h1 align="center">Media Filter</h1>

<p align="center"><strong>Media Filter</strong> is a desktop GUI tool for scanning media folders (video + audio), analyzing file metadata, and generating batch FFmpeg transcoding commands.<br>
<small>桌面端媒体文件扫描统计工具，支持视频和音频文件的码率 / 时长 / 大小查看，批量生成 FFmpeg 转码命令。</small></p>

<p align="center">
  <a href="#features">Features</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#requirements">Requirements</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#batch-command-presets">Presets</a>
</p>

---

## Features

- **Folder scanning** — Recursively scan folders for video + audio files; extract size, duration, and bitrate via ffprobe
  <br><small>递归扫描文件夹，支持视频和音频文件，通过 ffprobe 提取大小、时长、码率</small>
- **Multi-threaded** — Configurable thread count for fast processing of large media libraries
  <br><small>可配置线程数，快速处理大量媒体文件</small>
- **Sort & filter** — Sort by name, size, duration, or bitrate; filter by file format
  <br><small>按名称、大小、时长、码率排序；按格式筛选</small>
- **Selection stats** — Check multiple files to see live totals: count, combined duration, combined size
  <br><small>勾选多个文件实时显示总数量、总时长、总大小</small>
- **Export TXT** — Export file list with statistics (name, size, duration, bitrate) as a TXT report
  <br><small>导出文件列表及统计信息（文件名、大小、时长、码率）到 TXT 报表</small>
- **Batch commands** — Built-in presets for x265 CRF, NVENC HEVC, and NVENC H.264; fully customizable
  <br><small>内置转码预设（x265 / NVENC HEVC / NVENC H.264），支持自定义命令和参数</small>
- **Theme** — Dark / Light mode with smooth animated transitions
  <br><small>深色 / 浅色模式，流畅渐变动画过渡</small>
- **Bilingual UI** — Chinese / English interface toggle; preset commands translated on the fly
  <br><small>中英文界面一键切换，预设命令同步翻译</small>
- **Drag-select** — Click and drag to multi-select rows quickly
  <br><small>点击拖拽即可快速批量选择</small>

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/yvgui2004/media-filter.git
cd media-filter

# 2. Install dependencies
pip install -r requirements.txt

# 3. Make sure ffprobe is installed (see Requirements below)

# 4. Run
python 3.py
```

## Requirements

### 1. Python 3.10+

Download from [python.org](https://www.python.org/downloads/) and check **"Add Python to PATH"** during installation.
<br><small>从 [python.org](https://www.python.org/downloads/) 下载，安装时勾选 <strong>"Add Python to PATH"</strong>。</small>

```bash
python --version   # should be ≥ 3.10
```

### 2. CustomTkinter

```bash
pip install -r requirements.txt
```

Or with a mirror (e.g. in China) / 国内镜像加速：

```bash
pip install customtkinter -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. FFmpeg (includes ffprobe)

The app uses `ffprobe` to read media metadata. FFmpeg must be installed and available on your PATH.
<br><small>程序通过 <code>ffprobe</code> 读取媒体元数据，必须先安装 FFmpeg 并加入系统 PATH。</small>

**Windows:**

1. Download [ffmpeg-master-latest-win64-gpl.zip](https://github.com/BtbN/FFmpeg-Builds/releases/latest)
2. Extract to a directory, e.g. `C:\ffmpeg` / 解压到 `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to system PATH / 添加到 PATH：
   - Right-click **This PC** → Properties → Advanced system settings → Environment Variables
     <br><small>右键<strong>"此电脑"</strong> → 属性 → 高级系统设置 → 环境变量</small>
   - Find `Path` in System variables, add `C:\ffmpeg\bin`
     <br><small>在系统变量 <code>Path</code> 中添加 <code>C:\ffmpeg\bin</code></small>
4. Restart the terminal and verify / 重启终端验证：

```bash
ffprobe -version
```

**macOS:**

```bash
brew install ffmpeg
```

**Linux (Debian / Ubuntu):**

```bash
sudo apt install ffmpeg
```

### 4. Verify

```bash
python -c "import customtkinter; print('OK')"
ffprobe -version | head -1
```

## Usage

```bash
python 3.py
```

| Step | Action |
|------|--------|
| 1 | Click **Open Folder** / 点击"选择文件夹" |
| 2 | Sort by name / size / duration, filter by format / 排序、筛选 |
| 3 | Check boxes to select media files / 勾选媒体文件 |
| 4 | Optionally apply a batch command preset / 可选应用批量命令预设 |
| 5 | Copy file paths or execute commands / 复制路径或执行命令 |

## Batch Command Presets

| Preset | Command | Description |
|--------|---------|-------------|
| x265 CRF 23 | `ffmpeg -i input -c:v libx265 -crf 23 ...` | Compress ~75%, CPU encode |
| x265 CRF 26 | `ffmpeg -i input -c:v libx265 -crf 26 ...` | Compress ~85%, CPU encode |
| NVENC HEVC CQ 23 | `ffmpeg -i input -c:v hevc_nvenc -cq 23 ...` | GPU HEVC, high quality |
| NVENC HEVC CQ 26 | `ffmpeg -i input -c:v hevc_nvenc -cq 26 ...` | GPU HEVC, balanced |
| NVENC H.264 | `ffmpeg -i input -c:v h264_nvenc ...` | GPU H.264, max compatibility |

All presets can be customized in the **Batch Command** dialog. / 所有预设可在批量命令对话框中自定义。

## Project Structure

```
media-filter/
├── 3.py              # Main application / 主程序
├── requirements.txt  # Python dependencies / Python 依赖
├── LICENSE           # MIT license / MIT 许可证
└── README.md         # This file / 本文件
```

## License

MIT — feel free to use, modify, and distribute.
