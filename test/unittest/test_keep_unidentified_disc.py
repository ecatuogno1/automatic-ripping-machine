"""A disc whose type ARM could not determine is not ejected when the job fails (#1822)."""
from types import SimpleNamespace

import pytest

from arm.models.job import JobState
from arm.ripper import main


class FakeJob(SimpleNamespace):
    def eject(self):
        self.ejected = True


def _job(status, disctype):
    drive = SimpleNamespace(released=False)
    drive.release_current_job = lambda: setattr(drive, "released", True)
    return FakeJob(status=status, disctype=disctype, devpath="/dev/sr0", ejected=False, drive=drive)


def test_unidentified_disc_stays_in_the_drive():
    job = _job(JobState.FAILURE.value, "unknown")
    main.finish_with_drive(job)
    assert job.ejected is False
    assert job.drive.released is True


@pytest.mark.parametrize("status, disctype", [
    (JobState.SUCCESS.value, "dvd"),
    (JobState.FAILURE.value, "dvd"),  # e.g. PREVENT_99 or a failed rip: still ejected
    (JobState.FAILURE.value, "music"),
])
def test_other_jobs_still_eject(status, disctype):
    job = _job(status, disctype)
    main.finish_with_drive(job)
    assert job.ejected is True
