"""The ripper keeps waiting while a loading disc reports CDS_DRIVE_NOT_READY."""
import pytest

import arm.ripper.main as ripper_main
from arm.models.system_drives import CDS
from arm.ripper import utils


class FakeDrive:
    """Reports the given tray states in turn, then repeats the last one."""

    mount = "/dev/sr0"

    def __init__(self, states):
        self.states = list(states)
        self.tray = None
        self.polls = 0

    def tray_status(self):
        self.tray = self.states[min(self.polls, len(self.states) - 1)]
        self.polls += 1
        return self.tray

    @property
    def ready(self):
        return self.tray == CDS.DISC_OK


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(ripper_main.time, "sleep", calls.append)
    return calls


def test_waits_past_ten_seconds_while_the_disc_is_loading(sleeps):
    drive = FakeDrive([CDS.DRIVE_NOT_READY] * 30 + [CDS.DISC_OK])
    ripper_main.wait_until_ready(drive)
    assert drive.polls == 31
    assert len(sleeps) == 30


def test_open_tray_still_gives_up_after_ten_seconds(sleeps):
    drive = FakeDrive([CDS.TRAY_OPEN])
    with pytest.raises(utils.RipperException, match="TRAY_OPEN"):
        ripper_main.wait_until_ready(drive)
    assert drive.polls == ripper_main.READY_WAIT_SECONDS


def test_drive_that_never_gets_ready_still_fails(sleeps):
    drive = FakeDrive([CDS.DRIVE_NOT_READY])
    with pytest.raises(utils.RipperException, match="DRIVE_NOT_READY"):
        ripper_main.wait_until_ready(drive)
    assert drive.polls == ripper_main.LOADING_WAIT_SECONDS


def test_ready_drive_does_not_wait(sleeps):
    drive = FakeDrive([CDS.DISC_OK])
    ripper_main.wait_until_ready(drive)
    assert not sleeps
