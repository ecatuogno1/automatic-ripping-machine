"""IMDB_ID_IN_NAME: the IMDb id in the movie/series folder and main feature name"""
import os
from types import SimpleNamespace

import pytest

import arm.config.config as cfg
from arm.ripper import utils


def fake_job(**values):
    job = SimpleNamespace(title="The Matrix", title_manual=None, year="1999", imdb_id="tt0133093",
                          imdb_id_manual=None)
    for key, value in values.items():
        setattr(job, key, value)
    return job


@pytest.fixture
def style(monkeypatch):
    values = dict(cfg.arm_config)
    monkeypatch.setattr(cfg, "arm_config", values)
    return lambda name: values.update(IMDB_ID_IN_NAME=name)


def test_default_name_is_unchanged(style):
    style("")
    assert utils.fix_job_title(fake_job()) == "The Matrix (1999)"


def test_jellyfin_style(style):
    style("jellyfin")
    assert utils.fix_job_title(fake_job()) == "The Matrix (1999) [imdbid-tt0133093]"


def test_plex_style(style):
    style("plex")
    assert utils.fix_job_title(fake_job()) == "The Matrix (1999) {imdb-tt0133093}"


def test_without_year(style):
    style("jellyfin")
    assert utils.fix_job_title(fake_job(year="0000")) == "The Matrix [imdbid-tt0133093]"


@pytest.mark.parametrize("imdb_id", [None, "", "N/A", "tt12", "tt0133093/../x"])
def test_no_valid_id_no_suffix(style, imdb_id):
    style("jellyfin")
    assert utils.fix_job_title(fake_job(imdb_id=imdb_id)) == "The Matrix (1999)"


def test_unknown_style_is_off(style):
    style("kodi")
    assert utils.fix_job_title(fake_job()) == "The Matrix (1999)"


def test_manual_title_uses_manual_id(style):
    style("jellyfin")
    job = fake_job(title_manual="Matrix Reloaded", year="2003", imdb_id="tt0234215", imdb_id_manual="tt0234215")
    assert utils.fix_job_title(job) == "Matrix Reloaded (2003) [imdbid-tt0234215]"


def test_custom_title_does_not_reuse_identified_id(style):
    style("jellyfin")
    # "Custom title" sets title_manual but leaves the identified id, which may be for another title
    job = fake_job(title_manual="Home Videos", year="2010")
    assert utils.fix_job_title(job) == "Home Videos (2010)"


def test_main_feature_file_gets_id(style, tmp_path, monkeypatch):
    style("jellyfin")
    moved = []
    monkeypatch.setattr(utils, "move_files_main", lambda src, dst, base: moved.append(dst))
    folder = tmp_path / "The Matrix (1999) [imdbid-tt0133093]"
    job = fake_job(path=str(folder), video_type="movie", hasnicetitle=True,
                   config=SimpleNamespace(EXTRAS_SUB="extras", DEST_EXT="mkv"))
    utils.move_files(str(tmp_path), "title_t00.mkv", job, True)
    assert moved == [os.path.join(str(folder), "The Matrix (1999) [imdbid-tt0133093].mkv")]
