<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-41cd52?style=flat&logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

<h1 align="center">Media Filter v2</h1>

<p align="center">A rewrite of the original <code>media-filter</code> tool: a desktop GUI for scanning
media folders (video + audio), reading metadata with <code>ffprobe</code>, and generating batch
FFmpeg commands.<br>
<small>桌面端媒体文件扫描统计工具：递归扫描视频/音频，ffprobe 提取时长/码率，批量生成 FFmpeg 转码命令。</small></p>

---

## Why a rewrite?

The original (Python + CustomTkinter + `ttk.Treeview`) works, but had three structural problems:

1. **A 2400-line god class** (`VideoInfoApp`) mixing scanning, ffprobe parsing, formatting,
   theming, i18n and layout.
2. **`ttk.Treeview` does not virtualize** — large libraries get slow because every row is a
   real widget.
3. **Logic and UI were inseparable**, so nothing was testable without opening the window.

This version keeps the language (Python is the right choice — the real work happens inside the
external `ffprobe`/`ffmpeg` binaries) but replaces the UI with **Qt's model/view** and splits the
code into a pure, unit-tested `core/` and a thin Qt `ui/`.

## Features

- Recursive folder scan, `ffprobe` metadata (size / duration / video+audio bitrate)
- Multi-threaded probing with progress + cancel
- Sortable (click headers) and filterable (by format, by name search) virtualized table
- Checkbox selection with live totals (count / duration / size)
- Export TXT report
- Batch FFmpeg presets (x265 CRF 23/26, NVENC HEVC CQ 23/26, NVENC H.264, NVENC AV1) — copy, save `.bat`, or run
- Stream-copy / re-encode format conversion
- Dark / light / system theme, Chinese / English UI
- Config + window geometry persisted under the user config directory

## Quick start

```bash
# ffmpeg must be on PATH (provides ffprobe)

python -m venv .venv
.venv/Scripts/activate        # Windows (Git Bash: source .venv/Scripts/activate)
pip install -e .
python -m mediafilter
```

## Structure

```
media-filter-v2/
├── pyproject.toml
├── src/mediafilter/
│   ├── __main__.py            # entry point
│   ├── app.py                 # Qt bootstrap (config + translator + theme)
│   ├── config.py              # dataclass config -> platformdirs JSON
│   ├── export.py              # TXT report
│   ├── core/                  # pure logic, no Qt
│   │   ├── models.py          # MediaMetadata / FileRecord
│   │   ├── formats.py         # size / duration / bitrate formatting
│   │   ├── scanner.py         # os.walk + extension filter
│   │   ├── probe.py           # ffprobe wrapper + JSON parsing
│   │   ├── pool.py            # ThreadPoolExecutor orchestration
│   │   └── ffmpeg.py          # presets + command building
│   ├── i18n/                  # JSON locales + Translator
│   └── ui/                    # Qt layer
│       ├── main_window.py
│       ├── table_model.py     # QAbstractTableModel
│       ├── filter_proxy.py    # QSortFilterProxyModel
│       ├── worker.py          # background scan thread
│       ├── stats_bar.py
│       ├── theme.py           # Fusion + QSS palettes
│       └── widgets/           # batch command / format convert dialogs
└── tests/                     # pytest (core + model)
```

## Tests

```bash
.venv/Scripts/python.exe -m pytest -q
```