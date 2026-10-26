"""A disc's label and a submitted poster URL are untrusted: neither may run code"""
from types import SimpleNamespace

import pytest

from arm.ui import app, db
import arm.ripper.utils as ripper_utils
import arm.ui.utils as ui_utils
from arm.models.job import Job

HOSTILE_LABEL = 'x"; touch /tmp/pwned; "'


@pytest.fixture
def data_job(tmp_path, monkeypatch):
    """A data-disc job whose dd call is recorded instead of run"""
    for folder in ("raw", "completed", "logs"):
        (tmp_path / folder).mkdir()
    config = SimpleNamespace(RAW_PATH=str(tmp_path / "raw"), COMPLETED_PATH=str(tmp_path / "completed"),
                             LOGPATH=str(tmp_path / "logs"))
    job = SimpleNamespace(label=HOSTILE_LABEL, devpath="/dev/sr0", video_type="unknown", logfile="job.log",
                          config=config)
    monkeypatch.setitem(ripper_utils.cfg.arm_config, "DATA_RIP_PARAMETERS", "bs=2048 conv=noerror")
    monkeypatch.setattr(ripper_utils, "move_files_main", lambda *args, **kwargs: True)
    calls = []

    def fake_check_output(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return b""
    monkeypatch.setattr(ripper_utils.subprocess, "check_output", fake_check_output)
    return job, calls, tmp_path


def test_data_disc_label_never_reaches_a_shell(data_job):
    job, calls, tmp_path = data_job

    assert ripper_utils.rip_data(job) is True

    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert isinstance(cmd, list)
    assert not kwargs.get("shell")
    assert cmd[0] == "dd"
    assert cmd[1] == "if=/dev/sr0"
    # The whole label stays inside one argument, quotes and all
    assert cmd[2] == f"of={tmp_path / 'raw' / HOSTILE_LABEL / HOSTILE_LABEL}.part"
    assert cmd[3:] == ["bs=2048", "conv=noerror"]


def test_dd_messages_go_to_the_job_log(data_job):
    job, calls, tmp_path = data_job

    ripper_utils.rip_data(job)

    _, kwargs = calls[0]
    assert kwargs["stderr"].name == str(tmp_path / "logs" / "job.log")


@pytest.fixture
def client_with_job(monkeypatch):
    monkeypatch.setitem(app.config, "LOGIN_DISABLED", True)

    def fake_udev(self):
        self.disctype = "dvd"
        self.label = "SOME_DISC"
    monkeypatch.setattr(Job, "parse_udev", fake_udev)
    monkeypatch.setattr(ui_utils, "metadata_selector", lambda *args: None)  # no OMDb/TMDb calls
    with app.app_context():
        db.create_all()
        job = Job("/dev/sr0")
        db.session.add(job)
        db.session.commit()
        yield app.test_client(), job.job_id
        db.session.rollback()
        db.session.delete(db.session.get(Job, job.job_id))
        db.session.commit()


def update_title(client, job_id, poster):
    return client.get("/updatetitle", query_string={"job_id": job_id, "title": "Home", "year": "2015",
                                                    "type": "movie", "imdbID": "tt2224026", "poster": poster})


@pytest.mark.parametrize("poster", ["javascript:alert(document.cookie)", " JavaScript:alert(1)",
                                    "data:text/html,<script>alert(1)</script>"])
def test_updatetitle_does_not_store_a_script_poster(client_with_job, poster):
    client, job_id = client_with_job

    assert update_title(client, job_id, poster).status_code == 302

    db.session.expire_all()
    job = db.session.get(Job, job_id)
    assert job.title == "Home"
    assert job.poster_url is None
    assert job.poster_url_manual is None


def test_updatetitle_stores_a_web_poster(client_with_job):
    client, job_id = client_with_job
    poster = "https://image.tmdb.org/t/p/original/usFenYnk6mr8C62dB1MoAfSWMGR.jpg"

    update_title(client, job_id, poster)

    db.session.expire_all()
    job = db.session.get(Job, job_id)
    assert job.poster_url == poster
    assert job.poster_url_manual == poster
    page = client.get("/jobdetail", query_string={"job_id": job_id}).get_data(as_text=True)
    assert f'href="{poster}"' in page


def test_jobdetail_does_not_link_a_stored_script_poster(client_with_job):
    """A row saved before this fix may still hold a javascript: URL; the page must not link it"""
    client, job_id = client_with_job
    job = db.session.get(Job, job_id)
    job.poster_url = job.poster_url_auto = job.poster_url_manual = "javascript:alert(1)"
    db.session.commit()

    page = client.get("/jobdetail", query_string={"job_id": job_id}).get_data(as_text=True)

    assert "Job details" in page
    assert 'href="javascript:' not in page
