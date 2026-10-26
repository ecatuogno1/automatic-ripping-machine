"""The settings page reuses its slow version/update/hardware checks instead of running them per load"""
import collections

import psutil
import pytest

from arm.ui import app, db
import arm.ui.routes  # noqa: F401
import arm.ui.settings.settings as settings_page
import arm.ui.utils as ui_utils


@pytest.fixture
def calls(monkeypatch):
    counts = collections.Counter()

    def counted(name, value):
        def fake(*_args, **_kwargs):
            counts[name] += 1
            return value
        return fake

    monkeypatch.setattr(ui_utils, "git_check_version", counted("git show", ("2.21.0", "2.21.0")))
    monkeypatch.setattr(ui_utils, "get_git_revision_hash", counted("git rev-parse", "a380622"))
    monkeypatch.setattr(ui_utils, "git_check_updates", counted("GitHub API", True))
    monkeypatch.setattr(settings_page, "arm_subprocess", counted("HandBrakeCLI", "nvenc: version 12.1 is available"))
    # start every test with an empty cache (raising=False: main has no cache)
    monkeypatch.setattr(settings_page, "_check_cache", {}, raising=False)
    return counts


@pytest.fixture
def client(monkeypatch):
    # psutil has no sensors_temperatures on macOS/Windows; the page itself isn't under test here
    monkeypatch.setattr(psutil, "sensors_temperatures", lambda: {}, raising=False)
    with app.app_context():
        db.create_all()
        app.config.update(TESTING=True, LOGIN_DISABLED=True, WTF_CSRF_ENABLED=False)
        yield app.test_client()


def test_second_load_reuses_checks(calls, client):
    assert client.get("/settings").status_code == 200
    assert client.get("/settings").status_code == 200

    assert calls == {"git show": 1, "git rev-parse": 1, "GitHub API": 1, "HandBrakeCLI": 1}


def test_checks_run_again_after_cache_time(calls, client, monkeypatch):
    # with no cache time every load is past it
    monkeypatch.setattr(settings_page, "CHECK_CACHE_SECONDS", 0, raising=False)
    client.get("/settings")
    client.get("/settings")

    assert calls == {"git show": 2, "git rev-parse": 2, "GitHub API": 2, "HandBrakeCLI": 2}


def test_hardware_probe_result_is_kept(calls):
    with app.app_context():
        first = settings_page.check_hw_transcode_support()
        second = settings_page.check_hw_transcode_support()

    assert first["nvidia"] is True
    assert second == first
    assert calls["HandBrakeCLI"] == 1
