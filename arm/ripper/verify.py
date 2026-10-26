"""Check ripped video files with ffprobe before ARM moves them and reports success (VERIFY_RIP_OUTPUT).

These are container checks: each video file opens, has video packets, runs about as long as the
disc scan said, and its last seconds can be read and decoded. Nothing here decodes a whole file.
"""
import json
import logging
import math
import os
import shutil
import subprocess

import arm.config.config as cfg
from arm.ripper.utils import RipperException

VIDEO_EXTENSIONS = (".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts", ".webm")
# Only this window at the end of a file is demuxed and decoded
TAIL_SECONDS = 30
PROBE_TIMEOUT = 1200
TAIL_TIMEOUT = 300
# A gallery or menu still can be a few pictures in a file far shorter than its scanned title
STILL_MAX_PICTURES = 3
STILL_MIN_SCANNED = 10.0


class VerifyError(Exception):
    """A ripped file failed one of the checks; the message says which."""


def verify_rip_output(job, path):
    """
    Check every video file in path before it is moved to the completed folder.\n
    Does nothing unless VERIFY_RIP_OUTPUT is enabled, and only warns if ffprobe is not installed.
    :param job: current job
    :param path: folder holding the files that are about to be moved (raw or transcode output)
    :raises RipperException: if any file fails, so the job fails and its files are not deleted
    """
    if not cfg.arm_config.get("VERIFY_RIP_OUTPUT", False):
        return
    if shutil.which("ffprobe") is None:
        logging.warning("VERIFY_RIP_OUTPUT is enabled but ffprobe was not found; skipping rip verification")
        return
    path = str(path)
    files = video_files(path)
    if not files:
        if os.path.isdir(path) and any(entry.is_dir() for entry in os.scandir(path)):
            # A disc backup (BDMV/VIDEO_TS folders) has no video files of its own to check
            logging.info(f"No video files directly in {path} (disc backup); skipping rip verification")
            return
        raise RipperException(f"Rip verification failed: no video files were produced in '{path}'")
    scanned = scanned_lengths(job)
    main_file = max(files, key=lambda name: os.path.getsize(os.path.join(path, name)))
    failures = []
    for name in files:
        try:
            check_file(os.path.join(path, name), scanned.get(name), name == main_file)
        except VerifyError as error:
            logging.error(f"Rip verification failed for {name}: {error}")
            failures.append(f"{name}: {error}")
    if failures:
        raise RipperException(f"Rip verification failed for {len(failures)} of {len(files)} file(s), "
                              f"files were kept in '{path}'. " + "; ".join(failures))
    logging.info(f"Rip verification passed for {len(files)} file(s) in {path}")


def video_files(path):
    """Video files directly inside path, sorted by name"""
    if not os.path.isdir(path):
        return []
    return sorted(entry.name for entry in os.scandir(path)
                  if entry.is_file() and entry.name.lower().endswith(VIDEO_EXTENSIONS))


def scanned_lengths(job):
    """Scan length in seconds for each track file name; names claimed by two different lengths are dropped"""
    lengths = {}
    ambiguous = set()
    for track in job.tracks.all():
        try:
            length = float(track.length or 0)
        except (TypeError, ValueError):
            continue
        if length <= 0:
            continue
        for name in {track.filename, track.orig_filename}:
            if not name:
                continue
            name = os.path.basename(name)
            if lengths.get(name, length) != length:
                ambiguous.add(name)
            lengths[name] = length
    return {name: length for name, length in lengths.items() if name not in ambiguous}


def check_file(file_path, scanned, main):
    """
    Raise VerifyError if file_path is unreadable, has no video, does not match its scan length or is truncated.\n
    :param file_path: video file
    :param scanned: length in seconds the disc scan reported for it, or None if unknown
    :param main: True for the largest file, which is never treated as a still-image extra
    """
    data = ffprobe_json(["ffprobe", "-v", "error", "-count_packets", "-show_entries",
                         "format=duration,start_time:stream=codec_type,nb_read_packets,duration"
                         ":stream_tags=DURATION", "-of", "json", file_path], PROBE_TIMEOUT)
    try:
        duration = float(data["format"]["duration"])
        start = float(data["format"].get("start_time") or 0)
    except (KeyError, TypeError, ValueError) as error:
        raise VerifyError("ffprobe reported no duration") from error
    pictures = video_packets(data)
    if pictures <= 0 or not math.isfinite(duration) or duration <= 0:
        raise VerifyError("no readable video")
    if not main and still_image(pictures, duration, scanned):
        logging.info(f"{os.path.basename(file_path)} is a still-image extra ({pictures} picture(s) in "
                     f"{duration:.1f}s); not checking its runtime")
        return
    if scanned and not runtime_matches_scan(scanned, duration, main):
        raise VerifyError(f"runtime is {duration:.1f}s but the disc scan reported {scanned:.0f}s")
    check_tail(file_path, video_duration(data, duration), start)


def ffprobe_json(command, timeout):
    """Run ffprobe and return its JSON output"""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise VerifyError(f"ffprobe did not finish within {timeout}s") from error
    except subprocess.CalledProcessError as error:
        raise VerifyError(f"ffprobe could not read the file ({(error.stderr or '').strip()[:200]})") from error
    except OSError as error:
        raise VerifyError(f"ffprobe could not be run ({error})") from error
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise VerifyError("ffprobe returned unreadable output") from error


def video_packets(data):
    """Number of video packets ffprobe counted"""
    total = 0
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "video":
            try:
                total += int(stream.get("nb_read_packets") or 0)
            except (TypeError, ValueError):
                continue
    return total


def still_image(pictures, duration, scanned):
    """
    A slideshow or menu still rather than motion video: under one picture a second on average,
    or a few pictures in a file under a second long whose title the scan timed at ten seconds or more
    (DVD scans time a still's audio or chapter loop, not its pictures).
    """
    if pictures < max(2.0, duration):
        return True
    return (pictures <= STILL_MAX_PICTURES and duration < 1.0
            and scanned is not None and scanned >= STILL_MIN_SCANNED)


def runtime_matches_scan(scanned, actual, main):
    """
    The scan length is a navigation estimate, not the final mux duration, so allow a small difference.
    A shortfall can mean a truncated read: max(2s, 1%) for the main title, max(8s, 2%) for extras,
    which can mux a few seconds short. A longer file can't be truncated: max(5s, 2%).
    """
    if actual < scanned:
        limit = max(2.0, scanned * 0.01) if main else max(8.0, scanned * 0.02)
        return scanned - actual <= limit
    return actual - scanned <= max(5.0, scanned * 0.02)


def parse_clock(value):
    """Matroska DURATION tags are HH:MM:SS.fffffffff; plain seconds are also accepted"""
    text = str(value).strip()
    if ":" not in text:
        return float(text)
    hours, minutes, seconds = text.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def video_duration(data, container):
    """
    Where the first video track should end: its own duration or Matroska DURATION tag (which the muxer
    writes and a later truncation keeps), else the container duration, which spans the longest track.
    """
    for stream in data.get("streams") or []:
        if stream.get("codec_type") != "video":
            continue
        for value in (stream.get("duration"), (stream.get("tags") or {}).get("DURATION")):
            try:
                seconds = parse_clock(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(seconds) and 0 < seconds <= container + 1.0:
                return seconds
        break
    return container


def check_tail(file_path, duration, start):
    """
    A file cut short after its header was written still reports the full duration, so read and
    decode only the last TAIL_SECONDS: the last video packet must end near the expected end and
    the packets there must decode.
    """
    window = max(start, start + duration - TAIL_SECONDS)
    data = ffprobe_json(["ffprobe", "-v", "fatal", "-select_streams", "v:0", "-count_frames",
                         "-read_intervals", f"{window:.3f}%+{2 * TAIL_SECONDS}",
                         "-show_entries", "packet=pts_time,dts_time,duration_time:stream=nb_read_frames",
                         "-of", "json", file_path], TAIL_TIMEOUT)
    ends = []
    for packet in data.get("packets") or []:
        stamp = packet.get("pts_time")
        if stamp in (None, "N/A"):
            stamp = packet.get("dts_time")
        if stamp in (None, "N/A"):
            continue
        length = packet.get("duration_time")
        try:
            ends.append(float(stamp) + (float(length) if length not in (None, "N/A") else 0.0))
        except (TypeError, ValueError):
            continue
    try:
        frames = int((data.get("streams") or [{}])[0].get("nb_read_frames") or 0)
    except (TypeError, ValueError):
        frames = 0
    # At least half the tail must decode; field-coded interlaced video stores two packets per frame
    if not ends or frames < max(1, len(ends) // 4):
        raise VerifyError("the end of the video could not be decoded; it is truncated or damaged")
    end = max(ends) - start
    if end < duration - max(5.0, duration * 0.005):
        raise VerifyError(f"truncated: video ends at {end:.1f}s of {duration:.1f}s")
