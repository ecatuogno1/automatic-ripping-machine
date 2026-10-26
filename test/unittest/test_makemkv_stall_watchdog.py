"""Tests for the opt-in STALL_ABORT_SECONDS watchdog around makemkvcon"""
import stat
import sys
import time

import pytest

import arm.ui  # noqa: F401 - import order: arm.ui before the ripper (arm.models)
from arm.ripper import makemkv

STARTED = 'MSG:1005,0,1,"MakeMKV v1.17.8 started","%1 started","MakeMKV v1.17.8"'


def fake_makemkvcon(tmp_path, monkeypatch, body):
    """Install a stand-in makemkvcon (a Python script) that runs ``body``"""
    script = tmp_path / "makemkvcon"
    script.write_text(f"#!{sys.executable}\nimport sys, time\nprint({STARTED!r}, flush=True)\n{body}\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(makemkv.shutil, "which", lambda name: str(script))


def run_makemkvcon(options):
    return list(makemkv.run(options, makemkv.OutputType.MSG))


def test_silent_makemkvcon_is_stopped(tmp_path, monkeypatch):
    fake_makemkvcon(tmp_path, monkeypatch, "time.sleep(30)")
    monkeypatch.setitem(makemkv.cfg.arm_config, "STALL_ABORT_SECONDS", 1)
    started = time.monotonic()
    with pytest.raises(makemkv.MakeMkvStalledError) as error:
        run_makemkvcon(["info", "disc:0"])
    assert time.monotonic() - started < 20
    assert "made no progress for 1 seconds" in str(error.value)


def test_stalled_run_is_a_makemkv_failure(tmp_path, monkeypatch):
    fake_makemkvcon(tmp_path, monkeypatch, "time.sleep(30)")
    monkeypatch.setitem(makemkv.cfg.arm_config, "STALL_ABORT_SECONDS", "1")
    with pytest.raises(makemkv.MakeMkvRuntimeError):
        run_makemkvcon(["info", "disc:0"])


def test_progress_file_updates_keep_the_run_alive(tmp_path, monkeypatch):
    progress = tmp_path / "progress.log"
    # no stdout for 3s, but the progress bar moves every 0.2s
    fake_makemkvcon(tmp_path, monkeypatch, (
        f"f = open({str(progress)!r}, 'a')\n"
        "for i in range(15):\n"
        "    f.write(f'PRGV:{i},{i},65536\\n'); f.flush(); time.sleep(0.2)\n"
    ))
    monkeypatch.setitem(makemkv.cfg.arm_config, "STALL_ABORT_SECONDS", 1)
    messages = run_makemkvcon(["mkv", f"--progress={progress}", "dev:/dev/sr0", "all", str(tmp_path)])
    assert [m.code for m in messages] == [makemkv.MessageID.VERSION_INFO]


def test_repeated_progress_line_is_not_progress(tmp_path, monkeypatch):
    progress = tmp_path / "progress.log"
    fake_makemkvcon(tmp_path, monkeypatch, (
        f"f = open({str(progress)!r}, 'a')\n"
        "for i in range(150):\n"
        "    f.write('PRGV:5,5,65536\\n'); f.flush(); time.sleep(0.2)\n"
    ))
    monkeypatch.setitem(makemkv.cfg.arm_config, "STALL_ABORT_SECONDS", 1)
    with pytest.raises(makemkv.MakeMkvStalledError):
        run_makemkvcon(["mkv", f"--progress={progress}", "dev:/dev/sr0", "all", str(tmp_path)])


@pytest.mark.parametrize("value", [0, "", None, "not a number"])
def test_watchdog_off_waits_for_makemkvcon(tmp_path, monkeypatch, value):
    fake_makemkvcon(tmp_path, monkeypatch, "time.sleep(1.5)")
    monkeypatch.setitem(makemkv.cfg.arm_config, "STALL_ABORT_SECONDS", value)
    messages = run_makemkvcon(["info", "disc:0"])
    assert len(messages) == 1


def test_progress_file_option(tmp_path):
    assert makemkv._progress_file(["mkv", f"--progress={tmp_path}/1.log", 3]) == f"{tmp_path}/1.log"
    assert makemkv._progress_file(["info", "--progress=-stdout"]) is None
    assert makemkv._progress_file(["info", "disc:0"]) is None
