"""Title search results without an IMDb id (some TMDB titles) can still be selected."""

import datetime
import html
import re

import pytest

RESULTS = {"Search": [
    {"Title": "Known Film", "Year": "2001", "Type": "movie", "imdbID": "tt0000001", "Poster": "https://img/1.jpg"},
    {"Title": "Obscure Film", "Year": "2019", "Type": "movie", "imdbID": None, "Poster": "https://img/2.jpg"},
]}


@pytest.fixture
def page(monkeypatch):
    from arm.ui import app, db, utils as ui_utils
    from arm.models.job import Job
    import arm.ui.routes  # noqa: F401 -- register the blueprints as runui does

    monkeypatch.setattr(ui_utils, "metadata_selector", lambda *args, **kwargs: RESULTS)
    with app.app_context():
        db.create_all()
        app.config.update(TESTING=True, LOGIN_DISABLED=True, WTF_CSRF_ENABLED=False)
        job = Job.__mapper__.class_manager.new_instance()
        job.status, job.devpath, job.title = "waiting", "/dev/list-titles-test", "OBSCURE"
        job.start_time = datetime.datetime.now()
        db.session.add(job)
        db.session.commit()
        client = app.test_client()
        response = client.get(f"/list_titles?title=obscure&year=&job_id={job.job_id}")
        yield response.status_code, html.unescape(response.get_data(as_text=True)), client, job
        db.session.rollback()
        db.session.remove()


def test_result_without_imdb_id_saves_directly(page):
    status, body, _, _ = page

    assert status == 200
    assert "gettitle?imdbID=None" not in body
    assert "updatetitle?" in body
    assert "title=Obscure+Film" in body


def test_result_with_imdb_id_still_opens_details(page):
    _, body, _, _ = page

    assert "gettitle?imdbID=tt0000001" in body


def test_saving_result_without_imdb_id(page):
    _, body, client, job = page
    link = re.search(r'href="(/updatetitle\?[^"]*)"', body).group(1)

    assert client.get(link).status_code == 302
    assert job.title == "Obscure Film"
    assert job.imdb_id is None
