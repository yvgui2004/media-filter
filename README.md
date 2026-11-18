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

## How to use / 如何使用

**English**

1. Install Python 3.10+ and put `ffmpeg` on `PATH` — it provides `ffprobe`.
2. Install and launch:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   pip install -e .
   python -m mediafilter
   ```

3. **Scan** — click 「打开文件夹」 and choose a folder. The scan runs in the background and can be cancelled. Filter by format, tag or file name; click any column header to sort.
4. **Tag with AI (optional)** — click **AI 识别**. Local mode stays entirely on your machine; hybrid and cloud modes need an API endpoint and key in Settings. The caret next to the button switches mode. Nothing is uploaded before the confirmation card.
5. **Batch commands** — tick the files, open 「批量命令」, choose a preset, then copy, save or run. 「格式转换」 uses the same flow with a container / stream-copy choice.
6. **Settings** — the gear opens default recognition mode, API key (stored only on this machine and masked everywhere), model selection, the 26 built-in tags, custom labels, and sampling / upload options.

Full guide: [使用文档.md](使用文档.md) · [使用文档.pdf](使用文档.pdf)

**中文**

1. 安装 Python 3.10+，把 `ffmpeg`（自带 `ffprobe`）放进 `PATH`。
2. 安装并启动：命令同上。
3. **扫描** —— 点「打开文件夹」选目录，后台扫描可随时取消；按格式、标签、文件名筛选，点列头排序。
4. **AI 识别（可选）** —— 点 **AI 识别**。本地模式完全在本机推理；混合 / 全云端需要在设置里填接口地址和 Key。按钮右侧箭头切换模式，上传前一定会弹确认卡。
5. **批量命令** —— 勾选文件，打开「批量命令」，选预设后复制命令、存为 `.bat` 或直接执行。「格式转换」是同一流程里的容器与流拷贝选择。
6. **设置** —— 齿轮里可以改默认识别方式、API Key（只存本机、界面与日志全部打码）、模型、26 个内置标签、自定义标签，以及抽帧和上传选项。

## Tech at a glance / 技术一览

**English**

Python 3.10+ with a PySide6 / Qt6 desktop shell (Fusion plus token-driven QSS themes and a model/view table). Scanning calls `ffprobe` from a cancellable thread pool; FFmpeg commands are built as plain data in `core/`, kept apart from the UI. AI tagging is an optional extra: frames are piped from `ffmpeg` into ONNX Runtime with a YOLOv8n model, and cloud modes work with any OpenAI-compatible `/v1/models` endpoint. Config is JSON; the API key is encrypted with Windows DPAPI. 85 pytest cases and a strict pyright pass cover the core logic.

**中文**

Python 3.10+，界面为 PySide6 / Qt6（Fusion + token 驱动的 QSS 主题、model/view 表格）。扫描在可取消的线程池里调用 `ffprobe`；FFmpeg 命令在 `core/` 里以纯数据构建，和界面解耦。AI 识别是可选依赖：`ffmpeg` 管道抽帧，ONNX Runtime 跑 YOLOv8n；云端模式兼容任意 OpenAI 格式的 `/v1/models` 接口。配置是 JSON，API Key 用 Windows DPAPI 加密。85 个 pytest 用例与严格 pyright 检查覆盖核心逻辑。

## License / 许可

MIT — see [LICENSE](LICENSE).