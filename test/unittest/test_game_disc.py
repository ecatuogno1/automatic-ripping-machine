"""Game disc detection from synthetic sectors and files (no real disc data)"""
from types import SimpleNamespace

import pytest

from arm.ripper import game_disc

SECTOR = game_disc.SECTOR


def system_area(*fields):
    """16 zeroed sectors with (offset, bytes) fields written in"""
    head = bytearray(16 * SECTOR)
    for offset, value in fields:
        head[offset:offset + len(value)] = value
    return bytes(head)


def disc_image(path, head=b"", sector32=b""):
    """A file laid out like a disc: system area, then sector 32"""
    data = bytearray(33 * SECTOR)
    data[:len(head)] = head
    data[32 * SECTOR:32 * SECTOR + len(sector32)] = sector32
    path.write_bytes(bytes(data))
    return str(path)


GAMECUBE = system_area((0, b"GABC01"), (0x1C, bytes.fromhex("C2339F3D")), (0x20, b"Example Game"))
WII = system_area((0, b"RABC01"), (0x18, bytes.fromhex("5D1C9EA3")), (0x20, b"Example Wii Game"))
DREAMCAST = system_area((0, b"SEGA SEGAKATANA "), (0x40, b"T-0000    "), (0x80, b"EXAMPLE GAME"))


@pytest.mark.parametrize("head, platform, title, product", [
    (GAMECUBE, "gamecube", "Example Game", "GABC01"),
    (WII, "wii", "Example Wii Game", "RABC01"),
    (DREAMCAST, "dreamcast", "EXAMPLE GAME", "T-0000"),
])
def test_console_headers_in_the_system_area(head, platform, title, product):
    game = game_disc.from_system_area(head)
    assert game.platform == platform
    assert game.title == title
    assert game.product == product
    assert game.strong


def test_xbox_header_in_sector_32():
    game = game_disc.from_system_area(bytes(16 * SECTOR), b"MICROSOFT*XBOX*MEDIA" + bytes(SECTOR - 20))
    assert game.platform == "xbox"
    assert game.strong


def test_plain_data_disc_has_no_console_header():
    assert game_disc.from_system_area(bytes(16 * SECTOR), bytes(SECTOR)) is None
    assert game_disc.from_system_area(None, None) is None
    assert game_disc.from_system_area(b"short", None) is None


def test_system_cnf_tells_playstation_2_from_playstation():
    ps2 = game_disc.from_system_cnf("BOOT2 = cdrom0:\\SLUS_000.00;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n")
    assert ps2.platform == "ps2"
    assert ps2.product == "SLUS-00000"
    ps1 = game_disc.from_system_cnf("BOOT = cdrom:\\SCES_000.01;1\r\nTCB = 4\r\nEVENT = 10\r\n")
    assert ps1.platform == "ps1"
    assert ps1.product == "SCES-00001"
    assert game_disc.from_system_cnf("VER = 1.00\r\n") is None


def test_pc_disc_is_only_a_hint():
    autorun = game_disc.from_root_names(["autorun.inf", "SETUP.EXE"])
    assert autorun.platform == "pc"
    assert autorun.evidence == "AUTORUN.INF"
    assert not autorun.strong
    assert game_disc.from_root_names(["SETUP.EXE"]).evidence == "Windows program SETUP.EXE"
    assert game_disc.from_root_names(["README.TXT", "PHOTOS"]) is None


def test_console_header_wins_over_files():
    game = game_disc.detect(GAMECUBE, None, ["AUTORUN.INF"], "BOOT2 = cdrom0:\\SLUS_000.00;1")
    assert game.platform == "gamecube"
    assert game_disc.detect(bytes(16 * SECTOR), None, ["AUTORUN.INF"], "BOOT2 = x").platform == "ps2"


def test_read_sectors_reads_the_system_area_and_sector_32(tmp_path):
    path = disc_image(tmp_path / "disc", GAMECUBE, b"MICROSOFT*XBOX*MEDIA")
    head, sector32 = game_disc.read_sectors(path)
    assert head == GAMECUBE
    assert sector32.startswith(b"MICROSOFT*XBOX*MEDIA")
    assert game_disc.read_sectors(str(tmp_path / "missing")) == (None, None)


def job_for(tmp_path, disctype, head=b"", files=None, label="GAME_LABEL"):
    mount = tmp_path / "mnt"
    mount.mkdir()
    for name, data in (files or {}).items():
        (mount / name).write_bytes(data)
    return SimpleNamespace(devpath=disc_image(tmp_path / "sr0", head), mountpoint=str(mount),
                           disctype=disctype, label=label, title=None, job_id=1)


@pytest.fixture
def updates(monkeypatch):
    seen = []

    def database_updater(args, job, wait_time=90):
        seen.append(args)
        for key, value in args.items():
            setattr(job, key, value)
        return True

    monkeypatch.setattr(game_disc.utils, "database_updater", database_updater)
    return seen


def test_playstation_data_disc_is_named_after_its_platform(tmp_path, updates, caplog):
    caplog.set_level("INFO")
    job = job_for(tmp_path, "data", files={"SYSTEM.CNF": b"BOOT2 = cdrom0:\\SLUS_000.00;1\r\n", "DATA.BIN": b"x"})
    assert game_disc.check(job, mounted=True).platform == "ps2"
    assert job.title == "GAME_LABEL (PlayStation 2)"
    assert job.disctype == "data"
    assert "Game disc detected: PlayStation 2 (SLUS-00000) from its SYSTEM.CNF BOOT2 line" in caplog.text


def test_header_title_is_used_when_the_disc_has_one(tmp_path, updates):
    job = job_for(tmp_path, "data", head=DREAMCAST)
    game_disc.check(job, mounted=True)
    assert job.title == "EXAMPLE GAME (Dreamcast)"


def test_unmountable_video_disc_with_a_console_header_is_ripped_as_data(tmp_path, updates):
    job = job_for(tmp_path, "dvd", head=GAMECUBE)
    game_disc.check(job, mounted=False)
    assert job.disctype == "data"
    assert job.title == "Example Game (GameCube)"


def test_mounted_video_disc_is_left_alone(tmp_path, updates):
    job = job_for(tmp_path, "dvd", head=GAMECUBE)
    assert game_disc.check(job, mounted=True) is None
    assert job.disctype == "dvd"
    assert updates == []


def test_pc_and_plain_data_discs_keep_their_job_unchanged(tmp_path, updates, caplog):
    caplog.set_level("INFO")
    job = job_for(tmp_path, "data", files={"AUTORUN.INF": b"[autorun]\r\nopen=setup.exe\r\n"})
    assert game_disc.check(job, mounted=True).platform == "pc"
    assert "looks like PC software (AUTORUN.INF)" in caplog.text
    (tmp_path / "plain").mkdir()
    plain = job_for(tmp_path / "plain", "data", files={"PHOTO.JPG": b"x"})
    assert game_disc.check(plain, mounted=True) is None
    assert updates == []
    assert job.title is None


def test_unreadable_video_disc_explains_special_drive_platforms(tmp_path, updates, caplog):
    caplog.set_level("INFO")
    job = SimpleNamespace(devpath=str(tmp_path / "missing"), mountpoint="", disctype="dvd", label=None)
    assert game_disc.check(job, mounted=False) is None
    assert "GameCube, Wii, Xbox, Xbox 360" in caplog.text
    assert job.disctype == "dvd"


def test_music_discs_are_not_read(tmp_path, monkeypatch):
    monkeypatch.setattr(game_disc, "read_sectors", lambda path: pytest.fail("music disc was read"))
    assert game_disc.check(SimpleNamespace(disctype="music"), mounted=True) is None


def test_detection_errors_never_fail_the_rip(tmp_path, monkeypatch, caplog):
    def broken(path):
        raise ValueError("bad read")

    monkeypatch.setattr(game_disc, "read_sectors", broken)
    job = SimpleNamespace(devpath="/dev/sr0", mountpoint="", disctype="data", label=None)
    assert game_disc.check(job, mounted=False) is None
    assert "Game disc detection skipped" in caplog.text


def test_identify_checks_data_discs_before_unmounting(monkeypatch):
    from arm.ripper import identify

    calls = []
    monkeypatch.setattr(identify, "check_mount", lambda job: True)
    monkeypatch.setattr(identify.utils, "find_file", lambda name, path: False)
    monkeypatch.setattr(identify, "arm_subprocess", lambda cmd: calls.append(("cmd", cmd[0])))
    monkeypatch.setattr(identify.game_disc, "check", lambda job, mounted: calls.append(("check", mounted)))
    job = SimpleNamespace(devpath="/dev/sr0", mountpoint="/mnt/dev/sr0", disctype="data",
                          get_disc_type=lambda found: None)
    identify.identify(job)
    assert calls == [("check", True), ("cmd", "umount")]
