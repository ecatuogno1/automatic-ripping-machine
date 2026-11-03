"""'In library' label for finished jobs whose title Radarr/Sonarr already has a file for."""
import secrets
import types

import pytest
import requests

import arm.config.config as cfg
from arm.ui import arr_library

MOVIES = [{"imdbId": "tt0000001", "hasFile": True}, {"imdbId": "tt0000002", "hasFile": False}, "junk"]
SERIES = [{"imdbId": "tt0000003", "statistics": {"episodeFileCount": 4}},
          {"imdbId": "tt0000004", "statistics": {"episodeFileCount": 0}}]


class Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


@pytest.fixture
def apps(monkeypatch):
    """Configure Radarr and Sonarr, serve canned lists and record every request."""
    credential = secrets.token_hex(16)
    for prefix in ("RADARR", "SONARR"):
        monkeypatch.setitem(cfg.arm_config, f"{prefix}_URL", f"https://{prefix.lower()}.example")
        monkeypatch.setitem(cfg.arm_config, f"{prefix}_API_KEY", credential)
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response(SERIES if url.endswith("/series") else MOVIES)

    monkeypatch.setattr(arr_library.requests, "get", get)
    arr_library.clear()
    yield types.SimpleNamespace(calls=calls, credential=credential)
    arr_library.clear()


def job(imdb_id, video_type="movie", status="success"):
    return types.SimpleNamespace(job_id=1, imdb_id=imdb_id, video_type=video_type, status=status)


def test_movie_with_a_file_in_radarr_is_in_library(apps):
    assert arr_library.in_library(job("tt0000001")) == "Radarr"
    assert arr_library.in_library(job("tt0000002")) is None
    assert arr_library.in_library(job("tt9999999")) is None
    assert len(apps.calls) == 1
    url, kwargs = apps.calls[0]
    assert url == "https://radarr.example/api/v3/movie"
    assert kwargs["headers"] == {"X-Api-Key": apps.credential}
    assert kwargs["timeout"]


def test_series_with_episode_files_in_sonarr_is_in_library(apps):
    assert arr_library.in_library(job("tt0000003", "series")) == "Sonarr"
    assert arr_library.in_library(job("tt0000004", "series")) is None
    assert apps.calls[0][0] == "https://sonarr.example/api/v3/series"


def test_unfinished_or_unidentified_jobs_are_not_looked_up(apps):
    assert arr_library.in_library(job("tt0000001", status="ripping")) is None
    assert arr_library.in_library(job(None)) is None
    assert arr_library.in_library(job("tt0000001", "unknown")) is None
    assert apps.calls == []


def test_unconfigured_app_is_not_asked(apps, monkeypatch):
    monkeypatch.setitem(cfg.arm_config, "RADARR_API_KEY", "")
    assert arr_library.in_library(job("tt0000001")) is None
    assert apps.calls == []


def test_list_is_cached_and_refreshed_after_the_ttl(apps, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(arr_library.time, "monotonic", lambda: now[0])
    arr_library.in_library(job("tt0000001"))
    now[0] += arr_library.TTL_SECONDS - 1
    arr_library.in_library(job("tt0000001"))
    assert len(apps.calls) == 1
    now[0] += 2
    arr_library.in_library(job("tt0000001"))
    assert len(apps.calls) == 2


def test_unreachable_app_shows_nothing_and_is_retried_later(apps, monkeypatch, caplog):
    now = [1000.0]
    monkeypatch.setattr(arr_library.time, "monotonic", lambda: now[0])

    def refuse(url, **kwargs):
        apps.calls.append((url, kwargs))
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(arr_library.requests, "get", refuse)
    assert arr_library.in_library(job("tt0000001")) is None
    assert arr_library.in_library(job("tt0000001")) is None
    assert len(apps.calls) == 1
    assert apps.credential not in caplog.text
    now[0] += arr_library.RETRY_SECONDS + 1
    arr_library.in_library(job("tt0000001"))
    assert len(apps.calls) == 2


def test_history_and_job_detail_show_the_label(apps, monkeypatch):
    from arm.ui import app, db
    import arm.ui.routes  # noqa: F401
    import arm.ui.utils as ui_utils
    from arm.models.job import Job

    monkeypatch.setattr(ui_utils, "metadata_selector", lambda *args, **kwargs: None)
    monkeypatch.setattr(Job, "parse_udev", lambda self: setattr(self, "disctype", "bluray"))
    monkeypatch.setattr(Job, "get_pid", lambda self: None)
    with app.app_context():
        db.create_all()
        app.config.update(TESTING=True, LOGIN_DISABLED=True)
        found = Job("/dev/sr0")
        for field, value in {"title": "Found", "video_type": "movie", "imdb_id": "tt0000001",
                             "status": "success", "logfile": "found.log"}.items():
            setattr(found, field, value)
        db.session.add(found)
        db.session.commit()
        client = app.test_client()
        history = client.get("/history").get_data(as_text=True)
        detail = client.get(f"/jobdetail?job_id={found.job_id}").get_data(as_text=True)
        db.session.delete(found)
        db.session.commit()
    assert "In library" in history
    assert "In library" in detail
