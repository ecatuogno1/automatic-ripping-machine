"""Tests for VERIFY_RIP_OUTPUT: ffprobe checks of ripped files before they are moved (subprocess mocked)"""
import json
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

import arm.config.config as cfg
from arm.ripper import arm_ripper, utils, verify


def probe_result(duration, packets, video_duration=None):
    stream = {"codec_type": "video", "nb_read_packets": str(packets)}
    if video_duration is not None:
        stream["tags"] = {"DURATION": video_duration}
    return {"format": {"duration": str(duration), "start_time": "0.000000"},
            "streams": [stream, {"codec_type": "audio", "nb_read_packets": "9000"}]}


def tail_result(last_end, packets=60, frames=60):
    step = 30.0 / packets
    return {"packets": [{"pts_time": str(last_end - step * (packets - i)), "duration_time": str(step)}
                        for i in range(packets)],
            "streams": [{"nb_read_frames": frames}]}


class FakeFfprobe:
    """Answers the header probe and the tail probe for each file name"""

    def __init__(self, files):
        self.files = files
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        name = command[-1].rsplit("/", 1)[-1]
        header, tail = self.files[name]
        answer = tail if "-read_intervals" in command else header
        if isinstance(answer, Exception):
            raise answer
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(answer), stderr="")


def make_job(tracks):
    query = mock.MagicMock()
    query.all.return_value = [SimpleNamespace(filename=name, orig_filename=name, length=length)
                              for name, length in tracks]
    return SimpleNamespace(tracks=query)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setitem(cfg.arm_config, "VERIFY_RIP_OUTPUT", True)
    monkeypatch.setattr(verify.shutil, "which", lambda name: "/usr/bin/" + name)


def write(folder, name, size):
    (folder / name).write_bytes(b"\0" * size)


def run_verify(monkeypatch, folder, job, files):
    fake = FakeFfprobe(files)
    monkeypatch.setattr(verify.subprocess, "run", fake)
    verify.verify_rip_output(job, str(folder))
    return fake


def test_disabled_runs_nothing(monkeypatch, tmp_path):
    monkeypatch.setitem(cfg.arm_config, "VERIFY_RIP_OUTPUT", False)
    run = mock.Mock()
    monkeypatch.setattr(verify.subprocess, "run", run)
    verify.verify_rip_output(make_job([]), str(tmp_path))
    run.assert_not_called()


def test_missing_ffprobe_warns_and_skips(monkeypatch, tmp_path, caplog):
    monkeypatch.setitem(cfg.arm_config, "VERIFY_RIP_OUTPUT", True)
    monkeypatch.setattr(verify.shutil, "which", lambda name: None)
    run = mock.Mock()
    monkeypatch.setattr(verify.subprocess, "run", run)
    verify.verify_rip_output(make_job([]), str(tmp_path))
    run.assert_not_called()
    assert "ffprobe was not found" in caplog.text


def test_complete_rip_passes(enabled, monkeypatch, tmp_path):
    write(tmp_path, "title_t00.mkv", 300)
    write(tmp_path, "title_t01.mkv", 100)
    job = make_job([("title_t00.mkv", 5400), ("title_t01.mkv", 600)])
    fake = run_verify(monkeypatch, tmp_path, job, {
        # audio outlasts video: the video track's own duration is what the tail must reach
        "title_t00.mkv": (probe_result(5410.2, 129000, "01:30:00.500000000"), tail_result(5400.4)),
        "title_t01.mkv": (probe_result(598.0, 14000), tail_result(597.9)),
    })
    assert len(fake.calls) == 4


def test_truncated_file_with_full_header_fails(enabled, monkeypatch, tmp_path):
    write(tmp_path, "title_t00.mkv", 300)
    job = make_job([("title_t00.mkv", 5400)])
    with pytest.raises(utils.RipperException) as error:
        run_verify(monkeypatch, tmp_path, job, {
            "title_t00.mkv": (probe_result(5400.0, 129000), tail_result(2710.0)),
        })
    assert "title_t00.mkv: truncated" in str(error.value)
    assert str(tmp_path) in str(error.value)


def test_undecodable_tail_fails(enabled, monkeypatch, tmp_path):
    write(tmp_path, "title_t00.mkv", 300)
    with pytest.raises(utils.RipperException, match="could not be decoded"):
        run_verify(monkeypatch, tmp_path, make_job([]), {
            "title_t00.mkv": (probe_result(5400.0, 129000), tail_result(5400.0, frames=0)),
        })


def test_runtime_shorter_than_scan_fails(enabled, monkeypatch, tmp_path):
    write(tmp_path, "title_t00.mkv", 300)
    job = make_job([("title_t00.mkv", 5400)])
    with pytest.raises(utils.RipperException, match="disc scan reported 5400s"):
        run_verify(monkeypatch, tmp_path, job, {
            "title_t00.mkv": (probe_result(4100.0, 98000), tail_result(4100.0)),
        })


def test_unreadable_file_fails(enabled, monkeypatch, tmp_path):
    write(tmp_path, "title_t00.mkv", 300)
    broken = subprocess.CalledProcessError(1, "ffprobe", stderr="Invalid data found when processing input")
    with pytest.raises(utils.RipperException, match="Invalid data found"):
        run_verify(monkeypatch, tmp_path, make_job([]), {"title_t00.mkv": (broken, None)})


def test_every_failure_is_reported(enabled, monkeypatch, tmp_path):
    write(tmp_path, "a.mkv", 300)
    write(tmp_path, "b.mkv", 100)
    timeout = subprocess.TimeoutExpired("ffprobe", 1200)
    with pytest.raises(utils.RipperException) as error:
        run_verify(monkeypatch, tmp_path, make_job([]), {
            "a.mkv": (probe_result(100.0, 0), None),
            "b.mkv": (timeout, None),
        })
    assert "2 of 2 file(s)" in str(error.value)
    assert "a.mkv: no readable video" in str(error.value)
    assert "b.mkv: ffprobe did not finish" in str(error.value)


def test_still_image_extras_pass(enabled, monkeypatch, tmp_path):
    write(tmp_path, "title_t00.mkv", 300)
    write(tmp_path, "title_t05.mkv", 20)
    write(tmp_path, "title_t06.mkv", 10)
    job = make_job([("title_t00.mkv", 5400), ("title_t05.mkv", 2875), ("title_t06.mkv", 30)])
    fake = run_verify(monkeypatch, tmp_path, job, {
        "title_t00.mkv": (probe_result(5400.0, 129000), tail_result(5400.0)),
        # a gallery: 18 pictures over 424 s for a title scanned at 2875 s
        "title_t05.mkv": (probe_result(424.0, 18), None),
        # 3 pictures in 0.1 s for a title scanned at 30 s
        "title_t06.mkv": (probe_result(0.1, 3), None),
    })
    assert len(fake.calls) == 4


def test_main_title_is_never_a_still(enabled, monkeypatch, tmp_path):
    write(tmp_path, "title_t00.mkv", 300)
    job = make_job([("title_t00.mkv", 2875)])
    with pytest.raises(utils.RipperException, match="disc scan reported 2875s"):
        run_verify(monkeypatch, tmp_path, job, {"title_t00.mkv": (probe_result(424.0, 18), None)})


def test_no_video_files_fails(enabled, monkeypatch, tmp_path):
    (tmp_path / "notes.txt").write_text("x")
    with pytest.raises(utils.RipperException, match="no video files"):
        run_verify(monkeypatch, tmp_path, make_job([]), {})


def test_disc_backup_folder_is_skipped(enabled, monkeypatch, tmp_path):
    (tmp_path / "BDMV").mkdir()
    fake = run_verify(monkeypatch, tmp_path, make_job([]), {})
    assert fake.calls == []


def test_failed_verification_keeps_files_and_stops_the_job(monkeypatch, tmp_path):
    """rip_visual_media runs the check before moving files, deleting raw files or notifying"""
    config = SimpleNamespace(TRANSCODE_PATH=str(tmp_path / "transcode"), COMPLETED_PATH=str(tmp_path / "completed"),
                             SKIP_TRANSCODE=True, NOTIFY_RIP=False, MAINFEATURE=False, RIPMETHOD="mkv")
    job = SimpleNamespace(config=config, video_type="movie", devpath="/dev/sr0", disctype="bluray",
                          title="Movie", title_manual=None, status=None)
    raw = tmp_path / "raw"
    raw.mkdir()
    for name in ("database_updater", "save_disc_poster", "notify", "move_movie_poster",
                 "scan_emby", "set_permissions"):
        monkeypatch.setattr(utils, name, mock.Mock())
    monkeypatch.setattr(utils, "convert_job_type", lambda video_type: "movies")
    monkeypatch.setattr(utils, "fix_job_title", lambda job: "Movie")
    monkeypatch.setattr(utils, "check_for_dupe_folder", lambda dupes, path, job: path)
    delete = mock.Mock()
    monkeypatch.setattr(utils, "delete_raw_files", delete)
    monkeypatch.setattr(arm_ripper.db.session, "commit", mock.Mock())
    monkeypatch.setattr(arm_ripper.makemkv, "makemkv", lambda job: str(raw))
    move = mock.Mock()
    monkeypatch.setattr(arm_ripper, "move_files_post", move)
    monkeypatch.setattr(arm_ripper, "notify_exit", mock.Mock())
    checked = mock.Mock(side_effect=utils.RipperException("Rip verification failed: bad"))
    monkeypatch.setattr(verify, "verify_rip_output", checked)

    with pytest.raises(utils.RipperException, match="Rip verification failed"):
        arm_ripper.rip_visual_media(False, job, "log", 0)

    checked.assert_called_once_with(job, str(raw))
    move.assert_not_called()
    # only the empty transcode folder (unused with SKIP_TRANSCODE) is removed, never the raw files
    delete.assert_called_once_with([str(tmp_path / "transcode" / "movies" / "Movie")])
