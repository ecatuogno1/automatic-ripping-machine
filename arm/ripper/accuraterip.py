"""AccurateRip verification of ripped audio-CD tracks.

AccurateRip is a public database of per-track checksums submitted by other
people who ripped the same pressing. If our checksum for a track equals one
in the database, the track was read without errors.

The checksum is the public AccurateRip definition (as implemented by ARver,
accuraterip-checksum and whipper). Each stereo 16-bit frame is read as one
little-endian unsigned 32-bit word ``s`` and multiplied by its 1-based
position ``m`` inside the track:

* v1 = sum(m * s) mod 2**32
* v2 = sum(lo32(m * s) + hi32(m * s)) mod 2**32

The first track skips its first 5 sectors (minus one frame) and the last track
skips its last 5 sectors. Since lo + hi == p - hi * (2**32 - 1), v2 is
(sum(p) + sum(hi)) mod 2**32.

Checksums are only meaningful for a rip that was corrected for the drive's
read offset (cdparanoia ``-O``), see the abcde.conf wiki page.
"""

import logging
import os
import struct
import subprocess
import sys
from array import array
from itertools import repeat
from operator import mul, rshift

DEFAULT_URL = "https://www.accuraterip.com/accuraterip"
LOOKUP_TIMEOUT = 30
LEAD_IN = 150
SECTOR_FRAMES = 588
SKIP_FRAMES = 5 * SECTOR_FRAMES
MASK = 0xFFFFFFFF
CHUNK_BYTES = SECTOR_FRAMES * 4 * 1024


class AccurateRipError(ValueError):
    """A dBAR response or checksum input is malformed."""


# --- disc ids ------------------------------------------------------------------------------------

def freedb_id(offsets, leadout):
    """FreeDB/CDDB disc id from track offsets (including the 150-sector lead-in) and the lead-out."""
    def digits(value):
        return sum(int(c) for c in str(value))

    checksum = sum(digits(offset // 75) for offset in offsets)
    seconds = leadout // 75 - offsets[0] // 75
    return "%08x" % (((checksum % 0xFF) << 24) | (seconds << 8) | len(offsets))


def disc_ids(offsets, leadout):
    """AccurateRip disc id ``NNN-id1-id2-cddb`` from the audio track offsets and lead-out (libdiscid sectors)."""
    lsn = [offset - LEAD_IN for offset in offsets]
    end = leadout - LEAD_IN
    first = sum(lsn) + end
    second = sum(max(value, 1) * number for number, value in enumerate(lsn, 1)) + end * (len(lsn) + 1)
    return "%03d-%08x-%08x-%s" % (len(offsets), first & MASK, second & MASK, freedb_id(offsets, leadout))


def track_frames(offsets, leadout):
    """Frames (stereo samples) per track."""
    ends = list(offsets[1:]) + [leadout]
    return [(end - start) * SECTOR_FRAMES for start, end in zip(offsets, ends)]


# --- checksums -----------------------------------------------------------------------------------

def checksums(chunks, frames, index, count):
    """Return (v1, v2) for raw little-endian 16-bit stereo PCM of track ``index`` of ``count``."""
    if not 1 <= index <= count:
        raise AccurateRipError("Track index is outside the disc")
    start = SKIP_FRAMES if index == 1 else 1
    end = frames - SKIP_FRAMES if index == count else frames
    total = high = 0
    position = 1  # multiplier of the first frame in the next chunk
    pending = b""
    for chunk in chunks:
        data = pending + bytes(chunk)
        usable = len(data) - len(data) % 4
        pending = data[usable:]
        words = array("I")
        if words.itemsize != 4:
            words = array("L")
        words.frombytes(data[:usable])
        if sys.byteorder == "big":
            words.byteswap()
        first = max(start, position)
        last = min(end, position + len(words) - 1)
        if first <= last:
            products = list(map(mul, range(first, last + 1), words[first - position:last - position + 1]))
            total += sum(products)
            high += sum(map(rshift, products, repeat(32)))
        position += len(words)
    if pending or position - 1 != frames:
        raise AccurateRipError("Decoded audio is %d frames; the disc's TOC says %d" % (position - 1, frames))
    return total & MASK, (total + high) & MASK


# --- dBAR ----------------------------------------------------------------------------------------

def dbar_url(base, ids):
    """URL of the dBAR file for an AccurateRip disc id."""
    count, first, second, cddb = ids.split("-")
    value = int(first, 16)
    return "%s/%x/%x/%x/dBAR-%s-%s-%s-%s.bin" % (base.rstrip("/"), value & 0xF, value >> 4 & 0xF, value >> 8 & 0xF,
                                                 count, first, second, cddb)


def parse_dbar(data, ids):
    """Parse a dBAR body into a list of responses, each a list of (confidence, crc) per track."""
    count, first, second, cddb = ids.split("-")
    expected = (int(count), int(first, 16), int(second, 16), int(cddb, 16))
    responses, offset = [], 0
    while offset < len(data):
        if offset + 13 > len(data):
            raise AccurateRipError("Truncated dBAR header")
        header = struct.unpack_from("<BIII", data, offset)
        offset += 13
        if header != expected:
            raise AccurateRipError("dBAR response belongs to a different disc")
        if offset + 9 * header[0] > len(data):
            raise AccurateRipError("Truncated dBAR track table")
        tracks = []
        for _ in range(header[0]):
            confidence, crc, _crc450 = struct.unpack_from("<BII", data, offset)
            tracks.append((confidence, crc))
            offset += 9
        responses.append(tracks)
    return responses


def lookup(ids, base_url=DEFAULT_URL, timeout=LOOKUP_TIMEOUT, get=None):
    """Return ("present" | "absent" | "unavailable", responses). Never raises for network failures."""
    if get is None:
        import requests
        get = requests.get
    try:
        response = get(dbar_url(base_url, ids), timeout=timeout)
    except Exception as error:  # DNS, timeout, refused: unknown, not "absent"
        logging.warning(f"AccurateRip lookup failed: {type(error).__name__}")
        return "unavailable", []
    if response.status_code == 404:
        return "absent", []
    if response.status_code != 200:
        logging.warning(f"AccurateRip lookup returned HTTP {response.status_code}")
        return "unavailable", []
    try:
        responses = parse_dbar(response.content or b"", ids)
    except AccurateRipError as error:
        logging.warning(f"AccurateRip returned an unreadable response: {error}")
        return "unavailable", []
    return ("present" if responses else "absent"), responses


def match_track(responses, number, v1, v2):
    """Compare one track's checksums with every response. Returns {"status", "confidence"}."""
    best = 0
    for tracks in responses:
        confidence, crc = tracks[number - 1]
        if confidence >= 1 and crc in (v1, v2):
            best = max(best, confidence)
    return {"status": "match" if best else "mismatch", "confidence": best}


# --- verifying FLAC output -----------------------------------------------------------------------

def flac_track_number(path):
    """TRACKNUMBER tag of a FLAC file ("3" or "3/12"), or None."""
    try:
        output = subprocess.run(["metaflac", "--show-tag=TRACKNUMBER", path], capture_output=True, text=True,
                                check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in output.splitlines():
        value = line.partition("=")[2].split("/")[0].strip()
        if value.isdigit():
            return int(value)
    return None


def flac_pcm(path):
    """Yield the decoded raw PCM of a FLAC file in chunks."""
    command = ["flac", "-d", "-c", "-s", "--force-raw-format", "--endian=little", "--sign=signed", path]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        while True:
            chunk = process.stdout.read(CHUNK_BYTES)
            if not chunk:
                break
            yield chunk
    if process.returncode != 0:
        raise AccurateRipError(f"flac could not decode {os.path.basename(path)}")


def find_flac_tracks(output_dir, started, first_track, count):
    """Map audio position (1..count) to the FLAC file abcde wrote for it since ``started``."""
    found = {}
    for root, _dirs, files in os.walk(output_dir):
        for name in files:
            path = os.path.join(root, name)
            if not name.lower().endswith(".flac") or os.path.getmtime(path) < started:
                continue
            number = flac_track_number(path)
            if number is None:
                continue
            position = number - first_track + 1
            if position in found or not 1 <= position <= count:
                raise AccurateRipError(f"Cannot tell which file is track {number}")
            found[position] = path
    if sorted(found) != list(range(1, count + 1)):
        raise AccurateRipError(f"Found {len(found)} tagged FLAC files for {count} audio tracks")
    return found


def verify(disc, output_dir, started, get=None):
    """
    Verify the FLAC files of a finished rip against AccurateRip\n
    :param disc: the ``discid`` disc object of the ripped CD
    :param output_dir: directory abcde wrote to
    :param started: time.time() when the rip started (older files are ignored)
    :return: {"status": "present" | "absent" | "unavailable", "id", "tracks": [{"track", "status", "confidence"}]}
    """
    offsets = [track.offset for track in disc.tracks]
    ids = disc_ids(offsets, disc.sectors)
    status, responses = lookup(ids, get=get)
    result = {"status": status, "id": ids, "tracks": []}
    if status != "present":
        return result
    files = find_flac_tracks(output_dir, started, disc.first_track_num, len(offsets))
    for position, frames in enumerate(track_frames(offsets, disc.sectors), 1):
        try:
            v1, v2 = checksums(flac_pcm(files[position]), frames, position, len(offsets))
        except AccurateRipError as error:
            logging.warning(f"AccurateRip: track {position}: {error}")
            row = {"status": "mismatch", "confidence": 0}
        else:
            row = match_track(responses, position, v1, v2)
            logging.info(f"AccurateRip: track {position} v1={v1:08x} v2={v2:08x} {row['status']} "
                         f"(confidence {row['confidence']})")
        result["tracks"].append({"track": position, **row})
    return result


def summary(result):
    """One line for the job log and the notification."""
    if result["status"] == "absent":
        return f"AccurateRip: disc {result['id']} is not in the database, tracks not verified"
    if result["status"] == "unavailable":
        return "AccurateRip: lookup failed, tracks not verified"
    tracks = result["tracks"]
    bad = [str(row["track"]) for row in tracks if row["status"] != "match"]
    text = f"AccurateRip: {len(tracks) - len(bad)} of {len(tracks)} tracks accurately ripped"
    if bad:
        text += f"; track(s) {', '.join(bad)} did not match"
    return text
