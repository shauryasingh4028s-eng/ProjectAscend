"""Tests for Tiered Linear Level Curve Calculations, Boundaries, and Level History."""

import pytest
from Database.database import Database
from Modules.xp_manager import (
    XPManager,
    calculate_level_from_xp,
    get_level_progress,
    get_level_threshold,
)


class TestLevelSystemBoundaries:
    def test_level_calculations_and_thresholds(self):
        # Tier 1: Levels 1-10 (100 XP / level)
        assert calculate_level_from_xp(0) == 1
        assert calculate_level_from_xp(99) == 1
        assert calculate_level_from_xp(100) == 2
        assert calculate_level_from_xp(899) == 9

        # Tier 2: Levels 11-50 (250 XP / level)
        assert calculate_level_from_xp(900) == 10
        assert calculate_level_from_xp(901) == 10
        assert calculate_level_from_xp(1149) == 10
        assert calculate_level_from_xp(1150) == 11
        assert calculate_level_from_xp(4650) == 25
        assert calculate_level_from_xp(4651) == 25
        assert calculate_level_from_xp(10899) == 49
        assert calculate_level_from_xp(10900) == 50

        # Tier 3: Levels 51+ (500 XP / level)
        assert calculate_level_from_xp(10901) == 50
        assert calculate_level_from_xp(11399) == 50
        assert calculate_level_from_xp(11400) == 51
        assert calculate_level_from_xp(35900) == 100
        assert calculate_level_from_xp(35901) == 100

    def test_level_threshold_values(self):
        assert get_level_threshold(1) == 0
        assert get_level_threshold(2) == 100
        assert get_level_threshold(10) == 900
        assert get_level_threshold(11) == 1150
        assert get_level_threshold(25) == 4650
        assert get_level_threshold(50) == 10900
        assert get_level_threshold(51) == 11400
        assert get_level_threshold(100) == 35900

    def test_level_progress_tuple_math(self):
        # Level 1 (0 XP)
        lvl, into, for_lvl, rem = get_level_progress(0)
        assert (lvl, into, for_lvl, rem) == (1, 0, 100, 100)

        # Level 1 (99 XP)
        lvl, into, for_lvl, rem = get_level_progress(99)
        assert (lvl, into, for_lvl, rem) == (1, 99, 100, 1)

        # Level 10 (900 XP) -> Tier 2 transition
        lvl, into, for_lvl, rem = get_level_progress(900)
        assert (lvl, into, for_lvl, rem) == (10, 0, 250, 250)

        # Level 10 (901 XP)
        lvl, into, for_lvl, rem = get_level_progress(901)
        assert (lvl, into, for_lvl, rem) == (10, 1, 250, 249)

        # Level 25 (4650 XP)
        lvl, into, for_lvl, rem = get_level_progress(4650)
        assert (lvl, into, for_lvl, rem) == (25, 0, 250, 250)

        # Level 50 (10900 XP) -> Tier 3 transition
        lvl, into, for_lvl, rem = get_level_progress(10900)
        assert (lvl, into, for_lvl, rem) == (50, 0, 500, 500)

    def test_level_history_retroactive_population(self, tmp_path):
        db_path = tmp_path / "level_test.db"
        db = Database(str(db_path))

        # Manually record an XP event that puts user at Level 12 (1400 XP)
        db.cursor.execute("""
            INSERT INTO xp_events (activity_id, earned_date, amount, event_type)
            VALUES (999, '2026-01-01', 1400, 'activity_completion')
        """)
        db.connection.commit()

        # Sync and check level history
        db.sync_and_reconcile_xp_ledger()
        db.cursor.execute("SELECT level, xp_at_unlock FROM level_history ORDER BY level ASC")
        history = db.cursor.fetchall()

        # Levels 1 to 12 must be present retroactively
        unlocked_levels = [row[0] for row in history]
        assert unlocked_levels == list(range(1, 13))
        assert history[0] == (1, 0)
        assert history[9] == (10, 900)
        assert history[10] == (11, 1150)
        assert history[11] == (12, 1400)

        db.close()
