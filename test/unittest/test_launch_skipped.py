"""A run that never started a job (empty tray, repeated udev event) is not a failed rip."""

import runpy
import sys
from types import SimpleNamespace

import pytest

from arm.models.job import Job
from arm.models.system_drives import CDS, SystemDrives
from arm.ripper import logger, utils


class FakeDrive:
    def __init__(self, tray):
        self.tray = tray
        self.mount = "/dev/sr0"
        self.ready = tray == CDS.DISC_OK

    def tray_status(self):
        return self.tray


def drive_already_ripping(monkeypatch):
    """The drive's current job is still running (what duplicate_run_check looks for)."""
    running = SimpleNamespace(job_id=1, status="ripping", run_time=60)
    drive = SimpleNamespace(processing=True, job_current=running)
    monkeypatch.setattr(utils, "SystemDrives", SimpleNamespace(query=SimpleNamespace(
        filter_by=lambda **kwargs: SimpleNamespace(first=lambda: drive))))
    monkeypatch.setattr(utils, "db", SimpleNamespace(session=SimpleNamespace(
        query=lambda model: SimpleNamespace(filter=lambda *args: SimpleNamespace(all=lambda: [running])))))


@pytest.fixture
def launch(monkeypatch):
    """Run arm/ripper/main.py as udev would, with the drive and notifications faked."""
    notices = []
    monkeypatch.setattr(sys, "argv", ["main.py", "-d", "sr0", "--no-syslog"])
    monkeypatch.setattr(logger, "create_early_logger", lambda **kwargs: None)
    monkeypatch.setattr(utils, "arm_setup", lambda arm_log: None)
    monkeypatch.setattr(utils, "notify", lambda job, title, body: notices.append(body))
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    monkeypatch.setattr("signal.signal", lambda *args: None)

    def run(tray):
        drive = FakeDrive(tray)
        query = SimpleNamespace(filter_by=lambda **kwargs: SimpleNamespace(one=lambda: drive))
        monkeypatch.setattr(SystemDrives, "query", query)
        runpy.run_module("arm.ripper.main", run_name="__main__")
        return notices
    return run


@pytest.mark.parametrize("tray", [CDS.TRAY_OPEN, CDS.NO_DISC])
def test_open_or_empty_tray_is_not_reported_as_a_failure(launch, tray):
    assert launch(tray) == []


def test_drive_that_never_gets_ready_with_a_disc_is_still_reported(launch):
    notices = launch(CDS.DRIVE_NOT_READY)
    assert len(notices) == 1
    assert "Timed out waiting for drive to be ready" in notices[0]


def test_repeated_udev_event_is_not_reported_and_does_not_eject(launch, monkeypatch):
    ejected = []
    monkeypatch.setattr(Job, "parse_udev", lambda self: setattr(self, "disctype", "bluray"))
    monkeypatch.setattr(Job, "get_pid", lambda self: None)
    monkeypatch.setattr(Job, "eject", lambda self: ejected.append(self))
    monkeypatch.setattr(logger, "setup_job_log", lambda job: "job.log")
    monkeypatch.setattr("arm.ripper.ARMInfo.ARMInfo",
                        lambda *args: SimpleNamespace(arm_version="test", get_values=lambda: None))
    drive_already_ripping(monkeypatch)

    assert launch(CDS.DISC_OK) == []
    assert ejected == []


def test_duplicate_run_check_is_a_skipped_launch(monkeypatch):
    drive_already_ripping(monkeypatch)
    with pytest.raises(utils.LaunchSkipped):
        utils.duplicate_run_check("/dev/sr0")
