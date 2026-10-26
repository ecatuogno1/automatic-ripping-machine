"""The settings page asks before the Remove link deletes a drive"""
import re
import types
from pathlib import Path

from arm.ui import app
from arm.ui.forms import SystemInfoDrives
import arm.ui.routes  # noqa: F401

TEMPLATES = Path(__file__).resolve().parents[2] / "arm/ui/settings/templates/settings"


def render_drives(drive):
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.test_request_context("/settings"):
        template = app.jinja_env.get_template("settings/drives.html")
        return template.render(drives=[drive], form_drive=SystemInfoDrives())


def test_remove_link_asks_with_drive_name():
    drive = types.SimpleNamespace(drive_id=3, name='Drive "A"', mount="/dev/sr1", description="", serial_id="S1",
                                  job_current=None, job_previous=None)
    html = render_drives(drive)
    link = re.search(r'<a href="drive/remove/3"[^>]*>', html)
    assert link is not None
    # the drive name is HTML-escaped inside the attribute and never becomes inline script
    assert 'data-confirm="Remove Drive &#34;A&#34; (/dev/sr1) from ARM?"' in link.group(0)
    assert "onclick" not in link.group(0)


def test_settings_page_cancels_unconfirmed_clicks():
    script = (TEMPLATES / "settings.html").read_text()
    assert '$(document).on("click", "a[data-confirm]"' in script
    assert "window.confirm(this.dataset.confirm)" in script
