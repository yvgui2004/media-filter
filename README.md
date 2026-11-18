<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="PySide6" src="https://img.shields.io/badge/UI-PySide6%20%2F%20Qt6-41cd52?logo=qt&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

<h1 align="center">mediafilter</h1>

<p align="center">
  <b>EN</b> — A desktop media browser: scan a folder, see every video and audio file with its real metadata, tag it with AI, filter it, and turn a selection into batch FFmpeg commands.<br>
  <b>中文</b> — 桌面端媒体浏览器：扫描一个文件夹，在一张表里看清每个视频、音频的大小、时长和码率，再打标签、筛选，把勾选的文件变成批量 FFmpeg 命令。
</p>

---

## What it does / 它能做什么

**English**

- Recursively scans a folder and reads real metadata with `ffprobe`: size, duration, video and audio bitrate, format, modification time.
- Shows everything in a sortable, filterable table with checkboxes and live totals (file count, total duration, total size).
- **Optional AI tagging** — label videos by what is actually in them: people, screens, food, pets, vehicles, scenery, shot size, technical traits. Run it fully local with YOLOv8n, local-first with a cloud fallback (hybrid), or fully in the cloud. Results are cached per file.
- **Batch FFmpeg** — pick an x265 / NVENC preset, then copy the commands, save them as a `.bat`, or run them in place.
- Format conversion (stream copy or re-encode), TXT report export, light / dark / system themes, Chinese and English UI.

**中文**

- 递归扫描文件夹，用 `ffprobe` 读取真实元数据：大小、时长、音视频码率、格式、修改时间。
- 一张可排序、可筛选的表格，带勾选和实时统计（文件数、总时长、总大小）。
- **可选 AI 内容识别** —— 按画面内容打标签：人物、屏幕、食物、宠物、车辆、场景、景别、技术特征。支持纯本地（YOLOv8n）、本地先筛的混合模式、全云端三种跑法，结果按文件缓存。
- **批量 FFmpeg** —— 选 x265 / NVENC 预设，复制命令、存成 `.bat`，或直接执行。
- 格式转换（流拷贝或重编码）、导出 TXT 清单、浅色 / 深色 / 跟随系统主题、中英文界面。

## Install / 安装

**Source only / 仅源码** — this repository does not ship a prebuilt `.exe`, FFmpeg binaries, or model weights. Set up the environment once with the steps below.

### Requirements / 环境要求

- Windows 10 / 11, 64-bit. The API key is encrypted with Windows DPAPI; other platforms are untested.
- Python 3.10+ (3.13 tested).
- FFmpeg and `ffprobe`.
- Optional: a YOLOv8n ONNX model for local AI tagging.

**中文**：Windows 10/11 64 位（API Key 用 Windows DPAPI 加密，其他平台未验证）；Python 3.10+（3.13 已验证）；FFmpeg 与 `ffprobe`；本地 AI 识别还需要一个 YOLOv8n ONNX 模型（可选）。

### 1. Get the source / 获取源码

```bash
git clone https://github.com/yvgui2004/media-filter.git
cd media-filter
```

Or download **Code → Download ZIP** on GitHub and extract it. / 也可以在 GitHub 页面点 **Code → Download ZIP** 解压。

### 2. Install FFmpeg / 安装 FFmpeg

The app calls `ffprobe` for metadata and `ffmpeg` for AI frame extraction. It looks in `PATH`, then `C:\ffmpeg\bin`, then `C:\Program Files\ffmpeg\bin`.

```powershell
winget install Gyan.FFmpeg
```

If you prefer a portable copy, put `ffmpeg.exe` and `ffprobe.exe` in `C:\ffmpeg\bin`. Open a **new** terminal and check:

```powershell
ffmpeg -version
ffprobe -version
```

**中文**：程序用 `ffprobe` 读元数据、用 `ffmpeg` 抽帧。查找顺序是 `PATH` → `C:\ffmpeg\bin` → `C:\Program Files\ffmpeg\bin`。用 winget 安装，或把两个 exe 放进 `C:\ffmpeg\bin`。装完重开终端验证；已经打开的程序要重启才会重新查找。

### 3. Create a virtual environment / 创建虚拟环境

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
```

Use `py -3.13 -m venv .venv` if you have several Python versions. / 如果装了多个 Python，用 `py -3.13 -m venv .venv` 指定版本。

### 4. Install dependencies / 安装依赖

```powershell
.venv\Scripts\python.exe -m pip install -e ".[ai]"
```

`.[ai]` adds NumPy and ONNX Runtime for local AI. For scanning and cloud tagging only, `pip install -e .` is enough. / `.[ai]` 会装本地 AI 需要的 NumPy 和 ONNX Runtime；只扫描或用云端识别时 `pip install -e .` 就够了。

Mainland China mirror / 国内镜像：

```powershell
.venv\Scripts\python.exe -m pip install -e ".[ai]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 5. Local AI model (optional) / 本地 AI 模型（可选）

Local and hybrid modes need a YOLOv8 detection model. The repository does not include the weights (Ultralytics YOLOv8 is AGPL-3.0). Put a 640×640 ONNX file at `models/yolov8n_fp32.onnx`, or choose another path in **Settings → AI model**.

Export one yourself:

```powershell
.venv\Scripts\python.exe -m pip install ultralytics
.venv\Scripts\python.exe -c "from ultralytics import YOLO; YOLO('yolov8n.pt').export(format='onnx', opset=12)"
move yolov8n.onnx models\yolov8n_fp32.onnx
```

Scanning and cloud-only tagging work without this file. / 纯扫描和全云端识别不需要模型；本地 / 混合模式需要。

### 6. Run / 启动

```powershell
.venv\Scripts\python.exe -m mediafilter
```

Or double-click `run.bat` after step 4. The first launch opens the setup dialog; settings live in `%LOCALAPPDATA%\media-filter-v2\config.json`. / 装完第 4 步后也可以直接双击 `run.bat`。首次启动会打开设置向导，配置保存在 `%LOCALAPPDATA%\media-filter-v2\config.json`。

### Troubleshooting / 常见问题

- **`ffprobe not found`** — FFmpeg is missing or not on `PATH`. Install it, put it in `C:\ffmpeg\bin`, and restart the app. Without it scanning cannot start.
- **`AI model not found`** — the local ONNX file is missing. Set its path in Settings; scanning and cloud tagging still work.
- **Qt platform plugin error** — reinstall PySide6 in the venv (`pip install --force-reinstall PySide6`) and make sure Python is 64-bit.
- **`python` is not recognized** — use the `py` launcher, or reinstall Python with “Add Python to PATH”.
- **Reset settings** — delete `%LOCALAPPDATA%\media-filter-v2\config.json`. This also removes the saved API key and custom labels.

**中文**：

- **提示找不到 `ffprobe`** —— FFmpeg 没装或不在 `PATH`。装好、放进 `C:\ffmpeg\bin`，然后重启程序；没有它扫描无法开始。
- **提示找不到 AI 模型** —— 本地 ONNX 文件不存在。在设置里指定路径即可；扫描和云端识别不受影响。
- **Qt platform plugin 报错** —— 在虚拟环境里重装 PySide6，并确认 Python 是 64 位。
- **`python` 不是内部或外部命令** —— 用 `py` 启动器，或重装 Python 时勾选 “Add Python to PATH”。
- **重置设置** —— 删除 `%LOCALAPPDATA%\media-filter-v2\config.json`（会同时清掉 API Key 和自定义标签）。

### Tests (optional) / 测试（可选）

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev,ai]"
.venv\Scripts\python.exe -m pytest
```

117 pytest cases. / 共 117 个用例。

## How to use / 如何使用

After installation / 安装完成后：

1. **Scan** — click 「打开文件夹」 and choose a folder. The scan runs in the background and can be cancelled. Filter by format, tag or file name; click any column header to sort.
2. **Tag with AI (optional)** — click **AI 识别**. Local mode stays entirely on your machine; hybrid and cloud modes need an API endpoint and key in Settings. The caret next to the button switches mode. Nothing is uploaded before the confirmation card.
3. **Batch commands** — tick the files, open 「批量命令」, choose a preset, then copy, save or run. 「格式转换」 uses the same flow with a container / stream-copy choice.
4. **Settings** — the gear opens default recognition mode, API key (stored only on this machine and masked everywhere), model selection, the 26 built-in tags, custom labels, and sampling / upload options.

Full guide: [使用文档.md](使用文档.md)

**中文**：

1. **扫描** —— 点「打开文件夹」选目录，后台扫描可随时取消；按格式、标签、文件名筛选，点列头排序。
2. **AI 识别（可选）** —— 点 **AI 识别**。本地模式完全在本机推理；混合 / 全云端需要在设置里填接口地址和 Key。按钮右侧箭头切换模式，上传前一定会弹确认卡。
3. **批量命令** —— 勾选文件，打开「批量命令」，选预设后复制命令、存为 `.bat` 或直接执行。「格式转换」是同一流程里的容器与流拷贝选择。
4. **设置** —— 齿轮里可以改默认识别方式、API Key（只存本机、界面与日志全部打码）、模型、26 个内置标签、自定义标签，以及抽帧和上传选项。

## Tech at a glance / 技术一览

**English**

Python 3.10+ with a PySide6 / Qt6 desktop shell (Fusion plus token-driven QSS themes and a model/view table). Scanning calls `ffprobe` from a cancellable thread pool; FFmpeg commands are built as plain data in `core/`, kept apart from the UI. AI tagging is an optional extra: frames are piped from `ffmpeg` into ONNX Runtime with a YOLOv8n model, and cloud modes work with any OpenAI-compatible `/v1/models` endpoint. Config is JSON; the API key is encrypted with Windows DPAPI. 117 pytest cases and a strict pyright pass cover the core logic.

**中文**

Python 3.10+，界面为 PySide6 / Qt6（Fusion + token 驱动的 QSS 主题、model/view 表格）。扫描在可取消的线程池里调用 `ffprobe`；FFmpeg 命令在 `core/` 里以纯数据构建，和界面解耦。AI 识别是可选依赖：`ffmpeg` 管道抽帧，ONNX Runtime 跑 YOLOv8n；抽帧强度在本地和云端共用一套帧数策略。云端模式兼容任意 OpenAI 格式的 `/v1/models` 接口。配置是 JSON，API Key 用 Windows DPAPI 加密。117 个 pytest 用例与严格 pyright 检查覆盖核心逻辑。

## License / 许可

The application source is **MIT** — see [LICENSE](LICENSE).

This repository does not redistribute FFmpeg or YOLOv8 model weights. FFmpeg is a separate dependency under its own license (GPL or LGPL depending on the build); Ultralytics YOLOv8 weights are **AGPL-3.0**. If you redistribute them together with this project, comply with those licenses.

**中文**：应用源码采用 **MIT** 许可，见 [LICENSE](LICENSE)。仓库不再分发 FFmpeg 和 YOLOv8 模型权重：FFmpeg 是独立依赖，按其构建方式适用 GPL 或 LGPL；Ultralytics YOLOv8 权重为 **AGPL-3.0**。如果要随项目一起再分发，请遵守对应许可。