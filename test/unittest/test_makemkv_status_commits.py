"""MakeMKV job status updates must survive a briefly locked SQLite database (#1840)"""
from types import SimpleNamespace

import pytest
import sqlalchemy.exc

from arm.ui import app, db
import arm.ui.routes  # noqa: F401
from arm.ripper import makemkv, utils


@pytest.fixture
def locked_once(monkeypatch):
    """db.session.commit raising 'database is locked' on the n-th call, as another ARM process would cause"""
    calls = []

    def install(locked_call):
        def commit():
            calls.append(1)
            if len(calls) == locked_call:
                raise sqlalchemy.exc.OperationalError("UPDATE job", {}, Exception("database is locked"))

        monkeypatch.setattr(db.session, "commit", commit)
        monkeypatch.setattr(db.session, "rollback", lambda: None)
        monkeypatch.setattr(utils.time, "sleep", lambda seconds: None)
        return calls

    with app.app_context():
        yield install


def test_makemkv_info_status_commits_retry_a_locked_database(locked_once, monkeypatch):
    calls = locked_once(2)  # the VIDEO_INFO transition meets a locked database once
    monkeypatch.setattr(utils, "sleep_check_process", lambda *args, **kwargs: None)
    monkeypatch.setattr(makemkv, "run", lambda options, select: iter([]))
    monkeypatch.setitem(makemkv.cfg.arm_config, "MAX_CONCURRENT_MAKEMKVINFO", 0)
    job = SimpleNamespace(job_id=1, status=None, config=SimpleNamespace(MINLENGTH=600, MANUAL_WAIT_TIME=0))
    assert list(makemkv.makemkv_info(job, index=0)) == []
    assert job.status == "ripping"
    assert len(calls) == 5


def test_manual_mode_status_commits_retry_a_locked_database(locked_once, monkeypatch, tmp_path):
    calls = locked_once(1)  # the VIDEO_WAITING transition meets a locked database once
    ripped = []
    monkeypatch.setattr(utils, "get_drive_mode", lambda devpath: "manual")
    monkeypatch.setattr(makemkv, "get_track_info", lambda mdisc, job: None)
    monkeypatch.setattr(makemkv, "manual_wait", lambda job: True)
    monkeypatch.setattr(makemkv, "process_single_tracks", lambda job, rawpath, mode: ripped.append(job.status))
    job = SimpleNamespace(job_id=1, status=None, devpath="/dev/sr0", drive=SimpleNamespace(mdisc=0),
                          config=SimpleNamespace(MAINFEATURE=False))
    makemkv.makemkv_mkv(job, str(tmp_path))
    assert ripped == ["ripping"]
    assert len(calls) == 3
