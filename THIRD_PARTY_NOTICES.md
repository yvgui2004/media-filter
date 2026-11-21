# Third-party notices / 第三方组件说明

The **software source code** in this repository is licensed under the MIT license
(see `LICENSE`). The **prebuilt portable release** redistributes the components
below; each remains under its own license. If you redistribute the portable
package, keep these notices and comply with the licenses.

本仓库的**源码**采用 MIT 许可（见 `LICENSE`）。**预编译便携包**额外分发下列组件，
它们各自适用自己的许可；再分发便携包时请保留 `LICENSE` 和本说明，并遵守相应许可。
If you redistribute the portable package, keep `LICENSE` and this file with it.

## FFmpeg

- Component / 组件：`ffmpeg.exe`, `ffprobe.exe` and the shared libraries in
  `ffmpeg\bin`. The official CI portable release pins the BtbN FFmpeg-Builds
  asset `ffmpeg-N-129130-gcd39c36377-win64-gpl-shared.zip`; local development
  builds copy whichever FFmpeg build is found on `PATH` (run `ffmpeg -version`
  in the package to see the exact build).
- License / 许可：**GPL-3.0-or-later**.
- Source / 源码：
  - FFmpeg at the exact commit used by the build:
    <https://github.com/FFmpeg/FFmpeg/tree/cd39c36377>
  - Build scripts and dependency recipes:
    <https://github.com/FFmpeg-Builds/FFmpeg-Builds>
  - Pinned build release:
    <https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/tag/autobuild-2026-11-19-12-39>
- The app calls FFmpeg as a separate process; FFmpeg is not linked into
  `MediaFilter.exe`.
- If you need a source archive matching a specific portable release, open an
  issue at <https://github.com/yvgui2004/media-filter/issues>.

## Ultralytics YOLOv8n

- Component / 组件：`models/yolov8n_fp32.onnx` (YOLOv8n weights exported to ONNX).
- License / 许可：**AGPL-3.0**.
- Source / 源码：<https://github.com/ultralytics/ultralytics>.
  License text: <https://www.gnu.org/licenses/agpl-3.0.txt>.
- Export your own weights with `pip install ultralytics` if you need different
  license terms.
- The portable package bundles these weights. If you redistribute it, AGPL-3.0
  obligations apply; for commercial use, obtain a license from Ultralytics or
  replace the model with one under suitable terms.

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