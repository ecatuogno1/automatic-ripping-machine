"""Debug logs and the job API never show a secret setting: redaction by name pattern, not a fixed list"""
import logging
import secrets
from types import SimpleNamespace

import pytest

import arm.models.config as config_model
from arm.models.config import HIDDEN_VALUE, Config
from arm.models.job import Job

SECRET_NAMES = ("MAKEMKV_PERMA_KEY", "TMDB_API_KEY", "OMDB_API_KEY", "EMBY_PASSWORD", "EMBY_USERID",
                "EMBY_API_KEY", "PB_KEY", "PO_USER_KEY", "PO_APP_KEY", "ARM_API_KEY", "SOME_APIKEY",
                "PLEX_TOKEN", "CLIENT_SECRET", "JELLYFIN_AUTH", "DISCORD_WEBHOOK", "APPRISE_URLS")
VISIBLE_NAMES = ("RIPMETHOD", "HASHEDKEYS", "RAW_PATH", "MKV_ARGS", "EMBY_SERVER", "EMBY_USERNAME", "PASSES")


def marker():
    return "m" + secrets.token_hex(8)


def config_with(values):
    return Config({"RIPMETHOD": "mkv", "HASHEDKEYS": False, "RAW_PATH": "/home/arm/raw", **values}, 1)


def url_with_credentials(credentials, host):
    return "https" + "://" + credentials + "@" + host + "/"


@pytest.mark.parametrize("name", SECRET_NAMES)
def test_secret_setting_is_hidden_everywhere(name):
    value = marker()
    config = config_with({name: value})
    for shown in (str(config), config.list_params(), config.pretty_table(), str(config.get_d())):
        assert value not in shown
    assert name not in config.get_d()
    assert HIDDEN_VALUE in config.pretty_table()


@pytest.mark.parametrize("name", VISIBLE_NAMES)
def test_ordinary_settings_and_flags_stay_visible(name):
    assert not config_model.secret_name(name)


def test_ordinary_values_are_unchanged():
    config = config_with({})
    assert config.get_d()["RIPMETHOD"] == "mkv"
    assert config.get_d()["RAW_PATH"] == "/home/arm/raw"
    assert config_model.redact("MINLENGTH", 600) == 600
    assert config_model.redact("PLEX_TOKEN", "") == ""
    assert config_model.redact("UI_BASE_URL", "https://arm.example.invalid/") == "https://arm.example.invalid/"


def test_credentials_in_any_url_are_removed():
    password = marker()
    token = marker()
    host = "emby.example.invalid:8096"
    server = url_with_credentials("admin:" + password, host)
    assert config_model.redact("EMBY_SERVER", server) == url_with_credentials(HIDDEN_VALUE, host)
    json_url = url_with_credentials(token, "hooks.example.invalid")
    assert token not in config_model.redact("JSON_URL", json_url)
    config = config_with({"EMBY_SERVER": server})
    assert password not in config.pretty_table()
    assert password not in str(config.get_d())


def test_job_table_and_job_dict_hide_secrets():
    perma_key = marker()
    password = marker()
    job = Job.__mapper__.class_manager.new_instance()
    job.title = "Some Movie"
    job.label = "SOME_MOVIE"
    job.path = url_with_credentials("user:" + password, "share.example.invalid")
    # as the ripper's job holds it, loaded, without the backref that would make the table recursive
    job.__dict__["config"] = config_with({"MAKEMKV_PERMA_KEY": perma_key})
    table = job.pretty_table()
    assert "SOME_MOVIE" in table
    assert perma_key not in table
    assert password not in table
    assert password not in str(job.get_d())


def test_logged_arm_parameters_are_redacted(monkeypatch, caplog):
    import arm.config.config as cfg
    from arm.ripper import main

    password = marker()
    monkeypatch.setitem(cfg.arm_config, "EMBY_SERVER", url_with_credentials("admin:" + password,
                                                                            "emby.example.invalid"))
    job = SimpleNamespace(devpath="/dev/sr0", mountpoint="/mnt/dev/sr0", title="T", year="2001", video_type="movie",
                          hasnicetitle=True, label="L", disctype="dvd", manual_start=False)
    with caplog.at_level(logging.INFO):
        main.log_arm_params(job)
    assert "emby_server: " + url_with_credentials(HIDDEN_VALUE, "emby.example.invalid") in caplog.text
    assert password not in caplog.text
