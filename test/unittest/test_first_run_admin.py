"""First run: the admin account gets a random password shown once, and /setup closes once a user exists"""
from pathlib import Path
import re

import bcrypt
import pytest
from sqlalchemy import create_engine

import arm.config.config as cfg
from arm.ui import app, db
import arm.ui.routes  # noqa: F401 - registers /setup
import arm.ui.utils as ui_utils
import arm.ripper.utils as ripper_utils
from arm.models.user import User


REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    """A throwaway database, so these tests can't delete the admin account of an installed ARM"""
    monkeypatch.setattr(ui_utils.DriveUtils, "drives_update", lambda *args, **kwargs: None)
    engine = create_engine(f"sqlite:///{tmp_path / 'arm.db'}")
    monkeypatch.setitem(cfg.arm_config, "DBFILE", engine.url.database)
    with app.app_context():
        monkeypatch.setitem(db.engines, None, engine)
        db.create_all()
        yield db
        db.session.remove()
    engine.dispose()


def test_fixture_does_not_use_the_configured_database(app_db):
    assert str(app_db.engine.url) != app.config["SQLALCHEMY_DATABASE_URI"]


def announced_login(err):
    match = re.search(r"password: (\S+)", err)
    assert match, err
    return match.group(1)


def test_first_run_admin_password_is_printed_once_and_stored_hashed(app_db, capsys):
    assert ui_utils.setup_database() is True

    printed = announced_login(capsys.readouterr().err)
    admin = User.query.filter_by(email="admin").one()
    stored = admin.password if isinstance(admin.password, bytes) else admin.password.encode()
    assert printed.encode() not in stored
    assert bcrypt.checkpw(printed.encode(), stored)


def test_first_run_admin_password_differs_per_install(app_db, capsys):
    ui_utils.setup_database()
    first = announced_login(capsys.readouterr().err)
    User.query.delete()
    db.session.commit()
    ui_utils.setup_database()
    second = announced_login(capsys.readouterr().err)
    assert first != second
    assert len(first) >= 16


def test_existing_admin_is_kept_and_nothing_printed(app_db, capsys):
    ui_utils.setup_database()
    capsys.readouterr()
    assert ui_utils.setup_database() is True
    assert "password:" not in capsys.readouterr().err
    assert User.query.count() == 1


def test_setup_is_404_once_a_user_exists(app_db):
    ui_utils.setup_database()
    before = User.query.one().password

    response = app.test_client().get("/setup")

    assert response.status_code == 404
    assert User.query.one().password == before


def test_setup_still_works_on_a_first_run(app_db, capsys):
    response = app.test_client().get("/setup")

    assert response.status_code != 404
    assert User.query.filter_by(email="admin").count() == 1
    announced_login(capsys.readouterr().err)


def test_ripper_has_no_fixed_default_user():
    assert not hasattr(ripper_utils, "try_add_default_user")


@pytest.mark.parametrize("guide", ["scripts/installers/DebianInstaller.sh",
                                   "arm_wiki/Alternate-Install-Debian.md",
                                   "arm_wiki/Ubuntu-20.04-Automatic-Installation.md",
                                   "arm_wiki/Ubuntu-25.04-Install.md"])
def test_installs_with_the_shipped_service_are_told_to_read_the_log_it_writes(guide):
    log = re.search(r"^StandardError=append:(\S+)$", (REPO / "setup/armui.service").read_text(), re.MULTILINE).group(1)
    text = (REPO / guide).read_text()
    assert f"grep -A3 'ARM first run' {log}" in text
    assert "journalctl -u armui" not in text
