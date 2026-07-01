"""Live sampler tests using the real psutil backend (installed for CI/dev)."""

import os

import pytest

from memgraph.metrics import MetricsSampler

psutil = pytest.importorskip("psutil")


@pytest.fixture(scope="module")
def sampler():
    return MetricsSampler()


def test_ram_reads_real_values(sampler):
    m = sampler.ram()
    assert m.available and m.total > 0 and 0 <= m.pct <= 100


def test_cpu_reads(sampler):
    m = sampler.cpu()
    assert m.available and 0 <= m.pct <= 100


def test_vram_degrades_without_gpu(sampler):
    m = sampler.vram()
    if not sampler.gpu_available:
        assert m.available is False
        assert m.value_text() == "n/a"


def test_npu_never_raises(sampler):
    m = sampler.npu()          # almost always unavailable off Windows/NPU
    assert m.key == "npu"
    assert isinstance(m.available, bool)


def test_temps_never_raise(sampler):
    for m in (sampler.cpu_temp(), sampler.gpu_temp(), sampler.mem_temp()):
        assert m.kind == "temp"
        assert isinstance(m.available, bool)


def test_process_not_running_is_unavailable(sampler):
    m = sampler.process("definitely-not-real-xyz.exe")
    assert m.available is False and "not running" in m.detail


def test_process_matches_current(sampler):
    name = os.path.basename(psutil.Process().name())
    m = sampler.process(name)
    assert m.available is True and m.value > 0


def test_sample_orders_and_dispatches(sampler):
    metrics = sampler.sample(["ram", "cpu", "vram"], process_name="")
    assert [m.key for m in metrics] == ["ram", "cpu", "vram"]


def test_read_unknown_key_is_unavailable(sampler):
    m = sampler.read("nonsense")
    assert m.available is False
