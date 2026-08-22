"""Tests for the single authoritative application version source.

`Modules/version.py` holds APP_VERSION. Both the telemetry module (event
envelopes) and the app controller (version-update detection) must consume
it — the version string must never be duplicated in runtime code again.
"""

import os
import re
from pathlib import Path

# Qt offscreen for headless CI
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_version_format_is_semver_like():
    """The authoritative version stays a plain major.minor.patch string."""
    from Modules.version import APP_VERSION

    assert re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION), APP_VERSION


def test_telemetry_consumes_central_version():
    """Modules.telemetry re-exports the central APP_VERSION, not a copy."""
    import Modules.telemetry as telemetry
    from Modules.version import APP_VERSION

    assert telemetry.APP_VERSION == APP_VERSION


def test_event_envelope_reports_central_version(tmp_path):
    """A tracked event's app_version property equals the central APP_VERSION."""
    from PySide6.QtCore import QSettings

    from Modules.telemetry import AnalyticsClient
    from Modules.version import APP_VERSION

    qsettings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    client = AnalyticsClient(qsettings, telemetry_db_path=tmp_path / "events.db")
    qsettings.setValue("telemetry/consented", True)
    qsettings.sync()

    client.track("app_launched")
    _, event_data = client._event_store.get_pending_events(1)[0]

    assert event_data["properties"]["app_version"] == APP_VERSION


def test_app_controller_consumes_central_version():
    """app_controller imports the central version and keeps no local copy.

    (Statically inspected so this test doesn't need QtWidgets.)
    """
    source = (PROJECT_ROOT / "Modules" / "app_controller.py").read_text(
        encoding="utf-8"
    )

    assert "from Modules.version import APP_VERSION" in source
    # The old duplicated constant must be gone
    assert "_APP_VERSION" not in source
    assert '"1.4.0"' not in source
