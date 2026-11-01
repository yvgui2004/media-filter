from mediafilter.core import (
    AUDIO_EXTENSIONS,
    DEFAULT_EXTENSIONS,
    VIDEO_EXTENSIONS,
    build_command,
    default_presets,
)


def test_extension_sets_are_nonempty_and_disjoint():
    assert VIDEO_EXTENSIONS and AUDIO_EXTENSIONS
    assert not (VIDEO_EXTENSIONS & AUDIO_EXTENSIONS)
    assert DEFAULT_EXTENSIONS == VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def test_smoke_public_api():
    assert len(default_presets()) >= 5
    assert build_command("x {input} y {output}", "a.mp4", "b.mp4") == "x a.mp4 y b.mp4"