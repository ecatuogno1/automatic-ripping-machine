"""IDENTIFY_BY_RUNTIME: a DVD's identity is confirmed by the runtime of its longest title."""

import json
from types import SimpleNamespace

import pytest

import arm.config.config as cfg
from arm.ripper import identify, identify_runtime

KINGDOM = {"id": 4349, "title": "The Kingdom", "release_date": "2007-09-28", "runtime": 110,
           "imdb_id": "tt0431197", "vote_count": 2100, "poster_path": "/kingdom.jpg"}
KINGDOM_SHORT = {"id": 900001, "title": "The Kingdom", "release_date": "2019-03-01", "runtime": 14,
                 "imdb_id": "tt9000001", "vote_count": 3}
VAMPIRE = {"id": 900002, "title": "Kingdom of the Vampire", "release_date": "2007-01-01", "runtime": 75,
           "imdb_id": "tt0839875", "vote_count": 10}
HERCULES = {"id": 11970, "title": "Hercules", "release_date": "1997-06-13", "runtime": 93,
            "imdb_id": "tt0119282", "vote_count": 8000}


def movie(title, year, runtime, imdb_id, votes=1000):
    return identify_runtime.film([title], year, imdb_id, runtime, votes, None)


class FakeCatalog:
    """A metadata provider answering from fixed films and TV series names."""

    def __init__(self, films, series=()):
        self.films = {f["imdb_id"]: f for f in films}
        self.series = [[name] for name in series]

    def search(self, query, year=None):
        return [{"names": f["names"], "ref": key} for key, f in self.films.items()]

    def details(self, ref):
        return self.films[ref]

    def by_imdb(self, imdb_id):
        return self.films.get(imdb_id)

    def series_names(self, query):
        return self.series


@pytest.mark.parametrize("label, expected", [
    ("THE_KINGDOM", ("THE KINGDOM", None)),
    ("THE_MATRIX_DISC_1", ("THE MATRIX", None)),
    ("ALIEN_(1979)", ("ALIEN", 1979)),
    ("DRACULA_2000", ("DRACULA 2000", None)),
    ("DVD_VIDEO", ("", None)),
    ("not identified", ("", None)),
])
def test_search_title(label, expected):
    assert identify_runtime.search_title(label) == expected


def test_longest_track_seconds():
    tracks = [{"ix": 1, "length": 95.5}, {"ix": 2, "length": 6602.4}, {"ix": 3, "length": 0}]
    assert identify_runtime.longest_track_seconds(tracks) == pytest.approx(6602.4)
    assert identify_runtime.longest_track_seconds(None) is None


def test_runtime_picks_the_film_among_namesakes():
    catalog = FakeCatalog([movie("The Kingdom", 2007, 110, "tt0431197"),
                           movie("The Kingdom", 2019, 14, "tt9000001"),
                           movie("Kingdom of the Vampire", 2007, 75, "tt0839875")])
    chosen, method = identify_runtime.confirm(catalog, "THE_KINGDOM", 6602.4)
    assert chosen["imdb_id"] == "tt0431197"
    assert method == "label-and-runtime"


def test_clearly_closest_runtime_wins():
    # Killer Elite (2011, 116 min) and The Killer Elite (1975, 122 min) both fit a 116.6 min disc
    catalog = FakeCatalog([movie("Killer Elite", 2011, 116, "tt1448755"),
                           movie("The Killer Elite", 1975, 122, "tt0073243")])
    chosen, method = identify_runtime.confirm(catalog, "KILLER_ELITE", 116.6 * 60)
    assert chosen["imdb_id"] == "tt1448755"
    assert method == "label-and-closest-runtime"


@pytest.mark.parametrize("films, reason", [
    ([movie("The Kingdom", 2007, 110, "tt0431197")], "no film named like the label fits the runtime"),
    ([movie("The Kingdom", 2007, 92, "tt0431197"), movie("The Kingdom", 2011, 93, "tt9000002")],
     "several films named like the label fit the runtime"),
    ([movie("The Kingdom", 2007, None, "tt0431197"), movie("The Kingdom", 2011, 93, "tt9000002")],
     "a film named like the label has no known runtime"),
    ([movie("Something Else", 2007, 93, "tt9000003")], "no film is named like the label"),
])
def test_nothing_is_confirmed_without_a_single_runtime_match(films, reason):
    chosen, why = identify_runtime.confirm(FakeCatalog(films), "THE_KINGDOM", 93 * 60)
    assert chosen is None
    # the second pass (identify_loose) finds nothing better in these catalogs
    assert why.startswith(reason + "; second pass: ")


def test_crc64_answer_names_an_unlabelled_disc_when_its_runtime_fits():
    catalog = FakeCatalog([movie("Hercules", 1997, 93, "tt0119282")])
    answer = {"title": "Hercules", "year": "1997", "imdb_id": "tt0119282", "video_type": "movie"}
    chosen, method = identify_runtime.confirm(catalog, "not identified", 5603.0, answer)
    assert chosen["imdb_id"] == "tt0119282"
    assert method == "crc64-and-runtime"
    chosen, _ = identify_runtime.confirm(catalog, "not identified", 7200.0, answer)
    assert chosen is None


def test_crc64_answer_contradicting_the_label_confirms_nothing():
    catalog = FakeCatalog([movie("The Kingdom", 2007, 110, "tt0431197"),
                           movie("Kingdom of Heaven", 2005, 109, "tt0320661")])
    answer = {"imdb_id": "tt0320661", "video_type": "movie"}
    chosen, why = identify_runtime.confirm(catalog, "THE_KINGDOM", 6602.4, answer)
    assert chosen is None
    assert why == "the ARM online database and the label name different films"


def test_crc64_answer_with_another_runtime_is_ignored():
    catalog = FakeCatalog([movie("The Kingdom", 2007, 110, "tt0431197"),
                           movie("Kingdom of the Vampire", 2007, 75, "tt0839875")])
    answer = {"imdb_id": "tt0839875", "video_type": "movie"}
    chosen, _ = identify_runtime.confirm(catalog, "THE_KINGDOM", 6602.4, answer)
    assert chosen["imdb_id"] == "tt0431197"


def test_well_known_film_wins_over_a_namesake_series():
    catalog = FakeCatalog([movie("Limitless", 2011, 105, "tt1219289", votes=11000)], series=["Limitless"])
    chosen, method = identify_runtime.confirm(catalog, "LIMITLESS", 105.5 * 60)
    assert chosen["imdb_id"] == "tt1219289"
    assert method == "label-and-runtime-over-namesake-series"


def test_obscure_film_does_not_win_over_a_namesake_series():
    catalog = FakeCatalog([movie("Heroes", 2008, 88, "tt1270296", votes=40)], series=["Heroes"])
    chosen, why = identify_runtime.confirm(catalog, "HEROES", 88 * 60)
    assert chosen is None
    assert why == "a TV series shares the label's name"


def test_season_label_is_left_to_the_title_search():
    catalog = FakeCatalog([movie("Friends", 1994, 22, "tt0108778")])
    chosen, why = identify_runtime.confirm(catalog, "FRIENDS_S1_D1", 22 * 60)
    assert chosen is None
    assert why == "the label names a TV season"


def test_omdb_details_are_parsed(monkeypatch):
    answer = {"Response": "True", "Title": "Killer Elite", "Year": "2011", "imdbID": "tt1448755",
              "Runtime": "116 min", "imdbVotes": "160,123", "Poster": "https://example.com/p.jpg"}
    seen = {}

    def get(url, params=None, timeout=None):
        seen.update(params=params, timeout=timeout)
        return SimpleNamespace(json=lambda: answer, raise_for_status=lambda: None)

    monkeypatch.setattr(identify_runtime.requests, "get", get)
    found = identify_runtime.OMDb("omdb-test").details("tt1448755")
    assert found["runtime"] == 116
    assert found["votes"] == 160123
    assert found["year"] == 2011
    assert seen["params"]["i"] == "tt1448755"
    assert seen["timeout"] == identify_runtime.TIMEOUT


def tmdb_get(url, params=None, timeout=None):
    """requests.get answering like TMDB for the Kingdom and Hercules discs"""
    assert timeout == identify_runtime.TIMEOUT
    path = url[len(identify_runtime.TMDB_URL):]
    films = {f["id"]: f for f in (KINGDOM, KINGDOM_SHORT, VAMPIRE, HERCULES)}
    if path == "/search/movie":
        data = {"results": [f for f in films.values() if "kingdom" in f["title"].lower()]}
    elif path.startswith("/movie/"):
        data = films[int(path.split("/")[2])]
    elif path.startswith("/find/"):
        data = {"movie_results": [f for f in films.values() if f["imdb_id"] == path.split("/")[2]]}
    else:
        data = {"results": []}
    return SimpleNamespace(json=lambda: data, raise_for_status=lambda: None)


@pytest.fixture
def run_identify_dvd(monkeypatch):
    """identify_dvd() on a mocked disc; returns the job, the title searches and the lsdvd calls."""
    searches, lsdvd, disc = [], [], {}
    monkeypatch.setitem(cfg.arm_config, "METADATA_PROVIDER", "tmdb")
    monkeypatch.setitem(cfg.arm_config, "TMDB_API_KEY", "tmdb-test")
    monkeypatch.setitem(cfg.arm_config, "VIDEOTYPE", "auto")
    monkeypatch.setattr(identify_runtime.requests, "get", tmdb_get)
    monkeypatch.setattr(identify.pydvdid, "compute", lambda path: "1c4e8f92bd9629aa")
    monkeypatch.setattr(identify.utils, "database_updater",
                        lambda args, job: [setattr(job, key, value) for key, value in args.items()])
    monkeypatch.setattr(identify, "metadata_selector",
                        lambda job, title=None, year=None: searches.append(title))
    monkeypatch.setattr(identify, "identify_loop", lambda *args: None)
    monkeypatch.setattr(identify, "arm_subprocess", lambda args, *a, **k: lsdvd.append(args) or disc["lsdvd"])

    def run(enabled, label="THE_KINGDOM", crc=None, seconds=6602.4):
        # lsdvd -Oy prints one value per line
        disc["lsdvd"] = ("lsdvd = {\n  'device' : '/dev/sr0',\n  'track' : [\n    {\n      'ix' : 1,\n"
                         f"      'length' : {seconds},\n    }},\n    {{\n      'ix' : 2,\n"
                         "      'length' : 95.0,\n    },\n  ],\n}")
        monkeypatch.setitem(cfg.arm_config, "IDENTIFY_BY_RUNTIME", enabled)
        response = SimpleNamespace(read=lambda: json.dumps(
            {"success": bool(crc), "results": {"0": crc or {}}}).encode())
        monkeypatch.setattr(identify.urllib.request, "urlopen", lambda *args, **kwargs: response)
        job = SimpleNamespace(label=label, year=None, title=None, mountpoint="/mnt/dev/sr0",
                              devpath="/dev/sr0", crc_id=None, pretty_table=lambda: "")
        assert identify.identify_dvd(job) is True
        return job, searches, lsdvd
    return run


def test_identify_dvd_confirms_by_runtime_and_skips_the_title_search(run_identify_dvd):
    job, searches, lsdvd = run_identify_dvd(True)
    assert searches == []
    assert job.title == identify.utils.clean_for_filename("The Kingdom")
    assert job.year == "2007"
    assert job.imdb_id == "tt0431197"
    assert job.poster_url == identify_runtime.POSTER_BASE + "/kingdom.jpg"
    assert job.identity_verified is True
    assert len(lsdvd) == 1


def test_identify_dvd_keeps_a_runtime_confirmed_crc64_answer(run_identify_dvd):
    crc = {"title": "Hercules", "year": "1997", "imdb_id": "tt0119282", "video_type": "movie",
           "poster_img": "https://example.com/h.jpg"}
    job, searches, _ = run_identify_dvd(True, label="", crc=crc, seconds=5603.0)
    assert searches == []
    assert job.title == identify.utils.clean_for_filename("Hercules")
    assert job.imdb_id == "tt0119282"
    # a 110 min disc is not Hercules (93 min): the answer stays unconfirmed and the search runs
    job, searches, _ = run_identify_dvd(True, label="", crc=crc)
    assert searches == ["not identified"]
    assert getattr(job, "identity_verified", False) is False


def test_identify_dvd_unchanged_when_disabled(run_identify_dvd):
    job, searches, lsdvd = run_identify_dvd(False)
    assert searches == ["THE_KINGDOM"]
    assert getattr(job, "identity_verified", False) is False
    assert len(lsdvd) == 1


def test_identify_dvd_falls_back_when_the_provider_fails(run_identify_dvd, monkeypatch):
    def unreachable(*args, **kwargs):
        raise identify_runtime.requests.ConnectionError("down")

    monkeypatch.setattr(identify_runtime.requests, "get", unreachable)
    job, searches, _ = run_identify_dvd(True)
    assert searches == ["THE_KINGDOM"]
    assert getattr(job, "identity_verified", False) is False


def test_identify_skips_the_second_title_search_for_a_verified_identity(monkeypatch):
    details = []
    monkeypatch.setitem(cfg.arm_config, "GET_VIDEO_TITLE", True)
    monkeypatch.setattr(identify, "check_mount", lambda job: False)
    monkeypatch.setattr(identify, "arm_subprocess", lambda *args, **kwargs: None)
    monkeypatch.setattr(identify, "get_video_details", details.append)

    def verified(job):
        job.identity_verified = True
        return True

    monkeypatch.setattr(identify, "identify_dvd", verified)
    job = SimpleNamespace(disctype="dvd", devpath="/dev/sr0", title="The Kingdom", year="2007",
                          video_type="movie", pretty_table=lambda: "")
    identify.identify(job)
    assert details == []
    monkeypatch.setattr(identify, "identify_dvd", lambda job: True)
    identify.identify(SimpleNamespace(**{**vars(job), "identity_verified": False}))
    assert len(details) == 1
