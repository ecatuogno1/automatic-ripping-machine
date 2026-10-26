"""Identification commands can be time-limited, and expected conditions aren't logged as errors."""
import logging
import subprocess
import sys
from types import SimpleNamespace

import pytest

import arm.config.config as cfg
from arm.ripper import identify
from arm.ripper.ProcessHandler import arm_subprocess

PYTHON = sys.executable


def _errors(caplog):
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_timeout_stops_the_command_and_returns_none(caplog):
    with caplog.at_level(logging.DEBUG):
        result = arm_subprocess([PYTHON, "-c", "import time; time.sleep(30)"], timeout=0.5)
    assert result is None
    assert "did not finish within 0.5s" in caplog.text


def test_timeout_raises_with_check():
    with pytest.raises(subprocess.TimeoutExpired):
        arm_subprocess([PYTHON, "-c", "import time; time.sleep(30)"], timeout=0.5, check=True)


def test_signal_death_is_reported_by_name(caplog):
    cmd = [PYTHON, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGSEGV)"]
    with caplog.at_level(logging.DEBUG):
        assert arm_subprocess(cmd) is None
    assert "died with SIGSEGV" in caplog.text


def test_expected_returncode_is_logged_at_debug(caplog):
    with caplog.at_level(logging.DEBUG):
        assert arm_subprocess([PYTHON, "-c", "raise SystemExit(1)"], expected_returncodes=(1,)) is None
    assert not _errors(caplog)
    assert "exited with status 1" in caplog.text


def test_failure_level_lowers_the_log_level_and_drops_the_traceback(caplog):
    with caplog.at_level(logging.DEBUG):
        arm_subprocess([PYTHON, "-c", "raise SystemExit(2)"], failure_level=logging.WARNING)
    assert not _errors(caplog)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].exc_info is None


def test_other_failures_are_still_errors(caplog):
    with caplog.at_level(logging.DEBUG):
        arm_subprocess([PYTHON, "-c", "raise SystemExit(2)"])
    assert len(_errors(caplog)) == 1


@pytest.mark.parametrize("value, expected", [(0, None), ("", None), (None, None), ("bad", None), (120, 120)])
def test_identify_timeout_setting(monkeypatch, value, expected):
    monkeypatch.setitem(cfg.arm_config, "IDENTIFY_TIMEOUT_SECONDS", value)
    assert identify.identify_timeout() == expected


def test_setting_ships_disabled():
    assert cfg.arm_config["IDENTIFY_TIMEOUT_SECONDS"] == 0


def test_nothing_mounted_yet_is_not_an_error(monkeypatch, caplog):
    def findmnt_nothing_mounted(cmd, **_kwargs):
        raise subprocess.CalledProcessError(1, cmd, output="")

    monkeypatch.setattr(subprocess, "check_output", findmnt_nothing_mounted)
    with caplog.at_level(logging.DEBUG):
        assert identify.find_mount("/dev/sr0") is None
    assert not _errors(caplog)


def test_hanging_lsdvd_is_stopped_and_identification_continues(monkeypatch, caplog):
    calls = []

    def lsdvd_hangs(cmd, **kwargs):
        calls.append((cmd, kwargs.get("timeout")))
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    def fail(*_args, **_kwargs):
        raise RuntimeError("not available in this test")

    monkeypatch.setitem(cfg.arm_config, "IDENTIFY_TIMEOUT_SECONDS", 120)
    monkeypatch.setattr(subprocess, "check_output", lsdvd_hangs)
    monkeypatch.setattr(identify.pydvdid, "compute", fail)
    monkeypatch.setattr(identify, "metadata_selector", fail)
    job = SimpleNamespace(label="DAMAGED", year=None, title="Damaged", devpath="/dev/sr0", mountpoint="/mnt/dev/sr0",
                          crc_id=None, has_track_99=False, pretty_table=lambda: "")
    with caplog.at_level(logging.DEBUG):
        assert identify.identify_dvd(job) is True
    assert calls == [(["lsdvd", "-Oy", "/dev/sr0"], 120)]
    assert "did not finish within 120s" in caplog.text
    # identification goes on without the title list; pydvdid's failure is the only error
    assert all("Pydvdid" in r.getMessage() for r in _errors(caplog))
