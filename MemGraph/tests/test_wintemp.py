from memgraph._wintemp import parse_temps


def test_lhm_prefers_package_and_gpu_core():
    payload = {
        "source": "LibreHardwareMonitor",
        "sensors": [
            {"name": "Core #1", "value": 55.0, "parent": "/intelcpu/0"},
            {"name": "Core #2", "value": 61.0, "parent": "/intelcpu/0"},
            {"name": "CPU Package", "value": 58.0, "parent": "/intelcpu/0"},
            {"name": "GPU Core", "value": 47.0, "parent": "/gpu-nvidia/0"},
            {"name": "GPU Hot Spot", "value": 63.0, "parent": "/gpu-nvidia/0"},
        ],
        "acpi": [],
    }
    r = parse_temps(payload)
    assert r["cpu"] == 58.0          # prefers "CPU Package" over hotter cores
    assert r["gpu"] == 47.0          # prefers "GPU Core" over hot spot
    assert r["source"] == "LibreHardwareMonitor"


def test_amd_tctl_and_memory_bucket():
    payload = {
        "source": "LibreHardwareMonitor",
        "sensors": [
            {"name": "Core (Tctl/Tdie)", "value": 49.0, "parent": "/amdcpu/0"},
            {"name": "GPU Core", "value": 40.0, "parent": "/gpu-amd/0"},
            {"name": "Memory", "value": 38.0, "parent": "/ram/0"},
        ],
        "acpi": [],
    }
    r = parse_temps(payload)
    assert r["cpu"] == 49.0
    assert r["gpu"] == 40.0
    assert r["mem"] == 38.0


def test_falls_back_to_max_when_no_preferred_name():
    payload = {"source": "OpenHardwareMonitor", "sensors": [
        {"name": "Temperature #1", "value": 44.0, "parent": "/lpc/it87/0/cpu"},
        {"name": "Temperature #2", "value": 52.0, "parent": "/lpc/it87/0/cpu"},
    ], "acpi": []}
    r = parse_temps(payload)
    assert r["cpu"] == 52.0


def test_acpi_fallback_tenths_of_kelvin():
    # 3200 tenths-K = 320.0K = ~46.85C
    payload = {"source": "", "sensors": [], "acpi": [3200, 3150]}
    r = parse_temps(payload)
    assert r["cpu"] is not None
    assert 46 < r["cpu"] < 48
    assert r["source"] == "ACPI"


def test_ignores_bogus_values():
    payload = {"source": "LibreHardwareMonitor", "sensors": [
        {"name": "CPU Package", "value": 0.0, "parent": "/intelcpu/0"},
        {"name": "CPU Package", "value": 999.0, "parent": "/intelcpu/0"},
    ], "acpi": []}
    r = parse_temps(payload)
    assert r["cpu"] is None


def test_single_sensor_not_in_list():
    # ConvertTo-Json collapses a 1-element array to an object; handle it.
    payload = {"source": "LibreHardwareMonitor",
               "sensors": {"name": "CPU Package", "value": 50.0,
                           "parent": "/intelcpu/0"},
               "acpi": []}
    r = parse_temps(payload)
    assert r["cpu"] == 50.0


def test_empty_payload_safe():
    r = parse_temps({})
    assert r == {"cpu": None, "gpu": None, "mem": None, "source": ""}
