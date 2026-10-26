"""Optional hand-off of a finished rip to Radarr, Sonarr or Lidarr.

When the matching app is configured (URL and API key in arm.yaml), ARM asks it to import the
folder the rip ended up in, the same way a download client hands over a finished download.
The request is bounded by a timeout and an unreachable app only logs a warning: the rip has
already succeeded and the files stay where they are.
"""
import logging
import os
import re
import unicodedata

import requests

import arm.config.config as cfg

TIMEOUT = 30

# job type -> (app name, arm.yaml prefix, API version, import command)
APPS = {
    "movie": ("Radarr", "RADARR", "v3", "DownloadedMoviesScan"),
    "series": ("Sonarr", "SONARR", "v3", "DownloadedEpisodesScan"),
    "music": ("Lidarr", "LIDARR", "v1", "DownloadedAlbumsScan"),
}


def app_for(job):
    """The APPS entry for this job, or None when no *arr app handles its type."""
    if job.disctype == "music":
        return APPS["music"]
    if job.disctype in ("dvd", "bluray"):
        return APPS.get(job.video_type)
    return None


def connection(prefix):
    """(base url, api key) for an app, or None when either setting is empty."""
    url = str(cfg.arm_config.get(f"{prefix}_URL") or "").strip().rstrip("/")
    credential = str(cfg.arm_config.get(f"{prefix}_API_KEY") or "").strip()
    if not url or not credential:
        return None
    return url, credential


def arr_path(path):
    """Translate a path as ARM sees it into the path the *arr app sees (ARR_PATH_MAP)."""
    for pair in str(cfg.arm_config.get("ARR_PATH_MAP") or "").split(";"):
        local, separator, remote = pair.partition("=")
        local, remote = local.strip().rstrip("/"), remote.strip().rstrip("/\\")
        if separator and local and remote and (path == local or path.startswith(local + "/")):
            return remote + path[len(local):]
    return path


def music_folder(job):
    """
    The album folder abcde wrote this job's tracks to, or None if it can't be told apart.

    abcde names the folder itself (OUTPUTFORMAT), so look under its OUTPUTDIR for the files
    written since the job started; they must all share one folder below OUTPUTDIR.
    """
    match = re.search(r"^\s*OUTPUTDIR=[\"']?([^\"'\n]*)", cfg.abcde_config or "", re.MULTILINE)
    output_dir = match.group(1).strip().rstrip("/") if match else ""
    if not os.path.isabs(output_dir) or "$" in output_dir or not job.start_time:
        logging.info("abcde OUTPUTDIR is not a plain absolute path, can't tell which folder to import")
        return None
    started = job.start_time.timestamp()
    folders = set()
    for root, _dirs, files in os.walk(output_dir):
        if any(os.path.getmtime(os.path.join(root, name)) >= started for name in files):
            folders.add(root)
    if not folders:
        return None
    folder = os.path.commonpath(list(folders))
    if folder == output_dir:
        logging.info(f"abcde wrote to more than one folder in {output_dir} during this job, can't tell which to import")
        return None
    return folder


def import_job(job):
    """
    Ask the *arr app for this job's media type to import the finished rip.\n
    Does nothing unless that app's URL and API key are set. Never raises.
    :param job: current job, after its files were moved to their final folder
    :return: True if the app accepted the import command
    """
    try:
        return _import(job)
    except Exception as error:  # an optional hand-off must never fail a finished rip
        logging.warning(f"*arr import skipped after an unexpected error: {error}")
        return False


def _import(job):
    app = app_for(job)
    if app is None:
        return False
    name, prefix, version, command = app
    settings = connection(prefix)
    if settings is None:
        logging.debug(f"{prefix}_URL or {prefix}_API_KEY is empty. Skipping {name} import.")
        return False
    url, credential = settings
    folder = music_folder(job) if job.disctype == "music" else job.path
    if not folder or not os.path.isdir(folder) or not any(files for _root, _dirs, files in os.walk(folder)):
        logging.warning(f"No finished files found to hand to {name} ({folder}). Skipping {name} import.")
        return False
    body = {"name": command, "path": arr_path(folder),
            "importMode": str(cfg.arm_config.get("ARR_IMPORT_MODE") or "Move")}
    logging.info(f"Asking {name} to import {body['path']}")
    try:
        response = requests.post(f"{url}/api/{version}/command", json=body, timeout=TIMEOUT,
                                 headers={"X-Api-Key": credential})
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        status = getattr(error.response, "status_code", None)
        reason = f"HTTP {status}" if status else type(error).__name__
        logging.warning(f"{name} import request failed ({reason}). "
                        f"The rip is complete, import '{folder}' in {name} manually.")
        return False
    logging.info(f"{name} accepted the import of {body['path']}")
    return True


# Catalog lookups used by identify (ARR_IDENTIFY): (arm.yaml prefix, lookup path, ARM video type)
LOOKUPS = (("RADARR", "/api/v3/movie/lookup", "movie"), ("SONARR", "/api/v3/series/lookup", "series"))


def _title_keys(title):
    """Comparable forms of a title: lower-case letters and digits only, with and without a leading article."""
    text = unicodedata.normalize("NFKD", str(title or "")).encode("ascii", "ignore").decode().casefold()
    text = re.sub(r"[^a-z0-9 ]", "", text.replace("&", "and"))
    words = text.split()
    keys = {"".join(words)}
    if len(words) > 1 and words[0] in ("the", "a", "an"):
        keys.add("".join(words[1:]))
    return keys - {""}


def _search(prefix, path, term):
    """An app's lookup results for a search term; [] when the app isn't configured or doesn't answer."""
    settings = connection(prefix)
    if settings is None:
        return []
    url, credential = settings
    try:
        response = requests.get(url + path, params={"term": term}, headers={"X-Api-Key": credential},
                                timeout=TIMEOUT)
        response.raise_for_status()
        results = response.json()
    except (requests.exceptions.RequestException, ValueError) as error:
        logging.warning(f"{prefix.capitalize()} lookup failed ({type(error).__name__})")
        return []
    return [r for r in results if isinstance(r, dict) and isinstance(r.get("year"), int)] \
        if isinstance(results, list) else []


def _is_titled(result, wanted):
    """Whether a lookup result's title, original title or an alternate title is one of the wanted keys."""
    names = [result.get("title"), result.get("originalTitle")]
    names += [alt.get("title") for alt in result.get("alternateTitles") or [] if isinstance(alt, dict)]
    return any(_title_keys(name) & wanted for name in names)


def _candidates(term):
    """Lookup results from every configured app whose title or alternate title is the searched title."""
    wanted = _title_keys(term)
    return [(video_type, result) for prefix, path, video_type in LOOKUPS
            for result in _search(prefix, path, term) if _is_titled(result, wanted)]


def lookup(title, year=None):
    """
    Identify a title with the Radarr/Sonarr lookup when OMDb/TMDB found nothing (ARR_IDENTIFY).\n
    Only a result whose title is the searched title counts. Several such results are narrowed
    down by the year (or the year before, as a disc often comes out a year after the film);
    if that doesn't leave exactly one, nothing is chosen.
    :param title: title to search, words may be separated by "+", "_" or "-"
    :param year: release year if known
    :return: OMDb-style {"Search": [result]} like the other providers, or None
    """
    if not cfg.arm_config.get("ARR_IDENTIFY"):
        return None
    term = re.sub(r"[+_-]+", " ", str(title or "")).strip()
    if not _title_keys(term):
        return None
    found = _candidates(term)
    year = int(year) if str(year or "").isdigit() else None
    if len(found) > 1 and year:
        found = ([c for c in found if c[1]["year"] == year]
                 or [c for c in found if c[1]["year"] == year - 1])
    if len(found) != 1:
        if found:
            logging.info(f"Radarr/Sonarr lookup for '{term}' found {len(found)} titles with that name, choosing none")
        return None
    video_type, result = found[0]
    poster = next((image.get("remoteUrl") for image in result.get("images") or []
                   if isinstance(image, dict) and image.get("coverType") == "poster"), None)
    logging.info(f"Radarr/Sonarr lookup identified '{term}' as {result.get('title')} ({result['year']})")
    return {"Search": [{"Title": str(result.get("title")), "Year": str(result["year"]), "Type": video_type,
                        "imdbID": result.get("imdbId") or "", "Poster": poster or ""}]}
