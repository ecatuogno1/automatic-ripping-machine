"""Optional hand-off of a finished rip to Radarr, Sonarr or Lidarr.

When the matching app is configured (URL and API key in arm.yaml), ARM asks it to import the
folder the rip ended up in, the same way a download client hands over a finished download.
The request is bounded by a timeout and an unreachable app only logs a warning: the rip has
already succeeded and the files stay where they are.
"""
import logging
import os
import re

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
