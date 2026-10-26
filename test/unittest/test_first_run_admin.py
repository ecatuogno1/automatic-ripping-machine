"""First run: the admin account gets a random password shown once, and /setup closes once a user exists"""
import re

import bcrypt
import pytest

from arm.ui import app, db
import arm.ui.routes  # noqa: F401 - registers /setup
import arm.ui.utils as ui_utils
import arm.ripper.utils as ripper_utils
from arm.models.user import User


@pytest.fixture
def app_db(monkeypatch):
    monkeypatch.setattr(ui_utils.DriveUtils, "drives_update", lambda *args, **kwargs: None)
    with app.app_context():
        db.create_all()
        User.query.delete()
        db.session.commit()
        yield db
        db.session.rollback()
        User.query.delete()
        db.session.commit()


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
