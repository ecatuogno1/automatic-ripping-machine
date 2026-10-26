"""With SKIP_TRANSCODE the main feature is the longest file, not the largest."""

import json
from types import SimpleNamespace

from arm.ripper import arm_ripper


def write(path, name, size):
    (path / name).write_bytes(b"x" * size)


def fake_probe(monkeypatch, lengths):
    """ffprobe answers with the length in ``lengths`` for each file name, and fails for the rest."""
    def probe(file_path):
        name = file_path.rsplit("/", 1)[-1]
        if name not in lengths:
            return None
        return json.dumps({"format": {"duration": str(lengths[name])},
                           "streams": [{"codec_type": "video", "duration": str(lengths[name])}]})

    monkeypatch.setattr(arm_ripper.ffmpeg, "probe_source", probe)


def test_longest_file_beats_larger_extra(monkeypatch, tmp_path):
    # A 37 minute high-bitrate extra is larger than the 76 minute film
    write(tmp_path, "title_t10.mkv", 1400)
    write(tmp_path, "title_t53.mkv", 1500)
    fake_probe(monkeypatch, {"title_t10.mkv": 4560, "title_t53.mkv": 2220})

    assert arm_ripper.find_main_feature_file(["title_t53.mkv", "title_t10.mkv"], str(tmp_path)) == "title_t10.mkv"


def test_size_breaks_a_tie_and_covers_unreadable_lengths(monkeypatch, tmp_path):
    write(tmp_path, "a.mkv", 100)
    write(tmp_path, "b.mkv", 200)
    fake_probe(monkeypatch, {"a.mkv": 5000, "b.mkv": 5000})
    assert arm_ripper.find_main_feature_file(["a.mkv", "b.mkv"], str(tmp_path)) == "b.mkv"

    fake_probe(monkeypatch, {})
    assert arm_ripper.find_main_feature_file(["a.mkv", "b.mkv"], str(tmp_path)) == "b.mkv"


def test_skip_transcode_movie_moves_longest_as_main(monkeypatch, tmp_path):
    write(tmp_path, "title_t10.mkv", 1400)
    write(tmp_path, "title_t53.mkv", 1500)
    fake_probe(monkeypatch, {"title_t10.mkv": 4560, "title_t53.mkv": 2220})
    moved = []
    monkeypatch.setattr(arm_ripper.utils, "move_files",
                        lambda base, file, job, is_main: moved.append((file, is_main)))
    job = SimpleNamespace(video_type="movie", config=SimpleNamespace(MAINFEATURE=False, EXTRAS_SUB="extras"))

    arm_ripper.skip_transcode_movie(["title_t53.mkv", "title_t10.mkv"], job, str(tmp_path))

    assert ("title_t10.mkv", True) in moved
    assert ("title_t53.mkv", False) in moved


def test_no_files(tmp_path):
    assert arm_ripper.find_main_feature_file([], str(tmp_path)) == ""
