"""Requests to the remote crc64 database time out instead of hanging."""

import secrets
from types import SimpleNamespace

import requests

import arm.config.config as cfg
from arm.ripper import identify
from arm.ui import utils as ui_utils


def test_send_to_remote_db_times_out_and_reports_failure(monkeypatch):
    calls = []

    def unreachable(url, **kwargs):
        calls.append(kwargs)
        raise requests.Timeout("read timed out")

    job = SimpleNamespace(crc_id="ade5cef9590c59d1", title="Foo", year="2001", imdb_id="tt0000001",
                          hasnicetitle=True, label="FOO", video_type="movie",
                          get_d=lambda: {"title": "Foo"}, config=SimpleNamespace(get_d=lambda: {}))
    monkeypatch.setattr(ui_utils, "Job", SimpleNamespace(query=SimpleNamespace(get=lambda job_id: job)))
    monkeypatch.setitem(cfg.arm_config, "ARM_API_KEY", secrets.token_hex(8))
    monkeypatch.setattr(ui_utils.requests, "get", unreachable)

    result = ui_utils.send_to_remote_db(1)

    assert calls[0].get("timeout")
    assert result["status"] == "fail"
    assert result["title"] == "Foo"


def test_identify_dvd_crc64_lookup_has_a_timeout(monkeypatch):
    calls = []

    def unreachable(url, **kwargs):
        calls.append(kwargs)
        raise TimeoutError("timed out")

    monkeypatch.setattr(identify.pydvdid, "compute", lambda path: "ade5cef9590c59d1")
    monkeypatch.setattr(identify.urllib.request, "urlopen", unreachable)
    monkeypatch.setattr(identify, "metadata_selector", lambda *args, **kwargs: None)
    monkeypatch.setattr(identify, "identify_loop", lambda *args: None)
    monkeypatch.setattr(identify, "arm_subprocess", lambda *args, **kwargs: None)
    job = SimpleNamespace(label="FOO", year=None, title="Foo", mountpoint="/mnt/dev/sr0",
                          devpath="/dev/sr0", pretty_table=lambda: "")

    assert identify.identify_dvd(job) is True
    assert calls[0].get("timeout")
    assert job.crc_id == "ade5cef9590c59d1"
