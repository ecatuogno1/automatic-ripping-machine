"""Optional Radarr/Sonarr/Lidarr import after a rip: request shape, opt-in and failure handling."""
import datetime
import os
import secrets
import types

import pytest
import requests

import arm.config.config as cfg
from arm.ripper import arm_ripper, arr, utils
from arm.ripper import main as ripper_main

RADARR = "https://radarr.example"


class Response:
    def __init__(self, status=201):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code > 299:
            raise requests.exceptions.HTTPError(f"{self.status_code} error", response=self)


@pytest.fixture
def settings(monkeypatch):
    for key in ("RADARR", "SONARR", "LIDARR"):
        monkeypatch.setitem(cfg.arm_config, f"{key}_URL", "")
        monkeypatch.setitem(cfg.arm_config, f"{key}_API_KEY", "")
    monkeypatch.setitem(cfg.arm_config, "ARR_IMPORT_MODE", "Move")
    monkeypatch.setitem(cfg.arm_config, "ARR_PATH_MAP", "")
    return lambda key, value: monkeypatch.setitem(cfg.arm_config, key, value)


@pytest.fixture
def posts(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(arr.requests, "post", post)
    return calls


def video_job(tmp_path, video_type="movie"):
    folder = tmp_path / "completed" / video_type / "Some Title (2001)"
    folder.mkdir(parents=True)
    (folder / "Some Title (2001).mkv").write_bytes(b"x")
    return types.SimpleNamespace(disctype="bluray", video_type=video_type, path=str(folder),
                                 start_time=datetime.datetime.now())


def test_movie_rip_asks_radarr_to_import_its_folder(tmp_path, settings, posts, caplog):
    credential = secrets.token_hex(16)
    settings("RADARR_URL", RADARR + "/")
    settings("RADARR_API_KEY", credential)
    job = video_job(tmp_path)
    caplog.set_level("DEBUG")

    assert arr.import_job(job) is True
    assert len(posts) == 1
    url, kwargs = posts[0]
    assert url == RADARR + "/api/v3/command"
    assert kwargs["json"] == {"name": "DownloadedMoviesScan", "path": job.path, "importMode": "Move"}
    assert kwargs["headers"] == {"X-Api-Key": credential}
    assert kwargs["timeout"]
    assert credential not in caplog.text


def test_nothing_is_sent_when_the_app_is_not_configured(tmp_path, settings, posts):
    settings("RADARR_URL", RADARR)
    assert arr.import_job(video_job(tmp_path)) is False
    assert posts == []


def test_unreachable_app_logs_a_warning_and_never_raises(tmp_path, settings, monkeypatch, caplog):
    credential = secrets.token_hex(16)
    settings("RADARR_URL", RADARR)
    settings("RADARR_API_KEY", credential)

    def refuse(url, **kwargs):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(arr.requests, "post", refuse)
    assert arr.import_job(video_job(tmp_path)) is False
    assert "Radarr import request failed (ConnectionError)" in caplog.text
    assert credential not in caplog.text


def test_rejected_request_is_logged_with_its_status(tmp_path, settings, monkeypatch, caplog):
    settings("RADARR_URL", RADARR)
    settings("RADARR_API_KEY", secrets.token_hex(16))
    monkeypatch.setattr(arr.requests, "post", lambda url, **kwargs: Response(401))
    assert arr.import_job(video_job(tmp_path)) is False
    assert "HTTP 401" in caplog.text


def test_series_goes_to_sonarr_with_the_mapped_path(tmp_path, settings, posts):
    settings("SONARR_URL", "https://sonarr.example")
    settings("SONARR_API_KEY", secrets.token_hex(16))
    settings("RADARR_URL", RADARR)
    settings("RADARR_API_KEY", secrets.token_hex(16))
    settings("ARR_IMPORT_MODE", "Copy")
    settings("ARR_PATH_MAP", f"/elsewhere=/x;{tmp_path}/completed=/data/completed")
    job = video_job(tmp_path, "series")

    assert arr.import_job(job) is True
    url, kwargs = posts[0]
    assert url == "https://sonarr.example/api/v3/command"
    assert kwargs["json"] == {"name": "DownloadedEpisodesScan", "importMode": "Copy",
                              "path": "/data/completed/series/Some Title (2001)"}


def test_unidentified_and_data_discs_are_not_sent(tmp_path, settings, posts):
    settings("RADARR_URL", RADARR)
    settings("RADARR_API_KEY", secrets.token_hex(16))
    job = video_job(tmp_path, "unknown")
    assert arr.import_job(job) is False
    job.disctype, job.video_type = "data", "movie"
    assert arr.import_job(job) is False
    assert posts == []


def test_missing_output_folder_is_not_sent(tmp_path, settings, posts):
    settings("RADARR_URL", RADARR)
    settings("RADARR_API_KEY", secrets.token_hex(16))
    job = video_job(tmp_path)
    job.path = str(tmp_path / "never-created")
    assert arr.import_job(job) is False
    assert posts == []


def music_setup(tmp_path, monkeypatch, settings):
    music = tmp_path / "music"
    old_album = music / "Old Artist" / "Old Album"
    old_album.mkdir(parents=True)
    (old_album / "01 - Old.flac").write_bytes(b"x")
    started = datetime.datetime.now() + datetime.timedelta(seconds=-5)
    old_time = (started - datetime.timedelta(days=1)).timestamp()
    os.utime(old_album / "01 - Old.flac", (old_time, old_time))
    monkeypatch.setattr(cfg, "abcde_config", f'# comment\nOUTPUTDIR="{music}/"\n')
    settings("LIDARR_URL", "https://lidarr.example")
    settings("LIDARR_API_KEY", secrets.token_hex(16))
    return music, types.SimpleNamespace(disctype="music", video_type="Music", path=None, start_time=started)


def test_music_cd_sends_lidarr_the_album_folder_abcde_wrote(tmp_path, monkeypatch, settings, posts):
    music, job = music_setup(tmp_path, monkeypatch, settings)
    album = music / "New Artist" / "New Album"
    album.mkdir(parents=True)
    for number in (1, 2):
        (album / f"0{number} - Track.flac").write_bytes(b"x")

    assert arr.import_job(job) is True
    url, kwargs = posts[0]
    assert url == "https://lidarr.example/api/v1/command"
    assert kwargs["json"]["name"] == "DownloadedAlbumsScan"
    assert kwargs["json"]["path"] == str(album)


def test_music_cd_is_skipped_when_two_albums_were_written(tmp_path, monkeypatch, settings, posts):
    music, job = music_setup(tmp_path, monkeypatch, settings)
    for name in ("One", "Two"):
        (music / name).mkdir()
        (music / name / "01.flac").write_bytes(b"x")
    assert arr.import_job(job) is False
    assert posts == []


def test_finished_video_rip_hands_its_folder_over(monkeypatch, tmp_path):
    for name in ("database_updater", "save_disc_poster", "delete_raw_files", "move_movie_poster", "scan_emby",
                 "set_permissions", "notify"):
        monkeypatch.setattr(utils, name, lambda *a, **k: None)
    monkeypatch.setattr(utils, "check_for_dupe_folder", lambda have_dupes, path, job: path)
    for name in ("start_transcode", "move_files_post", "notify_exit"):
        monkeypatch.setattr(arm_ripper, name, lambda *a, **k: None)
    monkeypatch.setattr(arm_ripper, "rip_with_mkv", lambda *a, **k: False)
    imported = []
    monkeypatch.setattr(arr, "import_job", imported.append)
    job = types.SimpleNamespace(video_type="movie", title="Some Title", year="2001", title_manual=None,
                                hasnicetitle=True, devpath="/dev/sr0",
                                config=types.SimpleNamespace(TRANSCODE_PATH=str(tmp_path), COMPLETED_PATH=str(tmp_path),
                                                             SKIP_TRANSCODE=False))
    arm_ripper.rip_visual_media(False, job, "disc.log", False)
    assert imported == [job]


def test_finished_music_rip_hands_its_album_over(monkeypatch):
    from arm.ripper import identify, music_brainz
    for module, name in ((identify, "identify"), (utils, "notify_entry"), (utils, "check_for_wait"),
                         (utils, "notify"), (utils, "scan_emby"), (music_brainz, "main"),
                         (ripper_main, "log_arm_params"), (ripper_main, "check_fstab")):
        monkeypatch.setattr(module, name, lambda *a, **k: None)
    monkeypatch.setattr(utils, "job_dupe_check", lambda job: False)
    monkeypatch.setattr(utils, "rip_music", lambda job, logfile: True)
    monkeypatch.setattr(ripper_main.db.session, "commit", lambda: None)
    imported = []
    monkeypatch.setattr(arr, "import_job", imported.append)
    job = types.SimpleNamespace(disctype="music", title="Album", status="active")
    monkeypatch.setattr(ripper_main, "job", job, raising=False)
    monkeypatch.setattr(ripper_main, "log_file", "disc.log", raising=False)
    ripper_main.main()
    assert imported == [job]


def test_settings_are_off_by_default_and_documented():
    import json
    import yaml
    from arm.config import config_utils

    root = os.path.join(os.path.dirname(__file__), "..", "..")
    with open(os.path.join(root, "setup", "arm.yaml")) as defaults_file:
        defaults = yaml.safe_load(defaults_file)
    with open(os.path.join(root, "arm", "ui", "comments.json")) as comments_file:
        comments = json.load(comments_file)
    for app in ("RADARR", "SONARR", "LIDARR"):
        for key in (f"{app}_URL", f"{app}_API_KEY"):
            assert defaults[key] == ""
            assert comments[key].startswith("#")
    for key in ("ARR_IMPORT_MODE", "ARR_PATH_MAP"):
        assert comments[key].startswith("#")
    assert "Radarr / Sonarr / Lidarr" in config_utils.arm_yaml_check_groups(comments, "RADARR_URL")
