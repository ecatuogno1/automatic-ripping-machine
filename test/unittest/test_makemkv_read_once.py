"""READ_ONCE_DVD: copy a DVD once with dvdbackup, then let MakeMKV make the titles from the copy."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import arm.config.config as cfg
from arm.models import Track
from arm.ripper import makemkv, utils
from arm.ui import app, db

JOB_ID = 4242
LABEL = "MY_MOVIE"
# A stand-in for dvdbackup -M -r a -i <device> -o <dir> -n <name>: writes <dir>/<name>/VIDEO_TS
FAKE_DVDBACKUP = '''
import os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_DVDBACKUP_LOG"], "a") as log:
    log.write(" ".join(args) + "\\n")
mode = os.environ.get("FAKE_DVDBACKUP_MODE", "ok")
video_ts = os.path.join(args[args.index("-o") + 1], args[args.index("-n") + 1], "VIDEO_TS")
os.makedirs(video_ts)
files = {"VIDEO_TS.IFO": b"DVDVIDEO-VMG", "VIDEO_TS.BUP": b"DVDVIDEO-VMG",
         "VTS_01_0.IFO": b"DVDVIDEO-VTS", "VTS_01_1.VOB": b"video"}
if mode == "bad_ifo":
    files["VTS_01_0.IFO"] = b"garbage"
for name, data in files.items():
    with open(os.path.join(video_ts, name), "wb") as member:
        member.write(data + b"\\0" * 64)
if mode == "read_error":
    print("Error reading VTS_01_1.VOB", file=sys.stderr)
    sys.exit(1)
'''
SCAN = ['TCOUNT:1', 'TINFO:0,9,0,"1:30:00"', f'TINFO:0,27,0,"{LABEL}_t00.mkv"']


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Fake makemkvcon (recorded) and dvdbackup (a script); READ_ONCE_DVD enabled."""
    raw = tmp_path / "raw"
    raw.mkdir()
    tool = tmp_path / "dvdbackup"
    tool.write_text(f"#!{sys.executable}\n{FAKE_DVDBACKUP}")
    tool.chmod(0o755)
    log = tmp_path / "dvdbackup.log"
    monkeypatch.setenv("FAKE_DVDBACKUP_LOG", str(log))
    state = SimpleNamespace(commands=[], fail_from_copy=False, raw=raw,
                            dvdbackup=lambda: log.read_text().splitlines() if log.exists() else [])

    def fake_run(options, select):
        state.commands.append(list(options))
        source = next(o for o in options if o.startswith(("dev:", "file:", "disc:")))
        if options[0] == "info":
            for line in SCAN:
                msg_type, data = makemkv.parse_line(line)
                if msg_type in select:
                    yield data
            return
        output = Path(options[options.index("all") + 1])
        (output / f"{LABEL}_t00.mkv").write_bytes(b"mkv")
        if state.fail_from_copy and source.startswith("file:"):
            raise makemkv.MakeMkvRuntimeError(2, options, output="Failed to open the copy")

    monkeypatch.setattr(makemkv, "run", fake_run)
    monkeypatch.setattr(makemkv, "prep_mkv", lambda: None)
    monkeypatch.setattr(makemkv, "setup_rawpath", lambda _job, _path: tempfile.mkdtemp(prefix="rip_", dir=raw))
    monkeypatch.setattr(makemkv, "sleep", lambda *_: None)
    monkeypatch.setattr(makemkv, "disc_size", lambda _devpath: 1024, raising=False)
    monkeypatch.setattr(makemkv.shutil, "which", lambda name: str(tool) if name == "dvdbackup" else None)
    monkeypatch.setattr(utils, "sleep_check_process", lambda *_a, **_k: None)
    monkeypatch.setattr(utils, "get_drive_mode", lambda _devpath: "auto")
    monkeypatch.setitem(cfg.arm_config, "READ_ONCE_DVD", True)
    with app.app_context():
        db.create_all()
        monkeypatch.setattr(db.session, "refresh", lambda _obj: None)
        yield state
        Track.query.filter_by(job_id=JOB_ID).delete()
        db.session.commit()


def _job(raw, disctype="dvd"):
    config = SimpleNamespace(RIPMETHOD="mkv", MKV_ARGS="", MINLENGTH=600, MAXLENGTH=99999, MAINFEATURE=False,
                             MANUAL_WAIT_TIME=0, LOGPATH=str(raw), RAW_PATH=str(raw))
    return SimpleNamespace(job_id=JOB_ID, devpath="/dev/sr0", disctype=disctype, title="My Movie", label=LABEL,
                           config=config, drive=SimpleNamespace(mdisc=0), status=None, has_track_99=False,
                           eject=lambda: None)


def _sources(state, command):
    return [o for cmd in state.commands if cmd[0] == command
            for o in cmd if o.startswith(("dev:", "file:", "disc:"))]


def _backups(state):
    return sorted(p.name for p in state.raw.iterdir() if "_dvd_backup_" in p.name)


def test_titles_are_made_from_one_copy_of_the_disc(env):
    rawpath = makemkv.makemkv(_job(env.raw))
    copied = env.dvdbackup()
    assert len(copied) == 1
    # mirror the whole disc, abort on a read error instead of leaving a gap
    assert copied[0].startswith("-M -r a -i /dev/sr0 -o ")
    assert copied[0].endswith(f"-n {LABEL}")
    video_ts = os.path.join(copied[0].split(" -o ")[1].split(" -n ")[0], LABEL, "VIDEO_TS")
    assert _sources(env, "info") == [f"file:{video_ts}"]
    assert _sources(env, "mkv") == [f"file:{video_ts}"]
    assert os.listdir(rawpath) == [f"{LABEL}_t00.mkv"]
    # the temporary copy is gone once the titles are made
    assert _backups(env) == []


def test_disabled_by_default_rips_from_the_disc(env, monkeypatch):
    monkeypatch.delitem(cfg.arm_config, "READ_ONCE_DVD")
    makemkv.makemkv(_job(env.raw))
    assert env.dvdbackup() == []
    assert _sources(env, "mkv") == ["dev:/dev/sr0"]


@pytest.mark.parametrize("mode", ["read_error", "bad_ifo"])
def test_a_failed_or_incomplete_copy_is_removed_and_the_disc_ripped(env, monkeypatch, mode):
    monkeypatch.setenv("FAKE_DVDBACKUP_MODE", mode)
    makemkv.makemkv(_job(env.raw))
    assert len(env.dvdbackup()) == 1
    assert _sources(env, "info") == ["disc:0"]
    assert _sources(env, "mkv") == ["dev:/dev/sr0"]
    assert _backups(env) == []


def test_copy_is_kept_and_disc_ripped_when_makemkv_fails_on_the_copy(env):
    env.fail_from_copy = True
    rawpath = makemkv.makemkv(_job(env.raw))
    assert [s.split(":")[0] for s in _sources(env, "mkv")] == ["file", "dev"]
    # the verified whole-disc copy survives for the user
    kept = _backups(env)
    assert len(kept) == 1
    assert (env.raw / kept[0] / LABEL / "VIDEO_TS" / "VIDEO_TS.IFO").is_file()
    # the second rip starts clean: one MKV, one track row
    assert os.listdir(rawpath) == [f"{LABEL}_t00.mkv"]
    assert Track.query.filter_by(job_id=JOB_ID).count() == 1


def test_missing_dvdbackup_rips_from_the_disc(env, monkeypatch):
    monkeypatch.setattr(makemkv.shutil, "which", lambda _name: None)
    makemkv.makemkv(_job(env.raw))
    assert _sources(env, "mkv") == ["dev:/dev/sr0"]


def test_not_enough_space_rips_from_the_disc(env, monkeypatch):
    monkeypatch.setattr(makemkv, "disc_size", lambda _devpath: 10 ** 18)
    makemkv.makemkv(_job(env.raw))
    assert env.dvdbackup() == []
    assert _sources(env, "mkv") == ["dev:/dev/sr0"]


def test_protected_and_bluray_discs_are_not_copied(env):
    protected = _job(env.raw)
    protected.has_track_99 = True
    makemkv.makemkv(protected)
    makemkv.makemkv(_job(env.raw, disctype="bluray"))
    assert env.dvdbackup() == []
    assert _sources(env, "mkv") == ["dev:/dev/sr0", "dev:/dev/sr0"]
