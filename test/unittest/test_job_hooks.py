"""BASH_SCRIPT job environment and the JOB_WEBHOOK_URL job webhook"""
import datetime
import json
import secrets
from types import SimpleNamespace

import pytest
import requests

import arm.config.config as cfg
from arm.models.job import JobState
from arm.ripper import utils

WEBHOOK = "https://hooks.example.test/arm"


def fake_job(**values):
    track = SimpleNamespace(track_number="0", length=7200, filename="title_t00.mkv", ripped=True, main_feature=True)
    job = SimpleNamespace(job_id=42, title="The Matrix", year="1999", video_type="movie", imdb_id="tt0133093",
                          disctype="bluray", label="THE_MATRIX", path="/media/completed/movies/The Matrix (1999)",
                          status=JobState.SUCCESS.value, pid=1234, pid_hash=5678, errors=None,
                          start_time=datetime.datetime(2025, 1, 1, 20, 0, 0), tracks=[track],
                          config=SimpleNamespace(OMDB_API_KEY=secrets.token_hex(8)))
    for key, value in values.items():
        setattr(job, key, value)
    return job


@pytest.fixture
def config(monkeypatch):
    values = dict(cfg.arm_config)
    monkeypatch.setattr(cfg, "arm_config", values)
    return values


@pytest.fixture
def posted(monkeypatch):
    calls = []

    def post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(utils.requests, "post", post)
    return calls


def test_bash_script_keeps_arguments_and_gets_job_environment(monkeypatch):
    calls = []
    monkeypatch.setattr(utils, "arm_subprocess", lambda cmd, env=None: calls.append((cmd, env)))
    utils.bash_notify({"BASH_SCRIPT": "/opt/hook.sh"}, "ARM notification", "Done", fake_job(year=None))

    cmd, env = calls[0]
    assert cmd == ["/usr/bin/env", "bash", "/opt/hook.sh", "ARM notification", "Done"]
    assert env["ARM_JOB_ID"] == "42"
    assert env["ARM_TITLE"] == "The Matrix"
    assert env["ARM_YEAR"] == ""
    assert env["ARM_VIDEO_TYPE"] == "movie"
    assert env["ARM_IMDB_ID"] == "tt0133093"
    assert env["ARM_DISCTYPE"] == "bluray"
    assert env["ARM_OUTPUT_PATH"] == "/media/completed/movies/The Matrix (1999)"
    assert env["ARM_STATUS"] == "success"
    # The rest of ARM's environment (PATH ...) is still there
    assert "PATH" in env


def test_bash_script_without_job_has_no_job_variables(monkeypatch):
    calls = []
    monkeypatch.setattr(utils, "arm_subprocess", lambda cmd, env=None: calls.append((cmd, env)))
    utils.bash_notify({"BASH_SCRIPT": "/opt/hook.sh"}, "ARM notification", "Setup failed")
    assert not [name for name in calls[0][1] if name in utils.JOB_ENVIRONMENT]


def test_webhook_posts_finished_job_without_config(config, posted):
    config.update(JOB_WEBHOOK_URL=WEBHOOK, JOB_WEBHOOK_TIMEOUT=7)
    assert utils.job_webhook(fake_job()) is True

    call = posted[0]
    assert call["url"] == WEBHOOK
    assert call["timeout"] == 7
    body = call["json"]
    assert body["event"] == "job_completed"
    job = body["job"]
    assert job["job_id"] == 42
    assert job["imdb_id"] == "tt0133093"
    assert job["path"] == "/media/completed/movies/The Matrix (1999)"
    assert job["start_time"] == "2025-01-01T20:00:00"
    assert job["tracks"][0]["filename"] == "title_t00.mkv"
    assert "config" not in job
    assert "pid" not in job
    # Serialisable as sent
    json.dumps(body)


def test_webhook_reports_failed_job(config, posted):
    config.update(JOB_WEBHOOK_URL=WEBHOOK)
    utils.job_webhook(fake_job(status=JobState.FAILURE.value, errors="MakeMKV failed"))
    assert posted[0]["json"]["event"] == "job_failed"
    assert posted[0]["json"]["job"]["errors"] == "MakeMKV failed"
    assert posted[0]["timeout"] == 10


def test_webhook_disabled_by_default(config, posted):
    config.update(JOB_WEBHOOK_URL="")
    assert utils.job_webhook(fake_job()) is False
    assert not posted


def test_webhook_refuses_non_http_url(config, posted):
    config.update(JOB_WEBHOOK_URL="file:///etc/passwd")
    assert utils.job_webhook(fake_job()) is False
    assert not posted


def test_webhook_failure_is_logged_not_raised(config, monkeypatch, caplog):
    config.update(JOB_WEBHOOK_URL=WEBHOOK)

    def post(*_args, **_kwargs):
        raise requests.exceptions.ConnectTimeout("timed out")

    monkeypatch.setattr(utils.requests, "post", post)
    assert utils.job_webhook(fake_job()) is False
    assert "Job webhook failed for job 42" in caplog.text
    assert WEBHOOK not in caplog.text
