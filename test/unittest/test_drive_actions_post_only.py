"""The drive eject, remove and manual-rip actions answer only a CSRF-checked POST, never a plain GET.

A link or image on another site is a GET that carries the session cookie, so it must not open a tray,
delete a drive or start a rip.
"""
import re

import pytest


@pytest.fixture
def ui(monkeypatch):
    from arm.ui import app, db
    import arm.ui.routes  # noqa: F401 -- register the blueprints as runui does

    monkeypatch.setitem(app.config, "TESTING", True)
    monkeypatch.setitem(app.config, "LOGIN_DISABLED", True)
    with app.app_context():
        db.create_all()
        yield app, db
        db.session.rollback()
        db.session.remove()


@pytest.fixture
def calls(monkeypatch):
    """Record the tray toggle and the manual rip instead of running eject or the ARM wrapper"""
    from arm.models.system_drives import SystemDrives
    from arm.ui.settings import settings

    seen = []

    def eject(drive, method="eject"):
        seen.append(f"eject:{method}")

    class Process:
        returncode = 0

        def __init__(self, cmd, **kwargs):
            seen.append("manual")

        def communicate(self):
            return "", ""

    monkeypatch.setattr(SystemDrives, "eject", eject)
    monkeypatch.setattr(settings.subprocess, "Popen", Process)
    return seen


def make_drive(db):
    from arm.models.system_drives import SystemDrives

    drive = SystemDrives()
    drive.name, drive.mount, drive.stale = "Test Drive", "/dev/sr-test", False
    db.session.add(drive)
    db.session.commit()
    return drive.drive_id


def drive_exists(db, drive_id):
    from arm.models.system_drives import SystemDrives

    db.session.expire_all()
    return db.session.get(SystemDrives, drive_id) is not None


ACTIONS = [
    ("eject", "eject:toggle"),
    ("manual", "manual"),
    ("remove", None),
]


@pytest.mark.parametrize("action, effect", ACTIONS)
def test_a_get_changes_nothing(ui, calls, action, effect):
    app, db = ui
    drive_id = make_drive(db)
    # e.g. <img src="http://arm:8080/drive/manual/1"> on another site
    response = app.test_client().get(f"/drive/{action}/{drive_id}")
    assert response.status_code == 405
    assert calls == []
    assert drive_exists(db, drive_id)


@pytest.mark.parametrize("action, effect", ACTIONS)
def test_a_post_without_the_token_is_refused(ui, calls, action, effect):
    app, db = ui
    drive_id = make_drive(db)
    response = app.test_client().post(f"/drive/{action}/{drive_id}")
    assert response.status_code == 400
    assert calls == []
    assert drive_exists(db, drive_id)


@pytest.mark.parametrize("action, effect", ACTIONS)
def test_a_post_performs_the_action(ui, calls, monkeypatch, action, effect):
    app, db = ui
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", False)
    drive_id = make_drive(db)
    response = app.test_client().post(f"/drive/{action}/{drive_id}")
    assert response.status_code == 302
    if effect is None:
        assert calls == []
        assert not drive_exists(db, drive_id)
    else:
        assert calls == [effect]
        assert drive_exists(db, drive_id)


def test_the_drive_card_posts_each_action_with_the_token(ui):
    from flask import render_template
    from arm.models.system_drives import SystemDrives, CDS
    from arm.ui.forms import SystemInfoDrives

    app, db = ui
    drive_id = make_drive(db)
    drive = db.session.get(SystemDrives, drive_id)
    drive.tray = CDS.TRAY_OPEN
    with app.test_request_context("/settings"):
        page = render_template("settings/drives.html", drives=[drive], form_drive=SystemInfoDrives())
    assert 'href="drive/' not in page
    for form_id, action in (("driveEject", "eject"), ("driveManual", "manual"), ("driveRemove", "remove")):
        form = re.search(rf'<form id="{form_id}{drive_id}" action="drive/{action}/{drive_id}" method="post">'
                         r'(.*?)</form>', page, re.S)
        assert form, f"no POST form for drive/{action}"
        assert 'name="csrf_token"' in form.group(1)
        assert f'form="{form_id}{drive_id}"' in page
