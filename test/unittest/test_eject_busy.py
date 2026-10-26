"""Eject unmounts first, retries a busy drive, and the job only records a real eject (#1558, #1837)."""
import subprocess
from types import SimpleNamespace

import pytest

import arm.config.config as cfg
from arm.models import system_drives
from arm.models.job import Job
from arm.models.system_drives import SystemDrives

DEVPATH = "/dev/sr0"
BUSY = f"eject: cannot open {DEVPATH}: Device or resource busy"


@pytest.fixture
def commands(monkeypatch):
    """Record commands; ``results`` holds the outputs of the next eject calls (None = success)."""
    state = {"calls": [], "results": [], "mounted": False, "released": 0}

    def fake_subprocess(cmd, check=False, **_kwargs):
        state["calls"].append(cmd)
        if cmd[0] == "eject" and state["results"]:
            output = state["results"].pop(0)
            if output is not None:
                raise subprocess.CalledProcessError(1, cmd, output=output)
        return ""

    monkeypatch.setattr(system_drives, "arm_subprocess", fake_subprocess)
    monkeypatch.setattr(system_drives, "_is_mounted", lambda _dev: state["mounted"], raising=False)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    return state


def _drive(state):
    drive = SimpleNamespace(mount=DEVPATH)
    drive.release_current_job = lambda: state.__setitem__("released", state["released"] + 1)
    drive._run_eject = lambda cmd: SystemDrives._run_eject(drive, cmd)
    return drive


def _ejects(state):
    return [cmd for cmd in state["calls"] if cmd[0] == "eject"]


def test_busy_drive_is_retried_until_it_ejects(commands):
    commands["results"] = [BUSY, None]
    assert SystemDrives.eject(_drive(commands)) is None
    assert len(_ejects(commands)) == 2
    assert commands["released"] == 1


def test_still_busy_after_all_attempts_returns_the_error(commands):
    commands["results"] = [BUSY] * system_drives.EJECT_ATTEMPTS
    assert SystemDrives.eject(_drive(commands)) == BUSY
    assert len(_ejects(commands)) == system_drives.EJECT_ATTEMPTS


def test_other_errors_are_not_retried(commands):
    commands["results"] = ["eject: unable to find or open device"]
    assert SystemDrives.eject(_drive(commands)) == "eject: unable to find or open device"
    assert len(_ejects(commands)) == 1


def test_mounted_disc_is_unmounted_before_eject(commands):
    commands["mounted"] = True
    SystemDrives.eject(_drive(commands))
    assert commands["calls"][0] == ["umount", DEVPATH]
    assert commands["calls"][1][0] == "eject"


def test_unmounted_disc_is_not_unmounted(commands):
    SystemDrives.eject(_drive(commands))
    assert [cmd[0] for cmd in commands["calls"]] == ["eject"]


@pytest.mark.parametrize("error, ejected", [(None, True), (BUSY, False)])
def test_job_records_eject_only_when_it_worked(monkeypatch, error, ejected):
    monkeypatch.setitem(cfg.arm_config, "AUTO_EJECT", True)
    job = SimpleNamespace(ejected=False, devpath=DEVPATH, drive=SimpleNamespace(eject=lambda: error))
    Job.eject(job)
    assert job.ejected is ejected
