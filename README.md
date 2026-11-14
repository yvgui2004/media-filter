<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-41cd52?style=flat&logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

<h1 align="center">Media Filter v2</h1>

<p align="center">
A rewrite of the original <code>media-filter</code>: a desktop GUI that scans media folders (video + audio), reads metadata with <code>ffprobe</code>, and generates batch FFmpeg commands.<br>
原版 <code>media-filter</code> 的重写版：桌面端媒体扫描工具，递归读取视频/音频的时长、码率等元数据，批量生成 FFmpeg 转码命令。<br>
<small>中文文档 → <a href="使用文档.md">使用文档.md</a> · <a href="使用文档.pdf">PDF</a></small></p>

---

## Why a rewrite? / 为什么重写

The original (Python + CustomTkinter + `ttk.Treeview`) worked, but had three structural problems:

> 原版（Python + CustomTkinter + `ttk.Treeview`）能用，但有三个结构性问题：

| # | Problem | 问题 |
|---|---|---|
| 1 | **A 2400-line god class** (`VideoInfoApp`) mixing scanning, ffprobe parsing, formatting, theming, i18n and layout | **2400 行的上帝类**（`VideoInfoApp`），把扫描、ffprobe 解析、格式化、主题、i18n、布局全揉在一起 |
| 2 | **`ttk.Treeview` does not virtualize** — large libraries get slow because every row is a real widget | **`ttk.Treeview` 不做虚拟化**，每一行都是真实控件，文件一多就卡 |
| 3 | **Logic and UI were inseparable**, so nothing was testable without opening the window | **逻辑和界面绑死**，不开窗口就什么都测不了 |

This version keeps Python (the real work happens inside the external `ffprobe` / `ffmpeg` binaries) but replaces the UI with **Qt's model/view** and splits the code into a pure, unit-tested `core/` and a thin Qt `ui/`.

> 这一版仍然用 Python（真正干活的是外部 `ffprobe` / `ffmpeg`），但界面换成 **Qt 的 model/view**，代码拆成纯逻辑、可单测的 `core/` 和薄薄一层 Qt `ui/`。

## Features / 功能

| Feature | 功能 |
|---|---|
| Recursive folder scan; `ffprobe` metadata (size / duration / video + audio bitrate) | 递归扫描文件夹；`ffprobe` 读取大小 / 时长 / 音视频码率 |
| Multi-threaded probing with progress + cancel | 多线程探测，带进度和取消 |
| Sortable and filterable (format / name / tag) virtualized table | 可排序、可筛选（格式 / 文件名 / 标签）的虚拟化表格 |
| Checkbox selection with live totals (count / duration / size) | 勾选文件并实时统计数量 / 总时长 / 总大小 |
| Export TXT report | 导出 TXT 报告 |
| Batch FFmpeg presets (x265 CRF 23/26, NVENC HEVC CQ 23/26, NVENC H.264, NVENC AV1) — copy, save `.bat`, or run | FFmpeg 批量预设（x265 CRF 23/26、NVENC HEVC CQ 23/26、NVENC H.264、NVENC AV1），可复制、存为 `.bat` 或直接执行 |
| Stream-copy / re-encode format conversion | 流拷贝 / 重编码格式转换 |
| **AI content tagging** (optional): YOLOv8n on ONNX Runtime labels videos (person / screen / pets / vehicles …), filter by tag, cached per file | **AI 内容识别**（可选）：ONNX Runtime 跑 YOLOv8n，给视频打内容标签（人物 / 屏幕 / 宠物 / 车辆……），支持按标签筛选，按文件缓存 |
| Dark / light / system theme, Chinese / English UI | 深色 / 浅色 / 跟随系统主题，中英文界面 |
| Config + window geometry persisted | 配置和窗口位置持久化 |

## Quick start / 快速开始

`ffmpeg` must be on PATH — it provides `ffprobe`.

> `ffmpeg` 需要在 PATH 里，`ffprobe` 由它提供。

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows (Git Bash: source .venv/Scripts/activate) / Windows 激活虚拟环境
pip install -e .
python -m mediafilter
```

## AI content tagging (optional) / AI 内容识别（可选）

The tagger samples frames with `ffmpeg` (piped, no temp files), runs a YOLOv8n ONNX model on ONNX Runtime, and writes Chinese content tags back to the table. Scanning never depends on the AI extra: tagging starts from **AI 识别 / AI Tagging**, and results are cached by file identity + model version.

> 抽帧通过 `ffmpeg` 管道完成，不落临时文件；YOLOv8n ONNX 模型在 ONNX Runtime 上推理，结果以中文标签写回表格。扫描本身不依赖 AI 依赖包，点「AI 识别」才开始，结果按「文件 + 模型版本」缓存。

```bash
pip install -e ".[ai]"          # numpy + onnxruntime
pip install ultralytics         # only needed to export the ONNX model once / 只在导出模型时需要

python -c "from ultralytics import YOLO; YOLO('yolov8n.pt').export(format='onnx', imgsz=640, opset=17, simplify=True)"
mv yolov8n.onnx models/yolov8n_fp32.onnx
python -m mediafilter
```

Settings live in `config.json` (`ai_model_path`, `ai_sample_frames`, `ai_threads`, `ai_conf`); an empty `ai_model_path` auto-discovers `<project>/models/*.onnx`.

> 配置在 `config.json`：`ai_model_path`、`ai_sample_frames`、`ai_threads`、`ai_conf`；`ai_model_path` 留空时自动查找 `<project>/models/*.onnx`。

### Quantization benchmark / 量化实测

`python tools/quantize.py --videos <paths...>` builds INT8 variants and writes `benchmark.md`. Measured on this machine (AMD64, ORT 1.31, 640×640, 4 threads):

> `python tools/quantize.py --videos <paths...>` 生成 INT8 模型变体并写出 `benchmark.md`。本机实测（AMD64、ORT 1.31、640×640、4 线程）：

| Model / 模型 | Size / 体积 | Median latency / 中位延迟 | Class agreement / 类别一致率 |
|---|---|---|---|
| FP32 | 12.3 MB | ~10–17 ms | — |
| INT8 dynamic (whole graph) / 动态（全图） | 3.3 MB | ~19–28 ms | 83% |
| INT8 static QDQ (detection head kept FP32) / 静态 QDQ（检测头 FP32） | 6.0 MB | ~8–17 ms | 94% |

Takeaways: quantizing the whole graph zeroes the classification branch, so the `/model.22/*` detection head must stay FP32; on an x86 CPU, ONNX Runtime's INT8 kernels save size but not latency — real speedups need an NPU / OpenVINO / TensorRT backend. Details: [`benchmark.md`](benchmark.md).

> 结论：整图量化会把分类分支输出清零，所以检测头 `/model.22/*` 必须保留 FP32；在 x86 CPU 上，ONNX Runtime 的 INT8 内核只省体积、不提速，真要提速得靠 NPU / OpenVINO / TensorRT。详见 [`benchmark.md`](benchmark.md)。

## Structure / 目录结构

```
media-filter-ai/
├── pyproject.toml
├── models/                    # *.onnx, not committed / 模型，不入库
├── tools/quantize.py          # export + quantize + benchmark / 导出量化评测
├── tools/build_doc_pdf.py     # usage doc -> PDF / 使用文档转 PDF
├── src/mediafilter/
│   ├── __main__.py            # entry point / 启动入口
│   ├── app.py                 # Qt bootstrap (config + i18n + theme) / Qt 启动
│   ├── config.py              # dataclass config -> platformdirs JSON / 配置读写
│   ├── export.py              # TXT report / TXT 报告
│   ├── core/                  # pure logic, no Qt / 纯逻辑，无 Qt
│   │   ├── models.py          # MediaMetadata / FileRecord
│   │   ├── formats.py         # size / duration / bitrate formatting / 格式化
│   │   ├── scanner.py         # os.walk + extension filter / 目录遍历
│   │   ├── probe.py           # ffprobe wrapper + JSON parsing / ffprobe 封装
│   │   ├── pool.py            # ThreadPoolExecutor orchestration / 扫描线程池
│   │   ├── ffmpeg.py          # presets + command building / 预设与命令生成
│   │   ├── tagger.py          # frame sampling + YOLOv8 inference + tag mapping / 抽帧与推理
│   │   └── tag_cache.py       # cache keyed by path/mtime/size/model / 标签缓存
│   ├── i18n/                  # JSON locales + Translator / 多语言
│   └── ui/                    # Qt layer / Qt 界面层
│       ├── main_window.py
│       ├── table_model.py     # QAbstractTableModel
│       ├── filter_proxy.py    # QSortFilterProxyModel
│       ├── worker.py          # background scan thread / 扫描线程
│       ├── tag_worker.py      # background AI tagging / AI 识别线程
│       ├── stats_bar.py
│       ├── theme.py           # Fusion + QSS palettes / 主题
│       └── widgets/           # batch command / format convert dialogs / 对话框
└── tests/                     # pytest (core + model) / 单元测试
```

## Tests / 测试

```bash
.venv/Scripts/python.exe -m pytest -q
```

38 cases cover formatting, ffprobe parsing, scanning, command presets, pool cancellation, frame sampling, tag voting, YOLO output decoding, tag cache and the table/proxy models.

> 38 个用例，覆盖格式化、ffprobe 解析、扫描、命令预设、线程池取消、抽帧时间点、标签投票、YOLO 输出解码、标签缓存以及表格 / 筛选模型。

## License / 许可

MIT — see [LICENSE](LICENSE).

> MIT，见 [LICENSE](LICENSE)。