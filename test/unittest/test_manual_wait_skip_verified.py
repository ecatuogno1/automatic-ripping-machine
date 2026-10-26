"""MANUAL_WAIT_SKIP_VERIFIED skips the manual wait only for a runtime-confirmed identity."""

from types import SimpleNamespace

import pytest

import arm.config.config as cfg
from arm.ripper import utils


@pytest.fixture
def wait(monkeypatch):
    """check_for_wait() on a job; returns the seconds slept."""
    slept = []
    monkeypatch.setattr(utils.time, "sleep", slept.append)
    monkeypatch.setattr(utils, "database_updater", lambda args, job: None)
    monkeypatch.setattr(utils.db.session, "refresh", lambda job: None)

    def run(skip, verified):
        monkeypatch.setitem(cfg.arm_config, "MANUAL_WAIT_SKIP_VERIFIED", skip)
        job = SimpleNamespace(config=SimpleNamespace(MANUAL_WAIT=True, MANUAL_WAIT_TIME=10), title_manual=None)
        if verified:
            job.identity_verified = True
        slept.clear()
        utils.check_for_wait(job)
        return sum(slept)
    return run


def test_verified_identity_skips_the_wait(wait):
    assert wait(True, True) == 0


def test_unverified_identity_still_waits(wait):
    assert wait(True, False) == 10


def test_default_waits_for_verified_identity_too(wait):
    assert wait(False, True) == 10
