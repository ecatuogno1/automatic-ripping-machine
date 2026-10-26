"""Tests for the error reported when makemkvcon exits non-zero"""
from types import SimpleNamespace

import pytest

import arm.ui  # noqa: F401 - import order: arm.ui before the ripper (arm.models)
from arm.ripper import arm_ripper, makemkv, utils

MKV_CMD = ["mkv", "dev:/dev/sr0", "all", "/raw"]


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


def run_makemkvcon(monkeypatch, lines, returncode):
    monkeypatch.setattr(makemkv.shutil, "which", lambda name: "/usr/bin/makemkvcon")
    monkeypatch.setattr(makemkv.subprocess, "Popen", lambda cmd, **kwargs: FakeMakemkvcon(lines, returncode))
    return list(makemkv.run(MKV_CMD, makemkv.OutputType.MSG))


def test_non_zero_exit_reports_makemkvs_last_message(monkeypatch):
    output = ['MSG:1005,0,1,"MakeMKV v1.17.8 started","%1 started","MakeMKV v1.17.8"',
              'PRGV:10,20,65536',
              'MSG:5010,0,0,"Failed to open disc","Failed to open disc"']
    with pytest.raises(makemkv.MakeMkvRuntimeError) as error:
        run_makemkvcon(monkeypatch, output, 11)
    assert str(error.value) == "Call to MakeMKV failed with code: 11: Failed to open disc"


def test_error_context_is_bounded(monkeypatch, caplog):
    output = [f'MSG:1011,0,1,"line {i}","%1","line {i}"' for i in range(500)]
    caplog.set_level("DEBUG")
    with pytest.raises(makemkv.MakeMkvRuntimeError) as error:
        run_makemkvcon(monkeypatch, output, 1)
    assert str(error.value).endswith(": line 499")
    logged = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("MakeMKV output: "))
    context = logged[len("MakeMKV output: "):].splitlines()
    assert len(context) == 200
    assert context[0] == "line 300"


def test_successful_exit_raises_nothing(monkeypatch):
    output = ['MSG:5005,0,1,"2 titles saved","%1 titles saved","2"']
    assert [message.code for message in run_makemkvcon(monkeypatch, output, 0)] == [5005]


def test_error_without_output_keeps_the_exit_code_message():
    assert str(makemkv.MakeMkvRuntimeError(2, ["mkv"])) == "Call to MakeMKV failed with code: 2"
    assert str(makemkv.MakeMkvRuntimeError(2, ["mkv"], output="\n")) == "Call to MakeMKV failed with code: 2"


def test_job_error_carries_the_makemkv_reason(monkeypatch, tmp_path):
    """job.errors (UI and notification) is the RipperException text"""
    def failed_rip(job):
        raise makemkv.MakeMkvRuntimeError(11, ["mkv"], output="Failed to open disc")

    monkeypatch.setattr(utils, "convert_job_type", lambda video_type: "movies")
    monkeypatch.setattr(utils, "fix_job_title", lambda job: "Title (2001)")
    monkeypatch.setattr(utils, "check_for_dupe_folder", lambda have_dupes, path, job: path)
    monkeypatch.setattr(utils, "database_updater", lambda args, job: True)
    monkeypatch.setattr(utils, "save_disc_poster", lambda path, job: None)
    monkeypatch.setattr(arm_ripper, "rip_with_mkv", lambda job, protection: True)
    monkeypatch.setattr(arm_ripper.db.session, "commit", lambda: None)
    monkeypatch.setattr(makemkv, "makemkv", failed_rip)
    job = SimpleNamespace(video_type="movie", devpath="/dev/sr0", status=None,
                          config=SimpleNamespace(TRANSCODE_PATH=str(tmp_path / "transcode"),
                                                 COMPLETED_PATH=str(tmp_path / "completed")))
    with pytest.raises(utils.RipperException, match="Error while running MakeMKV: .*Failed to open disc"):
        arm_ripper.rip_visual_media(False, job, "job.log", 0)
