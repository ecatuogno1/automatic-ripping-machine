"""Recognise game discs from read-only reads of the disc

ARM rips a game disc like any other data disc (dd to an .iso). This module only works out which
platform the disc is for, so the job can be named after it and the log says what was found.
Nothing is written to the disc and nothing extra is mounted: the first 16 sectors (the system area,
where GameCube, Wii and Dreamcast keep their boot header), sector 32 (the Xbox XDVDFS header) and,
when identify() has mounted the disc, a few files in its root folder are read.

The detection functions take the bytes and file names they look at, so they can be tested without
a drive.
"""

import logging
import os
import re
from collections import namedtuple

from arm.ripper import utils

SECTOR = 2048
SYSTEM_CNF_MAX_BYTES = 4096

Game = namedtuple("Game", "platform evidence title product strong")

PLATFORMS = {
    "ps1": "PlayStation",
    "ps2": "PlayStation 2",
    "xbox": "Xbox",
    "gamecube": "GameCube",
    "wii": "Wii",
    "dreamcast": "Dreamcast",
    "pc": "PC",
}

# What a game disc that a normal drive can't read looks like to ARM: udev reports a DVD (or CD)
# but the drive returns no data from the start of the disc, so it can't be mounted either.
UNREADABLE_HINT = ("The drive could not read the start of this disc. If it is a GameCube, Wii, Xbox, Xbox 360 or "
                   "Dreamcast (GD-ROM) game, a normal DVD drive can't read it: these discs need a modified or "
                   "special drive (or the console itself) to be dumped.")


def _text(data, start, length):
    """Printable header text, or None"""
    value = data[start:start + length].decode("ascii", "replace")
    value = re.sub(r"[^\x20-\x7e]+", " ", value)
    return re.sub(r"\s+", " ", value).strip() or None


def from_system_area(head, sector32=None):
    """
    A console boot header in the first 16 sectors (or the Xbox header in sector 32)\n
    :param bytes head: sectors 0-15 of the disc (may be shorter or empty)
    :param bytes sector32: sector 32 of the disc, or None
    :return: Game or None
    """
    head = head or b""
    if head[0x1C:0x20] == bytes.fromhex("C2339F3D"):
        return Game("gamecube", "GameCube disc header", _text(head, 0x20, 64), _text(head, 0, 6), True)
    if head[0x18:0x1C] == bytes.fromhex("5D1C9EA3"):
        return Game("wii", "Wii disc header", _text(head, 0x20, 64), _text(head, 0, 6), True)
    if head[:16] == b"SEGA SEGAKATANA ":
        return Game("dreamcast", "Dreamcast IP.BIN header", _text(head, 0x80, 128), _text(head, 0x40, 10), True)
    if sector32 and sector32[:20] == b"MICROSOFT*XBOX*MEDIA":
        return Game("xbox", "Xbox XDVDFS header", None, None, True)
    return None


def _product(boot_path):
    """SLUS-20062 from a SYSTEM.CNF boot path like cdrom0:\\SLUS_200.62;1"""
    found = re.search(r"([A-Z]{4})[_-](\d{3})\.(\d{2})", boot_path.upper())
    return "%s-%s%s" % found.groups() if found else None


def from_system_cnf(text):
    """
    PlayStation 1 or 2 from the disc's SYSTEM.CNF (BOOT2 is PlayStation 2, BOOT is PlayStation)\n
    :param str text: contents of SYSTEM.CNF
    :return: Game or None
    """
    boot2 = re.search(r"^\s*BOOT2\s*=\s*(\S+)", text, re.M | re.I)
    if boot2:
        return Game("ps2", "SYSTEM.CNF BOOT2 line", None, _product(boot2.group(1)), True)
    boot = re.search(r"^\s*BOOT\s*=\s*(\S+)", text, re.M | re.I)
    if boot:
        return Game("ps1", "SYSTEM.CNF BOOT line", None, _product(boot.group(1)), True)
    return None


def from_root_names(names):
    """
    A PC program disc from its root folder. Plenty of software and driver CDs have an
    AUTORUN.INF too, so this is only a hint (strong=False).\n
    :param names: file names in the disc's root folder
    :return: Game or None
    """
    upper = {str(name).upper() for name in names}
    if "AUTORUN.INF" in upper:
        return Game("pc", "AUTORUN.INF", None, None, False)
    programs = sorted(name for name in upper if name.endswith(".EXE"))
    if programs:
        return Game("pc", "Windows program " + programs[0], None, None, False)
    return None


def read_sectors(devpath):
    """
    Sectors 0-15 and sector 32 of the disc, read-only\n
    :return: (head, sector32); either is None when the drive can't read it
    """
    head = sector32 = None
    try:
        with open(devpath, "rb", buffering=0) as disc:
            head = disc.read(16 * SECTOR) or None
            disc.seek(32 * SECTOR)
            sector32 = disc.read(SECTOR) or None
    except OSError as error:
        logging.debug(f"Could not read the start of {devpath}: {error}")
    return head, sector32


def _root_files(mountpoint):
    """{UPPERCASE NAME: real name} of the mounted disc's root folder"""
    try:
        return {name.upper(): name for name in os.listdir(mountpoint)}
    except OSError:
        return {}


def _read_system_cnf(mountpoint, files):
    if "SYSTEM.CNF" not in files:
        return None
    try:
        with open(os.path.join(mountpoint, files["SYSTEM.CNF"]), "rb") as config:
            return config.read(SYSTEM_CNF_MAX_BYTES).decode("ascii", "replace")
    except OSError:
        return None


def detect(head, sector32, root_names=(), system_cnf=None):
    """
    The game platform the disc's evidence supports, strongest evidence first\n
    :return: Game or None
    """
    found = from_system_area(head, sector32)
    if found is None and system_cnf:
        found = from_system_cnf(system_cnf)
    if found is None:
        found = from_root_names(root_names)
    return found


def job_title(job, game):
    """'<title> (<platform>)' with the header's title when it has one, else the disc label"""
    name = game.title or job.label or "Game disc"
    return f"{name} ({PLATFORMS[game.platform]})"


def check(job, mounted):
    """
    Look for a game disc while identify() still has it mounted. Never fails a rip.\n
    A data disc with a console marker gets the platform in its title. A disc udev called a DVD or
    Blu-ray that could not be mounted but carries a console header is ripped as data (MakeMKV can't
    rip a game disc). An unmountable video disc whose first sectors can't be read gets a log line
    explaining the special-drive platforms.\n
    :param job: Current job
    :param bool mounted: identify() mounted the disc
    :return: Game or None
    """
    if job.disctype not in ("data", "dvd", "bluray"):
        return None
    if job.disctype != "data" and mounted:
        return None  # a mounted video disc: identify() has already found VIDEO_TS or BDMV
    try:
        return _check(job, mounted)
    except Exception as error:  # noqa: BLE001 - detection only names the disc
        logging.warning(f"Game disc detection skipped: {error}")
        return None


def _check(job, mounted):
    head, sector32 = read_sectors(job.devpath)
    files = _root_files(job.mountpoint) if mounted and job.mountpoint else {}
    game = detect(head, sector32, files.keys(), _read_system_cnf(job.mountpoint, files) if files else None)
    if game is None:
        if job.disctype != "data" and head is None:
            logging.info(UNREADABLE_HINT)
        return None
    platform = PLATFORMS[game.platform]
    product = f" ({game.product})" if game.product else ""
    if not game.strong:
        logging.info(f"Data disc looks like {platform} software ({game.evidence}); ripping it as a data disc")
        return game
    logging.info(f"Game disc detected: {platform}{product} from its {game.evidence}; ripping it as a data disc")
    changes = {"title": job_title(job, game)}
    changes["title_auto"] = changes["title"]
    if job.disctype != "data":
        logging.info(f"Changing disc type from {job.disctype} to data: MakeMKV can't rip a {platform} disc")
        changes["disctype"] = "data"
    utils.database_updater(changes, job)
    return game
