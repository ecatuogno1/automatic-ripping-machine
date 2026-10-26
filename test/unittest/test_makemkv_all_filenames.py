"""After a MakeMKV "all" rip the tracks point at the files MakeMKV actually wrote."""

from types import SimpleNamespace

import pytest

from arm.ripper import makemkv


def track(number, filename, ripped=True):
    return SimpleNamespace(track_number=str(number), filename=filename, ripped=ripped)


@pytest.fixture
def no_db(monkeypatch):
    monkeypatch.setattr(makemkv.db.session, "commit", lambda: None)


def rip_all(monkeypatch, tmp_path, tracks, written):
    """Run makemkv_mkv() down the "all" branch with MakeMKV writing ``written`` into tmp_path."""
    def fake_run(cmd, select):
        for name in written:
            (tmp_path / name).write_bytes(b"x")
        return iter(())

    monkeypatch.setattr(makemkv.utils, "get_drive_mode", lambda devpath: "auto")
    monkeypatch.setattr(makemkv, "get_track_info", lambda index, job: None)
    monkeypatch.setattr(makemkv, "progress_log", lambda job: str(tmp_path / "progress.log"))
    monkeypatch.setattr(makemkv, "run", fake_run)
    config = SimpleNamespace(MAINFEATURE=False, MAXLENGTH="99999", MINLENGTH="600", MKV_ARGS="")
    job = SimpleNamespace(devpath="/dev/sr0", drive=SimpleNamespace(mdisc=0), config=config, tracks=tracks)
    makemkv.makemkv_mkv(job, str(tmp_path))


def test_all_rip_renumbered_files_are_matched(monkeypatch, tmp_path, no_db):
    # Short titles 0, 1 and 3 aren't saved, so MakeMKV numbers the saved titles 2 and 4 as t00 and t01
    tracks = [track(0, "B1_t00.mkv", False), track(1, "B4_t01.mkv", False), track(2, "A1_t02.mkv"),
              track(3, "C1_t03.mkv", False), track(4, "C2_t04.mkv")]

    rip_all(monkeypatch, tmp_path, tracks, ["A1_t00.mkv", "C2_t01.mkv"])

    assert tracks[2].filename == "A1_t00.mkv"
    assert tracks[4].filename == "C2_t01.mkv"
    assert tracks[0].filename == "B1_t00.mkv"


def test_same_named_titles_are_matched_by_order(tmp_path, no_db):
    # DVD titles are all called title_tNN; title_t01 on disk is title 3, not title 1
    for name in ("title_t00.mkv", "title_t01.mkv"):
        (tmp_path / name).write_bytes(b"x")
    tracks = [track(0, "title_t00.mkv", False), track(1, "title_t01.mkv"), track(3, "title_t03.mkv")]

    makemkv.reconcile_track_filenames(SimpleNamespace(tracks=tracks), str(tmp_path))

    assert tracks[1].filename == "title_t00.mkv"
    assert tracks[2].filename == "title_t01.mkv"


@pytest.mark.parametrize("written", [
    ["A1_t00.mkv"],                     # fewer files than ripped tracks
    ["X9_t00.mkv", "C2_t01.mkv"],       # a file from another title
])
def test_unmatched_files_leave_names_alone(tmp_path, no_db, written):
    for name in written:
        (tmp_path / name).write_bytes(b"x")
    tracks = [track(2, "A1_t02.mkv"), track(4, "C2_t04.mkv")]

    makemkv.reconcile_track_filenames(SimpleNamespace(tracks=tracks), str(tmp_path))

    assert [t.filename for t in tracks] == ["A1_t02.mkv", "C2_t04.mkv"]


def test_matching_names_are_kept(tmp_path, no_db):
    (tmp_path / "A1_t00.mkv").write_bytes(b"x")
    tracks = [track(0, "A1_t00.mkv")]

    makemkv.reconcile_track_filenames(SimpleNamespace(tracks=tracks), str(tmp_path))

    assert tracks[0].filename == "A1_t00.mkv"
