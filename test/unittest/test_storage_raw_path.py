"""The Storage card lists the raw (MakeMKV) path next to the transcode and completed paths"""
import types

import psutil

import arm.config.config as cfg
from arm.ui import app
import arm.ui.routes  # noqa: F401
import arm.ui.settings.ServerUtil as server_util

GIB = 1073741824


def test_raw_path_space_is_measured(monkeypatch, tmp_path):
    raw, work, done = (str(tmp_path / name) for name in ("raw", "work", "done"))
    monkeypatch.setitem(cfg.arm_config, "RAW_PATH", raw)
    monkeypatch.setitem(cfg.arm_config, "TRANSCODE_PATH", work)
    monkeypatch.setitem(cfg.arm_config, "COMPLETED_PATH", done)
    free = {raw: 50, work: 200, done: 900}
    monkeypatch.setattr(psutil, "disk_usage",
                        lambda path: types.SimpleNamespace(free=free[path] * GIB, percent=12.5))
    monkeypatch.setattr(psutil, "sensors_temperatures", lambda: {}, raising=False)
    with app.test_request_context("/"):
        util = server_util.ServerUtil()

    assert util.storage_raw_free == 50.0
    assert util.storage_raw_percent == 12.5
    assert util.storage_transcode_free == 200.0


def _render(**storage):
    serverutil = types.SimpleNamespace(cpu_util=5.0, cpu_temp=None, memory_free=1, memory_used=1, memory_percent=50,
                                       **storage)
    server = types.SimpleNamespace(name="ARM", description="", cpu="CPU", mem_total=2)
    stats = {"hw_support": {"intel": False, "nvidia": False, "amd": False}}
    with app.test_request_context("/"):
        return app.jinja_env.get_template("settings/sysinfo.html").render(
            serverutil=serverutil, server=server, stats=stats,
            raw_path="/media/raw", arm_path="/media/transcode", media_path="/media/completed")


def test_storage_card_shows_raw_path():
    html = _render(storage_raw_free=50.0, storage_raw_percent=91.0,
                   storage_transcode_free=200.0, storage_transcode_percent=40.0,
                   storage_completed_free=900.0, storage_completed_percent=10.0)
    assert "Raw: </h6>" in html
    assert "Path: /media/raw" in html
    assert "Free Space: 50.0 GB" in html
    # over 80 % used is drawn in red like the other paths
    assert 'progress-bar bg-danger"' in html
    # listed in the order a rip uses them
    assert html.index("Path: /media/raw") < html.index("Path: /media/transcode")
    assert html.index("Path: /media/transcode") < html.index("Path: /media/completed")


def test_unreadable_raw_path_is_reported():
    html = _render(storage_raw_free=None, storage_raw_percent=None,
                   storage_transcode_free=200.0, storage_transcode_percent=40.0,
                   storage_completed_free=900.0, storage_completed_percent=10.0)
    assert "Raw: Unable to get data on path" in html
    assert "Path: /media/raw" in html
