"""A Blu-ray's bdmt_eng.xml is untrusted disc content: its size is capped and a bad line is logged truncated"""
import logging
from types import SimpleNamespace

import pytest

from arm.ripper import identify


@pytest.fixture(autouse=True)
def no_database(monkeypatch):
    """identify_bluray commits the job; these jobs are plain objects, so skip the database"""
    monkeypatch.setattr(identify, "db", SimpleNamespace(session=SimpleNamespace(commit=lambda: None)))


def disc(tmp_path, xml):
    meta = tmp_path / "BDMV" / "META" / "DL"
    meta.mkdir(parents=True)
    (meta / "bdmt_eng.xml").write_bytes(xml)
    return SimpleNamespace(mountpoint=str(tmp_path), label="BIG_DISC", title=None, year=None)


def refuse_to_parse(_data):
    raise AssertionError("an oversized bdmt_eng.xml was parsed")


def test_an_oversized_metadata_file_is_not_parsed(tmp_path, monkeypatch, caplog):
    job = disc(tmp_path, b"<disclib>" + b" " * (identify.BLURAY_XML_MAX_BYTES + 10) + b"</disclib>")
    monkeypatch.setattr(identify.xmltodict, "parse", refuse_to_parse)

    with caplog.at_level(logging.WARNING):
        assert identify.identify_bluray(job) is True

    assert job.title == "BIG_DISC"
    assert "larger than" in caplog.text


def test_a_malformed_line_is_logged_truncated(tmp_path, caplog):
    job = disc(tmp_path, b"<disclib><di:x " + b"A" * 50000 + b"</disclib>")

    with caplog.at_level(logging.WARNING):
        identify.identify_bluray(job)

    warning = next(r.getMessage() for r in caplog.records if "Offending line" in r.getMessage())
    offending = warning.split("Offending line: ", 1)[1].split("\n", 1)[0]
    assert len(offending) <= identify.LOGGED_LINE_CHARS
    assert job.title == "BIG_DISC"


def test_a_normal_metadata_file_still_names_the_disc(tmp_path):
    xml = (b'<disclib xmlns:di="urn:BDA:bdmv;discinfo"><di:discinfo><di:title><di:name>Killer Elite - Blu-ray'
           b'</di:name></di:title></di:discinfo></disclib>')
    job = disc(tmp_path, xml)

    assert identify.identify_bluray(job) is True
    assert job.title == "Killer-Elite"
