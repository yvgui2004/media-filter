# Third-party notices / 第三方组件说明

The **software source code** in this repository is licensed under the MIT license
(see `LICENSE`). The **prebuilt portable release** redistributes the components
below; each remains under its own license. If you redistribute the portable
package, keep these notices and comply with the licenses.

本仓库的**源码**采用 MIT 许可（见 `LICENSE`）。**预编译便携包**额外分发下列组件，
它们各自适用自己的许可；再分发便携包时请保留本说明并遵守相应许可。

## FFmpeg

- Component / 组件：`ffmpeg.exe`, `ffprobe.exe` and the shared libraries in
  `ffmpeg\bin` (Windows build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)).
- License / 许可：**GPL-3.0-or-later**.
- Source / 源码：<https://www.ffmpeg.org/download.html>,
  Gyan's build sources: <https://www.gyan.dev/ffmpeg/builds/#sources>.
- The app calls FFmpeg as a separate process; FFmpeg is not linked into
  `MediaFilter.exe`.

## Ultralytics YOLOv8n

- Component / 组件：`models/yolov8n_fp32.onnx` (YOLOv8n weights exported to ONNX).
- License / 许可：**AGPL-3.0**.
- Source / 源码：<https://github.com/ultralytics/ultralytics>.
- Export your own weights with `pip install ultralytics` if you need different
  license terms.

## PySide6 / Qt for Python

- Component / 组件：PySide6 and Qt 6 runtime libraries bundled by PyInstaller.
- License / 许可：**LGPL-3.0** (PySide6 / Qt are used unmodified, dynamically
  loaded, and replaceable inside the frozen application).
- Source / 源码：<https://code.qt.io/cgit/pyside/pyside-setup.git/>,
  <https://www.qt.io/developers>.

## Python and other Python packages

Bundled Python packages keep their own licenses (Python PSF-2.0, NumPy BSD-3-Clause,
ONNX Runtime MIT, platformdirs MIT, send2trash BSD-3-Clause). Their license files
are included in the package metadata under `site-packages`.