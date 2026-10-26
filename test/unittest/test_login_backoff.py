"""Failed sign-ins are throttled per client address"""
import secrets
import threading

import bcrypt
import pytest

from arm.ui import app, db
import arm.ui.routes  # noqa: F401 - registers the blueprints' login manager
import arm.ui.utils as ui_utils
import arm.ui.auth.auth as auth
from arm.models.user import User

CLIENT = "192.0.2.10"
OTHER_CLIENT = "192.0.2.20"


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(auth, "login_throttle", auth.LoginThrottle(clock=fake))
    return fake


@pytest.fixture
def admin_login(monkeypatch):
    """An admin account with a generated password; returns that password"""
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(ui_utils, "arm_db_check", lambda: {"db_current": True, "db_exists": True})
    login = secrets.token_urlsafe(12)
    with app.app_context():
        db.create_all()
        User.query.delete()
        hashed = bcrypt.gensalt(4)
        db.session.add(User(email="admin", password=bcrypt.hashpw(login.encode(), hashed), hashed=hashed))
        db.session.commit()
    yield login
    with app.app_context():
        User.query.delete()
        db.session.commit()


def sign_in(login, client=CLIENT):
    # A fresh app context per request, so one sign-in (kept in flask.g) doesn't leak into the next
    with app.app_context(), app.test_client() as test_client:
        return test_client.post("/login", data={"username": "admin", "password": login},
                                environ_base={"REMOTE_ADDR": client})


def wrong():
    return secrets.token_urlsafe(12)


def fail(times, client=CLIENT):
    for _ in range(times):
        assert sign_in(wrong(), client).status_code == 200


def test_five_failures_pass_then_429_with_retry_after(admin_login, clock):
    fail(5)
    response = sign_in(wrong())
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"


def test_password_is_not_checked_while_waiting(admin_login, clock):
    fail(5)
    response = sign_in(admin_login)
    assert response.status_code == 429


def test_wait_doubles_after_each_failure(admin_login, clock):
    fail(5)
    clock.now += 1
    fail(1)
    assert sign_in(wrong()).headers["Retry-After"] == "2"
    clock.now += 2
    fail(1)
    assert sign_in(wrong()).headers["Retry-After"] == "4"


def test_wait_is_capped_at_15_minutes(admin_login, clock):
    throttle = auth.login_throttle
    for _ in range(40):
        throttle.failed(CLIENT)
    assert throttle.wait(CLIENT) == 900


def test_success_resets_the_count(admin_login, clock):
    fail(5)
    clock.now += 1
    assert sign_in(admin_login).status_code == 302
    fail(5)


def test_an_hour_without_failures_resets_the_count(admin_login, clock):
    fail(5)
    clock.now += 3601
    fail(5)


def test_other_clients_are_not_throttled(admin_login, clock):
    fail(5)
    assert sign_in(wrong()).status_code == 429
    assert sign_in(admin_login, OTHER_CLIENT).status_code == 302


def test_get_is_never_throttled(admin_login, clock):
    fail(5)
    with app.app_context(), app.test_client() as test_client:
        response = test_client.get("/login", environ_base={"REMOTE_ADDR": CLIENT})
    assert response.status_code == 200


def test_concurrent_failures_are_all_counted(clock):
    throttle = auth.login_throttle

    def worker():
        for _ in range(200):
            throttle.failed(CLIENT)
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert throttle.failures[CLIENT][0] == 1600
