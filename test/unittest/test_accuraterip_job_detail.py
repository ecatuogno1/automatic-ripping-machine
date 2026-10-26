"""The job page shows each music track's AccurateRip result."""


def test_job_detail_shows_accuraterip_per_track(monkeypatch):
    from arm.ui import app, db
    import arm.ui.routes  # noqa: F401
    import arm.ui.utils as ui_utils
    from arm.models.job import Job
    from arm.models.track import Track
    from arm.ripper import utils

    monkeypatch.setattr(ui_utils, "metadata_selector", lambda *args, **kwargs: None)
    monkeypatch.setattr(Job, "parse_udev", lambda self: setattr(self, "disctype", "music"))
    monkeypatch.setattr(Job, "get_pid", lambda self: None)
    with app.app_context():
        db.create_all()
        app.config.update(TESTING=True, LOGIN_DISABLED=True)
        job = Job("/dev/sr0")
        for field, value in {"title": "Album", "video_type": "Music", "status": "success",
                             "logfile": "album.log"}.items():
            setattr(job, field, value)
        db.session.add(job)
        db.session.commit()
        for number in ("1", "2", "A3"):
            db.session.add(Track(job.job_id, number, 1000, "n/a", 0.1, False, "ABCDE", "Album", f"Song {number}"))
        db.session.commit()
        utils.record_accuraterip_tracks(job, {"status": "present", "tracks": [
            {"track": 1, "status": "match", "confidence": 12},
            {"track": 2, "status": "mismatch", "confidence": 0},
            {"track": 3, "status": "match", "confidence": 4}]})
        statuses = {t.track_number: (t.status, t.error) for t in job.tracks}
        detail = app.test_client().get(f"/jobdetail?job_id={job.job_id}").get_data(as_text=True)
        job.tracks.delete()
        db.session.delete(job)
        db.session.commit()
    assert statuses["1"] == ("success", "AccurateRip confidence 12")
    assert statuses["2"] == ("fail", "Did not match AccurateRip")
    # A track number that isn't a plain number can't be matched to a disc position.
    assert statuses["A3"] == (None, None)
    assert "AccurateRip" in detail
    assert detail.count("No match") == 1
    assert detail.count(">Match<") == 1
