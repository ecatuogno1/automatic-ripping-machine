"""MAX_CONCURRENT_TRANSCODES counts running encoders even when the command is configured as a path"""
import types

import pytest

import arm.ripper.utils as utils


def _running(monkeypatch, names):
    procs = [types.SimpleNamespace(info={"name": name}) for name in names]
    monkeypatch.setattr(utils.psutil, "process_iter", lambda attrs=None: iter(procs))


class Slept(Exception):
    """sleep_check_process decided to wait"""


@pytest.fixture
def no_sleep(monkeypatch):
    def fake_sleep(_seconds):
        raise Slept()
    monkeypatch.setattr(utils.time, "sleep", fake_sleep)


@pytest.mark.parametrize("command", ["/usr/bin/ffmpeg", "FFMPEG", "/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner"])
def test_waits_when_limit_reached_for_configured_path(monkeypatch, no_sleep, command):
    _running(monkeypatch, ["python3", "ffmpeg"])
    with pytest.raises(Slept):
        utils.sleep_check_process(command, 1, sleep=1)


def test_starts_when_below_limit(monkeypatch, no_sleep):
    _running(monkeypatch, ["python3", "ffmpeg"])
    assert utils.sleep_check_process("/usr/bin/ffmpeg", 2, sleep=1) is True


def test_other_processes_are_not_counted(monkeypatch, no_sleep):
    _running(monkeypatch, ["ffprobe", "HandBrakeCLI", "makemkvcon"])
    assert utils.sleep_check_process("/usr/bin/ffmpeg", 1, sleep=1) is True


def test_plain_names_still_match(monkeypatch, no_sleep):
    _running(monkeypatch, ["HandBrakeCLI"])
    with pytest.raises(Slept):
        utils.sleep_check_process("HandBrakeCLI", 1, sleep=1)


@pytest.mark.parametrize("command, expected", [("/usr/bin/ffmpeg", "ffmpeg"), ("FFMPEG", "ffmpeg"),
                                               ("'/opt/my tools/ffmpeg' -nostdin", "ffmpeg"), ("", "")])
def test_executable_name(command, expected):
    assert utils.executable_name(command) == expected
