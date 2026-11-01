from mediafilter.core.formats import (
    format_bitrate,
    format_duration,
    format_size,
    parse_size_to_bytes,
)


def test_format_duration():
    assert format_duration(0) == "0:00"
    assert format_duration(65) == "1:05"
    assert format_duration(3661) == "1:01:01"
    assert format_duration(2 * 3600 + 9) == "2:00:09"


def test_format_size():
    assert format_size(0) == "0 B"
    assert format_size(1024) == "1.00 KB"
    assert format_size(2.5 * 1024 ** 3) == "2.50 GB"


def test_format_bitrate():
    assert format_bitrate(0) == ""
    assert format_bitrate(-5) == ""
    assert format_bitrate(800) == "800 bps"
    assert format_bitrate(128_000) == "128 kbps"
    assert format_bitrate(3_000_000) == "3.00 Mbps"


def test_parse_size_to_bytes():
    assert parse_size_to_bytes("1.5GB") == int(1.5 * 1024 ** 3)
    assert parse_size_to_bytes("240 MB") == 240 * 1024 ** 2
    assert parse_size_to_bytes("500kb") == 500 * 1024
    assert parse_size_to_bytes("garbage") is None
    assert parse_size_to_bytes("") is None