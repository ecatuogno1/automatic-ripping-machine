"""MakeMKV reads the job's own drive: dev:<path> for mkv rips, the drive's disc index for backups."""
from types import SimpleNamespace

import pytest

from arm.ripper import makemkv, utils
from arm.ui import app, db

DRIVE_LISTING = [
    'DRV:0,2,999,12,"BD-RE DRIVE A","OTHER_DISC","/dev/sr1"',
    'DRV:1,2,999,12,"BD-RE DRIVE B","THIS_DISC","/dev/sr0"',
    'DRV:2,256,999,0,"","",""',
]


@pytest.fixture
def commands(monkeypatch, tmp_path):
    """Record every makemkvcon command; only the disc:9999 scan produces output (the drive listing)."""
    calls = []

    def fake_run(options, select):
        calls.append(list(options))
        if "disc:9999" in options:
            for line in DRIVE_LISTING:
                msg_type, data = makemkv.parse_line(line)
                if msg_type in select:
                    yield data

    monkeypatch.setattr(makemkv, "run", fake_run)
    monkeypatch.setattr(makemkv, "prep_mkv", lambda: None)
    monkeypatch.setattr(makemkv, "setup_rawpath", lambda job, path: str(tmp_path))
    monkeypatch.setattr(makemkv, "sleep", lambda *_: None)
    monkeypatch.setattr(utils, "sleep_check_process", lambda *_a, **_k: None)
    monkeypatch.setattr(utils, "get_drive_mode", lambda _devpath: "auto")
    with app.app_context():
        db.create_all()
        monkeypatch.setattr(db.session, "refresh", lambda _obj: None)
        yield calls


def _job(tmp_path, disctype, ripmethod, drive=None):
    config = SimpleNamespace(RIPMETHOD=ripmethod, MKV_ARGS="", MINLENGTH=600, MAXLENGTH=99999, MAINFEATURE=False,
                             MANUAL_WAIT_TIME=0, LOGPATH=str(tmp_path), RAW_PATH=str(tmp_path))
    return SimpleNamespace(job_id=1, devpath="/dev/sr0", disctype=disctype, title="Title", config=config,
                           drive=drive, status=None, eject=lambda: None)


def test_mkv_rip_reads_the_device_without_scanning_every_drive(commands, tmp_path):
    makemkv.makemkv(_job(tmp_path, "dvd", "mkv"))
    assert not any("disc:9999" in cmd for cmd in commands)
    info = [cmd for cmd in commands if cmd[0] == "info"]
    assert len(info) == 1
    assert "dev:/dev/sr0" in info[0]
    rip = [cmd for cmd in commands if cmd[0] == "mkv"]
    assert len(rip) == 1
    assert "dev:/dev/sr0" in rip[0]


def test_backup_uses_the_disc_index_listed_for_the_jobs_device(commands, tmp_path):
    makemkv.makemkv(_job(tmp_path, "bluray", "backup"))
    backup = [cmd for cmd in commands if cmd[0] == "backup"]
    assert len(backup) == 1
    assert "disc:1" in backup[0]


def test_backup_uses_the_stored_disc_index(commands, tmp_path):
    makemkv.makemkv(_job(tmp_path, "bluray", "backup", drive=SimpleNamespace(mdisc=4)))
    assert not any("disc:9999" in cmd for cmd in commands)
    backup = [cmd for cmd in commands if cmd[0] == "backup"]
    assert "disc:4" in backup[0]


def test_backup_stops_when_makemkv_does_not_list_the_device(commands, tmp_path):
    job = _job(tmp_path, "bluray", "backup")
    job.devpath = "/dev/sr5"
    with pytest.raises(utils.RipperException, match="/dev/sr5"):
        makemkv.makemkv(job)
    assert not any(cmd[0] == "backup" for cmd in commands)
