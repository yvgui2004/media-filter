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

**文档：** 中文使用文档 → [使用文档.md](使用文档.md) · [PDF 版](使用文档.pdf)
（PDF 由 `tools/build_doc_pdf.py` 生成，改完 md 后重跑即可）

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
- **AI content tagging** (optional): YOLOv8n on ONNX Runtime labels videos with content tags
  (person / screen / pets / vehicles …), filter the table by tag, cached per file
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

## AI content tagging (optional)

The tagger samples frames with `ffmpeg` (piped, no temp files), runs a YOLOv8n
ONNX model on ONNX Runtime, and writes Chinese content tags back to the table.
Scanning itself never depends on the AI extra — it is enabled by pressing
**AI 识别 / AI Tagging**, and results are cached by file identity + model version.

```bash
pip install -e ".[ai]"          # numpy + onnxruntime
pip install ultralytics         # only needed to export the ONNX model once

python -c "from ultralytics import YOLO; YOLO('yolov8n.pt').export(format='onnx', imgsz=640, opset=17, simplify=True)"
mv yolov8n.onnx models/yolov8n_fp32.onnx
python -m mediafilter
```

Settings live in `config.json` (`ai_model_path`, `ai_sample_frames`, `ai_threads`,
`ai_conf`). An empty `ai_model_path` auto-discovers `<project>/models/*.onnx`.

### Quantization benchmark

`python tools/quantize.py --videos <paths...>` builds INT8 variants and writes
`benchmark.md`. Measured on this machine (AMD64, ORT 1.31, 640×640, 4 threads):

| model | size | median latency | class agreement vs FP32 |
|---|---|---|---|
| FP32 | 12.3 MB | ~10–17 ms | — |
| INT8 dynamic (whole graph) | 3.3 MB | ~19–28 ms | 83% |
| INT8 static QDQ (detection head kept FP32) | 6.0 MB | ~8–17 ms | 94% |

Takeaways: quantizing the whole graph zeroes the classification branch, so the
`/model.22/*` detection head must stay FP32; on an x86 CPU, ONNX Runtime's INT8
kernels save size but not latency — real speedups need an NPU/OpenVINO/TensorRT
backend. Details: [`benchmark.md`](benchmark.md).

## Structure

```
media-filter-ai/
├── pyproject.toml
├── models/                    # *.onnx (not committed; export script below)
├── tools/quantize.py          # ONNX export/quantize + benchmark report
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
│   │   ├── ffmpeg.py          # presets + command building
│   │   ├── tagger.py          # frame sampling + YOLOv8 ONNX inference + tag mapping
│   │   └── tag_cache.py       # tag cache keyed by path/mtime/size/model
│   ├── i18n/                  # JSON locales + Translator
│   └── ui/                    # Qt layer
│       ├── main_window.py
│       ├── table_model.py     # QAbstractTableModel
│       ├── filter_proxy.py    # QSortFilterProxyModel
│       ├── worker.py          # background scan thread
│       ├── tag_worker.py      # background AI tagging (cache + thread pool)
│       ├── stats_bar.py
│       ├── theme.py           # Fusion + QSS palettes
│       └── widgets/           # batch command / format convert dialogs
└── tests/                     # pytest (core + model)
```

## Tests

```bash
.venv/Scripts/python.exe -m pytest -q
```