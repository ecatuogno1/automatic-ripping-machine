"""KEEP_CRC_IDENTITY keeps the ARM online database (crc64) answer for a DVD."""

import json
from types import SimpleNamespace

import pytest

import arm.config.config as cfg
from arm.ripper import identify

CRC_ANSWER = {"success": True, "results": {"0": {
    "title": "The Kingdom", "year": "2007", "imdb_id": "tt0431197", "video_type": "movie",
    "poster_img": "https://example.com/kingdom.jpg"}}}


@pytest.fixture
def identify_known_dvd(monkeypatch):
    """identify_dvd() for a disc the crc64 database knows; returns the title searches made."""
    searches = []
    response = SimpleNamespace(read=lambda: json.dumps(CRC_ANSWER).encode())
    monkeypatch.setattr(identify.pydvdid, "compute", lambda path: "ade5cef9590c59d1")
    monkeypatch.setattr(identify.urllib.request, "urlopen", lambda *args, **kwargs: response)
    monkeypatch.setattr(identify.utils, "database_updater",
                        lambda args, job: [setattr(job, key, value) for key, value in args.items()])
    monkeypatch.setattr(identify, "metadata_selector",
                        lambda job, title=None, year=None: searches.append(title))
    monkeypatch.setattr(identify, "identify_loop", lambda *args: None)
    monkeypatch.setattr(identify, "arm_subprocess", lambda *args, **kwargs: None)

    def run(keep):
        monkeypatch.setitem(cfg.arm_config, "KEEP_CRC_IDENTITY", keep)
        job = SimpleNamespace(label="THE_KINGDOM", year=None, title=None, mountpoint="/mnt/dev/sr0",
                              devpath="/dev/sr0", pretty_table=lambda: "")
        assert identify.identify_dvd(job) is True
        return job, searches
    return run


def test_keep_crc_identity_skips_the_title_search(identify_known_dvd):
    job, searches = identify_known_dvd(True)
    assert searches == []
    assert job.title == "The Kingdom"
    assert job.imdb_id == "tt0431197"


def test_default_still_runs_the_title_search(identify_known_dvd):
    _, searches = identify_known_dvd(False)
    assert searches == ["THE_KINGDOM"]


def test_unknown_disc_is_searched_even_with_keep_crc_identity(identify_known_dvd, monkeypatch):
    monkeypatch.setitem(CRC_ANSWER, "success", False)
    _, searches = identify_known_dvd(True)
    assert searches == ["THE_KINGDOM"]
