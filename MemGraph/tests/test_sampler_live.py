"""Live sampler tests using the real psutil backend (installed for CI/dev).

These exercise MetricsSampler end-to-end without a GPU: RAM should read real
values, VRAM should degrade to unavailable, and the composed Sample should
honour the enable flags.
"""

import pytest

from memgraph.metrics import MetricsSampler

psutil = pytest.importorskip("psutil")


@pytest.fixture(scope="module")
def sampler():
    return MetricsSampler()


def test_ram_reads_real_values(sampler):
    r = sampler.ram()
    assert r.key == "ram"
    assert r.available is True
    assert r.total_bytes > 0
    assert 0 <= r.percent <= 100


def test_vram_degrades_without_gpu(sampler):
    r = sampler.vram()
    assert r.key == "vram"
    # On a headless CI box there is no NVIDIA GPU; must not raise.
    if not sampler.gpu_available:
        assert r.available is False
        assert r.readout() == "n/a"


def test_process_not_running_is_unavailable(sampler):
    r = sampler.process("definitely-not-a-real-process-xyz.exe")
    assert r.key == "process"
    assert r.available is False
    assert "not running" in r.detail


def test_process_matches_current_python(sampler):
    # The test runner itself is a python process, so this should be found.
    import os
    name = os.path.basename(psutil.Process().name())
    r = sampler.process(name)
    assert r.available is True
    assert r.used_bytes > 0


def test_sample_respects_flags(sampler):
    s = sampler.sample(show_ram=True, show_vram=False, show_process=False,
                       process_name="")
    assert s is not None
    assert s.primary.key == "ram"
    assert s.secondary == []


def test_sample_none_when_nothing_enabled(sampler):
    s = sampler.sample(show_ram=False, show_vram=False, show_process=False,
                       process_name="")
    assert s is None
