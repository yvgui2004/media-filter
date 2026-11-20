# Contributing / 参与贡献

Thanks for taking the time to help. Bug reports, translations, presets and small
fixes are all welcome. / 欢迎报 bug、补翻译、加预设或直接提交修复。

## Before you start / 开始之前

- **Bugs** — open an issue with the app version, Windows version, and the tail of
  `%LOCALAPPDATA%\media-filter-v2\mediafilter.log`. Redact anything sensitive;
  API keys are already masked by the app.
- **Features** — open an issue first for anything larger than a small fix, so we
  can agree on scope before you write code.
- **Security** — do **not** open a public issue. See [SECURITY.md](SECURITY.md).

## Development setup / 开发环境

```powershell
git clone https://github.com/yvgui2004/media-filter.git
cd media-filter
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,ai]"
```

FFmpeg / `ffprobe` must be on `PATH` (or in `C:\ffmpeg\bin`). Local AI tagging also
needs `models/yolov8n_fp32.onnx`; scanning and cloud tagging work without it.

## Checks before a PR / 提交前检查

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m pyright
```

Both are required: CI runs the same two commands on `windows-latest`. Tests run
headless (`QT_QPA_PLATFORM=offscreen`).

## Code layout / 代码结构

- `src/mediafilter/core/` — no Qt. Probing, scanning, FFmpeg command building,
  tagging, cloud client, cache, secret storage.
- `src/mediafilter/ui/` — Qt widgets, models and worker threads. Keep command
  construction and business rules in `core/`.
- `src/mediafilter/i18n/locales/zh.json` / `en.json` — every key must exist in
  both files; the UI falls back to English when a key is missing.
- `tests/` — one module per core feature; UI tests use the offscreen platform.

Please keep new user-facing strings in both locales, and add a test for logic you
change. Conventional, descriptive commit subjects are appreciated ("Fix batch
quoting for paths with spaces", not "fix").

## Translations / 翻译

The Chinese and English locales are maintained side by side. If you add a
language, mirror `en.json` and wire it into `src/mediafilter/i18n/`.