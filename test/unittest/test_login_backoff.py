"""Failed sign-ins are throttled per client address"""
import secrets
import threading

import bcrypt
import pytest
from sqlalchemy import create_engine

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
def admin_login(tmp_path, monkeypatch):
    """An admin account with a generated password, in a throwaway database so that an installed ARM's
    account is never touched; returns that password"""
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(ui_utils, "arm_db_check", lambda: {"db_current": True, "db_exists": True})
    login = secrets.token_urlsafe(12)
    engine = create_engine(f"sqlite:///{tmp_path / 'arm.db'}")
    with app.app_context():
        monkeypatch.setitem(db.engines, None, engine)
        db.create_all()
        hashed = bcrypt.gensalt(4)
        db.session.add(User(email="admin", password=bcrypt.hashpw(login.encode(), hashed), hashed=hashed))
        db.session.commit()
    yield login
    engine.dispose()


def test_fixture_does_not_use_the_configured_database(admin_login):
    with app.app_context():
        assert str(db.engine.url) != app.config["SQLALCHEMY_DATABASE_URI"]


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
    assert sign_in(wrong()).headers["Retry-After"] == "900"


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


def burst(monkeypatch, attempts=8):
    """Sign in from many threads at once, all held inside the password check; returns how many reached it"""
    entered = []
    real_hashpw = bcrypt.hashpw
    resume = threading.Event()
    finished = []
    settled = threading.Condition()

    def holding_hashpw(*args):
        with settled:
            entered.append(1)
            settled.notify_all()
        resume.wait(5)
        return real_hashpw(*args)

    def attempt():
        finished.append(sign_in(wrong()).status_code)
        with settled:
            settled.notify_all()

    monkeypatch.setattr(auth.bcrypt, "hashpw", holding_hashpw)
    threads = [threading.Thread(target=attempt) for _ in range(attempts)]
    for thread in threads:
        thread.start()
    with settled:  # until every attempt is either refused or inside the check
        settled.wait_for(lambda: len(entered) + len(finished) >= attempts, timeout=5)
    resume.set()
    for thread in threads:
        thread.join()
    return len(entered), finished


def test_a_burst_after_the_wait_checks_one_password(admin_login, clock, monkeypatch):
    fail(5)
    clock.now += 1
    checked, statuses = burst(monkeypatch)
    assert checked == 1
    assert statuses.count(429) == 7


def test_a_burst_from_a_new_client_checks_only_the_free_attempts(admin_login, clock, monkeypatch):
    checked, statuses = burst(monkeypatch)
    assert checked == auth.LoginThrottle.FREE
    assert statuses.count(429) == 3


def test_a_refused_form_does_not_hold_a_reservation(admin_login, clock):
    for _ in range(8):
        with app.app_context(), app.test_client() as test_client:
            response = test_client.post("/login", data={"username": "admin"}, environ_base={"REMOTE_ADDR": CLIENT})
        assert response.status_code == 200
    fail(5)
