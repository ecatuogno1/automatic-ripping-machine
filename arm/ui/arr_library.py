"""Whether Radarr or Sonarr already has a file for a finished job's title.

Read-only and optional: uses the RADARR_*/SONARR_* settings of the import hand-off. Each app's
list is fetched at most once every TTL_SECONDS (RETRY_SECONDS after a failure) with a short
timeout, and matched by IMDb id only. An unconfigured or unreachable app shows nothing.
"""
import logging
import threading
import time

import requests

from arm.ripper import arr

TTL_SECONDS = 120
RETRY_SECONDS = 30
TIMEOUT = (3, 10)

# video_type -> (arm.yaml prefix, API path, does this entry have a file)
LIBRARIES = {
    "movie": ("RADARR", "/api/v3/movie", lambda movie: movie.get("hasFile")),
    "series": ("SONARR", "/api/v3/series",
               lambda series: (series.get("statistics") or {}).get("episodeFileCount")),
}
_lock = threading.Lock()
_cache = {}


def _fetch(prefix, path, has_file):
    url, credential = arr.connection(prefix)
    response = requests.get(url + path, headers={"X-Api-Key": credential}, timeout=TIMEOUT)
    response.raise_for_status()
    entries = response.json()
    if not isinstance(entries, list):
        raise ValueError("unexpected response")
    return {entry["imdbId"] for entry in entries
            if isinstance(entry, dict) and entry.get("imdbId") and has_file(entry)}


def _imdb_ids(video_type):
    """IMDb ids with a file in the app for this video type; None when the app isn't usable."""
    prefix, path, has_file = LIBRARIES[video_type]
    if arr.connection(prefix) is None:
        return None
    with _lock:
        cached = _cache.get(prefix)
        if cached and time.monotonic() - cached["at"] < (TTL_SECONDS if cached["ids"] is not None else RETRY_SECONDS):
            return cached["ids"]
        try:
            ids = _fetch(prefix, path, has_file)
        except (requests.exceptions.RequestException, ValueError) as error:
            logging.warning(f"{prefix.capitalize()} library unavailable ({type(error).__name__})")
            ids = None
        _cache[prefix] = {"at": time.monotonic(), "ids": ids}
        return ids


def in_library(job):
    """The app's name if it has a file for this finished job's title, else None."""
    if job.status != "success" or job.video_type not in LIBRARIES or not job.imdb_id:
        return None
    ids = _imdb_ids(job.video_type)
    if ids and job.imdb_id in ids:
        return LIBRARIES[job.video_type][0].capitalize()
    return None


def clear():
    with _lock:
        _cache.clear()
