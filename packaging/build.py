"""Build the portable Windows release: one exe + FFmpeg beside it, zipped.

Usage (from the project root):

    .venv\\Scripts\\python.exe packaging\\build.py
    .venv\\Scripts\\python.exe packaging\\build.py --skip-build   # reuse dist\\MediaFilter.exe

FFmpeg is looked up in this order:
    1. %MEDIAFILTER_FFMPEG_DIR%
    2. C:\\ffmpeg\\bin
    3. the folder containing ``ffmpeg`` on PATH

Output:
    release\\MediaFilter-<version>-win64\\   unpacked portable folder
    release\\MediaFilter-<version>-win64.zip  what gets uploaded to GitHub Releases
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
RELEASE = ROOT / "release"
EXE_NAME = "MediaFilter.exe"


def project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("Cannot find version in pyproject.toml")
    return match.group(1)


def find_ffmpeg_dir() -> Path:
    candidates: list[Path] = []
    env = os.environ.get("MEDIAFILTER_FFMPEG_DIR")
    if env:
        candidates.append(Path(env))
    candidates += [Path(r"C:\ffmpeg\bin"), Path(r"C:\Program Files\ffmpeg\bin")]
    on_path = shutil.which("ffmpeg")
    if on_path:
        candidates.append(Path(on_path).resolve().parent)
    for folder in candidates:
        if (folder / "ffmpeg.exe").is_file() and (folder / "ffprobe.exe").is_file():
            return folder
    raise SystemExit(
        "FFmpeg not found. Set MEDIAFILTER_FFMPEG_DIR to a folder containing "
        "ffmpeg.exe and ffprobe.exe (e.g. the Gyan essentials build)."
    )


def run_pyinstaller() -> None:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        str(ROOT / "packaging" / "mediafilter.spec"),
    ]
    print("[build] " + " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def readme_text(version: str) -> str:
    return f"""Media Filter {version} 便携版 / Portable build
=====================================================

快速开始 / Quick start
----------------------
双击 MediaFilter.exe 即可运行。不需要安装 Python，不需要安装 FFmpeg。
Double-click MediaFilter.exe. No Python, no FFmpeg installation needed.

文件夹内容 / What is in this folder
-----------------------------------
  MediaFilter.exe     主程序，内置本地 AI 模型（YOLOv8n fp32）
                      The app, with the local AI model bundled inside.
  ffmpeg\\bin\\          视频探测与抽帧用的 ffmpeg / ffprobe
                      ffmpeg / ffprobe used for probing and frame extraction.
  使用说明.txt         本文件 / this file

请保持 ffmpeg 文件夹与 MediaFilter.exe 的相对位置不变，不要单独移动 exe。
Keep the ffmpeg folder next to MediaFilter.exe; do not move the exe alone.

环境要求 / Requirements
-----------------------
Windows 10 / 11，64 位。首次启动约 1-3 秒（单文件程序要先解压自身；
机械盘或杀软实时扫描时会慢一些）。

配置 / Configuration
--------------------
配置保存在 %LOCALAPPDATA%\\media-filter-v2\\config.json。
运行日志在同目录的 mediafilter.log（循环保存，便于反馈问题）。
云端识别需要在「设置」里填写 API Key（用 Windows DPAPI 加密保存）。
AI 模型已内置，无需额外下载；如需更换模型，在「设置 → AI 模型」里指定。

本地 AI 模型说明 / Model license
--------------------------------
内置的 YOLOv8n 权重源自 Ultralytics，采用 AGPL-3.0 许可。
Bundled YOLOv8n weights derive from Ultralytics and are licensed AGPL-3.0.

项目主页 / Project
------------------
https://github.com/yvgui2004/media-filter
"""


def assemble(version: str) -> Path:
    exe = DIST / EXE_NAME
    if not exe.is_file():
        raise SystemExit(f"{exe} not found. Run without --skip-build first.")

    folder = RELEASE / f"MediaFilter-{version}-win64"
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "ffmpeg" / "bin").mkdir(parents=True)

    shutil.copy2(exe, folder / EXE_NAME)
    ffmpeg_dir = find_ffmpeg_dir()
    # Shared builds need their DLLs beside the exes; static builds only have
    # the two executables. Copy everything except the unused ffplay.
    for item in ffmpeg_dir.iterdir():
        if item.is_file() and item.name.lower() != "ffplay.exe":
            shutil.copy2(item, folder / "ffmpeg" / "bin" / item.name)
    for name in ("LICENSE.txt", "LICENSE"):
        license_file = ffmpeg_dir.parent / name
        if license_file.is_file():
            shutil.copy2(license_file, folder / "ffmpeg" / name)
            break
    (folder / "使用说明.txt").write_text(readme_text(version), encoding="utf-8")
    return folder


def make_zip(folder: Path) -> Path:
    # ``folder.name`` ends in "-win64", which Path.with_suffix would treat as
    # a suffix and truncate ("MediaFilter-0.1.zip"). Append explicitly.
    archive = folder.parent / (folder.name + ".zip")
    if archive.exists():
        archive.unlink()
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    print(f"[zip] {len(files)} files, {total / 1_048_576:.1f} MiB -> {archive.name}")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in files:
            zf.write(path, path.relative_to(folder.parent))
            print(f"      + {path.relative_to(folder)}")
    return archive


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="reuse dist\\MediaFilter.exe")
    parser.add_argument("--no-zip", action="store_true", help="assemble the folder only")
    args = parser.parse_args()

    version = project_version()
    if not args.skip_build:
        run_pyinstaller()
    folder = assemble(version)
    print(f"[ok] {folder}")
    if not args.no_zip:
        archive = make_zip(folder)
        print(f"[ok] {archive}")
        print(f"[sha256] {sha256(archive)}  {archive.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())