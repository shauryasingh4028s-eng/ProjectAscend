"""Real-data validation against a COPY of the checked-in legacy database.

The checked-in Database/ascend.db predates v1.1: it has a legacy `tasks`
table, no xp_awarded column and no v1.1 tables. It holds 26 real historical
activities. This test migrates a COPY and verifies the calibration layer
operates on the real records without changing a single value.

The original file is never opened for writing.
"""

import sqlite3

import pytest

from Database.database import SCHEMA_VERSION, Database
from Modules.calibration_service import (
    RECOMMENDATION_MIN_OBSERVATIONS,
    build_calibration_report,
)


class TestRealDataMigration:
    def test_real_history_migrates_untouched(self, real_data_database_path):
        source_rows = sqlite3.connect(real_data_database_path).execute(
            "SELECT id, date, activity_type, name, estimated_minutes, "
            "completed, actual_minutes FROM activities ORDER BY id"
        ).fetchall()

        db = Database(real_data_database_path)
        assert db.get_schema_version() == SCHEMA_VERSION

        migrated = db.get_activities()
        assert len(migrated) == len(source_rows)
        for source, migrated_activity in zip(source_rows, migrated):
            assert migrated_activity.id == source[0]
            assert migrated_activity.date == source[1]
            assert migrated_activity.activity_type == source[2]
            assert migrated_activity.name == source[3]
            assert migrated_activity.estimated_minutes == source[4]
            assert migrated_activity.completed == bool(source[5])
            assert migrated_activity.actual_minutes == source[6]
            # The original estimate is backfilled for legacy records.
            assert migrated_activity.original_estimate_minutes == source[4]

        # v1.1 settings survive the upgrade unchanged.
        assert db.get_setting("total_xp") == "540"
        assert db.get_setting("daily_goal") == "210"
        db.close()

    def test_calibration_operates_on_real_records(self, real_data_database_path):
        db = Database(real_data_database_path)
        records = db.get_calibration_records()
        report = build_calibration_report(records)
        db.close()

        # 26 real activities, all completed; one has no recorded actual
        # time and is therefore not a valid observation.
        assert len(records) == 26
        assert report.summary.sample_count == 25
        assert report.summary.pending_count == 0
        assert report.summary.excluded_count == 1

        # 25 observations is enough for a high-confidence report - a real
        # recommendation is produced from real history, never fabricated.
        assert report.summary.evidence_level == "high_confidence"
        assert report.summary.suggested_multiplier is not None
        assert report.summary.mean_relative_error is not None

        # Spot-check one real observation: id 7, estimate 70, actual 71.
        observation = next(
            o for o in report.observations if o.activity_id == 7
        )
        assert observation.estimated_minutes == 70
        assert observation.actual_minutes == 71
        assert observation.relative_error == pytest.approx(1 / 70)

        # Categories are derived from the real records only.
        categories = {c.activity_type: c for c in report.categories}
        assert "Online Class" in categories
        assert categories["Online Class"].sample_count >= RECOMMENDATION_MIN_OBSERVATIONS

    def test_real_records_unchanged_after_migration(self, real_data_database_path):
        before = sqlite3.connect(real_data_database_path).execute(
            "SELECT id, date, activity_type, name, estimated_minutes, "
            "completed, actual_minutes FROM activities ORDER BY id"
        ).fetchall()

        db = Database(real_data_database_path)
        db.close()

        after = sqlite3.connect(real_data_database_path).execute(
            "SELECT id, date, activity_type, name, estimated_minutes, "
            "completed, actual_minutes FROM activities ORDER BY id"
        ).fetchall()
        assert before == after
