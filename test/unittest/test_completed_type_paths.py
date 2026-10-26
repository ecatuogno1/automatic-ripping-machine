"""COMPLETED_MOVIES_PATH / COMPLETED_TV_PATH / COMPLETED_DATA_PATH"""
import logging
import os
from types import SimpleNamespace

import pytest

import arm.config.config as cfg
from arm.ripper import arm_ripper, utils


@pytest.fixture
def config(monkeypatch, tmp_path):
    values = dict(cfg.arm_config)
    values.update(COMPLETED_MOVIES_PATH="", COMPLETED_TV_PATH="", COMPLETED_DATA_PATH="")
    monkeypatch.setattr(cfg, "arm_config", values)
    return values


def fake_job(tmp_path, **values):
    job = SimpleNamespace(title="Film", title_manual=None, year="2000", video_type="movie", disctype="bluray",
                          label="FILM", config=SimpleNamespace(COMPLETED_PATH=str(tmp_path / "completed"),
                                                               TRANSCODE_PATH=str(tmp_path / "transcode"),
                                                               RAW_PATH=str(tmp_path / "raw")))
    for key, value in values.items():
        setattr(job, key, value)
    return job


@pytest.mark.parametrize("video_type, disctype, sub_folder", [
    ("movie", "bluray", "movies"), ("series", "dvd", "tv"), ("unknown", "dvd", "unidentified"),
    ("unknown", "data", "unidentified")])
def test_defaults_keep_completed_sub_folders(config, tmp_path, video_type, disctype, sub_folder):
    job = fake_job(tmp_path, video_type=video_type, disctype=disctype)
    expected = os.path.join(str(tmp_path / "completed"), sub_folder)
    assert utils.completed_type_path(job, utils.convert_job_type(video_type)) == expected


@pytest.mark.parametrize("video_type, disctype, setting", [
    ("movie", "bluray", "COMPLETED_MOVIES_PATH"), ("series", "dvd", "COMPLETED_TV_PATH"),
    ("unknown", "data", "COMPLETED_DATA_PATH")])
def test_type_path_replaces_sub_folder(config, tmp_path, video_type, disctype, setting):
    config[setting] = str(tmp_path / "library")
    job = fake_job(tmp_path, video_type=video_type, disctype=disctype)
    assert utils.completed_type_path(job, utils.convert_job_type(video_type)) == str(tmp_path / "library")


def test_unidentified_video_ignores_type_paths(config, tmp_path):
    config.update(COMPLETED_MOVIES_PATH=str(tmp_path / "Movies"), COMPLETED_TV_PATH=str(tmp_path / "TV"),
                  COMPLETED_DATA_PATH=str(tmp_path / "ISO"))
    job = fake_job(tmp_path, video_type="unknown", disctype="dvd")
    assert utils.completed_type_path(job, "unidentified") == os.path.join(str(tmp_path / "completed"), "unidentified")


def test_movie_is_completed_into_movies_path(config, tmp_path, monkeypatch):
    config["COMPLETED_MOVIES_PATH"] = str(tmp_path / "Movies")
    paths = []
    monkeypatch.setattr(utils, "check_for_dupe_folder", lambda have_dupes, path, job: path)
    monkeypatch.setattr(utils, "database_updater", lambda args, job: paths.append(args.get("path")))
    for name in ("save_disc_poster", "move_movie_poster", "scan_emby", "set_permissions", "delete_raw_files"):
        monkeypatch.setattr(utils, name, lambda *args, **kwargs: None)
    for name in ("start_transcode", "move_files_post", "notify_exit"):
        monkeypatch.setattr(arm_ripper, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(arm_ripper, "rip_with_mkv", lambda *args: False)
    job = fake_job(tmp_path, devpath="/dev/sr0", config=SimpleNamespace(
        COMPLETED_PATH=str(tmp_path / "completed"), TRANSCODE_PATH=str(tmp_path / "transcode"),
        SKIP_TRANSCODE=False))

    arm_ripper.rip_visual_media(False, job, "film.log", 0)
    assert paths == [os.path.join(str(tmp_path / "Movies"), "Film (2000)")]


def test_data_disc_is_completed_into_data_path(config, tmp_path, monkeypatch):
    config.update(COMPLETED_DATA_PATH=str(tmp_path / "ISO"), DATA_RIP_PARAMETERS="")
    moved = []
    monkeypatch.setattr(utils.subprocess, "check_output", lambda *args, **kwargs: b"")
    monkeypatch.setattr(utils, "move_files_main", lambda src, dst, base: moved.append(dst))
    (tmp_path / "raw").mkdir()
    job = fake_job(tmp_path, disctype="data", video_type="unknown", devpath="/dev/sr0", logfile="data.log")
    job.config.LOGPATH = str(tmp_path)

    assert utils.rip_data(job) is True
    assert moved == [os.path.join(str(tmp_path / "ISO"), "FILM", "FILM.iso")]


def test_setup_creates_type_paths_that_are_set(config, tmp_path):
    config.update(RAW_PATH=str(tmp_path / "raw"), TRANSCODE_PATH=str(tmp_path / "transcode"),
                  COMPLETED_PATH=str(tmp_path / "completed"), LOGPATH=str(tmp_path / "logs"),
                  COMPLETED_TV_PATH=str(tmp_path / "TV"))
    utils.arm_setup(logging.getLogger("test"))
    assert (tmp_path / "TV").is_dir()
    assert not (tmp_path / "Movies").exists()
