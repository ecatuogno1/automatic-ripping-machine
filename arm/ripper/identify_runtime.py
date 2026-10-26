"""Confirm a DVD's identity by the runtime of its main title (IDENTIFY_BY_RUNTIME).

The usual title search takes the first OMDb/TMDB result for the disc label, so a label such as
THE_KINGDOM can become a different film of the same name. With IDENTIFY_BY_RUNTIME enabled,
ARM first looks up every film named like the label and accepts one only when the disc's longest
title (as reported by lsdvd) runs as long as the film and no other candidate fits as well. The
ARM online database (crc64) answer is treated as a hint under the same runtime check. When
nothing is confirmed, identification continues with the usual title search.
"""
import logging
import math
import re
import unicodedata

import requests

import arm.config.config as cfg
from arm.ripper import utils

TMDB_URL = "https://api.themoviedb.org/3"
OMDB_URL = "https://www.omdbapi.com/"
POSTER_BASE = "https://image.tmdb.org/t/p/original"
TIMEOUT = 15
# Films named like the label whose runtime is looked up. More than this is too common a name.
MAX_DETAILS = 10
# A film runtime fits the disc within 5 minutes, or 5% for long films.
TOLERANCE_SECONDS = 300
TOLERANCE_SHARE = 0.05
# Of several fitting films, one within 2 minutes wins when every other is 3 minutes further off.
CLOSEST_SECONDS = 120
RIVAL_MARGIN_SECONDS = 180
# A film named like a TV series only wins on a feature-length disc that runs within
# CLOSEST_SECONDS of a film with at least this many votes on the metadata provider.
FEATURE_SECONDS = 75 * 60
NAMESAKE_VOTES = 500
ARTICLES = ("the", "a", "an")
PLACEHOLDERS = {"", "notidentified", "dvd", "dvdvideo", "bluray", "video", "untitled"}
DISC_SUFFIX = re.compile(r"\s+(?:DVD|BLU\s?RAY|DIS[CK]\s*\d+|D\d)$", re.IGNORECASE)
SEASON = re.compile(r"\b(?:SEASON\s*\d+|S\d{1,2})\b", re.IGNORECASE)
IMDB_ID = re.compile(r"tt\d{5,10}")
# First-pass outcomes a looser reading of the label may still settle (identify_loose)
NO_NAMED = "no film is named like the label"
NONE_FITS = "no film named like the label fits the runtime"
SEVERAL_FIT = "several films named like the label fit the runtime"
NO_RUNTIME = "a film named like the label has no known runtime"
SECOND_PASS_REASONS = (NO_NAMED, NONE_FITS, SEVERAL_FIT, NO_RUNTIME)


def normalize(value):
    """Case-, accent- and punctuation-free form of a title"""
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return "".join(c for c in value if c.isalnum())


def without_article(value):
    """Normalized title without a leading English article: FAMILY_MAN ~ The Family Man"""
    words = re.sub(r"[_\s]+", " ", str(value or "")).strip().split(" ")
    if len(words) > 1 and words[0].casefold() in ARTICLES:
        words = words[1:]
    return normalize(" ".join(words))


def search_title(label):
    """(title, year) to search for: underscores as spaces, disc numbers dropped, a bracketed year split off"""
    title = re.sub(r"[_\s]+", " ", str(label or "")).strip()
    while DISC_SUFFIX.search(title):
        title = DISC_SUFFIX.sub("", title).strip()
    year = None
    # An unbracketed number may be part of the title (DRACULA 2000), so only "(1999)" counts as a year
    match = re.fullmatch(r"(.+?)\s+[\[(]((?:19|20)\d{2})[\])]", title)
    if match:
        title, year = match[1].strip(), int(match[2])
    if normalize(title) in PLACEHOLDERS:
        title = ""
    return title, year


def positive(value):
    """``value`` as a positive finite number, else None"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def longest_track_seconds(tracks):
    """Length in seconds of the longest title lsdvd reported, else None"""
    lengths = [positive(track.get("length")) for track in tracks or [] if isinstance(track, dict)]
    return max((length for length in lengths if length), default=None)


def year_of(value):
    """First four digits of a date or year string as an int, else None"""
    text = str(value or "")[:4]
    return int(text) if text.isdigit() and int(text) > 0 else None


def film(names, year, imdb_id, runtime, votes, poster):
    """The film record both providers return"""
    names = [n for n in names if n]
    return {"title": names[0] if names else None, "names": names, "year": year,
            "imdb_id": imdb_id if IMDB_ID.fullmatch(str(imdb_id or "")) else None,
            "runtime": positive(runtime), "votes": votes if isinstance(votes, int) else None,
            "poster": poster if str(poster or "").startswith("https://") else None}


class TMDb:
    """api.themoviedb.org v3 with TMDB_API_KEY"""

    def __init__(self, api_key):
        self.api_key = api_key

    def get(self, path, **params):
        params["api_key"] = self.api_key
        response = requests.get(TMDB_URL + path, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()

    def search(self, query, year=None):
        params = {"query": query, "include_adult": "false"}
        if year:
            params["year"] = year
        results = self.get("/search/movie", **params).get("results") or []
        return [{"names": [r.get("title"), r.get("original_title")], "ref": r["id"]}
                for r in results if isinstance(r, dict) and isinstance(r.get("id"), int)]

    def details(self, ref):
        data = self.get(f"/movie/{int(ref)}", append_to_response="external_ids")
        poster = POSTER_BASE + data["poster_path"] if data.get("poster_path") else None
        return film([data.get("title"), data.get("original_title")], year_of(data.get("release_date")),
                    data.get("imdb_id") or (data.get("external_ids") or {}).get("imdb_id"),
                    data.get("runtime"), data.get("vote_count"), poster)

    def by_imdb(self, imdb_id):
        found = self.get(f"/find/{imdb_id}", external_source="imdb_id").get("movie_results") or []
        return self.details(found[0]["id"]) if found else None

    def series_names(self, query):
        results = self.get("/search/tv", query=query).get("results") or []
        return [[r.get("name"), r.get("original_name")] for r in results if isinstance(r, dict)]


class OMDb:
    """www.omdbapi.com with OMDB_API_KEY"""

    def __init__(self, api_key):
        self.api_key = api_key

    def get(self, **params):
        params.update(apikey=self.api_key, r="json")
        response = requests.get(OMDB_URL, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        # OMDb answers "not found" with Response "False" rather than an HTTP error
        return {} if str(data.get("Response")) == "False" else data

    def search(self, query, year=None):
        params = {"s": query, "type": "movie"}
        if year:
            params["y"] = year
        results = self.get(**params).get("Search") or []
        return [{"names": [r.get("Title")], "ref": r["imdbID"]}
                for r in results if isinstance(r, dict) and IMDB_ID.fullmatch(str(r.get("imdbID") or ""))]

    def details(self, ref):
        data = self.get(i=ref)
        votes = str(data.get("imdbVotes") or "").replace(",", "")
        return film([data.get("Title")], year_of(data.get("Year")), data.get("imdbID"),
                    re.sub(r"\D", "", str(data.get("Runtime") or "")), int(votes) if votes.isdigit() else None,
                    data.get("Poster"))

    def by_imdb(self, imdb_id):
        found = self.details(imdb_id)
        return found if found["imdb_id"] else None

    def series_names(self, query):
        results = self.get(s=query, type="series").get("Search") or []
        return [[r.get("Title")] for r in results if isinstance(r, dict)]


def provider():
    """The configured METADATA_PROVIDER as a catalog, or None without an API key"""
    name = str(cfg.arm_config.get("METADATA_PROVIDER") or "").lower()
    if name == "tmdb" and cfg.arm_config.get("TMDB_API_KEY"):
        return TMDb(cfg.arm_config["TMDB_API_KEY"])
    if name == "omdb" and cfg.arm_config.get("OMDB_API_KEY"):
        return OMDb(cfg.arm_config["OMDB_API_KEY"])
    return None


def named_films(catalog, title, year):
    """Films whose title (or original title) is the label, with or without a leading article"""
    wanted = {normalize(title), without_article(title)}
    refs = {}
    for hit in catalog.search(title, year):
        keys = {key(n) for n in hit["names"] if n for key in (normalize, without_article)}
        if keys & wanted:
            refs.setdefault(hit["ref"], hit)
    if len(refs) > MAX_DETAILS:
        raise LookupError(f"{len(refs)} films are named like the label")
    films = [catalog.details(ref) for ref in refs]
    return [f for f in films if not year or f["year"] == year]


def gap(movie, seconds):
    """Seconds between the film's runtime and the disc's longest title"""
    return abs(movie["runtime"] * 60 - seconds)


def fits(movie, seconds):
    return movie["runtime"] is not None and gap(movie, seconds) <= max(TOLERANCE_SECONDS, seconds * TOLERANCE_SHARE)


def identified(movie):
    return bool(movie["imdb_id"]) and isinstance(movie["year"], int)


def placeholder(movie):
    """A catalog stub without runtime, year or IMDb id cannot be the disc's film"""
    return movie["runtime"] is None and movie["year"] is None and movie["imdb_id"] is None


def closest(movies, seconds):
    """The film within CLOSEST_SECONDS of the disc when every other is RIVAL_MARGIN_SECONDS further off"""
    ranked = sorted(movies, key=lambda m: gap(m, seconds))
    if len(ranked) < 2:
        return None
    best, runner_up = gap(ranked[0], seconds), gap(ranked[1], seconds)
    return ranked[0] if best <= CLOSEST_SECONDS and runner_up - best >= RIVAL_MARGIN_SECONDS else None


def by_label(title, films, seconds):
    """(film, method) when the runtime singles out one film named like the label, else (None, reason)"""
    if not films:
        return None, NO_NAMED
    if any(m["runtime"] is None and not placeholder(m) for m in films):
        return None, NO_RUNTIME
    plausible = [m for m in films if fits(m, seconds)]
    if len(plausible) == 1:
        chosen = plausible[0]
        exact = normalize(title) in {normalize(n) for n in chosen["names"]}
        method = "label-and-runtime" if exact else "label-without-article-and-runtime"
    else:
        chosen, method = closest(plausible, seconds), "label-and-closest-runtime"
    if chosen is None:
        return None, (SEVERAL_FIT if plausible
                      else NONE_FITS)
    if not identified(chosen):
        return None, "the matching film has no release year or IMDb id"
    return chosen, method


def label_consistent(title, movie):
    """The label names the hinted film (JET_LI_FEARLESS ~ Fearless), or the reverse"""
    label = without_article(title)
    for name in movie["names"]:
        other = without_article(name)
        if min(len(label), len(other)) >= 4 and (other in label or label in other):
            return True
    return False


def hint_film(catalog, crc_answer, films):
    """The film the ARM online database named for this disc's crc64, looked up on the provider"""
    if not crc_answer or str(crc_answer.get("video_type") or "movie").lower() != "movie":
        return None
    imdb_id = str(crc_answer.get("imdb_id") or "")
    if not IMDB_ID.fullmatch(imdb_id):
        return None
    known = next((m for m in films if m["imdb_id"] == imdb_id), None)
    try:
        return known or catalog.by_imdb(imdb_id)
    except Exception as error:  # the hint is extra evidence; the label result still stands
        logging.info(f"ARM online database film lookup failed ({type(error).__name__})")
        return None


def weigh_hint(title, chosen, method, hint, films, seconds):
    """Let the crc64 answer confirm, contradict or (for an unhelpful label) supply the identity"""
    if hint is None or not fits(hint, seconds):
        # The community database is user-submitted; an answer whose runtime differs is ignored
        return chosen, method
    if chosen is not None:
        if chosen["imdb_id"] == hint["imdb_id"]:
            return chosen, method + "-crc64-agrees"
        return None, "the ARM online database and the label name different films"
    if title and not label_consistent(title, hint):
        return None, method
    if any(m["imdb_id"] != hint["imdb_id"] and fits(m, seconds) for m in films):
        return None, "the ARM online database answer and another film both fit the runtime"
    if not identified(hint):
        return None, "the ARM online database film has no release year or IMDb id"
    return hint, "crc64-and-runtime"


def over_namesake(catalog, title, chosen, method, seconds):
    """A TV series named like the label only gives way to a well-known, closely matching film"""
    if chosen is None or not title or method.startswith("crc64"):
        return chosen, method
    wanted = normalize(title)
    if not any(wanted in {normalize(n) for n in names if n} for names in catalog.series_names(title)):
        return chosen, method
    if seconds >= FEATURE_SECONDS and gap(chosen, seconds) <= CLOSEST_SECONDS \
            and (chosen["votes"] or 0) >= NAMESAKE_VOTES:
        return chosen, method + "-over-namesake-series"
    return None, "a TV series shares the label's name"


def confirm(catalog, label, seconds, crc_answer=None):
    """(film, method) confirmed by the disc runtime, or (None, reason)"""
    title, year = search_title(label)
    if title and SEASON.search(title):
        return None, "the label names a TV season"
    films = named_films(catalog, title, year) if title else []
    chosen, method = by_label(title, films, seconds)
    hint = hint_film(catalog, crc_answer, films)
    chosen, method = weigh_hint(title, chosen, method, hint, films, seconds)
    chosen, method = over_namesake(catalog, title, chosen, method, seconds)
    if chosen is None and method in SECOND_PASS_REASONS:
        from arm.ripper import identify_loose  # imports this module
        loose, how = identify_loose.second_pass(catalog, label, seconds, hint, films)
        return (loose, how) if loose else (None, f"{method}; second pass: {how}")
    return chosen, method


def identify(job, label, tracks, crc_answer=None):
    """
    Set the job's identity when the disc runtime confirms one film

    :param job: the job to identify
    :param label: the disc label as cleaned for the title search
    :param tracks: the titles lsdvd reported, or None
    :param crc_answer: the ARM online database result for the disc's crc64, if any
    :return: True if the identity was confirmed and set, False to use the usual title search
    """
    seconds = longest_track_seconds(tracks)
    catalog = provider()
    if not seconds or catalog is None or str(cfg.arm_config.get("VIDEOTYPE")).lower() == "series":
        logging.info("Runtime identification skipped: needs a DVD title length, a metadata provider "
                     "API key and VIDEOTYPE other than series")
        return False
    try:
        chosen, method = confirm(catalog, label, seconds, crc_answer)
    except Exception as error:  # an optional check must never stop identification
        logging.info(f"Runtime identification unavailable ({type(error).__name__}); using the title search")
        return False
    if chosen is None:
        logging.info(f"Runtime identification not confirmed: {method}; using the title search")
        return False
    title = utils.clean_for_filename(chosen["title"])
    args = {"title": title, "title_auto": title,
            "year": str(chosen["year"]), "year_auto": str(chosen["year"]),
            "imdb_id": chosen["imdb_id"], "imdb_id_auto": chosen["imdb_id"],
            "video_type": "movie", "video_type_auto": "movie", "hasnicetitle": True}
    if chosen["poster"]:
        args.update(poster_url=chosen["poster"], poster_url_auto=chosen["poster"])
    utils.database_updater(args, job)
    # Not stored: tells the rest of this run that the identity was confirmed, not guessed
    job.identity_verified = True
    logging.info(f"Identified by runtime: {chosen['title']} ({chosen['year']}) {chosen['imdb_id']}, "
                 f"{chosen['runtime']:.0f} min film for a {seconds / 60:.0f} min title; {method}")
    return True
