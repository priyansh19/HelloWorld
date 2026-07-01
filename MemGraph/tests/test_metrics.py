import pytest

from memgraph.metrics import (
    MetricReading,
    Sample,
    color_for_level,
    format_bytes,
    level_for_percent,
    percent,
)


@pytest.mark.parametrize("value,expected", [
    (0, "0 B"),
    (512, "512 B"),
    (1024, "1.0 KB"),
    (1536, "1.5 KB"),
    (1024 ** 2, "1.0 MB"),
    (int(1.5 * 1024 ** 3), "1.5 GB"),
    (2 * 1024 ** 4, "2.0 TB"),
])
def test_format_bytes(value, expected):
    assert format_bytes(value) == expected


def test_percent_safe_and_clamped():
    assert percent(0, 0) == 0.0
    assert percent(5, 0) == 0.0
    assert percent(50, 100) == 50.0
    assert percent(200, 100) == 100.0
    assert percent(-5, 100) == 0.0


@pytest.mark.parametrize("pct,level", [
    (0, "ok"),
    (69, "ok"),
    (70, "warn"),
    (87, "warn"),
    (88, "crit"),
    (100, "crit"),
])
def test_level_for_percent(pct, level):
    assert level_for_percent(pct, amber=70, red=88) == level


def test_color_for_level():
    assert color_for_level("ok") == "#38c172"
    assert color_for_level("warn") == "#f6a609"
    assert color_for_level("crit") == "#e3342f"
    assert color_for_level("unknown") == "#38c172"


def test_metric_reading_percent_and_readout():
    r = MetricReading("ram", "RAM", used_bytes=8 * 1024 ** 3,
                      total_bytes=16 * 1024 ** 3)
    assert r.percent == 50.0
    assert r.readout() == "8.0 GB / 16.0 GB"
    assert r.level(70, 88) == "ok"


def test_metric_reading_unavailable_readout():
    r = MetricReading("vram", "VRAM", 0, 0, available=False)
    assert r.readout() == "n/a"
    assert r.percent == 0.0


def test_sample_all_readings_orders_primary_first():
    primary = MetricReading("ram", "RAM", 1, 2)
    sec = MetricReading("vram", "VRAM", 1, 2)
    s = Sample(primary=primary, secondary=[sec])
    assert s.all_readings() == [primary, sec]
