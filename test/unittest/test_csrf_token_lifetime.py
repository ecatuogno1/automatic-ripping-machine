"""CSRF tokens last for the session; a refused token is explained instead of a bare 400 page"""
import time

import pytest
from flask_wtf.csrf import generate_csrf

from arm.ui import app, db
import arm.ui.routes  # noqa: F401 - registers the error handlers

OUT_OF_DATE = "out of date"
ARM_PAGE = "://".join(("http", "localhost/settings"))


@pytest.fixture
def client(monkeypatch):
    with app.app_context():
        db.create_all()
    monkeypatch.setitem(app.config, "TESTING", True)
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    return app.test_client()


def page_token(client):
    """The token a page rendered for this browser session"""
    with client:
        client.get("/login")
        return generate_csrf()


def test_a_page_left_open_for_hours_still_works(client, monkeypatch):
    assert app.config["WTF_CSRF_TIME_LIMIT"] is None
    token = page_token(client)
    later = time.time() + 6 * 3600
    monkeypatch.setattr("itsdangerous.timed.time.time", lambda: later)
    response = client.post("/login", data={"csrf_token": token, "username": "nobody", "password": ""})
    assert OUT_OF_DATE not in response.get_data(as_text=True)
    assert response.status_code != 400


def test_a_form_from_an_arm_page_goes_back_to_it_with_a_message(client):
    response = client.post("/login", data={"username": "nobody"}, headers={"Referer": ARM_PAGE})
    assert response.status_code == 302
    assert response.headers["Location"] == ARM_PAGE
    with client.session_transaction() as session:
        assert OUT_OF_DATE in str(session.get("_flashes"))


@pytest.mark.parametrize("headers", [
    {"Referer": "https://other-site.example/page"},  # another site's form is not followed back
    {},  # no referrer
    {"X-Requested-With": "XMLHttpRequest", "Referer": ARM_PAGE},  # the settings page's save
    {"Accept": "application/json"},
])
def test_other_requests_get_the_reason_as_json(client, headers):
    response = client.post("/login", data={"username": "nobody"}, headers=headers)
    assert response.status_code == 400
    assert OUT_OF_DATE in response.get_json()["message"]


def test_a_secure_request_is_not_sent_back_to_a_plain_http_page(client):
    response = client.post("/login", data={"username": "nobody"}, base_url="https://localhost",
                           headers={"Referer": ARM_PAGE})
    assert response.status_code == 400
    assert OUT_OF_DATE in response.get_json()["message"]


def test_a_form_behind_a_tls_proxy_still_goes_back_to_its_page(client):
    # The proxy talks plain http to ARM, so the request looks insecure while the browser's page is https
    response = client.post("/login", data={"username": "nobody"}, headers={"Referer": "https://localhost/settings"})
    assert response.status_code == 302
    assert response.headers["Location"] == "https://localhost/settings"


def test_a_json_body_counts_as_a_script(client):
    response = client.post("/login", json={"username": "nobody"}, headers={"Referer": ARM_PAGE})
    assert response.status_code == 400
    assert OUT_OF_DATE in response.get_json()["message"]
