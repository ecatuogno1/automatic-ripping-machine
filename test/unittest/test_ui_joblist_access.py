"""What /json?mode=joblist returns to a client that is not signed in, and which routes allow cross-origin reads"""
import datetime

import pytest

from arm.ui import app, db, json_api
import arm.ui.utils as ui_utils
from arm.models.config import Config
from arm.models.job import Job


@pytest.fixture
def app_db():
    with app.app_context():
        db.create_all()
        db.engine.dispose()
        yield db
        db.session.rollback()
        Config.query.delete()
        Job.query.delete()
        db.session.commit()
        db.engine.dispose()


@pytest.fixture
def active_job(app_db):
    """An active job (no Job.__init__: that probes the drive) with a per-job config"""
    job = Job.__mapper__.class_manager.new_instance()
    job.status, job.stage, job.disctype, job.video_type = "active", "", "dvd", "movie"
    job.title, job.title_manual, job.year, job.devpath = "Example Film", None, "1999", "/dev/sr0"
    job.poster_url, job.start_time = "None", datetime.datetime(2026, 1, 2, 3, 4)
    job.logfile, job.path = "Example_Film_123.log", "/home/arm/media/completed/movies/Example Film (1999)"
    job.errors, job.crc_id, job.label = "MakeMKV failed", "crc-example", "EXAMPLE_FILM"
    app_db.session.add(job)
    app_db.session.commit()
    config = Config.__mapper__.class_manager.new_instance()
    config.job_id, config.RIPMETHOD, config.MAINFEATURE = job.job_id, "mkv", False
    config.MINLENGTH, config.MAXLENGTH = "600", "99999"
    config.RAW_PATH, config.EMBY_USERNAME = "/home/arm/media/raw", "emby-operator"
    app_db.session.add(config)
    app_db.session.commit()
    return job


def poll_joblist(monkeypatch, authenticated):
    monkeypatch.setattr(ui_utils, "authenticated_state", lambda: authenticated)
    monkeypatch.setattr(json_api, "authenticated_state", lambda: authenticated)
    body = app.test_client().get("/json?mode=joblist").get_json()
    assert body["success"] is True
    assert body["authenticated"] is authenticated
    return body, next(iter(body["results"].values()))


def test_anonymous_joblist_has_only_the_job_cards_fields(active_job, monkeypatch):
    body, entry = poll_joblist(monkeypatch, authenticated=False)
    assert entry["job_id"] == str(active_job.job_id)
    assert entry["title"] == "Example Film"
    assert entry["status"] == "active"
    for private in ("logfile", "path", "errors", "crc_id", "label", "pid", "mountpoint"):
        assert private not in entry
    assert set(entry) <= json_api.PUBLIC_JOB_FIELDS | {"config"}
    assert entry["config"] == {"RIPMETHOD": "mkv", "MAINFEATURE": "False", "MINLENGTH": "600",
                               "MAXLENGTH": "99999"}
    assert "/home/arm/media" not in str(body)
    assert "emby-operator" not in str(body)


def test_signed_in_joblist_keeps_the_full_job(active_job, monkeypatch):
    _, entry = poll_joblist(monkeypatch, authenticated=True)
    assert entry["logfile"] == "Example_Film_123.log"  # the job card's "View logfile" button
    assert entry["errors"] == "MakeMKV failed"
    assert entry["config"]["RAW_PATH"] == "/home/arm/media/raw"


def test_only_the_json_api_answers_cross_origin(app_db, monkeypatch):
    monkeypatch.setattr(ui_utils, "authenticated_state", lambda: False)
    monkeypatch.setattr(json_api, "authenticated_state", lambda: False)
    client = app.test_client()
    origin = {"Origin": "https://elsewhere.example.invalid"}
    joblist = client.get("/json?mode=joblist", headers=origin)
    assert joblist.headers.get("Access-Control-Allow-Origin") == "*"
    assert "Access-Control-Allow-Credentials" not in joblist.headers
    for path in ("/login", "/settings", "/jobdetail?job_id=1", "/static/js/common.js"):
        assert "Access-Control-Allow-Origin" not in client.get(path, headers=origin).headers, path
