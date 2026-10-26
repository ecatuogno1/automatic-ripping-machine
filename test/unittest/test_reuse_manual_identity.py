"""REUSE_MANUAL_IDENTITY: a re-inserted DVD takes the title set by hand for the same disc."""

import pytest

import arm.config.config as cfg
from arm.models.job import Job
from arm.ripper import identify
from arm.ui import app, db


def make_job(monkeypatch, crc_id, **fields):
    monkeypatch.setattr(Job, "parse_udev", lambda self: setattr(self, "disctype", "dvd"))
    monkeypatch.setattr(Job, "get_pid", lambda self: None)
    job = Job("/dev/sr0")
    job.label = "THE_KINGDOM"
    job.crc_id = crc_id
    for key, value in fields.items():
        setattr(job, key, value)
    db.session.add(job)
    db.session.commit()
    return job


@pytest.fixture
def database(monkeypatch):
    with app.app_context():
        db.create_all()
        monkeypatch.setitem(cfg.arm_config, "REUSE_MANUAL_IDENTITY", True)
        yield
        db.session.rollback()


def test_new_job_takes_the_earlier_manual_identity(database, monkeypatch):
    make_job(monkeypatch, "aa11", status="fail", title="The-Kingdom", title_manual="The-Kingdom",
             year="2007", year_manual="2007", imdb_id_manual="tt0431197", video_type_manual="movie",
             poster_url_manual="https://example.com/k.jpg")
    job = make_job(monkeypatch, "aa11", title="Kingdom-of-the-Vampire", year="2007", imdb_id="tt0839875")
    assert identify.reuse_manual_identity(job) is True
    assert job.title == "The-Kingdom"
    assert job.title_manual == "The-Kingdom"
    assert job.imdb_id == "tt0431197"
    assert job.video_type == "movie"
    assert job.poster_url == "https://example.com/k.jpg"
    assert job.hasnicetitle is True


def test_custom_title_keeps_its_year(database, monkeypatch):
    make_job(monkeypatch, "bb22", status="fail", title="Family-Holiday", title_manual="Family-Holiday", year="2019")
    job = make_job(monkeypatch, "bb22", title="DVD_VIDEO", imdb_id="tt9000001")
    assert identify.reuse_manual_identity(job) is True
    assert job.title == "Family-Holiday"
    assert job.year == "2019"
    assert job.imdb_id == "tt9000001"


def test_other_discs_and_automatic_titles_are_ignored(database, monkeypatch):
    make_job(monkeypatch, "cc33", status="success", title="The-Kingdom")
    make_job(monkeypatch, "dd44", status="fail", title="Other", title_manual="Other")
    job = make_job(monkeypatch, "cc33", title="The-Kingdom")
    assert identify.reuse_manual_identity(job) is False
    assert job.title_manual is None


def test_disabled_leaves_the_job_alone(database, monkeypatch):
    make_job(monkeypatch, "ee55", status="fail", title="Manual", title_manual="Manual")
    job = make_job(monkeypatch, "ee55", title="Auto")
    monkeypatch.setitem(cfg.arm_config, "REUSE_MANUAL_IDENTITY", False)
    assert identify.reuse_manual_identity(job) is False
    assert job.title == "Auto"
