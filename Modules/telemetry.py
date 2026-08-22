"""Anonymous product analytics for Project Ascend.

Privacy-first, consent-gated analytics that helps understand aggregate
product usage without collecting any personal data, task content, or
productivity details.

Key principles:
- ENABLED BY DEFAULT: Analytics is enabled by default for fresh installations and can be disabled at any time.
- MINIMAL: Only predefined events with empty per-event properties.
- NON-BLOCKING: Every operation wrapped in try/except. Never crashes or delays the app.
- LOCAL-FIRST: Events queue to local SQLite before transmission.
- NO PII: No names, emails, task content, school info, location, files, or device IDs.
"""

import json
import logging
import os
import platform
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
# CONFIGURE: Create a PostHog project and fill in POSTHOG_API_KEY.
# The project API key is PUBLIC by design (like a Google Analytics tracking ID).
# It grants write-only access to one project's event stream.
# No privileged secret, admin token, or database password is embedded.
POSTHOG_API_KEY = ""  # ← Fill in from PostHog project settings
POSTHOG_BATCH_URL = "https://us.i.posthog.com/batch/"
# ──────────────────────────────────────────────────────────────────────────────

# ─── CONSTANTS ────────────────────────────────────────────────────────────────
APP_VERSION = "1.4.0"
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

    Events are stored here before being transmitted to PostHog.
    The queue is bounded to MAX_QUEUE_SIZE events.
    """

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Create the events table if it doesn't exist."""
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_events (
                    event_id TEXT PRIMARY KEY,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to initialize event store: {e}")

    def enqueue(self, event_id: str, event_data: dict) -> bool:
        """Add an event to the queue. Returns True on success.

        Prevents duplicates by event_id (PRIMARY KEY constraint).
        """
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()

            # Check if event already exists (idempotency)
            cursor.execute("SELECT 1 FROM pending_events WHERE event_id = ?", (event_id,))
            if cursor.fetchone():
                conn.close()
                return False

            # Insert the event
            cursor.execute(
                "INSERT INTO pending_events (event_id, event_json, created_at) VALUES (?, ?, ?)",
                (event_id, json.dumps(event_data), datetime.now(timezone.utc).isoformat())
            )

            # Enforce queue size limit - delete oldest events
            cursor.execute(f"""
                DELETE FROM pending_events
                WHERE event_id NOT IN (
                    SELECT event_id FROM pending_events
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
        """Return up to `limit` pending events, oldest first."""
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT event_id, event_json FROM pending_events ORDER BY created_at ASC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            conn.close()
            return [(row[0], json.loads(row[1])) for row in rows]
        except Exception as e:
            logger.debug(f"Failed to get pending events: {e}")
            return []

    def delete_events(self, event_ids: list):
        """Delete events by their IDs (after successful transmission)."""
        if not event_ids:
            return
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(event_ids))
            cursor.execute(f"DELETE FROM pending_events WHERE event_id IN ({placeholders})", event_ids)
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
    """HTTP transmitter for PostHog batch API.

    Sends events to POSTHOG_BATCH_URL with the project API key.
    When POSTHOG_API_KEY is empty, transmission is a no-op.
    """

    def __init__(self):
        self._api_key = POSTHOG_API_KEY
        self._batch_url = POSTHOG_BATCH_URL

    def send_batch(self, events: list) -> bool:
        """Send a batch of events to PostHog. Returns True on success.

        events: list of event dicts (without event_id wrapper)
        """
        if not self._api_key:
            # No API key configured - no-op
            logger.debug("PostHog API key not configured - skipping transmission")
            return True

        if not events:
            return True

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
                if response.status == 200:
                    return True
                else:
                    logger.debug(f"PostHog returned status {response.status}")
                    return False
        except (URLError, HTTPError) as e:
            logger.debug(f"PostHog HTTP error: {e}")
            return False
        except Exception as e:
            logger.debug(f"PostHog transmission failed: {e}")
            return False


# ─── FLUSH WORKER THREAD (NON-BLOCKING HTTP) ─────────────────────────────────
class FlushWorker(QThread if QT_AVAILABLE else object):
    """Worker thread for non-blocking HTTP transmission.

    Prevents network I/O from blocking the UI thread.
    """

    flush_completed = QtSignal(bool) if QT_AVAILABLE else None

    def __init__(self, backend: AnalyticsBackend, events: list, event_ids: list, parent=None):
        if QT_AVAILABLE:
            super().__init__(parent)
        self._backend = backend
        self._events = events
        self._event_ids = event_ids
        self._success = False

    def run(self):
        """Execute HTTP transmission in worker thread."""
        try:
            self._success = self._backend.send_batch(self._events)
        except Exception as e:
            logger.debug(f"Flush worker failed: {e}")
            self._success = False
        finally:
            if QT_AVAILABLE and self.flush_completed:
                self.flush_completed.emit(self._success)

    @property
    def success(self) -> bool:
        return self._success

    @property
    def event_ids(self) -> list:
        return self._event_ids


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
            event_id = str(uuid.uuid4())
            event_data = self._build_event(event_name, event_id)

            # Enqueue to local store
            self._event_store.enqueue(event_id, event_data)

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

    def _build_event(self, event_name: str, event_id: str) -> dict:
        """Build the event envelope with common properties."""
        return {
            "event": event_name,
            "event_id": event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "properties": {
                "distinct_id": self._installation_id.get(),
                "$process_person_profile": False,
                "app_version": APP_VERSION,
                "os_family": OS_FAMILY,
                "telemetry_schema": TELEMETRY_SCHEMA_VERSION,
            }
        }

    def flush(self):
        """Attempt to send pending events to PostHog.

        Called periodically by QTimer and on app shutdown.
        Non-blocking: spawns a worker thread for HTTP transmission.
        """
        try:
            if not self.is_enabled():
                return

            # Get pending events
            pending = self._event_store.get_pending_events(FLUSH_BATCH_SIZE)
            if not pending:
                return

            # Extract event data and IDs
            events_to_send = [event_data for event_id, event_data in pending]
            event_ids = [event_id for event_id, _ in pending]

            # Use worker thread for non-blocking HTTP
            if QT_AVAILABLE and QThread is not None:
                worker = FlushWorker(self._backend, events_to_send, event_ids)
                
                # Clean up finished workers
                self._active_workers = [w for w in self._active_workers if w.isRunning()]
                
                # Store reference to prevent garbage collection
                self._active_workers.append(worker)
                
                worker.flush_completed.connect(
                    lambda success, ids=event_ids: self._on_flush_complete(success, ids)
                )
                worker.flush_completed.connect(
                    lambda success, w=worker: self._cleanup_worker(w)
                )
                worker.start()
            else:
                # Fallback: synchronous (for tests or when Qt unavailable)
                success = self._backend.send_batch(events_to_send)
                self._on_flush_complete(success, event_ids)

        except Exception as e:
            logger.debug(f"Failed to flush events: {e}")

    def _cleanup_worker(self, worker):
        """Remove worker from active list after completion."""
        try:
            if worker in self._active_workers:
                self._active_workers.remove(worker)
        except Exception as e:
            logger.debug(f"Failed to cleanup worker: {e}")

    def _on_flush_complete(self, success: bool, event_ids: list):
        """Handle flush completion from worker thread."""
        try:
            if success:
                # Delete sent events
                self._event_store.delete_events(event_ids)
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
