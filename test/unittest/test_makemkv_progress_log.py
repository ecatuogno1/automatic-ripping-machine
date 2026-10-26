"""Tests for the MakeMKV progress log path when LOGPATH contains spaces"""
import os
from types import SimpleNamespace

import arm.ui  # noqa: F401 - import order: arm.ui before the ripper (arm.models)
from arm.ripper import makemkv


def progress_job(tmp_path):
    logpath = tmp_path / "arm logs"
    (logpath / "progress").mkdir(parents=True)
    track = SimpleNamespace(track_number="0", length=6000, filename="title_t00.mkv", process=True)
    return SimpleNamespace(job_id=12, devpath="/dev/sr0", no_of_titles=1, tracks=[track],
                           config=SimpleNamespace(LOGPATH=str(logpath), MKV_ARGS="", MINLENGTH=600,
                                                  MAXLENGTH=99999))


def test_progress_log_path_is_not_shell_quoted(tmp_path):
    job = progress_job(tmp_path)
    assert makemkv.progress_log(job) == os.path.join(job.config.LOGPATH, "progress", "12.log")


def test_single_track_rip_uses_the_path_the_ui_reads(tmp_path, monkeypatch):
    """The UI (json_api) reads LOGPATH/progress/<job_id>.log and .log.batchinfo unquoted"""
    job = progress_job(tmp_path)
    commands = []
    monkeypatch.setattr(makemkv, "run", lambda cmd, select: commands.append(cmd) or iter([]))
    makemkv.process_single_tracks(job, str(tmp_path / "raw"), "manual")
    expected = os.path.join(job.config.LOGPATH, "progress", "12.log")
    assert f"--progress={expected}" in commands[0]
    assert os.path.isfile(expected + ".batchinfo")
