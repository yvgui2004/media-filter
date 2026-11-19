# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the portable Windows build.

The build script in this folder (``build.py``) drives PyInstaller with this
spec, then assembles the release zip. Run it with the project virtualenv:

    .venv\\Scripts\\python.exe packaging\\build.py

The app is packaged as onefile (a single ``MediaFilter.exe``) but FFmpeg stays
outside the executable, next to it. Extracting ~200 MB of FFmpeg on every
launch would add 10-20 s to start-up; keeping it in ``ffmpeg/bin`` beside the
exe costs nothing and ``probe.py`` finds it there.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

datas = [
    (str(SRC / "mediafilter" / "i18n" / "locales"), "mediafilter/i18n/locales"),
    (str(SRC / "mediafilter" / "assets"), "mediafilter/assets"),
]

# Local AI model: config.py/tagger.py look in <bundle>/models first.
model = ROOT / "models" / "yolov8n_fp32.onnx"
if model.is_file():
    datas.append((str(model), "models"))

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Not imported anywhere in the app; the PySide6 wheel ships them all.
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DRender",
        "PySide6.QtBluetooth",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtGraphs",
        "PySide6.QtLocation",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtNetworkAuth",
        "PySide6.QtNfc",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickControls2",
        "PySide6.QtQuickWidgets",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtSensors",
        "PySide6.QtSerialBus",
        "PySide6.QtSerialPort",
        "PySide6.QtSql",
        "PySide6.QtStateMachine",
        "PySide6.QtTest",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebSockets",
        "tkinter",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MediaFilter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(SRC / "mediafilter" / "assets" / "app_icon.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
)