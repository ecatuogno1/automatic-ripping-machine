"""The ripper doesn't start a job while the database needs an update (#1485)."""
from types import SimpleNamespace

import pytest

from arm.ripper import main, utils

HEAD = "2e0dc31fcb2e"


def test_outdated_database_stops_the_ripper():
    with pytest.raises(utils.RipperException, match="database needs to be updated"):
        main.require_current_db(SimpleNamespace(head_version=HEAD, db_version="469d88477c13"))


def test_current_database_passes():
    main.require_current_db(SimpleNamespace(head_version=HEAD, db_version=HEAD))


def test_unknown_head_does_not_block():
    main.require_current_db(SimpleNamespace(head_version="unknown", db_version=HEAD))


def test_setup_checks_the_database_before_using_the_drive(monkeypatch):
    calls = []

    class Stop(Exception):
        pass

    monkeypatch.setattr(main, "entry", lambda: SimpleNamespace(devpath="sr0", syslog=False))
    monkeypatch.setattr(main.logger, "create_early_logger", lambda **_kwargs: None)
    monkeypatch.setattr(main.utils, "arm_setup", lambda _log: None)
    monkeypatch.setattr(main, "ARMInfo", lambda *_args: SimpleNamespace(head_version=HEAD, db_version="old"))
    monkeypatch.setattr(main, "signal", lambda *_args: None)

    def drive_query(**_kwargs):
        calls.append("drive")
        raise Stop

    monkeypatch.setattr(main, "SystemDrives", SimpleNamespace(query=SimpleNamespace(filter_by=drive_query)))
    with pytest.raises(utils.RipperException, match="database needs to be updated"):
        main.setup()
    assert calls == []
