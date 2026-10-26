"""arm.yaml / apprise.yaml are written so that every value loads back with the same value and type"""
import importlib
import os

import pytest
import yaml

import arm.config.config as cfg
from arm.config import config_utils
from arm.ui import app, db
import arm.ui.routes  # noqa: F401

# A Windows-style path and an apostrophe: the old writer turned these into YAML that no longer loads
BACKSLASH_ARGS = "--subtitle-lang-list 'eng' --srt-file C:\\subs\\x.srt"


@pytest.fixture
def config_files(tmp_path, monkeypatch):
    """A private arm.yaml and apprise.yaml; cfg is reloaded from them and restored afterwards"""
    original = os.environ["ARM_CONFIG_FILE"]
    with open(original) as stream:
        values = yaml.safe_load(stream)
    apprise_path = tmp_path / "apprise.yaml"
    apprise_path.write_text("PUSHOVER_USER_KEY: abc\nNTFY_TOPIC: arm\n")
    values.update(APPRISE=str(apprise_path), CHOWN_USER=None)
    arm_path = tmp_path / "arm.yaml"
    arm_path.write_text(yaml.safe_dump(values, sort_keys=False))
    monkeypatch.setenv("ARM_CONFIG_FILE", str(arm_path))
    importlib.reload(cfg)
    with app.app_context():
        db.create_all()
        app.config.update(TESTING=True, LOGIN_DISABLED=True, WTF_CSRF_ENABLED=False)
        yield arm_path, apprise_path
    monkeypatch.setenv("ARM_CONFIG_FILE", original)
    importlib.reload(cfg)


def load(path):
    with open(path) as stream:
        return yaml.safe_load(stream)


def page_form(values):
    """What the settings page posts for ``values`` (every field shown as the template renders it)"""
    return {key: "" if value is None else str(value) for key, value in values.items()}


def test_import_rewrite_keeps_null_values(config_files):
    arm_path, _ = config_files
    saved = load(arm_path)
    assert "CHOWN_USER" in saved
    assert saved["CHOWN_USER"] is None
    assert cfg.arm_config["CHOWN_USER"] is None


def test_save_settings_round_trips_values(config_files):
    arm_path, _ = config_files
    form = page_form(cfg.arm_config)
    form["HB_ARGS_DVD"] = BACKSLASH_ARGS
    form["MANUAL_WAIT_TIME"] = "45"
    del form["WEBSERVER_PORT"]  # a field the page did not post keeps its value
    response = app.test_client().post("/save_settings", data=form)
    body = response.get_json()
    assert body["success"] is True
    assert "settings" not in body
    saved = load(arm_path)
    assert saved["HB_ARGS_DVD"] == BACKSLASH_ARGS
    assert saved["MANUAL_WAIT_TIME"] == 45
    assert saved["CHOWN_USER"] is None
    assert saved["WEBSERVER_PORT"] == cfg.arm_config["WEBSERVER_PORT"]


def test_save_apprise_keeps_unposted_keys(config_files):
    _, apprise_path = config_files
    response = app.test_client().post("/save_apprise_cfg", data={"NTFY_TOPIC": "it's \\arm"})
    assert response.get_json()["success"] is True
    saved = load(apprise_path)
    assert saved["NTFY_TOPIC"] == "it's \\arm"
    assert saved["PUSHOVER_USER_KEY"] == "abc"


def test_untouched_field_keeps_type():
    current = {"DEST": "0123", "OFFSETS": {"a": 6}, "EMPTY": None, "FLAG": True}
    posted = config_utils.merge_form(current, page_form(current))
    assert posted == current


def test_write_refuses_text_that_does_not_load_back(tmp_path):
    path = tmp_path / "arm.yaml"
    path.write_text("KEY: 1\n")
    with pytest.raises(ValueError):
        config_utils.write_yaml_file(str(path), "KEY: \"C:\\x\"\n", {"KEY": "C:\\x"})
    assert path.read_text() == "KEY: 1\n"
    assert config_utils.write_yaml_file(str(path), config_utils.render_plain_yaml({"KEY": 2}), {"KEY": 2})
    assert load(path) == {"KEY": 2}
