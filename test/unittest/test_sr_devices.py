"""Drives numbered /dev/sr10 and above are handled like /dev/sr0-/dev/sr9 (#1574)."""
import fnmatch
import io
import logging
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import arm.ripper.main as ripper_main

REPO = Path(__file__).resolve().parents[2]
DEVICES = ["sr0", "sr1", "sr9", "sr10", "sr11", "sr23"]


def _kernel_patterns(rules_file):
    patterns = []
    for line in rules_file.read_text().splitlines():
        if line.lstrip().startswith("#"):
            continue
        patterns += re.findall(r'KERNEL=="([^"]+)"', line)
    return patterns


@pytest.mark.parametrize("rules_file", sorted((REPO / "setup").glob("*.rules")), ids=lambda p: p.name)
def test_udev_rules_match_every_sr_device(rules_file):
    for pattern in _kernel_patterns(rules_file):
        for device in DEVICES:
            # udev matches KERNEL with fnmatch-style globs ('|' separates alternatives)
            assert any(fnmatch.fnmatchcase(device, alt) for alt in pattern.split("|")), (rules_file.name, device)


@pytest.mark.parametrize("script", ["scripts/installers/DebianInstaller.sh", "scripts/installers/docker-setup.sh"])
def test_installer_mount_point_loops_cover_every_sr_device(script):
    globs = re.findall(r"for dev in (/dev/sr\S*); do", (REPO / script).read_text())
    assert globs
    for pattern in globs:
        for device in DEVICES:
            assert fnmatch.fnmatchcase(f"/dev/{device}", pattern), (pattern, device)


def _run_check_fstab(monkeypatch, devpath, fstab):
    monkeypatch.setattr(ripper_main, "job", SimpleNamespace(devpath=devpath))
    monkeypatch.setattr(ripper_main, "open", lambda *_a, **_k: io.StringIO(fstab), raising=False)
    ripper_main.check_fstab()


def test_check_fstab_does_not_take_sr10_entry_for_sr1(monkeypatch, caplog):
    fstab = "/dev/sr10  /mnt/dev/sr10  udf,iso9660  defaults,users,utf8,ro  0  0\n"
    with caplog.at_level(logging.INFO):
        _run_check_fstab(monkeypatch, "/dev/sr1", fstab)
    assert "No fstab entry found" in caplog.text
    assert "fstab entry is" not in caplog.text


def test_check_fstab_finds_sr10_entry(monkeypatch, caplog):
    fstab = ("/dev/sr1  /mnt/dev/sr1  udf,iso9660  defaults,users,utf8,ro  0  0\n"
             "/dev/sr10  /mnt/dev/sr10  udf,iso9660  defaults,users,utf8,ro  0  0\n")
    with caplog.at_level(logging.INFO):
        _run_check_fstab(monkeypatch, "/dev/sr10", fstab)
    assert "fstab entry is: /dev/sr10  /mnt/dev/sr10" in caplog.text
