"""identify_dvd() searches for the title without the studio's aspect/edition markers."""

from types import SimpleNamespace

import pytest

from arm.ripper import identify


@pytest.mark.parametrize("label, expected", [
    ("THE_MATRIX_16X9", "THE_MATRIX"),
    ("THE_MATRIX_169", "THE_MATRIX"),
    ("RED_DAWN_4X3_FF_N_A", "RED_DAWN"),
    ("LAST_BOY_SCOUT_16X9_LB_NA", "LAST_BOY_SCOUT"),
    ("GLADIATOR_WS", "GLADIATOR"),
    ("BRAVEHEART_SCE", "BRAVEHEART"),
    ("ALIEN_unrated", "ALIEN"),
    ("BLADE_RUNNER_2049", "BLADE_RUNNER_2049"),
    ("DRACULA_2000", "DRACULA_2000"),
    ("SEA_OF_LOVE", "SEA_OF_LOVE"),
    ("WS", "WS"),
])
def test_strip_label_markers(label, expected):
    assert identify.strip_label_markers(label) == expected


def test_identify_dvd_searches_without_markers(monkeypatch):
    searched = []

    def no_fingerprint(path):
        raise OSError("no disc")

    monkeypatch.setattr(identify.pydvdid, "compute", no_fingerprint)
    monkeypatch.setattr(identify, "metadata_selector",
                        lambda job, title=None, year=None: searched.append(title) or {"Search": []})
    monkeypatch.setattr(identify, "identify_loop", lambda *args: None)
    monkeypatch.setattr(identify, "arm_subprocess", lambda *args, **kwargs: None)
    job = SimpleNamespace(label="THE_MATRIX_16X9_WS", year=None, title="x", mountpoint="/mnt/dev/sr0",
                          devpath="/dev/sr0", pretty_table=lambda: "")

    assert identify.identify_dvd(job) is True
    assert searched == ["THE_MATRIX"]
