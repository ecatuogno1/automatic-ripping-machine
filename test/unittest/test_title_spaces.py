"""Titles are searched with spaces; TITLE_SPACES keeps the spaces in folder/file names."""

from types import SimpleNamespace

import pytest

import arm.config.config as cfg
from arm.ripper import identify, utils


def test_clean_for_filename_joins_words_with_dashes_by_default(monkeypatch):
    monkeypatch.delitem(cfg.arm_config, "TITLE_SPACES", raising=False)

    assert utils.clean_for_filename("The Boondock Saints") == "The-Boondock-Saints"


@pytest.mark.parametrize("title, expected", [
    ("The Boondock Saints", "The Boondock Saints"),
    ("The  Fox and the Hound", "The Fox and the Hound"),
    ("Mission: Impossible - Fallout", "Mission- Impossible - Fallout"),
    ("Tom & Jerry [Blu-ray]", "Tom and Jerry"),
])
def test_clean_for_filename_keeps_spaces_with_title_spaces(monkeypatch, title, expected):
    monkeypatch.setitem(cfg.arm_config, "TITLE_SPACES", True)

    assert utils.clean_for_filename(title) == expected


@pytest.mark.parametrize("provider, function", [("omdb", "call_omdb_api"), ("tmdb", "tmdb_search")])
def test_search_replaces_word_separators_with_spaces(monkeypatch, provider, function):
    searched = []
    monkeypatch.setitem(cfg.arm_config, "METADATA_PROVIDER", provider)
    monkeypatch.setattr(identify.ui_utils, function, lambda title, year: searched.append(title))

    identify.metadata_selector(SimpleNamespace(), "The-Boondock_Saints+II", "2009")

    assert searched == ["The Boondock Saints II"]
