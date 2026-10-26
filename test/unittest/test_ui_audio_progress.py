"""Progress of an audio CD rip in the job list, with and without a known track count"""
import datetime
import logging
import types

import arm.config.config as cfg
import arm.ui.json_api as json_api

ABCDE_LOG = (
    "Grabbing track 01: Track 1...\n"
    "Ripping from sector       0 (track  1 [0:00.00])\n"
    "Grabbing track 02: Track 2...\n"
    "Ripping from sector   18000 (track  2 [0:00.00])\n"
    "Grabbing track 03: Track 3...\n"
    "Ripping from sector   36000 (track  3 [0:00.00])\n"
)


def _audio_job(tmp_path, monkeypatch, no_of_titles):
    monkeypatch.setitem(cfg.arm_config, "LOGPATH", str(tmp_path))
    (tmp_path / "music_cd.log").write_text(ABCDE_LOG)
    return types.SimpleNamespace(logfile="music_cd.log", no_of_titles=no_of_titles,
                                 start_time=datetime.datetime.now() - datetime.timedelta(minutes=6),
                                 stage=None, eta=None, progress=None, progress_round=None)


def test_unidentified_cd_shows_current_track_without_errors(tmp_path, monkeypatch, caplog):
    # MusicBrainz didn't know the disc, so no_of_titles was never set
    job = _audio_job(tmp_path, monkeypatch, None)
    results = {}
    with caplog.at_level(logging.DEBUG):
        json_api.process_audio_logfile(job.logfile, job, results)

    assert results["stage"] == "Track: 3"
    assert job.stage == "Track: 3"
    assert job.eta == "Unknown"
    assert job.progress == 0
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_identified_cd_shows_track_of_total_and_progress(tmp_path, monkeypatch):
    job = _audio_job(tmp_path, monkeypatch, 12)
    results = {}
    json_api.process_audio_logfile(job.logfile, job, results)

    assert results["stage"] == "Track: 3/12"
    assert job.progress == round(100 * 3 / 13)
    assert "@" in job.eta
