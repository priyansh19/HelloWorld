import json

from memgraph.config import (
    Config,
    load_config,
    save_config,
    REFRESH_MS_MIN,
    REFRESH_MS_MAX,
)


def test_defaults_are_valid():
    cfg = Config()
    cfg.clamp()
    assert REFRESH_MS_MIN <= cfg.refresh_ms <= REFRESH_MS_MAX
    assert 0.2 <= cfg.opacity <= 1.0
    assert cfg.threshold_red > cfg.threshold_amber


def test_clamp_coerces_out_of_range_values():
    cfg = Config(refresh_ms=0, opacity=5.0, history_seconds=999999)
    cfg.clamp()
    assert cfg.refresh_ms == REFRESH_MS_MIN
    assert cfg.opacity == 1.0
    assert cfg.history_seconds <= 3600


def test_red_threshold_forced_above_amber():
    cfg = Config(threshold_amber=90, threshold_red=50).clamp()
    assert cfg.threshold_red > cfg.threshold_amber


def test_history_points_scales_with_refresh():
    cfg = Config(refresh_ms=1000, history_seconds=120).clamp()
    assert cfg.history_points == 120
    cfg2 = Config(refresh_ms=500, history_seconds=120).clamp()
    assert cfg2.history_points == 240


def test_from_dict_ignores_unknown_and_fills_missing():
    cfg = Config.from_dict({"refresh_ms": 2000, "bogus_key": 123})
    assert cfg.refresh_ms == 2000
    assert cfg.show_ram is True  # default filled in
    assert not hasattr(cfg, "bogus_key")


def test_roundtrip_save_load(tmp_path):
    p = tmp_path / "config.json"
    cfg = Config(refresh_ms=1500, process_name="llama.exe", opacity=0.5)
    save_config(cfg, p)
    loaded = load_config(p)
    assert loaded.refresh_ms == 1500
    assert loaded.process_name == "llama.exe"
    assert loaded.opacity == 0.5


def test_load_missing_returns_defaults(tmp_path):
    loaded = load_config(tmp_path / "does_not_exist.json")
    assert loaded.refresh_ms == Config().refresh_ms


def test_load_corrupt_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ this is not valid json ")
    loaded = load_config(p)
    assert loaded.refresh_ms == Config().refresh_ms


def test_save_is_atomic_and_indented(tmp_path):
    p = tmp_path / "config.json"
    save_config(Config(), p)
    data = json.loads(p.read_text())
    assert "refresh_ms" in data
    assert not (tmp_path / "config.json.tmp").exists()
