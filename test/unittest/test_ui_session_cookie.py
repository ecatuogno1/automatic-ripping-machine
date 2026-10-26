"""Flags on the UI's session and Flask-Login remember-me cookies"""
from datetime import timedelta

from flask import session
from flask_login import login_user

from arm.ui import app


class _User:
    """The minimum Flask-Login needs to write a remember-me cookie"""
    is_active = True
    is_authenticated = True
    is_anonymous = False

    def get_id(self):
        return "1"


def test_session_cookie_is_httponly_and_samesite_lax():
    with app.test_request_context("/"):
        session["probe"] = 1
        response = app.make_response("")
        app.session_interface.save_session(app, session, response)
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Secure" not in cookie  # plain HTTP on the LAN


def test_remember_cookie_is_httponly_and_samesite_lax():
    with app.test_request_context("/"):
        login_user(_User(), remember=True, duration=timedelta(days=1))
        response = app.process_response(app.make_response(""))
    cookie = next(c for c in response.headers.getlist("Set-Cookie") if c.startswith("remember_token="))
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Secure" not in cookie
