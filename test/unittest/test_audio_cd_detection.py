"""An audio CD is typed as music even when udev has not reported its audio tracks (#952)."""
from types import SimpleNamespace

import pytest

from arm.models import job as job_module
from arm.models.job import Job

DEVPATH = "/dev/sr0"
# linux/cdrom.h
CDROM_DISC_STATUS = 0x5327
CDS_AUDIO = 100
CDS_DATA_1 = 101
CDS_MIXED = 105


@pytest.fixture
def drive(monkeypatch):
    """Fake udev properties and CDROM_DISC_STATUS result for DEVPATH."""
    state = {"udev": {}, "status": None, "ioctls": 0}

    def ioctl(_fd, request):
        assert request == CDROM_DISC_STATUS
        state["ioctls"] += 1
        return state["status"]

    monkeypatch.setattr(job_module.pyudev.Devices, "from_device_file", lambda _context, _path: state["udev"])
    monkeypatch.setattr(job_module.os, "open", lambda *_args: 99)
    monkeypatch.setattr(job_module.os, "close", lambda _fd: None)
    monkeypatch.setattr(job_module, "fcntl", SimpleNamespace(ioctl=ioctl), raising=False)
    return state


def _disctype():
    job = SimpleNamespace(devpath=DEVPATH, label=None)
    Job.parse_udev(job)
    return job.disctype


def test_audio_cd_without_udev_track_count_is_music(drive):
    drive["udev"] = {"ID_CDROM_MEDIA": "1", "ID_CDROM_MEDIA_CD": "1"}
    drive["status"] = CDS_AUDIO
    assert _disctype() == "music"


def test_data_cd_stays_unknown(drive):
    drive["udev"] = {"ID_CDROM_MEDIA_CD": "1"}
    drive["status"] = CDS_DATA_1
    assert _disctype() == "unknown"


def test_disc_with_a_filesystem_is_not_probed(drive):
    drive["udev"] = {"ID_CDROM_MEDIA_CD": "1", "ID_FS_TYPE": "iso9660", "ID_FS_LABEL": "BACKUP"}
    drive["status"] = CDS_MIXED
    assert _disctype() == "unknown"
    assert drive["ioctls"] == 0


def test_udev_audio_track_count_still_wins(drive):
    drive["udev"] = {"ID_CDROM_MEDIA_CD": "1", "ID_CDROM_MEDIA_TRACK_COUNT_AUDIO": "12"}
    assert _disctype() == "music"
    assert drive["ioctls"] == 0


def test_unreadable_disc_status_stays_unknown(drive, monkeypatch):
    def fail(*_args):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(job_module, "fcntl", SimpleNamespace(ioctl=fail), raising=False)
    drive["udev"] = {"ID_CDROM_MEDIA_CD": "1"}
    assert _disctype() == "unknown"
