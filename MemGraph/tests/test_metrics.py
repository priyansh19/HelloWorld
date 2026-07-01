import pytest

from memgraph.metrics import (
    ALL_METRIC_KEYS,
    DEFAULT_METRICS,
    METRIC_BY_KEY,
    Metric,
    color_for_level,
    format_bytes,
    percent,
    severity,
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


@pytest.mark.parametrize("value,level", [
    (0, "ok"), (69, "ok"), (70, "warn"), (87, "warn"), (88, "crit"), (100, "crit"),
])
def test_severity(value, level):
    assert severity(value, amber=70, red=88) == level


def test_color_for_level():
    assert color_for_level("ok") == "#3ddc84"
    assert color_for_level("warn") == "#ffb020"
    assert color_for_level("crit") == "#ff5470"
    assert color_for_level("???") == "#3ddc84"


def test_registry_consistency():
    assert DEFAULT_METRICS and all(k in ALL_METRIC_KEYS for k in DEFAULT_METRICS)
    assert set(METRIC_BY_KEY) == set(ALL_METRIC_KEYS)


def test_bytes_metric():
    m = Metric("ram", "RAM", "bytes", value=8 * 1024 ** 3, total=16 * 1024 ** 3)
    assert m.pct == 50.0
    assert m.value_text() == "50%"
    assert m.sub_text() == "8.0 GB / 16.0 GB"
    assert m.graph_value() == 50.0
    assert m.level(70, 88, 75, 88) == "ok"


def test_percent_metric():
    m = Metric("cpu", "CPU", "percent", value=91.0)
    assert m.pct == 91.0
    assert m.value_text() == "91%"
    assert m.level(70, 88, 75, 88) == "crit"


def test_temp_metric_uses_temp_thresholds():
    m = Metric("cpu_temp", "CPU Temp", "temp", value=80.0)
    assert m.value_text() == "80°C"
    # 80°C: below usage-red(88) but above temp-amber(75) -> warn via temp path.
    assert m.level(70, 88, 75, 88) == "warn"
    # graph value clamps into 0-100 band.
    assert m.graph_value() == 80.0


def test_unavailable_metric():
    m = Metric("vram", "VRAM", "bytes", available=False, detail="no NVIDIA GPU")
    assert m.value_text() == "n/a"
    assert m.sub_text() == "no NVIDIA GPU"
    assert m.level(70, 88, 75, 88) == "ok"
