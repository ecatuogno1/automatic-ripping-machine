"""MAKEMKV_NOSCAN keeps makemkvcon off other drives when it reads a dev: source."""
import collections

import pytest

import arm.config.config as cfg
from arm.ripper import makemkv


class FakeProcess:
    """Stands in for makemkvcon: records the command, prints nothing, exits 0."""

    commands = []

    def __init__(self, cmd, **_kwargs):
        FakeProcess.commands.append(cmd)
        self.pid = 1
        self.returncode = 0
        self.stdout = iter(())

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


@pytest.fixture
def makemkvcon(monkeypatch):
    FakeProcess.commands = []
    monkeypatch.setattr(makemkv.shutil, "which", lambda _name: "makemkvcon")
    monkeypatch.setattr(makemkv.subprocess, "Popen", FakeProcess)
    return FakeProcess.commands


def _run(options):
    collections.deque(makemkv.run(options, makemkv.OutputType.MSG), maxlen=0)


@pytest.mark.parametrize("command", [
    ["info", "--cache=1", "dev:/dev/sr0", "--minlength=600"],
    ["mkv", "--progress=1.log", "dev:/dev/sr0", "all", "/raw", "--minlength=600"],
])
def test_dev_source_gets_noscan_when_enabled(monkeypatch, makemkvcon, command):
    monkeypatch.setitem(cfg.arm_config, "MAKEMKV_NOSCAN", True)
    _run(command)
    cmd = makemkvcon[0]
    assert "--noscan" in cmd
    # --noscan follows the command name and the dev: source is still read
    assert cmd.index("--noscan") == cmd.index(command[0]) + 1
    assert "dev:/dev/sr0" in cmd


def test_drive_listing_still_scans(monkeypatch, makemkvcon):
    monkeypatch.setitem(cfg.arm_config, "MAKEMKV_NOSCAN", True)
    _run(["info", "--cache=1", "disc:9999"])
    assert "--noscan" not in makemkvcon[0]


def test_default_leaves_the_command_unchanged(monkeypatch, makemkvcon):
    monkeypatch.delitem(cfg.arm_config, "MAKEMKV_NOSCAN", raising=False)
    command = ["info", "--cache=1", "dev:/dev/sr0", "--minlength=600"]
    _run(command)
    assert makemkvcon[0] == ["makemkvcon", "--robot", "--messages=-stdout"] + command


def test_noscan_is_not_added_twice(monkeypatch, makemkvcon):
    monkeypatch.setitem(cfg.arm_config, "MAKEMKV_NOSCAN", True)
    _run(["mkv", "--noscan", "dev:/dev/sr0", "all", "/raw"])
    assert makemkvcon[0].count("--noscan") == 1


def test_setting_ships_disabled():
    assert cfg.arm_config["MAKEMKV_NOSCAN"] is False
