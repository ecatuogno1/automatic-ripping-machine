"""The System panel reports measured CPU, temperature, memory and storage figures"""
import collections
import types

import psutil

from arm.ui import app
import arm.ui.routes  # noqa: F401
import arm.ui.settings.ServerUtil as server_util

CpuTimes = collections.namedtuple("CpuTimes", "user nice system idle iowait")
Temp = collections.namedtuple("Temp", "label current high critical")
GIB = 1073741824


class FakeCpu:
    """cpu_times() and a clock the test moves forward"""

    def __init__(self):
        self.now = 100.0
        self.busy = 0.0
        self.idle = 0.0

    def times(self):
        return CpuTimes(user=self.busy, nice=0.0, system=0.0, idle=self.idle, iowait=0.0)

    def clock(self):
        return self.now

    def advance(self, seconds, busy_share):
        self.now += seconds
        self.busy += seconds * busy_share
        self.idle += seconds * (1 - busy_share)


def build(monkeypatch, temps=None, memory=None, disk=None):
    """A ServerUtil with psutil's readings replaced"""
    monkeypatch.setattr(psutil, "sensors_temperatures", lambda: temps or {}, raising=False)
    if memory is not None:
        monkeypatch.setattr(psutil, "virtual_memory", lambda: memory)
    if disk is not None:
        monkeypatch.setattr(psutil, "disk_usage", disk)
    with app.test_request_context("/"):
        return server_util.ServerUtil()


def test_cpu_usage_is_measured_over_a_window(monkeypatch):
    fake = FakeCpu()
    monkeypatch.setattr(server_util, "CPU", server_util.CpuSampler(fake.times, fake.clock), raising=False)
    fake.advance(2, 0.25)
    assert build(monkeypatch).cpu_util == 25.0
    # a second page right after the first keeps the measured figure instead of a millisecond window
    fake.advance(0.01, 1.0)
    assert build(monkeypatch).cpu_util == 25.0


def test_cpu_sampler_waits_for_its_first_window():
    fake = FakeCpu()
    sampler = server_util.CpuSampler(fake.times, fake.clock)
    fake.advance(0.2, 0.5)
    assert sampler.percent() is None
    fake.advance(1, 0.5)
    assert sampler.percent() == 50.0


def test_temperature_reads_amd_phenom_sensor(monkeypatch):
    temps = {"atk0110": [Temp("CPU Temperature", 48.0, None, None)]}
    assert build(monkeypatch, temps=temps).cpu_temp == 48.0


def test_temperature_prefers_intel_package_reading(monkeypatch):
    temps = {"coretemp": [Temp("Core 0", 40.0, 80.0, 100.0), Temp("Package id 0", 55.0, 80.0, 100.0)]}
    assert build(monkeypatch, temps=temps).cpu_temp == 55.0


def test_temperature_not_reported_is_none(monkeypatch):
    assert build(monkeypatch, temps={}).cpu_temp is None
    monkeypatch.delattr(psutil, "sensors_temperatures", raising=False)
    with app.test_request_context("/"):
        assert server_util.ServerUtil().cpu_temp is None


def test_memory_used_is_total_minus_available(monkeypatch):
    memory = types.SimpleNamespace(total=16 * GIB, available=10 * GIB, used=3 * GIB, percent=37.5)
    util = build(monkeypatch, memory=memory)
    assert util.memory_used == 6.0
    assert util.memory_free == 10.0


def test_unreadable_storage_path_is_not_reported_as_full(monkeypatch):
    def denied(path):
        raise PermissionError(path)

    util = build(monkeypatch, disk=denied)
    assert util.storage_transcode_free is None
    assert util.storage_completed_percent is None


def test_panel_renders_unmeasured_figures():
    serverutil = types.SimpleNamespace(cpu_util=None, cpu_temp=None, memory_free=1, memory_used=1, memory_percent=50,
                                       storage_raw_free=3.0, storage_raw_percent=20,
                                       storage_transcode_free=None, storage_transcode_percent=None,
                                       storage_completed_free=2.0, storage_completed_percent=10)
    server = types.SimpleNamespace(name="ARM", description="", cpu="CPU", mem_total=2)
    stats = {"hw_support": {"intel": False, "nvidia": False, "amd": False}}
    with app.test_request_context("/"):
        html = app.jinja_env.get_template("settings/sysinfo.html").render(
            serverutil=serverutil, server=server, stats=stats, arm_path="/t", media_path="/c")
    assert "measuring, reload in a moment" in html
    assert "Transcode: Unable to get data on path" in html
    assert "Completed: Unable to get data on path" not in html
