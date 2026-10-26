"""The settings save endpoints must not send arm.yaml / apprise.yaml values back to the browser."""
import secrets

import pytest

import arm.config.config as cfg
from arm.ui import app, db
import arm.ui.routes  # noqa: F401  (registers the blueprints)
from arm.ui.settings import settings as settings_routes


@pytest.fixture
def client(monkeypatch, tmp_path):
    with app.app_context():
        db.create_all()
    app.config.update(TESTING=True, LOGIN_DISABLED=True, WTF_CSRF_ENABLED=False)
    # Saving must not touch the real files
    monkeypatch.setattr(cfg, "arm_config_path", str(tmp_path / "arm.yaml"))
    monkeypatch.setattr(cfg, "apprise_config_path", str(tmp_path / "apprise.yaml"))
    monkeypatch.setattr(settings_routes.importlib, "reload", lambda module: module)
    with app.test_client() as test_client:
        yield test_client


def test_ripper_settings_response_has_no_settings(client, monkeypatch):
    marker = secrets.token_hex(8)
    monkeypatch.setitem(cfg.arm_config, "TMDB_API_KEY", marker)
    response = client.post("/save_settings", data={"TMDB_API_KEY": marker})
    assert "settings" not in response.get_json()
    assert marker not in response.get_data(as_text=True)


def test_apprise_response_has_no_settings(client, monkeypatch):
    marker = secrets.token_hex(8)
    monkeypatch.setattr(cfg, "apprise_config", {"PUSHOVER_TOKEN": marker})
    response = client.post("/save_apprise_cfg", data={"PUSHOVER_TOKEN": marker})
    assert "settings" not in response.get_json()
    assert marker not in response.get_data(as_text=True)
