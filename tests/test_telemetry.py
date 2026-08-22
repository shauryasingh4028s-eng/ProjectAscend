"""Tests for the anonymous analytics (telemetry) module.

Covers:
- Installation ID creation and persistence
- Consent (opt-in) behaviour
- Event schema validation (PostHog `uuid` dedup field)
- Local queue persistence
- Duplicate prevention (event_uuid)
- Legacy `event_id` schema migration (no data loss on upgrade)
- PostHog 4xx = permanent failure (no endless retry), 5xx/429/network = retryable
- Offline behaviour / queue bounded at 500
- Failed transmission / retry
- Malformed backend responses
- Analytics failure not affecting the application
- No PII in any event
- first_launch / app_launched logic
- Consent-gated queue (no events before consent)
"""

import json
import os
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from Modules.telemetry import SendResult
from Modules.version import APP_VERSION

# Qt offscreen for headless CI
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ─── FIXTURES ──────────────────────────────────────────────────────────────────

@pytest.fixture
def qsettings(tmp_path):
    """A QSettings instance backed by a temporary file, isolated per test."""
    from PySide6.QtCore import QSettings

    settings_path = tmp_path / "test_settings.ini"
    qs = QSettings(str(settings_path), QSettings.IniFormat)
    yield qs
    # Clean up
    qs.clear()
    qs.sync()


@pytest.fixture
def telemetry_db(tmp_path):
    """A temporary path for the telemetry SQLite database."""
    return tmp_path / "telemetry" / "events.db"


@pytest.fixture
def client(qsettings, telemetry_db):
    """An AnalyticsClient with no PostHog API key (transmission is no-op)."""
    from Modules.telemetry import AnalyticsClient

    c = AnalyticsClient(qsettings, telemetry_db_path=telemetry_db)
    return c


@pytest.fixture
def consented_client(qsettings, telemetry_db):
    """An AnalyticsClient with consent already granted."""
    from Modules.telemetry import AnalyticsClient

    qsettings.setValue("telemetry/consented", True)
    qsettings.sync()
    c = AnalyticsClient(qsettings, telemetry_db_path=telemetry_db)
    return c


@pytest.fixture
def qcore_app():
    """A QApplication for signal and event processing in tests."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# ─── INSTALLATION ID TESTS ────────────────────────────────────────────────────

class TestInstallationId:
    """Tests for InstallationId generation and persistence."""

    def test_installation_id_generated_once(self, qsettings):
        from Modules.telemetry import InstallationId

        iid = InstallationId(qsettings)
        first = iid.get()
        second = iid.get()
        assert first == second
        assert InstallationId._is_valid_uuid(first)

    def test_installation_id_persisted_across_instances(self, qsettings):
        from Modules.telemetry import InstallationId

        iid1 = InstallationId(qsettings)
        id1 = iid1.get()

        iid2 = InstallationId(qsettings)
        id2 = iid2.get()

        assert id1 == id2

    def test_installation_id_is_valid_uuid4(self, qsettings):
        from Modules.telemetry import InstallationId

        iid = InstallationId(qsettings)
        value = iid.get()
        parsed = uuid.UUID(value)
        assert parsed.version == 4

    def test_installation_id_reset_on_reconsent(self, qsettings):
        from Modules.telemetry import InstallationId

        iid = InstallationId(qsettings)
        original = iid.get()
        reset = iid.reset()

        assert original != reset
        assert InstallationId._is_valid_uuid(reset)
        # After reset, get() returns the new value
        assert iid.get() == reset


# ─── CONSENT TESTS ────────────────────────────────────────────────────────────

class TestConsent:
    """Tests for the consent mechanism (enabled by default, user controllable)."""

    def test_consent_default_is_enabled(self, client):
        """When telemetry/consented key is absent, analytics is enabled by default."""
        assert client.is_enabled() is True

    def test_consent_fresh_installation_enabled_by_default(self, qsettings, telemetry_db):
        """Fresh installation has analytics enabled by default without explicit key."""
        from Modules.telemetry import AnalyticsClient

        assert not qsettings.contains("telemetry/consented")
        c = AnalyticsClient(qsettings, telemetry_db_path=telemetry_db)
        assert c.is_enabled() is True
        assert qsettings.value("telemetry/consented", True, type=bool) is True

    def test_consent_existing_false_preserved(self, qsettings, telemetry_db):
        """Existing False consent is preserved and remains disabled."""
        from Modules.telemetry import AnalyticsClient

        qsettings.setValue("telemetry/consented", False)
        qsettings.sync()

        c = AnalyticsClient(qsettings, telemetry_db_path=telemetry_db)
        assert c.is_enabled() is False
        assert qsettings.value("telemetry/consented", True, type=bool) is False

    def test_consent_existing_true_preserved(self, qsettings, telemetry_db):
        """Existing True consent is preserved and remains enabled."""
        from Modules.telemetry import AnalyticsClient

        qsettings.setValue("telemetry/consented", True)
        qsettings.sync()

        c = AnalyticsClient(qsettings, telemetry_db_path=telemetry_db)
        assert c.is_enabled() is True
        assert qsettings.value("telemetry/consented", True, type=bool) is True

    def test_consent_toggling_persists_correctly(self, client, qsettings):
        """Disabling and re-enabling persists correctly to settings."""
        client.disable()
        assert client.is_enabled() is False
        assert qsettings.value("telemetry/consented", True, type=bool) is False

        client.enable()
        assert client.is_enabled() is True
        assert qsettings.value("telemetry/consented", True, type=bool) is True

    def test_consent_enable(self, client, qsettings):
        """Setting consent to True makes is_enabled() return True."""
        client.disable()
        assert client.is_enabled() is False
        client.enable()
        assert client.is_enabled() is True
        assert qsettings.value("telemetry/consented", type=bool) is True

    def test_consent_disable(self, consented_client, qsettings):
        """Disabling consent sets the flag to False."""
        consented_client.disable()
        assert consented_client.is_enabled() is False
        assert qsettings.value("telemetry/consented", type=bool) is False

    def test_consent_disable_purges_queue(self, consented_client, telemetry_db):
        """Disabling consent clears all pending events from the local store."""
        consented_client.track("app_launched")
        consented_client.track("session_started")

        # Verify events are queued
        assert consented_client._event_store.count() == 2

        consented_client.disable()

        # Queue should be empty after disable
        assert consented_client._event_store.count() == 0

    def test_no_events_collected_without_consent(self, client):
        """track() calls when disabled produce zero queued events."""
        client.disable()
        client.track("app_launched")
        client.track("session_started")
        client.track("task_created")
        assert client._event_store.count() == 0

    def test_no_events_queued_before_consent(self, client):
        """first_launch is not queued on startup when disabled."""
        client.disable()
        client.track_first_launch_or_app_launched()
        assert client._event_store.count() == 0

    def test_events_collected_after_consent(self, consented_client):
        """track() after consent writes to the local queue."""
        consented_client.track("app_launched")
        assert consented_client._event_store.count() == 1

    def test_enable_resets_installation_id(self, client, qsettings):
        """Re-enabling analytics generates a fresh installation ID."""
        client.disable()
        # Get initial ID
        original_id = client._installation_id.get()

        # Enable (consent)
        client.enable()
        new_id = client._installation_id.get()

        assert original_id != new_id


# ─── EVENT SCHEMA TESTS ──────────────────────────────────────────────────────

class TestEventSchema:
    """Tests for event envelope structure and validation."""

    def test_event_schema_structure(self, consented_client):
        """Every generated event has all required envelope fields."""
        consented_client.track("app_launched")

        pending = consented_client._event_store.get_pending_events(1)
        assert len(pending) == 1

        event_uuid, event_data = pending[0]
        props = event_data["properties"]

        assert event_data["event"] == "app_launched"
        assert "timestamp" in event_data
        # PostHog's server-side dedup field; the legacy `event_id` key must
        # no longer appear on the wire envelope.
        assert "uuid" in event_data
        assert "event_id" not in event_data
        # The local queue key and the wire uuid are the same value
        assert event_data["uuid"] == event_uuid
        assert props["distinct_id"] == consented_client._installation_id.get()
        assert props["$process_person_profile"] is False
        assert props["app_version"] == APP_VERSION
        assert props["os_family"] in ("windows", "macos", "linux", "unknown")
        assert props["telemetry_schema"] == 1

    def test_event_uuid_is_uuid4(self, consented_client):
        """Each event gets a unique UUID4 uuid (PostHog dedup field)."""
        consented_client.track("app_launched")
        pending = consented_client._event_store.get_pending_events(1)
        _, event_data = pending[0]

        parsed = uuid.UUID(event_data["uuid"])
        assert parsed.version == 4

    def test_only_predefined_events_allowed(self, consented_client):
        """Unknown event names are silently dropped."""
        consented_client.track("not_a_real_event")
        consented_client.track("delete_system32")
        consented_client.track("")
        assert consented_client._event_store.count() == 0

    def test_all_predefined_events_accepted(self, consented_client):
        """Every predefined event name is accepted."""
        from Modules.telemetry import ALLOWED_EVENTS

        for event_name in ALLOWED_EVENTS:
            consented_client.track(event_name)

        assert consented_client._event_store.count() == len(ALLOWED_EVENTS)

    def test_no_extra_properties_in_events(self, consented_client):
        """Events carry only the common envelope properties.

        No per-event custom properties are transmitted in v1.4.
        """
        consented_client.track("app_launched")
        pending = consented_client._event_store.get_pending_events(1)
        _, event_data = pending[0]

        props = event_data["properties"]
        allowed_property_keys = {
            "distinct_id",
            "$process_person_profile",
            "app_version",
            "os_family",
            "telemetry_schema",
        }

        assert set(props.keys()) == allowed_property_keys

    def test_timestamp_is_iso8601_utc(self, consented_client):
        """Timestamps are ISO-8601 and in UTC."""
        consented_client.track("app_launched")
        pending = consented_client._event_store.get_pending_events(1)
        _, event_data = pending[0]

        ts = event_data["timestamp"]
        assert "T" in ts
        # Should end with +00:00 or Z
        assert ts.endswith("+00:00") or ts.endswith("Z")

    def test_app_version_in_envelope(self, consented_client):
        """Every event includes the authoritative application version."""
        consented_client.track("session_started")
        pending = consented_client._event_store.get_pending_events(1)
        _, event_data = pending[0]

        assert event_data["properties"]["app_version"] == APP_VERSION


# ─── LOCAL PERSISTENCE TESTS ─────────────────────────────────────────────────

class TestLocalPersistence:
    """Tests for the local SQLite event queue."""

    def test_event_persisted_to_local_queue(self, consented_client, telemetry_db):
        """track() writes one row to local SQLite."""
        consented_client.track("app_launched")
        assert consented_client._event_store.count() == 1

        # Verify the database file exists
        assert telemetry_db.exists()

    def test_multiple_events_persisted(self, consented_client):
        """Multiple track() calls create multiple queue entries."""
        consented_client.track("app_launched")
        consented_client.track("session_started")
        consented_client.track("task_completed")
        assert consented_client._event_store.count() == 3

    def test_events_survive_new_client_instance(self, qsettings, telemetry_db):
        """Events persist across AnalyticsClient instances."""
        from Modules.telemetry import AnalyticsClient

        c1 = AnalyticsClient(qsettings, telemetry_db_path=telemetry_db)
        c1.enable()
        c1.track("app_launched")
        c1.track("session_started")

        # New instance, same DB
        c2 = AnalyticsClient(qsettings, telemetry_db_path=telemetry_db)
        assert c2._event_store.count() == 2

    def test_queue_bounded_at_500(self, consented_client):
        """Oldest events are dropped when queue exceeds 500."""
        from Modules.telemetry import MAX_QUEUE_SIZE

        # Enqueue 600 events (over the limit)
        for i in range(600):
            consented_client.track("app_launched")

        count = consented_client._event_store.count()
        assert count <= MAX_QUEUE_SIZE

    def test_oldest_events_dropped_when_capped(self, consented_client):
        """When the queue is full, oldest events are dropped first."""
        from Modules.telemetry import MAX_QUEUE_SIZE

        # Fill beyond capacity
        event_ids_sent = []
        for i in range(MAX_QUEUE_SIZE + 50):
            consented_client.track("app_launched")

        # The queue should be at exactly the max
        assert consented_client._event_store.count() == MAX_QUEUE_SIZE


# ─── DUPLICATE PREVENTION TESTS ───────────────────────────────────────────────

class TestDuplicatePrevention:
    """Tests for event_id-based idempotency."""

    def test_duplicate_prevention(self, consented_client):
        """Same event UUID is never enqueued twice.

        Since track() generates a new UUID each time, duplicates must be
        tested by directly calling EventStore.enqueue with the same
        event_uuid.
        """
        event_uuid = str(uuid.uuid4())
        event_data = {
            "event": "app_launched",
            "uuid": event_uuid,
            "timestamp": "2026-08-21T00:00:00Z",
        }

        result1 = consented_client._event_store.enqueue(event_uuid, event_data)
        result2 = consented_client._event_store.enqueue(event_uuid, event_data)

        assert result1 is True
        assert result2 is False  # Duplicate rejected
        assert consented_client._event_store.count() == 1

    def test_different_event_uuids_are_separate(self, consented_client):
        """Events with different event UUIDs are stored separately."""
        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())
        data = {"event": "app_launched"}

        consented_client._event_store.enqueue(id1, data)
        consented_client._event_store.enqueue(id2, data)

        assert consented_client._event_store.count() == 2


# ─── TRANSMISSION TESTS ──────────────────────────────────────────────────────

class TestTransmission:
    """Tests for HTTP batch transmission to PostHog."""

    def test_flush_sends_batch(self, consented_client):
        """Mock HTTP backend receives correct batch JSON."""
        consented_client.track("app_launched")
        consented_client.track("session_started")

        mock_backend = MagicMock()
        mock_backend.send_batch.return_value = SendResult.SUCCESS
        consented_client._backend = mock_backend

        consented_client.flush()
        
        # Wait for worker thread to complete
        import time
        time.sleep(0.1)

        # Backend was called with 2 events
        mock_backend.send_batch.assert_called_once()
        events = mock_backend.send_batch.call_args[0][0]
        assert len(events) == 2
        assert events[0]["event"] == "app_launched"
        assert events[1]["event"] == "session_started"

    def test_successful_flush_clears_queue(self, consented_client, qcore_app):
        """After successful POST, flushed events are deleted from local store."""
        consented_client.track("app_launched")
        consented_client.track("session_started")

        mock_backend = MagicMock()
        mock_backend.send_batch.return_value = SendResult.SUCCESS
        consented_client._backend = mock_backend

        consented_client.flush()

        # Wait for worker thread to complete with event processing
        import time
        for _ in range(100):  # Wait up to 1 second
            if len(consented_client._active_workers) == 0:
                break
            qcore_app.processEvents()
            time.sleep(0.01)

        # Process any remaining events
        for _ in range(10):
            qcore_app.processEvents()
            time.sleep(0.01)

        assert consented_client._event_store.count() == 0

    def test_flush_retry_on_failure(self, consented_client, qcore_app):
        """Transiently failed flush keeps events queued for next attempt."""
        consented_client.track("app_launched")

        mock_backend = MagicMock()
        mock_backend.send_batch.return_value = SendResult.RETRYABLE_FAILURE
        consented_client._backend = mock_backend

        consented_client.flush()
        
        # Wait for worker thread to complete with event processing
        import time
        for _ in range(100):  # Wait up to 1 second
            if len(consented_client._active_workers) == 0:
                break
            qcore_app.processEvents()
            time.sleep(0.01)
        
        # Process any remaining events
        for _ in range(10):
            qcore_app.processEvents()
            time.sleep(0.01)

        # Events should still be queued
        assert consented_client._event_store.count() == 1

        # Next flush retries
        mock_backend.send_batch.return_value = SendResult.SUCCESS
        consented_client.flush()
        
        # Wait for worker thread to complete with event processing
        for _ in range(100):  # Wait up to 1 second
            if len(consented_client._active_workers) == 0:
                break
            qcore_app.processEvents()
            time.sleep(0.01)
        
        # Process any remaining events
        for _ in range(10):
            qcore_app.processEvents()
            time.sleep(0.01)
        
        assert consented_client._event_store.count() == 0

    def test_malformed_backend_response(self, consented_client):
        """Non-200 responses don't crash the client; events stay queued."""
        consented_client.track("app_launched")

        mock_backend = MagicMock()
        mock_backend.send_batch.side_effect = Exception("Connection refused")
        consented_client._backend = mock_backend

        # Should not raise
        consented_client.flush()

        # Events still queued
        assert consented_client._event_store.count() == 1

    def test_no_transmission_without_api_key(self, consented_client):
        """A backend without an API key treats transmission as a no-op SUCCESS."""
        from Modules.telemetry import AnalyticsBackend

        consented_client.track("app_launched")

        # Explicitly unconfigured backend (independent of the shipped key):
        # no network call is attempted and the send is a no-op SUCCESS.
        backend = AnalyticsBackend()
        backend._api_key = ""
        with patch("Modules.telemetry.urlopen") as mock_urlopen:
            result = backend.send_batch([{"event": "test"}])
        assert result is SendResult.SUCCESS
        mock_urlopen.assert_not_called()

    def test_flush_does_nothing_without_consent(self, qsettings, telemetry_db):
        """Flush does nothing when consent is disabled."""
        from Modules.telemetry import AnalyticsClient

        qsettings.setValue("telemetry/consented", False)
        qsettings.sync()
        c = AnalyticsClient(qsettings, telemetry_db_path=telemetry_db)
        # Manually enqueue an event bypassing consent
        event_id = str(uuid.uuid4())
        c._event_store.enqueue(event_id, {"event": "app_launched"})

        mock_backend = MagicMock()
        c._backend = mock_backend

        c.flush()

        # Backend should not have been called (consent is disabled)
        mock_backend.send_batch.assert_not_called()


# ─── OFFLINE BEHAVIOUR TESTS ─────────────────────────────────────────────────

class TestOfflineBehaviour:
    """Tests for when the internet is unavailable."""

    def test_offline_events_accumulate(self, consented_client):
        """When backend is unreachable, events stay in queue across multiple calls."""
        mock_backend = MagicMock()
        mock_backend.send_batch.return_value = SendResult.RETRYABLE_FAILURE
        consented_client._backend = mock_backend

        consented_client.track("app_launched")
        consented_client.flush()  # Fails
        consented_client.track("session_started")
        consented_client.flush()  # Fails

        assert consented_client._event_store.count() == 2

    def test_events_queue_without_network(self, consented_client, qsettings, telemetry_db):
        """track() works fine regardless of network state."""
        from Modules.telemetry import AnalyticsClient

        # Even with a backend that always fails, track() succeeds
        consented_client.track("app_launched")
        assert consented_client._event_store.count() == 1


# ─── FIRST LAUNCH / APP LAUNCHED TESTS ───────────────────────────────────────

class TestFirstLaunch:
    """Tests for first_launch vs app_launched distinction."""

    def test_first_launch_fires_once(self, consented_client, qsettings):
        """first_launch fires on first launch, app_launched on subsequent."""
        consented_client.track_first_launch_or_app_launched()

        pending = consented_client._event_store.get_pending_events(10)
        assert len(pending) == 1
        _, event_data = pending[0]
        assert event_data["event"] == "first_launch"

        # Second call should fire app_launched
        consented_client._event_store.clear()
        consented_client.track_first_launch_or_app_launched()

        pending = consented_client._event_store.get_pending_events(10)
        assert len(pending) == 1
        _, event_data = pending[0]
        assert event_data["event"] == "app_launched"

    def test_first_launch_deferred_without_consent(self, client, qsettings):
        """If analytics is disabled, first_launch flag stays unset; fires correctly once enabled."""
        client.disable()
        # Attempt first launch without consent
        client.track_first_launch_or_app_launched()
        assert client._event_store.count() == 0

        # The first_launch_sent flag should NOT be set
        assert qsettings.value("telemetry/first_launch_sent", False, type=bool) is False

        # Now enable consent
        client.enable()

        # First launch should now fire correctly
        client.track_first_launch_or_app_launched()
        pending = client._event_store.get_pending_events(10)
        assert len(pending) == 1
        _, event_data = pending[0]
        assert event_data["event"] == "first_launch"

    def test_subsequent_launches_fire_app_launched(self, consented_client, qsettings):
        """After first_launch is recorded, subsequent calls fire app_launched."""
        # Mark first launch as sent
        qsettings.setValue("telemetry/first_launch_sent", True)
        qsettings.sync()

        consented_client.track_first_launch_or_app_launched()
        pending = consented_client._event_store.get_pending_events(10)
        assert len(pending) == 1
        _, event_data = pending[0]
        assert event_data["event"] == "app_launched"


# ─── NON-BLOCKING / FAILURE ISOLATION TESTS ──────────────────────────────────

class TestFailureIsolation:
    """Tests ensuring analytics failures never affect the application."""

    def test_track_never_raises(self, client):
        """track() never raises an exception, even with broken internals."""
        # Break the event store by replacing it with a broken mock
        client._event_store = MagicMock()
        client._event_store.enqueue.side_effect = Exception("Disk full")

        # Should not raise
        client.enable()
        client.track("app_launched")  # No exception

    def test_flush_never_raises(self, client):
        """flush() never raises an exception."""
        client._event_store = MagicMock()
        client._event_store.get_pending_events.side_effect = Exception("DB corrupted")

        client.enable()
        client.flush()  # No exception

    def test_enable_never_raises(self, client):
        """enable() never raises."""
        client._qsettings = MagicMock()
        client._qsettings.setValue.side_effect = Exception("Settings locked")

        client.enable()  # No exception

    def test_disable_never_raises(self, client):
        """disable() never raises."""
        client._qsettings = MagicMock()
        client._qsettings.setValue.side_effect = Exception("Settings locked")
        client._event_store = MagicMock()
        client._event_store.clear.side_effect = Exception("DB locked")

        client.disable()  # No exception

    def test_track_first_launch_never_raises(self, client):
        """track_first_launch_or_app_launched() never raises."""
        client._qsettings = MagicMock()
        client._qsettings.value.side_effect = Exception("Settings broken")

        client.enable = MagicMock()
        client.is_enabled = MagicMock(return_value=True)
        client._qsettings.value = MagicMock(side_effect=[True, False])

        client.track_first_launch_or_app_launched()  # No exception

    def test_is_enabled_never_raises(self, client):
        """is_enabled() returns False on any internal error."""
        client._qsettings = MagicMock()
        client._qsettings.value.side_effect = Exception("Corrupted")

        assert client.is_enabled() is False


# ─── NO PII TESTS ─────────────────────────────────────────────────────────────

class TestNoPII:
    """Tests ensuring no personal or sensitive data is ever collected."""

    def test_no_pii_in_any_event(self, consented_client):
        """No excluded fields appear in any event.

        The only properties allowed in the envelope are the ones defined
        by the schema. Any property outside this set is considered a
        potential PII leak.
        """
        from Modules.telemetry import ALLOWED_EVENTS

        allowed_property_keys = {
            "distinct_id",
            "$process_person_profile",
            "app_version",
            "os_family",
            "telemetry_schema",
        }

        for event_name in ALLOWED_EVENTS:
            consented_client.track(event_name)

        pending = consented_client._event_store.get_pending_events(100)
        for event_id, event_data in pending:
            props = event_data.get("properties", {})
            unexpected_keys = set(props.keys()) - allowed_property_keys
            assert not unexpected_keys, (
                f"Unexpected properties {unexpected_keys} in event "
                f"'{event_data['event']}'"
            )

    def test_no_task_content_in_events(self, consented_client):
        """Task names and descriptions are never transmitted."""
        consented_client.track("task_created")
        consented_client.track("task_completed")

        pending = consented_client._event_store.get_pending_events(10)
        for _, event_data in pending:
            props_str = json.dumps(event_data)
            assert "NCERT" not in props_str
            assert "Homework" not in props_str
            assert "Project" not in props_str

    def test_no_cumulative_xp(self, consented_client):
        """Cumulative XP totals are never transmitted."""
        consented_client.track("xp_changed")

        pending = consented_client._event_store.get_pending_events(10)
        for _, event_data in pending:
            props = event_data["properties"]
            # Only common envelope properties
            assert "xp_total" not in props
            assert "total_xp" not in props

    def test_no_exact_duration(self, consented_client):
        """Exact session durations are never transmitted."""
        consented_client.track("session_completed")

        pending = consented_client._event_store.get_pending_events(10)
        for _, event_data in pending:
            props = event_data["properties"]
            assert "duration" not in props
            assert "seconds" not in props
            assert "minutes" not in props


# ─── EVENT STORE DIRECT TESTS ────────────────────────────────────────────────

class TestEventStore:
    """Direct tests for the EventStore SQLite queue."""

    def test_event_store_creates_database(self, tmp_path):
        from Modules.telemetry import EventStore

        db_path = tmp_path / "test_events.db"
        store = EventStore(db_path)
        assert db_path.exists()

    def test_enqueue_and_count(self, tmp_path):
        from Modules.telemetry import EventStore

        store = EventStore(tmp_path / "test_events.db")
        store.enqueue("id1", {"event": "test1"})
        store.enqueue("id2", {"event": "test2"})
        assert store.count() == 2

    def test_get_pending_events_ordered(self, tmp_path):
        from Modules.telemetry import EventStore

        store = EventStore(tmp_path / "test_events.db")
        store.enqueue("id1", {"event": "first"})
        store.enqueue("id2", {"event": "second"})

        pending = store.get_pending_events(10)
        assert len(pending) == 2
        assert pending[0][1]["event"] == "first"
        assert pending[1][1]["event"] == "second"

    def test_delete_events(self, tmp_path):
        from Modules.telemetry import EventStore

        store = EventStore(tmp_path / "test_events.db")
        store.enqueue("id1", {"event": "test1"})
        store.enqueue("id2", {"event": "test2"})
        store.enqueue("id3", {"event": "test3"})

        store.delete_events(["id1", "id3"])
        assert store.count() == 1

        pending = store.get_pending_events(10)
        assert pending[0][0] == "id2"

    def test_clear(self, tmp_path):
        from Modules.telemetry import EventStore

        store = EventStore(tmp_path / "test_events.db")
        store.enqueue("id1", {"event": "test1"})
        store.enqueue("id2", {"event": "test2"})
        store.clear()
        assert store.count() == 0


# ─── POSTHOG BATCH FORMAT TEST ───────────────────────────────────────────────

class TestPostHogBatchFormat:
    """Tests verifying the outgoing batch format matches PostHog's API spec."""

    def test_batch_event_format(self, consented_client):
        """Events in the batch have the correct PostHog structure."""
        consented_client.track("app_launched")

        pending = consented_client._event_store.get_pending_events(1)
        _, local_event = pending[0]

        # The format sent to PostHog /batch/ should have:
        # - "event": event name
        # - "uuid": event UUID (PostHog server-side dedup field)
        # - "properties": { "distinct_id": ..., ... }
        # - "timestamp": ISO 8601
        assert "event" in local_event
        assert "uuid" in local_event
        assert "event_id" not in local_event  # legacy key must not leak
        assert "properties" in local_event
        assert "timestamp" in local_event
        uuid.UUID(local_event["uuid"])  # must be a valid UUID
        assert "distinct_id" in local_event["properties"]
        assert "$process_person_profile" in local_event["properties"]

    def test_batch_payload_structure(self, consented_client):
        """The full batch payload matches PostHog's expected format."""
        consented_client.track("app_launched")

        mock_backend = MagicMock()
        mock_backend.send_batch.return_value = SendResult.SUCCESS
        consented_client._backend = mock_backend

        consented_client.flush()

        # Wait for worker thread
        import time
        time.sleep(0.1)

        # The batch argument passed to send_batch should be a list of event dicts
        batch = mock_backend.send_batch.call_args[0][0]
        assert isinstance(batch, list)
        assert len(batch) == 1

        event = batch[0]
        assert "event" in event
        assert "properties" in event
        assert "uuid" in event  # PostHog dedup field present on the wire
        assert "event_id" not in event
        assert "distinct_id" in event["properties"]
        assert event["properties"]["$process_person_profile"] is False


# ─── HTTP THREADING TEST ─────────────────────────────────────────────────────

class TestHTTPThreading:
    """Tests verifying that HTTP transmission doesn't block the UI thread."""

    def test_flush_uses_worker_thread(self, consented_client):
        """Verify that flush() uses a worker thread for HTTP transmission."""
        from Modules.telemetry import QT_AVAILABLE, FlushWorker
        
        consented_client.track("app_launched")

        mock_backend = MagicMock()
        mock_backend.send_batch.return_value = SendResult.SUCCESS
        consented_client._backend = mock_backend

        # Track if FlushWorker is instantiated
        original_init = FlushWorker.__init__
        worker_created = []

        def tracking_init(self, backend, events, event_uuids, parent=None):
            worker_created.append(True)
            original_init(self, backend, events, event_uuids, parent)
        
        FlushWorker.__init__ = tracking_init
        
        try:
            consented_client.flush()
            
            # If Qt is available, worker thread should be created
            if QT_AVAILABLE:
                assert len(worker_created) > 0, "FlushWorker should be created when Qt is available"
            
            # Wait for completion
            import time
            time.sleep(0.1)
            
            # Backend should have been called
            mock_backend.send_batch.assert_called()
            
        finally:
            FlushWorker.__init__ = original_init

    def test_http_timeout_does_not_block_ui(self, consented_client):
        """Verify that network timeout doesn't freeze the application."""
        import time
        from unittest.mock import patch
        
        consented_client.track("app_launched")
        
        # Simulate a slow network call (but with short timeout for test)
        def slow_send_batch(events):
            time.sleep(0.05)  # Simulate network delay
            return SendResult.SUCCESS
        
        mock_backend = MagicMock()
        mock_backend.send_batch.side_effect = slow_send_batch
        consented_client._backend = mock_backend
        
        # flush() should return immediately (non-blocking)
        start_time = time.time()
        consented_client.flush()
        flush_return_time = time.time() - start_time
        
        # flush() should return in < 0.02s (worker thread started but not blocking)
        # The actual HTTP call happens in the worker thread
        assert flush_return_time < 0.02, "flush() should return immediately without blocking"
        
        # Wait for worker thread to complete
        time.sleep(0.1)
        
        # Backend should have been called in the worker thread
        mock_backend.send_batch.assert_called()


# ─── SETTINGS PAGE ANALYTICS UI TESTS ────────────────────────────────────────

class TestSettingsPageAnalytics:
    """Tests for the SettingsPage analytics UI and consent toggle."""

    def test_settings_page_fresh_install_checked_by_default(self, qapp, database, tmp_path, monkeypatch):
        """A fresh installation loads with analytics checkbox checked and default True."""
        from Modules.settings_page import SettingsPage
        from PySide6.QtCore import QSettings

        settings_path = tmp_path / "settings_fresh.ini"
        qs = QSettings(str(settings_path), QSettings.IniFormat)
        qs.clear()
        qs.sync()

        monkeypatch.setattr("Modules.settings_page.QSettings", lambda *args, **kwargs: qs)

        page = SettingsPage(database)
        assert page.analytics_checkbox.isChecked() is True
        assert "is being shared" in page.analytics_status.text()
        assert page.app_settings.value("telemetry/consented", True, type=bool) is True

    def test_settings_page_existing_false_preserved(self, qapp, database, tmp_path, monkeypatch):
        """Existing False consent is preserved and checkbox loads unchecked."""
        from Modules.settings_page import SettingsPage
        from PySide6.QtCore import QSettings

        settings_path = tmp_path / "settings_false.ini"
        qs = QSettings(str(settings_path), QSettings.IniFormat)
        qs.setValue("telemetry/consented", False)
        qs.sync()

        monkeypatch.setattr("Modules.settings_page.QSettings", lambda *args, **kwargs: qs)

        page = SettingsPage(database)
        assert page.analytics_checkbox.isChecked() is False
        assert "not being shared" in page.analytics_status.text()
        assert qs.value("telemetry/consented", True, type=bool) is False

    def test_settings_page_existing_true_preserved(self, qapp, database, tmp_path, monkeypatch):
        """Existing True consent is preserved and checkbox loads checked."""
        from Modules.settings_page import SettingsPage
        from PySide6.QtCore import QSettings

        settings_path = tmp_path / "settings_true.ini"
        qs = QSettings(str(settings_path), QSettings.IniFormat)
        qs.setValue("telemetry/consented", True)
        qs.sync()

        monkeypatch.setattr("Modules.settings_page.QSettings", lambda *args, **kwargs: qs)

        page = SettingsPage(database)
        assert page.analytics_checkbox.isChecked() is True
        assert "is being shared" in page.analytics_status.text()
        assert qs.value("telemetry/consented", True, type=bool) is True

    def test_settings_page_toggling_persists_and_notifies_controller(self, qapp, database, tmp_path, monkeypatch):
        """User unchecking and checking updates QSettings and calls telemetry enable/disable."""
        from Modules.settings_page import SettingsPage
        from PySide6.QtCore import QSettings

        settings_path = tmp_path / "settings_toggle.ini"
        qs = QSettings(str(settings_path), QSettings.IniFormat)
        qs.clear()
        qs.sync()

        monkeypatch.setattr("Modules.settings_page.QSettings", lambda *args, **kwargs: qs)

        mock_telemetry = MagicMock()
        mock_controller = MagicMock()
        mock_controller.telemetry = mock_telemetry
        qapp._ascend_controller = mock_controller

        page = SettingsPage(database)

        # Uncheck analytics
        page.analytics_checkbox.setChecked(False)
        assert qs.value("telemetry/consented", True, type=bool) is False
        assert "not being shared" in page.analytics_status.text()
        mock_telemetry.disable.assert_called()

        # Re-check analytics
        page.analytics_checkbox.setChecked(True)
        assert qs.value("telemetry/consented", True, type=bool) is True
        assert "is being shared" in page.analytics_status.text()
        mock_telemetry.enable.assert_called()


# ─── PERMANENT HTTP FAILURE (4XX) TESTS ──────────────────────────────────────

class TestPermanentHttpFailure:
    """HTTP 4xx = permanent configuration/request failure; 5xx/429/network
    errors stay retryable. A rejected batch must never be retried every
    5 minutes forever. All paths remain non-blocking and failure-safe."""

    def _backend_with_key(self):
        from Modules.telemetry import AnalyticsBackend

        backend = AnalyticsBackend()
        backend._api_key = "phc_test_key"  # pretend a key is configured
        return backend

    @staticmethod
    def _http_error(code):
        from urllib.error import HTTPError

        return HTTPError(
            "https://us.i.posthog.com/batch/", code, f"HTTP {code}", {}, None
        )

    @staticmethod
    def _ok_response(status=200):
        response = MagicMock()
        response.status = status
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        return response

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 410])
    def test_4xx_is_permanent_and_stops_network_retries(self, code):
        """A 4xx disables the backend for the session; no further HTTP calls."""
        backend = self._backend_with_key()

        with patch(
            "Modules.telemetry.urlopen", side_effect=self._http_error(code)
        ) as mock_urlopen:
            result = backend.send_batch(
                [{"event": "app_launched", "properties": {"distinct_id": "x"}}]
            )
            assert result is SendResult.PERMANENT_FAILURE
            assert backend.transmission_disabled is True

            # Every subsequent attempt short-circuits without network access
            again = backend.send_batch([{"event": "app_launched"}])
            assert again is SendResult.PERMANENT_FAILURE
            assert mock_urlopen.call_count == 1

    @pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
    def test_429_and_5xx_are_retryable(self, code):
        """429 rate limiting and 5xx stay retryable; backend keeps trying."""
        backend = self._backend_with_key()

        with patch(
            "Modules.telemetry.urlopen", side_effect=self._http_error(code)
        ) as mock_urlopen:
            assert (
                backend.send_batch([{"event": "app_launched"}])
                is SendResult.RETRYABLE_FAILURE
            )
            assert backend.transmission_disabled is False

            # Retries are allowed for transient statuses
            assert (
                backend.send_batch([{"event": "app_launched"}])
                is SendResult.RETRYABLE_FAILURE
            )
            assert mock_urlopen.call_count == 2

    def test_network_error_is_retryable(self):
        from urllib.error import URLError

        backend = self._backend_with_key()
        with patch(
            "Modules.telemetry.urlopen", side_effect=URLError("connection refused")
        ):
            assert (
                backend.send_batch([{"event": "app_launched"}])
                is SendResult.RETRYABLE_FAILURE
            )
        assert backend.transmission_disabled is False

    def test_timeout_is_retryable(self):
        backend = self._backend_with_key()
        with patch("Modules.telemetry.urlopen", side_effect=TimeoutError("timed out")):
            assert (
                backend.send_batch([{"event": "app_launched"}])
                is SendResult.RETRYABLE_FAILURE
            )
        assert backend.transmission_disabled is False

    def test_unexpected_exception_is_retryable_and_never_raises(self):
        backend = self._backend_with_key()
        with patch(
            "Modules.telemetry.urlopen", side_effect=Exception("something weird")
        ):
            assert (
                backend.send_batch([{"event": "app_launched"}])
                is SendResult.RETRYABLE_FAILURE
            )
        assert backend.transmission_disabled is False

    def test_retryable_failure_can_recover_on_next_flush(self):
        """After a transient failure a later successful send returns SUCCESS."""
        backend = self._backend_with_key()
        with patch("Modules.telemetry.urlopen", side_effect=self._http_error(503)):
            assert (
                backend.send_batch([{"event": "app_launched"}])
                is SendResult.RETRYABLE_FAILURE
            )
        with patch(
            "Modules.telemetry.urlopen", return_value=self._ok_response(200)
        ):
            assert (
                backend.send_batch([{"event": "app_launched"}]) is SendResult.SUCCESS
            )
        assert backend.transmission_disabled is False

    def test_permanent_failure_stops_flush_but_keeps_queue(
        self, consented_client, monkeypatch
    ):
        """Client side: a 4xx keeps events queued but stops further sends."""
        monkeypatch.setattr("Modules.telemetry.QT_AVAILABLE", False)  # sync path

        consented_client.track("app_launched")

        mock_backend = MagicMock()
        mock_backend.send_batch.return_value = SendResult.PERMANENT_FAILURE
        consented_client._backend = mock_backend

        consented_client.flush()

        # Events kept (a future build with a corrected key can deliver them)
        assert consented_client._event_store.count() == 1
        assert consented_client._transmission_disabled is True

        # Subsequent flushes don't even ask the backend
        consented_client.flush()
        consented_client.flush()
        mock_backend.send_batch.assert_called_once()

    def test_reconsent_rearms_transmission(self, consented_client, monkeypatch):
        """Re-enabling analytics clears the permanent-failure latch."""
        monkeypatch.setattr("Modules.telemetry.QT_AVAILABLE", False)

        consented_client.track("app_launched")

        mock_backend = MagicMock()
        mock_backend.send_batch.return_value = SendResult.PERMANENT_FAILURE
        consented_client._backend = mock_backend

        consented_client.flush()
        assert consented_client._transmission_disabled is True

        consented_client.enable()
        assert consented_client._transmission_disabled is False
        mock_backend.reset_transmission_disabled.assert_called_once()

        mock_backend.send_batch.return_value = SendResult.SUCCESS
        consented_client.flush()
        assert consented_client._event_store.count() == 0


# ─── LEGACY SCHEMA MIGRATION TESTS ───────────────────────────────────────────

class TestEventStoreMigration:
    """Legacy `event_id` queue schemas must keep working after the `uuid`
    migration: no data loss, no crash, and old payloads gain the PostHog
    `uuid` field on the way out."""

    LEGACY_UUID = "11111111-2222-4333-8444-555555555555"

    def _create_legacy_db(self, db_path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE pending_events (
                event_id TEXT PRIMARY KEY,
                event_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        legacy_event = {
            "event": "app_launched",
            "event_id": self.LEGACY_UUID,
            "timestamp": "2026-08-01T10:00:00+00:00",
            "properties": {
                "distinct_id": "legacy-install",
                "$process_person_profile": False,
                "app_version": "1.3.0",
                "os_family": "windows",
                "telemetry_schema": 1,
            },
        }
        conn.execute(
            "INSERT INTO pending_events VALUES (?, ?, ?)",
            (self.LEGACY_UUID, json.dumps(legacy_event), "2026-08-01T10:00:00+00:00"),
        )
        conn.commit()
        conn.close()

    def test_legacy_schema_migrated_and_data_preserved(self, tmp_path):
        from Modules.telemetry import EventStore

        db_path = tmp_path / "telemetry" / "events.db"
        self._create_legacy_db(db_path)

        store = EventStore(db_path)  # triggers migration

        conn = sqlite3.connect(str(db_path))
        columns = {row[1] for row in conn.execute("PRAGMA table_info(pending_events)")}
        conn.close()
        assert "event_uuid" in columns
        assert "event_id" not in columns

        # Existing queued event survived the migration
        assert store.count() == 1
        pending = store.get_pending_events(10)
        assert pending[0][0] == self.LEGACY_UUID

        # New events enqueue normally against the migrated schema
        assert store.enqueue(str(uuid.uuid4()), {"event": "session_started"}) is True
        assert store.count() == 2

    def test_migration_is_idempotent(self, tmp_path):
        """Opening the store again after migration is a no-op."""
        from Modules.telemetry import EventStore

        db_path = tmp_path / "telemetry" / "events.db"
        self._create_legacy_db(db_path)

        EventStore(db_path)
        store = EventStore(db_path)  # second open: already migrated
        assert store.count() == 1

    def test_fresh_database_uses_new_schema(self, tmp_path):
        from Modules.telemetry import EventStore

        db_path = tmp_path / "telemetry" / "events.db"
        EventStore(db_path)

        conn = sqlite3.connect(str(db_path))
        columns = {row[1] for row in conn.execute("PRAGMA table_info(pending_events)")}
        conn.close()
        assert "event_uuid" in columns
        assert "event_id" not in columns

    def test_normalize_for_transmission(self):
        from Modules.telemetry import AnalyticsClient

        legacy = {"event": "app_launched", "event_id": "abc-123"}
        normalized = AnalyticsClient._normalize_for_transmission(legacy)
        assert normalized == {"event": "app_launched", "uuid": "abc-123"}

        current = {"event": "app_launched", "uuid": "abc-123"}
        assert AnalyticsClient._normalize_for_transmission(current) == current

    def test_legacy_payload_normalized_and_delivered_on_flush(
        self, qsettings, tmp_path, monkeypatch
    ):
        """End-to-end: an event queued by an old build is sent with `uuid`
        and removed from the queue after a successful flush."""
        from Modules.telemetry import AnalyticsClient

        monkeypatch.setattr("Modules.telemetry.QT_AVAILABLE", False)  # sync path

        db_path = tmp_path / "telemetry" / "events.db"
        self._create_legacy_db(db_path)

        qsettings.setValue("telemetry/consented", True)
        qsettings.sync()

        client = AnalyticsClient(qsettings, telemetry_db_path=db_path)
        mock_backend = MagicMock()
        mock_backend.send_batch.return_value = SendResult.SUCCESS
        client._backend = mock_backend

        client.flush()

        sent = mock_backend.send_batch.call_args[0][0]
        assert len(sent) == 1
        assert sent[0]["uuid"] == self.LEGACY_UUID  # renamed from event_id
        assert "event_id" not in sent[0]
        assert client._event_store.count() == 0
