"""A very short title ("9") that OMDb answers with "Too many results." is looked up by its exact title."""

import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

NINE = {"Title": "9", "Year": "2009", "imdbID": "tt0472033", "Type": "movie", "Poster": "p", "Response": "True"}


@pytest.fixture
def omdb(monkeypatch):
    import arm.config.config as cfg
    import arm.ui  # noqa: F401
    from arm.ui import metadata

    monkeypatch.setitem(cfg.arm_config, "OMDB_API_KEY", "k")
    requested = []

    def urlopen(url, timeout=None):
        query = parse_qs(urlparse(url).query)
        requested.append(query)
        if "s" in query:
            body = {"Response": "False", "Error": "Too many results."}
        elif query.get("t") == ["9"]:
            body = NINE
        else:
            body = {"Response": "False", "Error": "Movie not found!"}
        return SimpleNamespace(read=lambda: json.dumps(body).encode())

    monkeypatch.setattr(metadata.urllib.request, "urlopen", urlopen)
    return SimpleNamespace(module=metadata, requested=requested)


def test_too_many_results_falls_back_to_exact_title(omdb):
    result = omdb.module.call_omdb_api("9", "2009")

    assert result["Search"][0]["imdbID"] == "tt0472033"
    assert omdb.requested[-1]["t"] == ["9"]
    assert omdb.requested[-1]["y"] == ["2009"]


def test_exact_title_not_found_returns_none(omdb):
    assert omdb.module.call_omdb_api("It", "") is None


def test_imdb_lookup_does_not_retry(omdb):
    omdb.module.call_omdb_api(imdb_id="tt0472033")

    assert len(omdb.requested) == 1
