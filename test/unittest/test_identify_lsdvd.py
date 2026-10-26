"""identify_dvd() finds the lsdvd title list even when libdvdread prints diagnostics first."""
import logging
from types import SimpleNamespace

import pytest

import arm.config.config as cfg
from arm.ripper import identify, utils

DIAGNOSTICS = ("libdvdread: Zero check failed in src/ifo_read.c:1296 for vtsi_mat->zero_1 : 0x00000000\n"
               "libdvdread: Zero check failed in src/ifo_read.c:1298 for vtsi_mat->zero_2 : 0x00000000\n")


def _lsdvd(count):
    tracks = ", ".join(f"{{'ix': {n}, 'length': 60.0}}" for n in range(1, count + 1))
    return f"lsdvd = {{\n  'device': '/dev/sr0',\n  'track': [{tracks}],\n}}\n"


@pytest.fixture
def run_identify_dvd(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("not available in this test")

    monkeypatch.setattr(identify.pydvdid, "compute", fail)
    monkeypatch.setattr(identify, "metadata_selector", fail)
    monkeypatch.setitem(cfg.arm_config, "PREVENT_99", True)

    def run(lsdvd_output):
        monkeypatch.setattr(identify, "arm_subprocess", lambda _cmd: lsdvd_output)
        job = SimpleNamespace(label="CROSSOVER", year=None, title="Crossover", devpath="/dev/sr0",
                              mountpoint="/mnt/dev/sr0", crc_id=None, has_track_99=False, pretty_table=lambda: "")
        identify.identify_dvd(job)
        return job

    return run


def test_99_titles_after_libdvdread_diagnostics_trigger_prevent_99(run_identify_dvd):
    with pytest.raises(utils.RipperException, match="Track 99"):
        run_identify_dvd(DIAGNOSTICS + _lsdvd(99))


def test_normal_disc_after_diagnostics_is_not_flagged(run_identify_dvd, caplog):
    with caplog.at_level(logging.ERROR):
        job = run_identify_dvd(DIAGNOSTICS + _lsdvd(12))
    assert job.has_track_99 is False
    assert "Failed to parse lsdvd output" not in caplog.text


def test_malformed_output_is_logged_not_raised(run_identify_dvd, caplog):
    with caplog.at_level(logging.ERROR):
        job = run_identify_dvd("lsdvd = {'track': not_a_literal}\n")
    assert job.has_track_99 is False
    assert "Failed to parse lsdvd output" in caplog.text


def test_output_without_a_dict_is_ignored(run_identify_dvd):
    job = run_identify_dvd(DIAGNOSTICS)
    assert job.has_track_99 is False
