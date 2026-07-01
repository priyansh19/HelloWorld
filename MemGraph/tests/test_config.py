import json

from memgraph.config import (
    Config,
    load_config,
    save_config,
    REFRESH_MS_MIN,
    REFRESH_MS_MAX,
)


def test_defaults_are_valid():
    cfg = Config().clamp()
    assert REFRESH_MS_MIN <= cfg.refresh_ms <= REFRESH_MS_MAX
    assert 0.2 <= cfg.opacity <= 1.0
    assert cfg.threshold_red > cfg.threshold_amber
    assert cfg.temp_red > cfg.temp_amber
    assert cfg.enabled_metrics  # never empty


def test_clamp_coerces_out_of_range_values():
    cfg = Config(refresh_ms=0, opacity=5.0, history_seconds=999999).clamp()
    assert cfg.refresh_ms == REFRESH_MS_MIN
    assert cfg.opacity == 1.0
    assert cfg.history_seconds <= 3600


def test_thresholds_forced_monotonic():
    cfg = Config(threshold_amber=90, threshold_red=50,
                 temp_amber=100, temp_red=40).clamp()
    assert cfg.threshold_red > cfg.threshold_amber
    assert cfg.temp_red > cfg.temp_amber


def test_history_points_scales_with_refresh():
    assert Config(refresh_ms=1000, history_seconds=120).clamp().history_points == 120
    assert Config(refresh_ms=500, history_seconds=120).clamp().history_points == 240


def test_enabled_metrics_filtered_deduped_ordered():
    cfg = Config(enabled_metrics=["cpu", "bogus", "cpu", "ram"]).clamp()
    assert cfg.enabled_metrics == ["cpu", "ram"]


def test_enabled_metrics_never_empty():
    cfg = Config(enabled_metrics=["bogus", "alsobogus"]).clamp()
    assert cfg.enabled_metrics == ["ram"]


def test_legacy_flags_migrated():
    cfg = Config.from_dict({"show_ram": True, "show_vram": False,
                            "show_process": True})
    assert cfg.enabled_metrics == ["ram", "process"]


def test_from_dict_ignores_unknown_and_fills_missing():
    cfg = Config.from_dict({"refresh_ms": 2000, "bogus_key": 123})
    assert cfg.refresh_ms == 2000
    assert cfg.enabled_metrics  # default filled in
    assert not hasattr(cfg, "bogus_key")


def test_roundtrip_save_load(tmp_path):
    p = tmp_path / "config.json"
    cfg = Config(refresh_ms=1500, process_name="llama.exe", opacity=0.5,
                 enabled_metrics=["cpu", "gpu", "gpu_temp"])
    save_config(cfg, p)
    loaded = load_config(p)
    assert loaded.refresh_ms == 1500
    assert loaded.process_name == "llama.exe"
    assert loaded.opacity == 0.5
    assert loaded.enabled_metrics == ["cpu", "gpu", "gpu_temp"]


def test_load_missing_returns_defaults(tmp_path):
    assert load_config(tmp_path / "nope.json").refresh_ms == Config().refresh_ms


def test_load_corrupt_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ not valid json ")
    assert load_config(p).refresh_ms == Config().refresh_ms


def test_save_is_atomic_and_indented(tmp_path):
    p = tmp_path / "config.json"
    save_config(Config(), p)
    data = json.loads(p.read_text())
    assert "enabled_metrics" in data
    assert not (tmp_path / "config.json.tmp").exists()
