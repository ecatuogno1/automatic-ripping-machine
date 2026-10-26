"""Radarr/Sonarr lookup as a last identification source (ARR_IDENTIFY)."""
import secrets
import types

import pytest
import requests

import arm.config.config as cfg
from arm.ripper import arr, identify, utils

POSTER = "https://image.example/poster.jpg"


def movie(title, year, **extra):
    return {"title": title, "year": year, "imdbId": f"tt{year}0", "tmdbId": year,
            "images": [{"coverType": "fanart", "remoteUrl": "https://image.example/fanart.jpg"},
                       {"coverType": "poster", "remoteUrl": POSTER}], **extra}


class Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


@pytest.fixture
def lookups(monkeypatch):
    """Radarr and Sonarr configured with ARR_IDENTIFY on; set .movies/.series to the canned lookup results."""
    state = types.SimpleNamespace(movies=[], series=[], calls=[], credential=secrets.token_hex(16))
    monkeypatch.setitem(cfg.arm_config, "ARR_IDENTIFY", True)
    for prefix in ("RADARR", "SONARR"):
        monkeypatch.setitem(cfg.arm_config, f"{prefix}_URL", f"https://{prefix.lower()}.example")
        monkeypatch.setitem(cfg.arm_config, f"{prefix}_API_KEY", state.credential)

    def get(url, **kwargs):
        state.calls.append((url, kwargs))
        return Response(state.series if "/series/" in url else state.movies)

    monkeypatch.setattr(arr.requests, "get", get)
    return state


def test_off_unless_arr_identify_is_set(lookups, monkeypatch):
    monkeypatch.setitem(cfg.arm_config, "ARR_IDENTIFY", False)
    lookups.movies = [movie("The Matrix", 1999)]
    assert arr.lookup("THE+MATRIX") is None
    assert lookups.calls == []


def test_exact_title_match_is_returned_in_omdb_format(lookups):
    lookups.movies = [movie("The Matrix", 1999), movie("The Matrix Reloaded", 2003)]
    result = arr.lookup("THE+MATRIX", "1999")
    assert result == {"Search": [{"Title": "The Matrix", "Year": "1999", "Type": "movie",
                                  "imdbID": "tt19990", "Poster": POSTER}]}
    url, kwargs = lookups.calls[0]
    assert url == "https://radarr.example/api/v3/movie/lookup"
    assert kwargs["params"] == {"term": "THE MATRIX"}
    assert kwargs["headers"] == {"X-Api-Key": lookups.credential}
    assert kwargs["timeout"]


def test_label_without_the_article_and_alternate_titles_match(lookups):
    lookups.movies = [movie("Léon: The Professional", 1994, alternateTitles=[{"title": "Léon"}])]
    assert arr.lookup("LEON")["Search"][0]["Title"] == "Léon: The Professional"
    lookups.movies = [movie("The Matrix", 1999)]
    assert arr.lookup("MATRIX")["Search"][0]["Year"] == "1999"


def test_loose_results_are_not_accepted(lookups):
    lookups.movies = [movie("Star Wars", 1977), movie("Star Trek", 2009)]
    assert arr.lookup("STAR") is None


def test_same_title_is_narrowed_by_year_or_the_year_before(lookups):
    lookups.movies = [movie("Dune", 1984), movie("Dune", 2021)]
    assert arr.lookup("DUNE") is None
    assert arr.lookup("DUNE", "2021")["Search"][0]["Year"] == "2021"
    assert arr.lookup("DUNE", "1985")["Search"][0]["Year"] == "1984"
    assert arr.lookup("DUNE", "2000") is None


def test_series_comes_from_sonarr(lookups):
    lookups.series = [{"title": "Firefly", "year": 2002, "imdbId": "tt0303461", "images": []}]
    result = arr.lookup("FIREFLY")
    assert result["Search"][0]["Type"] == "series"
    assert result["Search"][0]["imdbID"] == "tt0303461"
    assert lookups.calls[1][0] == "https://sonarr.example/api/v3/series/lookup"


def test_unreachable_app_is_skipped(lookups, monkeypatch, caplog):
    def get(url, **kwargs):
        if "radarr" in url:
            raise requests.exceptions.ConnectTimeout("timed out")
        return Response([{"title": "Firefly", "year": 2002}])

    monkeypatch.setattr(arr.requests, "get", get)
    assert arr.lookup("FIREFLY")["Search"][0]["Title"] == "Firefly"
    assert "Radarr lookup failed (ConnectTimeout)" in caplog.text
    assert lookups.credential not in caplog.text


@pytest.fixture
def video_job(monkeypatch):
    monkeypatch.setattr(utils, "database_updater", lambda args, job: [setattr(job, k, v) for k, v in args.items()])
    return types.SimpleNamespace(title="THE_MATRIX", year=None, hasnicetitle=False)


def test_get_video_details_falls_back_to_the_lookup(lookups, monkeypatch, video_job):
    monkeypatch.setattr(identify, "identify_loop", lambda *args: None)  # OMDb/TMDB found nothing
    lookups.movies = [movie("The Matrix", 1999)]
    identify.get_video_details(video_job)
    assert video_job.title == "The-Matrix"
    assert video_job.imdb_id == "tt19990"
    assert video_job.hasnicetitle is True


def test_get_video_details_keeps_what_omdb_found(lookups, monkeypatch, video_job):
    monkeypatch.setattr(identify, "identify_loop", lambda job, *args: setattr(job, "hasnicetitle", True))
    identify.get_video_details(video_job)
    assert lookups.calls == []


def test_setting_is_off_by_default_and_documented():
    import json
    import os
    import yaml

    root = os.path.join(os.path.dirname(__file__), "..", "..")
    with open(os.path.join(root, "setup", "arm.yaml")) as defaults_file:
        assert yaml.safe_load(defaults_file)["ARR_IDENTIFY"] is False
    with open(os.path.join(root, "arm", "ui", "comments.json")) as comments_file:
        assert json.load(comments_file)["ARR_IDENTIFY"].startswith("#")
