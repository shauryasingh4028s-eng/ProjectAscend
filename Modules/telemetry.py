"""Anonymous product analytics for Project Ascend.

Privacy-first, consent-gated analytics that helps understand aggregate
product usage without collecting any personal data, task content, or
productivity details.

Key principles:
- ENABLED BY DEFAULT: Analytics is enabled by default for fresh installations and can be disabled at any time.
- MINIMAL: Only predefined events with empty per-event properties.
- NON-BLOCKING: Every operation wrapped in try/except. Never crashes or delays the app.
- LOCAL-FIRST: Events queue to local SQLite before transmission.
- FAIL-SAFE TRANSMISSION: Network errors, timeouts, HTTP 429 and 5xx responses are
  retried on the next flush; an HTTP 4xx response (invalid/revoked API key or a
  malformed request) permanently stops transmission for the rest of the session.
  PostHog deduplicates events server-side by each event's `uuid` field.
- NO PII: No names, emails, task content, school info, location, files, or device IDs.
"""

import json
import logging
import os
import platform
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from Modules.version import APP_VERSION  # Single authoritative application version

# Import Qt threading for non-blocking HTTP
try:
    from PySide6.QtCore import QThread, Signal as QtSignal
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    QThread = None

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
# PostHog Cloud (verified July 2026)
# Free tier: 1M events/month. No credit card required.
#
# The project API key for the Project Ascend analytics project is set below.
# The project API key is PUBLIC by design (like a Google Analytics tracking ID).
# It grants write-only access to one project's event stream.
# No privileged secret, admin token, or database password is embedded.
POSTHOG_API_KEY = "phc_qs78bn7PSeyND74kQyVTGDHStwHgft2QtaiSqHBzccMa"  # Project ingestion key (public, write-only by design)
POSTHOG_BATCH_URL = "https://us.i.posthog.com/batch/"
# ──────────────────────────────────────────────────────────────────────────────

# ─── CONSTANTS ────────────────────────────────────────────────────────────────
# APP_VERSION comes from Modules.version (single authoritative source above).
TELEMETRY_SCHEMA_VERSION = 1
MAX_QUEUE_SIZE = 500
FLUSH_BATCH_SIZE = 50
FLUSH_INTERVAL_MS = 300000  # 5 minutes

# Allowed event names - no others will be queued
ALLOWED_EVENTS = frozenset({
    "first_launch",
    "app_launched",
    "session_started",
    "session_completed",
    "task_created",
    "task_completed",
    "daily_goal_completed",
    "planner_used",
    "insights_viewed",
    "xp_changed",
    "app_version_updated",
})

# OS family detection (only "windows", "macos", "linux")
def _detect_os_family() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    elif system == "linux":
        return "linux"
    else:
        return "unknown"

OS_FAMILY = _detect_os_family()

logger = logging.getLogger(__name__)


# ─── TRANSMISSION RESULT ──────────────────────────────────────────────────────
class SendResult(Enum):
    """Outcome of a single batch transmission attempt.

    SUCCESS:            batch accepted (or a no-op: no key configured / empty batch).
    RETRYABLE_FAILURE:  transient problem — network error, timeout, HTTP 429 or 5xx.
                        Events stay queued and are retried on the next flush.
    PERMANENT_FAILURE:  HTTP 4xx (other than 429) — an invalid/revoked API key or a
                        malformed request. Retrying the same configuration cannot
                        succeed, so transmission stops for the rest of the session.
    """

    SUCCESS = "success"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"


# ─── INSTALLATION ID ──────────────────────────────────────────────────────────
class InstallationId:
    """Generates and persists a random UUID4 for this installation.

    The ID is stored in QSettings under "telemetry/installation_id".
    It is reset when the user opts out and opts back in.
    """

    def __init__(self, qsettings):
        self._qsettings = qsettings
        self._key = "telemetry/installation_id"

    def get(self) -> str:
        """Return the current installation ID, generating one if absent."""
        try:
            existing = self._qsettings.value(self._key, type=str)
            if existing and self._is_valid_uuid(existing):
                return existing

            new_id = str(uuid.uuid4())
            self._qsettings.setValue(self._key, new_id)
            self._qsettings.sync()
            return new_id
        except Exception as e:
            logger.debug(f"Failed to get/generate installation ID: {e}")
            return str(uuid.uuid4())

    def reset(self) -> str:
        """Generate a new installation ID (for re-consent)."""
        try:
            new_id = str(uuid.uuid4())
            self._qsettings.setValue(self._key, new_id)
            self._qsettings.sync()
            return new_id
        except Exception as e:
            logger.debug(f"Failed to reset installation ID: {e}")
            return str(uuid.uuid4())

    @staticmethod
    def _is_valid_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError):
            return False


# ─── EVENT STORE (LOCAL SQLITE QUEUE) ─────────────────────────────────────────
class EventStore:
    """Local SQLite queue for pending analytics events.

    Events are keyed by their event UUID — the same value that is sent to
    PostHog in each event's `uuid` field, where it enables server-side
    deduplication. The queue is bounded to MAX_QUEUE_SIZE events.

    Schema migration: builds before the `uuid` migration used a primary-key
    column named `event_id`. On first run with a current build the table is
    rebuilt in place (a rebuild instead of RENAME COLUMN works on every
    SQLite version), preserving every previously queued event, so restart
    persistence is unaffected by the upgrade.
    """

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Create the events table if needed and migrate legacy schemas."""
        try:
            conn = sqlite3.connect(str(self._db_path))
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pending_events (
                        event_uuid TEXT PRIMARY KEY,
                        event_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
                columns = {
                    row[1] for row in cursor.execute("PRAGMA table_info(pending_events)")
                }
                if "event_uuid" not in columns and "event_id" in columns:
                    # Legacy schema (event_id PRIMARY KEY): rebuild the table
                    # with the new column name, keeping all queued events.
                    # INSERT OR IGNORE makes a re-run after an interrupted
                    # migration safe.
                    cursor.execute("DROP TABLE IF EXISTS pending_events_new")
                    cursor.execute("""
                        CREATE TABLE pending_events_new (
                            event_uuid TEXT PRIMARY KEY,
                            event_json TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        )
                    """)
                    cursor.execute("""
                        INSERT OR IGNORE INTO pending_events_new (event_uuid, event_json, created_at)
                        SELECT event_id, event_json, created_at FROM pending_events
                    """)
                    cursor.execute("DROP TABLE pending_events")
                    cursor.execute("ALTER TABLE pending_events_new RENAME TO pending_events")
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"Failed to initialize event store: {e}")

    def enqueue(self, event_uuid: str, event_data: dict) -> bool:
        """Add an event to the queue. Returns True on success.

        Prevents duplicates by event_uuid (PRIMARY KEY constraint).
        """
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()

            # Check if event already exists (idempotency)
            cursor.execute("SELECT 1 FROM pending_events WHERE event_uuid = ?", (event_uuid,))
            if cursor.fetchone():
                conn.close()
                return False

            # Insert the event
            cursor.execute(
                "INSERT INTO pending_events (event_uuid, event_json, created_at) VALUES (?, ?, ?)",
                (event_uuid, json.dumps(event_data), datetime.now(timezone.utc).isoformat())
            )

            # Enforce queue size limit - delete oldest events
            cursor.execute(f"""
                DELETE FROM pending_events
                WHERE event_uuid NOT IN (
                    SELECT event_uuid FROM pending_events
                    ORDER BY created_at DESC
                    LIMIT {MAX_QUEUE_SIZE}
                )
            """)

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.debug(f"Failed to enqueue event: {e}")
            return False

    def get_pending_events(self, limit: int = FLUSH_BATCH_SIZE) -> list:
        """Return up to `limit` pending events as (event_uuid, event_data), oldest first."""
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT event_uuid, event_json FROM pending_events ORDER BY created_at ASC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            conn.close()
            return [(row[0], json.loads(row[1])) for row in rows]
        except Exception as e:
            logger.debug(f"Failed to get pending events: {e}")
            return []

    def delete_events(self, event_uuids: list):
        """Delete events by their UUIDs (after successful transmission)."""
        if not event_uuids:
            return
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(event_uuids))
            cursor.execute(
                f"DELETE FROM pending_events WHERE event_uuid IN ({placeholders})",
                event_uuids,
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to delete events: {e}")

    def clear(self):
        """Delete all pending events (used on opt-out)."""
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_events")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to clear event store: {e}")

    def count(self) -> int:
        """Return the number of pending events."""
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM pending_events")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logger.debug(f"Failed to count pending events: {e}")
            return 0


# ─── ANALYTICS BACKEND (HTTP TRANSMITTER) ─────────────────────────────────────
class AnalyticsBackend:
    """HTTP transmitter for the PostHog batch API.

    Sends events to POSTHOG_BATCH_URL with the project API key.
    When POSTHOG_API_KEY is empty, transmission is a no-op.

    Failure policy: network errors, timeouts, HTTP 429 (rate limiting) and
    HTTP 5xx are transient and return SendResult.RETRYABLE_FAILURE so events
    are retried on the next flush. Any other HTTP 4xx means the request
    itself can never succeed — typically an invalid or revoked API key — so
    the backend returns SendResult.PERMANENT_FAILURE and refuses further
    network calls for the rest of the session instead of retrying the same
    request every few minutes.
    """

    def __init__(self):
        self._api_key = POSTHOG_API_KEY
        self._batch_url = POSTHOG_BATCH_URL
        self._transmission_disabled = False

    @property
    def transmission_disabled(self) -> bool:
        """True after PostHog permanently rejected a batch (HTTP 4xx)."""
        return self._transmission_disabled

    def reset_transmission_disabled(self):
        """Re-allow transmission (used when analytics is re-consented)."""
        self._transmission_disabled = False

    def send_batch(self, events: list) -> SendResult:
        """Send a batch of events to PostHog. Returns the SendResult outcome.

        events: list of event dicts in the PostHog wire format (with `uuid`).

        Never raises: any unexpected error is logged at debug level and
        reported as a retryable failure.
        """
        if self._transmission_disabled:
            # A 4xx earlier this session means retrying cannot succeed.
            logger.debug("PostHog transmission disabled for this session (earlier 4xx)")
            return SendResult.PERMANENT_FAILURE

        if not self._api_key:
            # No API key configured - no-op
            logger.debug("PostHog API key not configured - skipping transmission")
            return SendResult.SUCCESS

        if not events:
            return SendResult.SUCCESS

        try:
            payload = {
                "api_key": self._api_key,
                "batch": events
            }

            data = json.dumps(payload).encode("utf-8")
            req = Request(
                self._batch_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urlopen(req, timeout=10) as response:
                if 200 <= response.status < 300:
                    return SendResult.SUCCESS
                return self._classify_http_status(response.status)
        except HTTPError as e:
            # Non-2xx responses surface as HTTPError (a URLError subclass, so
            # this except clause must come first).
            return self._classify_http_status(e.code)
        except (URLError, TimeoutError, OSError) as e:
            # Network unreachable, DNS failure, connection reset, timeout, ...
            logger.debug(f"PostHog network error (retryable): {e}")
            return SendResult.RETRYABLE_FAILURE
        except Exception as e:
            logger.debug(f"PostHog transmission failed (retryable): {e}")
            return SendResult.RETRYABLE_FAILURE

    def _classify_http_status(self, status: int) -> SendResult:
        """Map an HTTP status code to a transmission outcome."""
        if 400 <= status < 500 and status != 429:
            # Invalid/revoked API key (401/403) or a request PostHog refuses
            # to process (400/404, ...). Retrying the same configuration
            # cannot succeed.
            logger.debug(
                f"PostHog permanently rejected the batch (HTTP {status}) - "
                "disabling transmission for this session"
            )
            self._transmission_disabled = True
            return SendResult.PERMANENT_FAILURE
        # 5xx, 429 rate limiting, and anything unexpected: try again later.
        logger.debug(f"PostHog transient failure (HTTP {status}) - will retry on next flush")
        return SendResult.RETRYABLE_FAILURE


# ─── FLUSH WORKER THREAD (NON-BLOCKING HTTP) ─────────────────────────────────
class FlushWorker(QThread if QT_AVAILABLE else object):
    """Worker thread for non-blocking HTTP transmission.

    Prevents network I/O from blocking the UI thread. Emits the SendResult
    via flush_completed; connected slots run on the GUI thread (queued
    delivery), so queue bookkeeping never runs concurrently with track().
    """

    flush_completed = QtSignal(object) if QT_AVAILABLE else None  # carries a SendResult

    def __init__(self, backend: AnalyticsBackend, events: list, event_uuids: list, parent=None):
        if QT_AVAILABLE:
            super().__init__(parent)
        self._backend = backend
        self._events = events
        self._event_uuids = event_uuids
        self._result = SendResult.RETRYABLE_FAILURE

    def run(self):
        """Execute HTTP transmission in worker thread."""
        try:
            self._result = self._backend.send_batch(self._events)
        except Exception as e:
            logger.debug(f"Flush worker failed: {e}")
            self._result = SendResult.RETRYABLE_FAILURE
        finally:
            if QT_AVAILABLE and self.flush_completed:
                self.flush_completed.emit(self._result)

    @property
    def result(self) -> SendResult:
        return self._result

    @property
    def event_uuids(self) -> list:
        return self._event_uuids


# ─── ANALYTICS CLIENT (ORCHESTRATOR) ──────────────────────────────────────────
class AnalyticsClient:
    """Main analytics orchestrator.

    Handles consent, event validation, queueing, and transmission scheduling.
    All public methods are non-blocking and wrapped in try/except.
    """

    def __init__(self, qsettings, telemetry_db_path: Optional[Path] = None):
        self._qsettings = qsettings
        self._consent_key = "telemetry/consented"
        self._first_launch_key = "telemetry/first_launch_sent"

        # Initialize components
        self._installation_id = InstallationId(qsettings)

        if telemetry_db_path is None:
            # Default path: %LOCALAPPDATA%\ProjectAscend\telemetry\events.db
            local_app_data = Path(os.getenv("LOCALAPPDATA", Path.home()))
            telemetry_db_path = local_app_data / "ProjectAscend" / "telemetry" / "events.db"

        self._event_store = EventStore(telemetry_db_path)
        self._backend = AnalyticsBackend()

        # Flush scheduler (QTimer) - initialized lazily to avoid Qt dependency in tests
        self._flush_timer = None

        # Set when PostHog permanently rejects a batch (HTTP 4xx) this session.
        # flush() early-returns while set; cleared on restart and on re-consent.
        self._transmission_disabled = False

        # Keep references to worker threads to prevent garbage collection
        self._active_workers = []

    def is_enabled(self) -> bool:
        """Return True if analytics is enabled (enabled by default)."""
        try:
            return self._qsettings.value(self._consent_key, True, type=bool)
        except Exception as e:
            logger.debug(f"Failed to check consent status: {e}")
            return False

    def enable(self):
        """Enable analytics (user opted in)."""
        try:
            self._qsettings.setValue(self._consent_key, True)
            self._qsettings.sync()
            # Reset installation ID for privacy (unlink old and new data)
            self._installation_id.reset()
            # Re-consent re-arms transmission after any permanent (4xx) failure
            self._transmission_disabled = False
            self._backend.reset_transmission_disabled()
        except Exception as e:
            logger.debug(f"Failed to enable analytics: {e}")

    def disable(self):
        """Disable analytics (user opted out). Purges the local queue."""
        try:
            self._qsettings.setValue(self._consent_key, False)
            self._qsettings.sync()
            self._event_store.clear()
        except Exception as e:
            logger.debug(f"Failed to disable analytics: {e}")

    def track(self, event_name: str):
        """Queue an event if consent is granted.

        This is the main entry point for all analytics events.
        Non-blocking: returns immediately, writes to local SQLite.
        """
        try:
            # Check consent
            if not self.is_enabled():
                return

            # Validate event name
            if event_name not in ALLOWED_EVENTS:
                logger.debug(f"Unknown event name: {event_name}")
                return

            # Build event envelope
            event_uuid = str(uuid.uuid4())
            event_data = self._build_event(event_name, event_uuid)

            # Enqueue to local store
            self._event_store.enqueue(event_uuid, event_data)

        except Exception as e:
            logger.debug(f"Failed to track event: {e}")

    def track_first_launch_or_app_launched(self):
        """Track first_launch or app_launched based on local state.

        Called once per app startup. Fires first_launch only once per installation.
        """
        try:
            if not self.is_enabled():
                return

            first_launch_sent = self._qsettings.value(self._first_launch_key, False, type=bool)

            if not first_launch_sent:
                # First launch after consent
                self.track("first_launch")
                self._qsettings.setValue(self._first_launch_key, True)
                self._qsettings.sync()
            else:
                # Subsequent launch
                self.track("app_launched")

        except Exception as e:
            logger.debug(f"Failed to track launch: {e}")

    def _build_event(self, event_name: str, event_uuid: str) -> dict:
        """Build the event envelope with common properties."""
        return {
            "event": event_name,
            # PostHog deduplicates events by their top-level `uuid` field.
            # The same UUID keys the local queue, so retried deliveries are
            # dropped server-side instead of counted twice.
            "uuid": event_uuid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "properties": {
                "distinct_id": self._installation_id.get(),
                "$process_person_profile": False,
                "app_version": APP_VERSION,
                "os_family": OS_FAMILY,
                "telemetry_schema": TELEMETRY_SCHEMA_VERSION,
            }
        }

    @staticmethod
    def _normalize_for_transmission(event_data: dict) -> dict:
        """Return the event in the current PostHog wire format.

        Events queued by builds older than the `uuid` migration stored their
        event UUID under a legacy `event_id` key inside the JSON payload;
        rename it on the way out so migrated events also get PostHog's
        server-side deduplication.
        """
        if "uuid" not in event_data and "event_id" in event_data:
            event_data = dict(event_data)
            event_data["uuid"] = event_data.pop("event_id")
        return event_data

    def flush(self):
        """Attempt to send pending events to PostHog.

        Called periodically by QTimer and on app shutdown.
        Non-blocking: spawns a worker thread for HTTP transmission.
        """
        try:
            if not self.is_enabled():
                return

            if self._transmission_disabled:
                # PostHog permanently rejected a batch (HTTP 4xx) earlier this
                # session. Retrying the same configuration cannot succeed, so
                # don't keep hammering the API every flush interval.
                return

            # Get pending events
            pending = self._event_store.get_pending_events(FLUSH_BATCH_SIZE)
            if not pending:
                return

            # Extract event UUIDs and normalize payloads to the wire format
            events_to_send = [
                self._normalize_for_transmission(event_data)
                for _, event_data in pending
            ]
            event_uuids = [event_uuid for event_uuid, _ in pending]

            # Use worker thread for non-blocking HTTP
            if QT_AVAILABLE and QThread is not None:
                worker = FlushWorker(self._backend, events_to_send, event_uuids)

                # Clean up finished workers
                self._active_workers = [w for w in self._active_workers if w.isRunning()]

                # Store reference to prevent garbage collection
                self._active_workers.append(worker)

                worker.flush_completed.connect(
                    lambda result, ids=event_uuids: self._on_flush_complete(result, ids)
                )
                worker.flush_completed.connect(
                    lambda result, w=worker: self._cleanup_worker(w)
                )
                worker.start()
            else:
                # Fallback: synchronous (for tests or when Qt unavailable)
                result = self._backend.send_batch(events_to_send)
                self._on_flush_complete(result, event_uuids)

        except Exception as e:
            logger.debug(f"Failed to flush events: {e}")

    def _cleanup_worker(self, worker):
        """Remove worker from active list after completion."""
        try:
            if worker in self._active_workers:
                self._active_workers.remove(worker)
        except Exception as e:
            logger.debug(f"Failed to cleanup worker: {e}")

    def _on_flush_complete(self, result, event_uuids: list):
        """Handle flush completion (runs on the GUI thread via queued signal)."""
        try:
            if result is SendResult.SUCCESS:
                # Delete sent events
                self._event_store.delete_events(event_uuids)
            elif result is SendResult.PERMANENT_FAILURE:
                # The current configuration can never deliver these events.
                # Keep the queue intact — a future build with a corrected
                # API key can still deliver it — but stop transmitting for
                # the rest of this session.
                self._transmission_disabled = True
            # RETRYABLE_FAILURE: events stay queued and are retried next flush.
        except Exception as e:
            logger.debug(f"Failed to handle flush completion: {e}")

    def start_flush_timer(self, parent=None):
        """Start the periodic flush timer (requires Qt).

        Call this from AppController after AnalyticsClient is created.
        """
        try:
            from PySide6.QtCore import QTimer
            self._flush_timer = QTimer(parent)
            self._flush_timer.timeout.connect(self.flush)
            self._flush_timer.start(FLUSH_INTERVAL_MS)
        except Exception as e:
            logger.debug(f"Failed to start flush timer: {e}")

    def stop_flush_timer(self):
        """Stop the periodic flush timer."""
        try:
            if self._flush_timer:
                self._flush_timer.stop()
        except Exception as e:
            logger.debug(f"Failed to stop flush timer: {e}")
