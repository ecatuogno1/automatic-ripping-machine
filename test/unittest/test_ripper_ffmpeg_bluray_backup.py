"""FFmpeg transcodes of a MakeMKV Blu-ray backup (RIPMETHOD backup) read the folder through bluray:"""
import types

import pytest

import arm.ripper.ffmpeg as ffmpeg


@pytest.fixture
def backup(tmp_path):
    """A MakeMKV backup folder: <raw>/<title>/BDMV/..."""
    folder = tmp_path / "Inception"
    (folder / "BDMV" / "STREAM").mkdir(parents=True)
    (folder / "BDMV" / "index.bdmv").write_bytes(b"")
    return folder


@pytest.fixture
def probe_cmds(monkeypatch):
    """Record ffprobe commands; ffprobe 'fails' like it does on a directory"""
    cmds = []

    def fake_check_output(cmd, **_kwargs):
        cmds.append(cmd)
        raise ffmpeg.subprocess.CalledProcessError(1, cmd, output=b"Is a directory")
    monkeypatch.setattr(ffmpeg.subprocess, "check_output", fake_check_output)
    return cmds


@pytest.fixture
def fake_job(monkeypatch):
    """A job whose tracks and commits stay in memory (like put_track would register them)"""
    job = types.SimpleNamespace(no_of_titles=None, tracks=[], config=None)

    def fake_put_track(job_, t_no, seconds, *_args):
        job_.tracks.append(types.SimpleNamespace(track_number=str(t_no), length=seconds))
    monkeypatch.setattr(ffmpeg.utils, "put_track", fake_put_track)
    monkeypatch.setattr(ffmpeg, "ffmpeg_sleep_check", lambda _job: None)
    monkeypatch.setattr(ffmpeg, "db", types.SimpleNamespace(session=types.SimpleNamespace(commit=lambda: None)))
    return job


def test_input_for_backup_folder_is_bluray(backup):
    assert ffmpeg.ffmpeg_input(str(backup)) == f"bluray:{backup}"
    assert ffmpeg.ffmpeg_input(str(backup / "BDMV")) == f"bluray:{backup}"


def test_input_for_files_and_devices_is_unchanged(tmp_path):
    mkv = tmp_path / "title_t00.mkv"
    mkv.write_bytes(b"")
    assert ffmpeg.ffmpeg_input(str(mkv)) == str(mkv)
    assert ffmpeg.ffmpeg_input("/dev/sr0") == "/dev/sr0"


def test_probe_reads_backup_through_bluray(backup, probe_cmds):
    ffmpeg.probe_source(str(backup))
    assert probe_cmds
    assert f"bluray:{backup}" in probe_cmds[0]


def test_unreadable_backup_fails_with_reason_not_type_error(backup, probe_cmds, fake_job):
    # main: ffprobe failed on the folder, a fallback track 0 was registered with no_of_titles None,
    # and ffmpeg_all crashed with "'>' not supported between instances of 'int' and 'NoneType'"
    with pytest.raises(RuntimeError, match="libbluray"):
        ffmpeg.ffmpeg_all(str(backup), "/tmp/out", fake_job)


def test_folder_without_bdmv_fails_with_reason(tmp_path, probe_cmds, fake_job):
    (tmp_path / "title_t00.mkv").write_bytes(b"")
    with pytest.raises(RuntimeError, match="RIPMETHOD"):
        ffmpeg.ffmpeg_all(str(tmp_path), "/tmp/out", fake_job)


def test_transcode_command_reads_backup_through_bluray(backup, probe_cmds, monkeypatch):
    started = []

    class FakePopen:
        def __init__(self, args, **_kwargs):
            started.append(args)
            self.stdout = []
            self.returncode = 0

        def wait(self):
            return 0
    monkeypatch.setattr(ffmpeg.subprocess, "Popen", FakePopen)
    ffmpeg.run_transcode_cmd(str(backup), "/tmp/out/title_1.mkv", None, "-y", "-c copy")

    assert f"bluray:{backup}" in started[0]
    assert f"bluray:{backup}" in probe_cmds[0]
