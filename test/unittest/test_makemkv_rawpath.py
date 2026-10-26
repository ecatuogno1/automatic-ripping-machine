"""Tests for the raw folder MakeMKV rips into (setup_rawpath)"""
import os
from types import SimpleNamespace

import pytest

import arm.ui  # noqa: F401 - import order: arm.ui before the ripper (arm.models)
from arm.ripper import makemkv


def raw_job(tmp_path, title="Not Identified", stage="179264974469"):
    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    return SimpleNamespace(title=title, stage=stage, config=SimpleNamespace(RAW_PATH=str(raw)))


def test_new_title_gets_its_own_folder(tmp_path):
    job = raw_job(tmp_path)
    path = makemkv.setup_rawpath(job, os.path.join(job.config.RAW_PATH, job.title))
    assert path == os.path.join(job.config.RAW_PATH, job.title)
    assert os.path.isdir(path)


def test_existing_folder_is_not_reused(tmp_path):
    job = raw_job(tmp_path)
    (tmp_path / "raw" / job.title).mkdir()  # an earlier rip of the same title
    path = makemkv.setup_rawpath(job, os.path.join(job.config.RAW_PATH, job.title))
    assert path == os.path.join(job.config.RAW_PATH, f"{job.title}_{job.stage}")
    assert os.path.isdir(path)


def test_folder_created_by_another_job_meanwhile_is_not_shared(tmp_path, monkeypatch):
    """Two drives ripping discs with the same title: the other job creates the folder first"""
    job = raw_job(tmp_path)
    shared = os.path.join(job.config.RAW_PATH, job.title)
    real_makedirs = os.makedirs

    def other_job_wins(path, *args, **kwargs):
        if path == shared and not os.path.isdir(shared):
            real_makedirs(shared)  # the other job's makedirs ran between our check and ours
        return real_makedirs(path, *args, **kwargs)

    monkeypatch.setattr(makemkv.os, "makedirs", other_job_wins)
    path = makemkv.setup_rawpath(job, shared)
    assert path != shared
    assert path == os.path.join(job.config.RAW_PATH, f"{job.title}_{job.stage}")


def test_folder_that_cannot_be_created_raises(tmp_path, monkeypatch):
    job = raw_job(tmp_path)

    def denied(path, *args, **kwargs):
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr(makemkv.os, "makedirs", denied)
    with pytest.raises(OSError, match="Couldn't create the base file path"):
        makemkv.setup_rawpath(job, os.path.join(job.config.RAW_PATH, job.title))


def test_both_folders_taken_raises(tmp_path):
    job = raw_job(tmp_path)
    (tmp_path / "raw" / job.title).mkdir()
    (tmp_path / "raw" / f"{job.title}_{job.stage}").mkdir()
    with pytest.raises(OSError, match="already exists"):
        makemkv.setup_rawpath(job, os.path.join(job.config.RAW_PATH, job.title))
