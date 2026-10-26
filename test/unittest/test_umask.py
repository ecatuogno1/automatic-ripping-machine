"""UMASK from arm.yaml is applied to the ripper process (#1010)."""
import os

import pytest

import arm.config.config as cfg
from arm.ripper import main


@pytest.fixture
def umask_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(os, "umask", calls.append)
    return calls


@pytest.mark.parametrize("value, expected", [("0o002", 0o002), (22, 0o022), ("027", 0o027)])
def test_umask_is_applied(monkeypatch, umask_calls, value, expected):
    monkeypatch.setitem(cfg.arm_config, "UMASK", value)
    main.set_umask()
    assert umask_calls == [expected]


@pytest.mark.parametrize("value", ["", None, "rw-r--r--"])
def test_unset_or_invalid_umask_is_ignored(monkeypatch, umask_calls, value):
    monkeypatch.setitem(cfg.arm_config, "UMASK", value)
    main.set_umask()
    assert umask_calls == []


def test_setup_applies_umask(monkeypatch, umask_calls):
    class Stop(Exception):
        pass

    def stop(_log):
        raise Stop

    monkeypatch.setitem(cfg.arm_config, "UMASK", "0o002")
    monkeypatch.setattr(main, "entry", lambda: type("Args", (), {"devpath": "sr0", "syslog": False})())
    monkeypatch.setattr(main.logger, "create_early_logger", lambda **_kwargs: None)
    monkeypatch.setattr(main.utils, "arm_setup", stop)
    monkeypatch.setattr(main, "signal", lambda *_args: None)
    with pytest.raises(Stop):
        main.setup()
    assert umask_calls == [0o002]
