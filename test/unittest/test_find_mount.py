"""find_mount() only returns where the disc's filesystem is mounted, not where the device node is (#1784)."""
import json

from arm.ripper import identify

DEVPATH = "/dev/sr0"


def _findmnt(monkeypatch, filesystems):
    calls = []

    def fake_subprocess(cmd, **_kwargs):
        calls.append(cmd)
        return json.dumps({"filesystems": filesystems})

    monkeypatch.setattr(identify, "arm_subprocess", fake_subprocess)
    monkeypatch.setattr(identify.os, "access", lambda *_args: True)
    return calls


def test_findmnt_matches_the_source_device_only(monkeypatch):
    calls = _findmnt(monkeypatch, [{"target": "/mnt/dev/sr0", "source": DEVPATH}])
    assert identify.find_mount(DEVPATH) == "/mnt/dev/sr0"
    assert calls == [["findmnt", "--json", "--source", DEVPATH]]


def test_bind_mounted_device_node_is_not_a_mountpoint(monkeypatch):
    # LXC passes the drive in by bind-mounting the node onto /dev/sr0
    _findmnt(monkeypatch, [{"target": DEVPATH, "source": "udev[/sr0]"}])
    assert identify.find_mount(DEVPATH) is None
