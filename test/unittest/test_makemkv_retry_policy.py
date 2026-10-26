"""Tests for classifying failed MakeMKV calls and the opt-in MAKEMKV_READ_RETRIES policy"""
import pytest

import arm.ui  # noqa: F401 - import order: arm.ui before the ripper (arm.models)
from arm.ripper import makemkv

STARTED = 'MSG:1005,0,1,"MakeMKV v1.17.8 started","%1 started","MakeMKV v1.17.8"'


def read_error(error):
    return (f'MSG:2003,0,3,"Error \'{error}\' occurred while reading \'/VIDEO_TS/VTS_01_1.VOB\' '
            f'at offset \'1048576\'",'
            f'"Error \'%1\' occurred while reading \'%2\' at offset \'%3\'",'
            f'"{error}","/VIDEO_TS/VTS_01_1.VOB","1048576"')


MEDIUM_ERROR = read_error(makemkv.ERROR_MESSAGE_MEDIUM_ERROR)
TRAY_OPEN = read_error(makemkv.ERROR_MESSAGE_TRAY_OPEN)
OPEN_FAILED = 'MSG:5010,0,0,"Failed to open disc","Failed to open disc"'
EXPIRED = 'MSG:5021,260,1,"This application version is too old.","%1","This application version is too old."'
WRITE_ERROR = ('MSG:2019,0,2,"Error \'Posix error - No space left on device\' occurred while creating \'/raw/t.mkv\'",'
               '"Error \'%1\' occurred while creating \'%2\'","Posix error - No space left on device","/raw/t.mkv"')


class FakeMakemkvcon:
    """Stands in for subprocess.Popen(makemkvcon ...): fixed stdout lines, then an exit code"""

    def __init__(self, lines, returncode):
        self.lines = [line + "\n" for line in lines]
        self.returncode = None
        self.exit_code = returncode
        self.pid = 1234

    @property
    def stdout(self):
        yield from self.lines
        self.returncode = self.exit_code

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def failed_call(monkeypatch, lines, returncode=1):
    """Run makemkv.run() against canned output and return the MakeMkvRuntimeError it raised"""
    monkeypatch.setattr(makemkv.shutil, "which", lambda name: "/usr/bin/makemkvcon")
    monkeypatch.setattr(makemkv.subprocess, "Popen", lambda cmd, **kwargs: FakeMakemkvcon(lines, returncode))
    monkeypatch.setitem(makemkv.cfg.arm_config, "STALL_ABORT_SECONDS", 0)
    with pytest.raises(makemkv.MakeMkvRuntimeError) as error:
        list(makemkv.run(["mkv", "dev:/dev/sr0", "all", "/raw"], makemkv.OutputType.MSG))
    return error.value


@pytest.mark.parametrize("lines, expected", [
    ([STARTED, MEDIUM_ERROR, MEDIUM_ERROR], makemkv.FailureClass.READ_ERROR),
    ([STARTED, OPEN_FAILED], makemkv.FailureClass.READ_ERROR),
    ([STARTED, MEDIUM_ERROR, TRAY_OPEN], makemkv.FailureClass.DISC_REMOVED),
    ([STARTED, MEDIUM_ERROR, EXPIRED], makemkv.FailureClass.LICENCE),
    ([STARTED, MEDIUM_ERROR, WRITE_ERROR], makemkv.FailureClass.WRITE_ERROR),
    ([STARTED], makemkv.FailureClass.OTHER),
])
def test_failed_call_is_classified_from_its_messages(monkeypatch, lines, expected):
    assert failed_call(monkeypatch, lines).failure_class == expected


def test_failed_title_is_classified(monkeypatch):
    # RIP_TITLE_ERROR raises while makemkvcon is still running
    title_failed = ('MSG:5003,0,2,"Failed to save title 0 to file /raw/t.mkv",'
                    '"Failed to save title %1 to file %2","0","/raw/t.mkv"')
    error = failed_call(monkeypatch, [STARTED, MEDIUM_ERROR, title_failed], returncode=0)
    assert error.failure_class == makemkv.FailureClass.READ_ERROR


def test_stall_is_classified():
    error = makemkv.MakeMkvStalledError(5, ["makemkvcon"])
    assert makemkv.failure_class(error, set()) == makemkv.FailureClass.STALLED
    assert makemkv.failure_class(error, {makemkv.FailureClass.DISC_REMOVED}) == makemkv.FailureClass.DISC_REMOVED


class FakeRun:
    """Stands in for makemkv.run(): each call fails with the next class (or succeeds on None)"""

    def __init__(self, rawpath, outcomes):
        self.rawpath = rawpath
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, cmd, select):
        self.calls += 1
        (self.rawpath / f"title_t0{self.calls}.mkv").write_bytes(b"partial")
        outcome = self.outcomes.pop(0)
        if outcome is not None:
            error = makemkv.MakeMkvRuntimeError(1, list(cmd))
            error.failure_class = outcome
            raise error
        yield from ()


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.setattr(makemkv, "sleep", lambda seconds: None)
    (tmp_path / "earlier_track.mkv").write_bytes(b"done")
    return tmp_path


def rip_pass(monkeypatch, raw, retries, outcomes):
    fake = FakeRun(raw, outcomes)
    monkeypatch.setattr(makemkv, "run", fake)
    monkeypatch.setitem(makemkv.cfg.arm_config, "MAKEMKV_READ_RETRIES", retries)
    makemkv.rip_pass(["mkv", "dev:/dev/sr0", "1", str(raw)], str(raw))
    return fake


def test_read_error_is_retried_once_from_a_clean_folder(monkeypatch, raw):
    fake = rip_pass(monkeypatch, raw, 1, [makemkv.FailureClass.READ_ERROR, None])
    assert fake.calls == 2
    assert sorted(p.name for p in raw.iterdir()) == ["earlier_track.mkv", "title_t02.mkv"]


def test_stall_is_retried(monkeypatch, raw):
    assert rip_pass(monkeypatch, raw, 1, [makemkv.FailureClass.STALLED, None]).calls == 2


@pytest.mark.parametrize("failure", [makemkv.FailureClass.LICENCE, makemkv.FailureClass.DISC_REMOVED,
                                     makemkv.FailureClass.WRITE_ERROR, makemkv.FailureClass.OTHER])
def test_other_failures_are_never_retried(monkeypatch, raw, failure):
    with pytest.raises(makemkv.MakeMkvRipFailed) as error:
        rip_pass(monkeypatch, raw, 3, [failure, None])
    assert str(error.value) == f"MakeMKV rip failed: {failure.value} (not retried)"


def test_retries_are_bounded(monkeypatch, raw):
    outcomes = [makemkv.FailureClass.READ_ERROR] * 3
    with pytest.raises(makemkv.MakeMkvRipFailed) as error:
        rip_pass(monkeypatch, raw, 2, outcomes)
    assert str(error.value) == "MakeMKV rip failed: the disc could not be read (after 3 attempts)"


@pytest.mark.parametrize("value", [0, "", None, "nope"])
def test_retries_off_keeps_the_original_error(monkeypatch, raw, value):
    fake = FakeRun(raw, [makemkv.FailureClass.READ_ERROR, None])
    monkeypatch.setattr(makemkv, "run", fake)
    monkeypatch.setitem(makemkv.cfg.arm_config, "MAKEMKV_READ_RETRIES", value)
    with pytest.raises(makemkv.MakeMkvRuntimeError) as error:
        makemkv.rip_pass(["mkv"], str(raw))
    assert not isinstance(error.value, makemkv.MakeMkvRipFailed)
    assert fake.calls == 1
