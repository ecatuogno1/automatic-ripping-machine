"""AccurateRip verification of abcde's FLAC output (ACCURATERIP_VERIFY)."""

import os
import random
import stat
import struct
import sys
from types import SimpleNamespace

import pytest

from arm.ripper import accuraterip

# (tracks on disc, track, frames, kind, v1, v2): checksums of seeded PCM, cross-checked with
# ARver 1.5.0 and accuraterip-checksum, which agreed with each other on every vector.
VECTORS = [
    (1, 1, 23520, "max", "f3a27090", "ffffbb17"),
    (3, 1, 7644, "max", "fe8412d4", "ffffed9f"),
    (3, 2, 12348, "max", "fb74a0da", "ffffcfc4"),
    (3, 3, 17640, "ramp", "ecf3651c", "ede9d174"),
    (4, 1, 7056, "max", "fec60602", "ffffefeb"),
    (4, 2, 4116, "noise", "8f8c692d", "8fcd5717"),
    (4, 3, 14700, "noise", "7044d61c", "738226c5"),
    (4, 4, 5292, "max", "ffd5c6e8", "fffff6d0"),
    (2, 1, 2940, "max", "fffff484", "ffffffff"),
    (2, 2, 3528, "noise", "fdfa30b4", "fdfb8802"),
]


def vector_pcm():
    rng = random.Random(1846)
    for _count, _track, frames, _kind, _v1, _v2 in VECTORS:
        kind = rng.choice(["noise", "max", "ramp"])
        if kind == "noise":
            yield kind, bytes(rng.getrandbits(8) for _ in range(frames * 4))
        elif kind == "max":
            yield kind, b"\xff" * (frames * 4)
        else:
            yield kind, b"".join((i % 65536).to_bytes(2, "little") * 2 for i in range(frames))


def test_checksums_match_reference_implementations():
    for (count, track, frames, kind, v1, v2), (generated, data) in zip(VECTORS, vector_pcm()):
        assert generated == kind
        assert accuraterip.checksums([data], frames, track, count) == (int(v1, 16), int(v2, 16))
        # Chunk boundaries (even mid-frame) must not change the result.
        step = 4 * 587 + 2
        chunks = [data[i:i + step] for i in range(0, len(data), step)]
        assert accuraterip.checksums(chunks, frames, track, count) == (int(v1, 16), int(v2, 16))


def test_checksum_rejects_audio_shorter_or_longer_than_the_toc():
    with pytest.raises(accuraterip.AccurateRipError):
        accuraterip.checksums([b"\x00" * 8], 3, 1, 1)
    with pytest.raises(accuraterip.AccurateRipError):
        accuraterip.checksums([b"\x00" * 10], 2, 2, 2)
    with pytest.raises(accuraterip.AccurateRipError):
        accuraterip.checksums([b""], 0, 3, 2)


def test_disc_ids():
    # Cross-checked with libdiscid (FreeDB id) and ARver (AccurateRip ids).
    assert accuraterip.disc_ids([150, 22345, 40000, 61234], 90000) == "004-00033ff3-000d15b7-2e04ae04"
    # MusicBrainz disc 1P6UC2rLbzoS4UcC7O6cRJhfEc4- (Abbey Road); AccurateRip serves a dBAR file for this id.
    offsets = [150, 19849, 33726, 49423, 65078, 78067, 113257, 127326, 139893, 158225, 169350, 174474, 180081,
               189063, 196083, 203500, 214139]
    assert accuraterip.disc_ids(offsets, 215885) == "017-00237985-01b1c52e-e60b3c11"
    assert accuraterip.dbar_url(accuraterip.DEFAULT_URL, "017-00237985-01b1c52e-e60b3c11") == (
        accuraterip.DEFAULT_URL + "/5/8/9/dBAR-017-00237985-01b1c52e-e60b3c11.bin")
    assert accuraterip.track_frames([150, 170], 200) == [20 * 588, 30 * 588]


def dbar(ids, responses):
    count, first, second, cddb = ids.split("-")
    body = b""
    for tracks in responses:
        body += struct.pack("<BIII", int(count), int(first, 16), int(second, 16), int(cddb, 16))
        for confidence, crc in tracks:
            body += struct.pack("<BII", confidence, crc, 0)
    return body


IDS = "002-00000abc-00000def-0a000102"


def test_parse_dbar_and_match_rules():
    body = dbar(IDS, [[(5, 0x11), (0, 0x22)], [(12, 0xAA), (3, 0xBB)]])
    responses = accuraterip.parse_dbar(body, IDS)
    assert responses == [[(5, 0x11), (0, 0x22)], [(12, 0xAA), (3, 0xBB)]]
    # v1 or v2 may match; the best confidence wins.
    assert accuraterip.match_track(responses, 1, 0xAA, 0x11) == {"status": "match", "confidence": 12}
    assert accuraterip.match_track(responses, 2, 0x01, 0xBB) == {"status": "match", "confidence": 3}
    # A checksum with confidence 0 never counts.
    assert accuraterip.match_track(responses, 2, 0x22, 0x22) == {"status": "mismatch", "confidence": 0}
    with pytest.raises(accuraterip.AccurateRipError):
        accuraterip.parse_dbar(body, "002-00000abc-00000def-ffffffff")
    with pytest.raises(accuraterip.AccurateRipError):
        accuraterip.parse_dbar(body[:-3], IDS)


def fake_get(status=200, body=b"", error=None):
    def get(url, timeout):
        assert url.startswith("https://")
        assert timeout
        if error:
            raise error
        return SimpleNamespace(status_code=status, content=body)
    return get


def test_lookup_tells_absent_from_unavailable():
    body = dbar(IDS, [[(5, 0x11), (2, 0x22)]])
    assert accuraterip.lookup(IDS, get=fake_get(body=body)) == ("present", [[(5, 0x11), (2, 0x22)]])
    assert accuraterip.lookup(IDS, get=fake_get(status=404)) == ("absent", [])
    assert accuraterip.lookup(IDS, get=fake_get(status=503)) == ("unavailable", [])
    assert accuraterip.lookup(IDS, get=fake_get(body=b"\x01junk")) == ("unavailable", [])
    assert accuraterip.lookup(IDS, get=fake_get(error=TimeoutError())) == ("unavailable", [])


# --- rip_music with ACCURATERIP_VERIFY -----------------------------------------------------------

SECTORS = [20, 15, 25]
OFFSETS = [150, 170, 185]
LEADOUT = 210

# abcde writes one "FLAC" per track; our fake format is a TRACKNUMBER line followed by raw PCM.
ABCDE = r'''#!{python}
import os, random
out = os.environ["FAKE_ABCDE_OUT"] + "/Artist/Album"
os.makedirs(out, exist_ok=True)
for n, sectors in enumerate({sectors}, 1):
    pcm = random.Random("track-%d" % n).randbytes(sectors * 588 * 4)
    with open(out + "/%02d - Song.flac" % n, "wb") as f:
        f.write(b"%d\n" % n + pcm)
print("Finished.")
'''
METAFLAC = r'''#!{python}
import sys
print("TRACKNUMBER=" + open(sys.argv[-1], "rb").readline().decode().strip())
'''
FLAC = r'''#!{python}
import sys
data = open(sys.argv[-1], "rb").read()
sys.stdout.buffer.write(data[data.index(b"\n") + 1:])
'''


def pcm(number):
    return random.Random("track-%d" % number).randbytes(SECTORS[number - 1] * 588 * 4)


def disc_checksums():
    return [accuraterip.checksums([pcm(n)], SECTORS[n - 1] * 588, n, 3) for n in (1, 2, 3)]


@pytest.fixture
def rip(tmp_path, monkeypatch):
    import requests
    import arm.config.config as cfg
    from arm.ripper import music_brainz, utils

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, script in (("abcde", ABCDE), ("metaflac", METAFLAC), ("flac", FLAC)):
        path = bin_dir / name
        path.write_text(script.format(python=sys.executable, sectors=SECTORS))
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_ABCDE_OUT", str(tmp_path / "music"))
    conf = tmp_path / "abcde.conf"
    conf.write_text('OUTPUTTYPE=flac\nOUTPUTDIR="%s"\n' % (tmp_path / "music"))
    monkeypatch.setitem(cfg.arm_config, "ABCDE_CONFIG_FILE", str(conf))
    monkeypatch.setitem(cfg.arm_config, "ACCURATERIP_VERIFY", True)
    disc = SimpleNamespace(first_track_num=1, sectors=LEADOUT, tracks=[SimpleNamespace(offset=o) for o in OFFSETS])
    monkeypatch.setattr(music_brainz, "get_disc_id", lambda job: disc)
    updates, notes, served = [], [], {}
    monkeypatch.setattr(utils, "database_updater", lambda values, job: updates.append(values))
    monkeypatch.setattr(utils, "notify", lambda job, title, body: notes.append(body))
    monkeypatch.setattr(utils, "record_accuraterip_tracks", lambda job, result: None)
    monkeypatch.setattr(requests, "get", lambda url, timeout: SimpleNamespace(**served))
    job = SimpleNamespace(disctype="music", devpath="/dev/sr0", title="Album",
                          config=SimpleNamespace(LOGPATH=str(tmp_path)))
    ids = accuraterip.disc_ids(OFFSETS, LEADOUT)

    def run(crcs=None, status=200, fail_on_mismatch=False):
        monkeypatch.setitem(cfg.arm_config, "ACCURATERIP_FAIL_ON_MISMATCH", fail_on_mismatch)
        served.update(status_code=status, content=dbar(ids, [[(4, crc) for crc in crcs]]) if crcs else b"")
        return utils.rip_music(job, "music.log")

    return run, updates, notes


def test_accurate_rip_is_reported(rip):
    run, updates, notes = rip
    assert run(crcs=[v2 for _v1, v2 in disc_checksums()]) is True
    assert updates[-1] == {"status": "active"}
    assert notes == ["Music CD: Album AccurateRip: 3 of 3 tracks accurately ripped"]


def test_mismatch_is_flagged_but_keeps_the_rip_by_default(rip):
    run, updates, notes = rip
    crcs = [v1 for v1, _v2 in disc_checksums()]
    crcs[1] ^= 1
    assert run(crcs=crcs) is True
    assert notes[-1].endswith("2 of 3 tracks accurately ripped; track(s) 2 did not match")


def test_mismatch_fails_the_job_when_configured(rip):
    run, updates, _ = rip
    crcs = [v1 for v1, _v2 in disc_checksums()]
    crcs[2] ^= 1
    assert run(crcs=crcs, fail_on_mismatch=True) is False
    assert updates[-1]["status"] == "fail"
    assert "track(s) 3 did not match" in updates[-1]["errors"]


@pytest.mark.parametrize("status,text", [(404, "not in the database"), (500, "lookup failed")])
def test_unknown_disc_never_fails_the_job(rip, status, text):
    run, updates, notes = rip
    assert run(status=status, fail_on_mismatch=True) is True
    assert text in notes[-1]
