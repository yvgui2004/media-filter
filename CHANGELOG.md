# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Ticking is now the table's only persistent selection state. Clicking a row
  ticks it; dragging shows a transient preview (blue for tick, a dashed
  outline for untick), commits on release and clears the highlight. Batch
  processing and export use ticks only, show the tick count, and are disabled
  when nothing is ticked.
- The AI mode popover now lands from the caret with a 170ms rise, three cards
  fading in 20ms apart and the 8-cell upload strips sweeping in lockstep.
  Picking a mode pulses the chosen card, swaps the mode word with a fade and
  retracts in 100ms after a short confirmation beat; the caret rotates
  instead of swapping icons. The hybrid-without-labels warning unfolds by
  height instead of popping the menu taller.
- The context menu acts on the row under the cursor without changing ticks;
  "Clear Ticks" clears every tick, including files hidden by filters.
- Portable packages now include `LICENSE` and `THIRD_PARTY_NOTICES.md`; the
  FFmpeg notice names the pinned BtbN build and links its exact source commit
  and build scripts.
- README now lists the 8 local YOLOv8n tags explicitly and marks scene,
  shot-size and technical tags as cloud-only.

### Fixed

- The AI mode popover now matches the design prototype's layout: 73px cards,
  a 35px header with the legend packed at the prototype's 5px gaps, a 24px
  warning row instead of 36px, full-height scope strips, the sliders icon and
  12px chevrons in the footer, and the prototype's wording (本地, 仅匹配,
  回退本地).
- The batch dialog's 高级选项 row could not be opened: the click target was an
  empty layout beside the actual disclosure row, so it had no size and never
  received a click. The row now wraps the line, chevron, title and summary and
  responds to mouse and keyboard.
- The portable build's version resource was still 0.1.0; it now reports 0.2.0.

## [0.2.0] — 2026-11-21

GPU-accelerated tagging and one batch-processing dialog.

### Added

- **GPU inference on Windows.** Local tagging now uses ONNX Runtime DirectML, so
  NVIDIA, AMD and Intel GPUs all accelerate the same YOLOv8n model. Advanced
  settings offers Auto / CPU / GPU, lists the detected adapter, skips the WARP
  software renderer, and falls back to CPU if the DirectML session fails.
- **Local colour tags for cats, dogs and cars.** A detected animal or vehicle
  also gets a colour prefix (`黑猫`, `白狗`, `白车`) sampled on this PC: the
  detection box is cropped to the animal centre or vehicle body band, converted
  to HSV with NumPy (no OpenCV), and voted across frames so a single odd frame
  cannot decide the result. Advanced settings has a "sample colour tags locally"
  switch (on by default); cloud-only mode disables it. Cache keys include whether
  colour sampling is on and the palette version, so toggling it re-tags instead
  of serving stale labels.
- Settings mode cards drop the radio dot; the accent border marks the selection.
  The first-run cards keep the dot.
- Tag-triggered release workflow: pushing `v*` runs tests and pyright, downloads
  the pinned FFmpeg and model inputs (SHA-256 verified), builds the portable
  zip, publishes the Release with notes and a `.sha256` file, and optionally
  opens the winget update PR. A manual dry run keeps the zip as an artifact.
- The YOLOv8n ONNX weights are published as a pinned `model-v1` release asset so
  CI builds are reproducible without committing binaries.
- **One batch-processing entry.** The separate batch-command and format-convert
  toolbar buttons are merged into a single 批量处理 dialog with three task cards
  (fast convert, compress, custom FFmpeg). It builds per-file commands for
  x265 / x264, NVIDIA NVENC and AMD AMF with a CPU fallback, plans collision-safe
  output paths, previews the exact commands, shows overall and per-file
  progress, and summarises successes, failures and size savings.

### Fixed

- Switching tasks in the batch dialog resets the form to the top instead of
  leaving it scrolled halfway down the previous task.
- The advanced-options summary line hides while the panel is expanded.
- The hover row lookup in `select_field.py` is narrowed for pyright.

## [0.1.1] — 2026-11-20

Reliability release: every fix below came from reproducing the issue against a
real FFmpeg build on Windows.

### Fixed

- **Batch commands with spaces in the path.** Windows was launched through
  `shlex.split(posix=False)`, which kept the literal quotes and made FFmpeg fail
  with "Error opening input". Commands now go to `Popen` as a string on Windows,
  and `%` is escaped correctly in generated `.bat` files.
- **Silent batch failures.** Running a batch now reports succeeded / failed
  counts and the tail of each failure's stderr, and cancelling stops after the
  current file instead of racing through the rest.
- **Slow scan cancel.** Cancelling a scan now kills the running `ffprobe`
  instead of waiting for the timeout (measured 0.46 s instead of ~5 s).
- **Audio files shown as failed AI targets.** An audio-only file no longer gets
  an invented video bitrate or enters AI tagging; it shows `—` for tags.
- **Table rows after deletion.** `remove_rows` rebuilt the path → row index so
  later edits and selections act on the right file.
- **Window close during work.** `closeEvent` cancels and joins the scan / tag
  workers, with a logged fallback terminate.
- **Tag palette drift.** The local model now only emits the 8 built-in tags it
  can actually recognise; scene / shot / technical tags stay cloud-only. Cache
  keys include the enabled tag set, so changing the palette re-tags instead of
  serving stale results.
- **Cloud endpoint hard-coded to localhost.** Removed; endpoints are read from
  settings. Requests retry once without `reasoning_effort` when an
  OpenAI-compatible server rejects it with HTTP 400.
- **Deleting to the Recycle Bin without `send2trash`.** The app now explains the
  missing dependency instead of deleting in place, and only removes rows that
  were actually deleted.
- **Filter refresh on newer Qt.** Uses `beginFilterChange` / `endFilterChange`
  with an `invalidateFilter` fallback.

### Added

- Rotating log at `%LOCALAPPDATA%\media-filter-v2\mediafilter.log` (1 MB × 3)
  plus hooks for uncaught exceptions in the main thread and in workers.
- `python -m mediafilter [folder]` scans a folder on launch; the frozen
  `MediaFilter.exe <folder>` does the same.
- `docs/screenshots/` with light, dark, batch and settings captures and a demo
  GIF, generated from the real widgets by `scripts/capture_screenshots.py` and
  `scripts/capture_gif.py`.
- GitHub Actions CI (Windows): pytest + pyright on every push and pull request.
- `THIRD_PARTY_NOTICES.md` covering FFmpeg (GPL-3.0), YOLOv8 (AGPL-3.0) and
  PySide6 / Qt (LGPL-3.0); LICENSE now names the copyright holder.
- `pyrightconfig.json` is portable and tracked; `pyright` is part of the `dev`
  extra.
- Landing page source at `docs/index.html` (GitHub Pages).

### Changed

- Test suite grew from 117 to 128 cases; pyright reports zero errors.
- README: new hero with demo GIF, direct download button, log path, local vs
  cloud tag coverage, and development / CI notes.
- `使用文档.md` and the portable package note now use `%LOCALAPPDATA%` for the
  config path and document the log file.
- Removed the unused local "color tag" setting from the settings dialog and
  config.

## [0.1.0] — 2026-11-19

First public release.

### Added

- Recursive folder scan with real `ffprobe` metadata (size, duration, video /
  audio bitrate, format, modification time).
- Sortable / filterable table with checkboxes, live totals, TXT export.
- AI tagging: local YOLOv8n (ONNX Runtime), hybrid local-first + cloud, and
  cloud-only modes, with per-file caching and 26 built-in tags.
- Batch FFmpeg command generation (x265 / NVENC presets), copy / save `.bat` /
  run, plus format conversion (stream copy or re-encode).
- Light / dark / system themes, Chinese and English UI.
- Portable Windows build with Python, FFmpeg and the model bundled.