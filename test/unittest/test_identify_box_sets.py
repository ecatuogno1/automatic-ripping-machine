"""get_video_details() searches TV box-set titles without their season/disc markers and pressing year."""

from types import SimpleNamespace

import pytest

from arm.ripper import identify

FOUND = {"Search": [{"Title": "found"}]}


def run_search(monkeypatch, title, year, matches):
    """Run get_video_details() with a fake provider that only answers the (title, year) pairs in ``matches``."""
    searched = []

    def fake_selector(job, title=None, year=None):
        searched.append((title, year or None))
        return FOUND if (title, year or None) in matches else None

    monkeypatch.setattr(identify, "metadata_selector", fake_selector)
    identify.get_video_details(SimpleNamespace(title=title, year=year))
    return searched


@pytest.mark.parametrize("title, expected", [
    ("Person_of_Interest_S2_D2", "Person_of_Interest"),
    ("Avatar_Book_1_Disc_2", "Avatar"),
    ("Legend_Of_Korra_Book_3_Disc_1", "Legend_Of_Korra"),
    ("Firefly Season One Disc 2", "Firefly"),
    ("Doctor-Who-S01", "Doctor-Who"),
    ("The_Book_of_Eli", "The_Book_of_Eli"),
    ("Blade_Runner_2049", "Blade_Runner_2049"),
    ("OBAN_STAR_RACERS_2", "OBAN_STAR_RACERS_2"),
])
def test_strip_set_markers(title, expected):
    assert identify.strip_set_markers(title) == expected


def test_box_set_searches_show_name_without_pressing_year_first(monkeypatch):
    searched = run_search(monkeypatch, "Person_of_Interest_S2_D2", "2025",
                          {("Person+of+Interest", None), ("Person", "2025")})

    assert searched[0] == ("Person+of+Interest", None)
    assert len(searched) == 1


def test_box_set_never_searches_a_single_word(monkeypatch):
    searched = run_search(monkeypatch, "Person_of_Interest_S2_D2", "2025", {("Person", "2025"), ("Person", None)})

    assert ("Person", "2025") not in searched
    assert ("Person", None) not in searched


def test_dash_slicing_retries_without_year(monkeypatch):
    # clean_for_filename() puts dashes between words; a shorter title must also be tried without the year
    searched = run_search(monkeypatch, "OBAN-STAR-RACERS-2", "2020", {("OBAN-STAR-RACERS", None)})

    assert searched[-1] == ("OBAN-STAR-RACERS", None)


def test_movie_title_still_searched_with_year_first(monkeypatch):
    searched = run_search(monkeypatch, "Dune", "2021", {("Dune", "2021")})

    assert searched == [("Dune", "2021")]
