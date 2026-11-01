"""FFmpeg command templates and command building.

Templates use ``{input}`` and ``{output}`` placeholders; the UI substitutes
real paths at generation time, so templates stay path-independent and are
safe to persist in config.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Preset:
    key: str                 # stable internal id
    template: str            # ffmpeg command with {input}/{output}
    name: str                # default display name (localized by UI where possible)
    description: str = ""


def default_presets() -> list[Preset]:
    return [
        Preset(
            "x265_crf23",
            'ffmpeg -hwaccel auto -i "{input}" -c:v libx265 -crf 23 -preset medium '
            '-c:a aac -b:a 96k -movflags +faststart "{output}"',
            "x265 CRF 23",
            "H.265 (CPU) · high quality · ~75% smaller, no GPU needed but slower",
        ),
        Preset(
            "x265_crf26",
            'ffmpeg -hwaccel auto -i "{input}" -c:v libx265 -crf 26 -preset medium '
            '-c:a aac -b:a 96k -movflags +faststart "{output}"',
            "x265 CRF 26",
            "H.265 (CPU) · good quality · ~85% smaller, smallest output but slowest",
        ),
        Preset(
            "nvenc_hevc_cq23",
            'ffmpeg -hwaccel cuda -i "{input}" -c:v hevc_nvenc -cq 23 -rc vbr '
            '-c:a aac -b:a 96k -movflags +faststart "{output}"',
            "NVENC HEVC CQ 23",
            "H.265 (NVIDIA GPU) · high quality · fast, needs an NVIDIA card",
        ),
        Preset(
            "nvenc_hevc_cq26",
            'ffmpeg -hwaccel cuda -i "{input}" -c:v hevc_nvenc -preset p7 -tune hq '
            '-rc vbr -cq 26 -qmin 20 -qmax 32 -c:a aac -b:a 96k '
            '-movflags +faststart "{output}"',
            "NVENC HEVC CQ 26",
            "H.265 (NVIDIA GPU) · good quality · smaller output, fast, needs an NVIDIA card",
        ),
        Preset(
            "nvenc_h264",
            'ffmpeg -hwaccel cuda -i "{input}" -c:v h264_nvenc -preset p7 -tune hq '
            '-rc vbr -cq 23 -c:a aac -b:a 96k -movflags +faststart "{output}"',
            "NVENC H.264",
            "H.264 (NVIDIA GPU) · best compatibility · fast, needs an NVIDIA card; larger than H.265",
        ),
        Preset(
            "nvenc_av1",
            'ffmpeg -hwaccel cuda -i "{input}" -c:v av1_nvenc -preset p7 -rc constqp '
            '-qp 30 -c:a aac -b:a 96k -movflags +faststart "{output}"',
            "NVENC AV1",
            "AV1 (NVIDIA GPU, RTX 40/50) · best compression, smallest output, fast",
        ),
    ]


def build_command(template: str, input_path: str | Path, output_path: str | Path) -> str:
    """Substitute placeholders into a template."""
    return template.replace("{input}", str(input_path)).replace("{output}", str(output_path))


def build_output_path(
    input_path: str | Path,
    suffix: str = "_out",
    extension: str | None = None,
) -> Path:
    """Derive an output path next to the input file.

    ``extension`` is a container extension (with or without the dot); when
    omitted the original container is kept.
    """
    path = Path(input_path)
    ext = (extension or path.suffix).lstrip(".")
    return path.with_name(f"{path.stem}{suffix}.{ext}")