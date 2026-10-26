"""IDENTIFY_BY_RUNTIME second pass: looser label readings, still settled only by runtime."""

import pytest

from arm.ripper import identify_loose, identify_runtime


def movie(title, year, runtime, imdb_id, votes=1000):
    return identify_runtime.film([title], year, imdb_id, runtime, votes, None)


PRIMAL_FEAR = movie("Primal Fear", 1996, 129, "tt0117381")
PINEAPPLE = movie("Pineapple Express", 2008, 111, "tt0910936")
SUBSPECIES = movie("Subspecies", 1991, 83, "tt0103002")
SUBSPECIES_2 = movie("Bloodstone: Subspecies II", 1993, 88, "tt0106436")
SUBSPECIES_3 = movie("Bloodlust: Subspecies III", 1994, 83, "tt0109268")


class QueryCatalog:
    """A metadata provider that answers each search query from a fixed table."""

    def __init__(self, answers, series=()):
        self.answers = {query.lower(): films for query, films in answers.items()}
        self.series = [[name] for name in series]
        self.queries = []

    def search(self, query, year=None):
        self.queries.append(query)
        return [{"names": f["names"], "ref": f["imdb_id"]} for f in self.answers.get(query.lower(), [])]

    def details(self, ref):
        return next(f for films in self.answers.values() for f in films if f["imdb_id"] == ref)

    def by_imdb(self, imdb_id):
        return None

    def series_names(self, query):
        return self.series


@pytest.mark.parametrize("label, expected", [
    ("SUBSPECIES2_V2", "SUBSPECIES 2"),
    ("BEOWULF_DC", "BEOWULF"),
    ("SHOOTER_AC_43", "SHOOTER"),
    ("PINEAPPLE_EXP", "PINEAPPLE EXP"),
    ("INU0NNW1", ""),
])
def test_words(label, expected):
    assert identify_loose.words(label) == expected


def test_segment_splits_run_together_words():
    assert identify_loose.segment("INTHENAMEOFTHEKING") == "in the name of the king"


@pytest.mark.parametrize("title, name, expected", [
    ("CHANGINGLANES", "Changing Lanes", "exact"),
    ("HITMAN", "The Hitman", "article"),
    ("SUBSPECIES 2", "Bloodstone: Subspecies II", "numbered"),
    ("PINEAPPLE EXP", "Pineapple Express", "prefix"),
    ("PRIMFEAR", "Primal Fear", "abbreviation"),
    ("PRECIOUS", "Precious Bane", None),
    ("SUBSPECIES 2", "Bloodlust: Subspecies III", None),
])
def test_relation(title, name, expected):
    assert identify_loose.relation(title, [name]) == expected


def test_abbreviated_label_is_settled_by_runtime():
    catalog = QueryCatalog({"PRIM": [PRIMAL_FEAR, movie("Prime", 2005, 105, "tt0387514")]})
    chosen, method = identify_runtime.confirm(catalog, "PRIMFEAR", 129.5 * 60)
    assert chosen["imdb_id"] == "tt0117381"
    assert method == "loose-abbreviation-label-and-runtime"


def test_shortened_label_is_settled_by_runtime():
    catalog = QueryCatalog({"PINEAPPLE EXP": [PINEAPPLE]})
    chosen, method = identify_runtime.confirm(catalog, "PINEAPPLE_EXP", 111.6 * 60)
    assert chosen["imdb_id"] == "tt0910936"
    assert method == "loose-prefix-label-and-runtime"


def test_loose_match_with_another_runtime_is_not_accepted():
    catalog = QueryCatalog({"PINEAPPLE EXP": [PINEAPPLE]})
    chosen, why = identify_runtime.confirm(catalog, "PINEAPPLE_EXP", 95 * 60)
    assert chosen is None
    assert why.endswith("second pass: no prefix match fits the disc runtime")


def test_sequel_number_picks_the_sequel():
    catalog = QueryCatalog({"SUBSPECIES": [SUBSPECIES, SUBSPECIES_2, SUBSPECIES_3]})
    chosen, method = identify_runtime.confirm(catalog, "SUBSPECIES2_V2", 88.3 * 60)
    assert chosen["imdb_id"] == "tt0106436"
    assert method == "loose-numbered-label-and-runtime"
    assert "SUBSPECIES 2" in catalog.queries


def test_close_rivals_are_not_decided():
    rival = movie("Pineapple Express: The Return", 2010, 112, "tt9000010")
    catalog = QueryCatalog({"PINEAPPLE EXP": [PINEAPPLE, rival]})
    chosen, why = identify_runtime.confirm(catalog, "PINEAPPLE_EXP", 111.6 * 60)
    assert chosen is None
    assert why.endswith("several related titles are close to the disc runtime")


def test_short_disc_is_not_named_by_a_loose_match():
    catalog = QueryCatalog({"PINEAPPLE EXP": [movie("Pineapple Express", 2008, 30, "tt0910936")]})
    chosen, why = identify_runtime.confirm(catalog, "PINEAPPLE_EXP", 30 * 60)
    assert chosen is None
    assert "shorter than a feature" in why


def test_crc64_answer_settles_a_label_with_pressing_words():
    # BULLETPROOF_US: no film is called that, and Bulletproof (1996) runs much longer than the disc
    monk = movie("Bulletproof Monk", 2003, 104, "tt0245803")
    catalog = QueryCatalog({"BULLETPROOF": [movie("Bulletproof", 1996, 84, "tt0115783")]})
    catalog.by_imdb = lambda imdb_id: monk if imdb_id == "tt0245803" else None
    answer = {"title": "Bulletproof Monk", "imdb_id": "tt0245803", "video_type": "movie"}
    chosen, method = identify_runtime.confirm(catalog, "BULLETPROOF_US", 104.2 * 60, answer)
    assert chosen["imdb_id"] == "tt0245803"
    assert method == "crc64-hint-and-closest-runtime"


def test_namesake_series_hold_is_not_loosened():
    catalog = QueryCatalog({"HEROES": [movie("Heroes", 2008, 88, "tt1270296", votes=40)]}, series=["Heroes"])
    chosen, why = identify_runtime.confirm(catalog, "HEROES", 88 * 60)
    assert chosen is None
    assert why == "a TV series shares the label's name"
    assert catalog.queries == ["HEROES"]
