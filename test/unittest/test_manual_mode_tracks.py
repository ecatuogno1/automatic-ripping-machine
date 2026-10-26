"""In manual drive mode the disc's titles are listed before the MANUAL_WAIT, so they can be chosen during it."""

from types import SimpleNamespace

import pytest

from arm.ripper import arm_ripper, makemkv


def make_job(disctype="dvd", **config):
    settings = {"RIPMETHOD": "mkv", "MAINFEATURE": False, "SKIP_TRANSCODE": False}
    settings.update(config)
    return SimpleNamespace(disctype=disctype, devpath="/dev/sr0", has_track_99=False,
                           config=SimpleNamespace(**settings))


@pytest.fixture
def scans(monkeypatch):
    scanned = []
    monkeypatch.setattr(makemkv, "scan_tracks", scanned.append)
    return scanned


@pytest.mark.parametrize("job", [
    make_job("dvd"),
    make_job("bluray"),
    make_job("dvd", RIPMETHOD="backup_dvd"),
], ids=["dvd", "bluray-mkv", "dvd-backup_dvd"])
def test_manual_mode_lists_titles_first(monkeypatch, scans, job):
    monkeypatch.setattr(arm_ripper.utils, "get_drive_mode", lambda devpath: "manual")

    arm_ripper.scan_tracks_for_manual_mode(job)

    assert scans == [job]


@pytest.mark.parametrize("mode, job", [
    ("auto", make_job("dvd")),
    ("manual", make_job("dvd", MAINFEATURE=True)),
    ("manual", make_job("bluray", RIPMETHOD="backup")),
    ("manual", make_job("music")),
], ids=["auto-mode", "mainfeature", "bluray-backup", "music"])
def test_no_early_scan_without_manual_track_selection(monkeypatch, scans, mode, job):
    monkeypatch.setattr(arm_ripper.utils, "get_drive_mode", lambda devpath: mode)

    arm_ripper.scan_tracks_for_manual_mode(job)

    assert scans == []


def test_main_lists_titles_before_waiting(monkeypatch):
    from arm.ripper import main

    calls = []
    job = SimpleNamespace(disctype="other")
    monkeypatch.setattr(main, "job", job, raising=False)
    monkeypatch.setattr(main.identify, "identify", lambda j: None)
    monkeypatch.setattr(main.utils, "job_dupe_check", lambda j: False)
    monkeypatch.setattr(main.utils, "notify_entry", lambda j: None)
    monkeypatch.setattr(main.arm_ripper, "scan_tracks_for_manual_mode", lambda j: calls.append("scan"))
    monkeypatch.setattr(main.utils, "check_for_wait", lambda j: calls.append("wait"))
    monkeypatch.setattr(main, "log_arm_params", lambda j: None)
    monkeypatch.setattr(main, "check_fstab", lambda: None)

    main.main()

    assert calls == ["scan", "wait"]


class FakeTracks:
    def __init__(self, count):
        self.count_value = count

    def filter_by(self, **kwargs):
        return self

    def count(self):
        return self.count_value


@pytest.mark.parametrize("listed, scans_again", [(3, False), (0, True)])
def test_makemkv_mkv_reuses_listed_titles(monkeypatch, listed, scans_again):
    scanned = []
    monkeypatch.setattr(makemkv.utils, "get_drive_mode", lambda devpath: "manual")
    monkeypatch.setattr(makemkv, "get_track_info", lambda index, job: scanned.append(index))
    monkeypatch.setattr(makemkv, "manual_wait", lambda job: True)
    monkeypatch.setattr(makemkv, "process_single_tracks", lambda job, rawpath, mode: None)
    monkeypatch.setattr(makemkv.db.session, "commit", lambda: None)
    job = SimpleNamespace(devpath="/dev/sr0", drive=SimpleNamespace(mdisc=0), tracks=FakeTracks(listed),
                          config=SimpleNamespace(MAINFEATURE=False), status=None)

    makemkv.makemkv_mkv(job, "/raw")

    assert (scanned == [0]) is scans_again
