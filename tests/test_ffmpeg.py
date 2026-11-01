from mediafilter.core.ffmpeg import (
    build_command,
    build_output_path,
    default_presets,
)


def test_build_command_substitutes_placeholders():
    tpl = 'ffmpeg -i "{input}" -c:v libx265 "{output}"'
    assert build_command(tpl, "in.mkv", "out.mp4") == (
        'ffmpeg -i "in.mkv" -c:v libx265 "out.mp4"'
    )


def test_build_output_path_keeps_container_by_default():
    assert build_output_path("C:/videos/movie.mkv", "_x265") == (
        __import__("pathlib").Path("C:/videos/movie_x265.mkv")
    )


def test_build_output_path_overrides_extension():
    out = build_output_path("C:/videos/movie.mkv", "_x265", ".mp4")
    assert out.name == "movie_x265.mp4"


def test_default_presets_are_well_formed():
    presets = default_presets()
    keys = {p.key for p in presets}
    assert {"x265_crf23", "x265_crf26", "nvenc_hevc_cq23",
            "nvenc_hevc_cq26", "nvenc_h264", "nvenc_av1"} <= keys
    for p in presets:
        assert "{input}" in p.template and "{output}" in p.template