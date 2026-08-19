"""Project Ascend v1.5 gamification: real data, persistence and UI safety."""

from datetime import date, timedelta
import hashlib
from pathlib import Path

import pytest

from Database.database import SCHEMA_VERSION, Database
from Modules.achievement_manager import AchievementManager
from Modules.activity import Activity
from Modules.character_manager import CharacterManager
from Modules.gamification_config import (
    ACHIEVEMENTS,
    CHARACTERS,
    XP_PER_LEVEL,
    evolution_stage_for_level,
    level_for_xp,
    rank_for_level,
)
from Modules.milestone_manager import MilestoneManager
from Modules.progression_service import ProgressionService
from Modules.streak_manager import StreakManager
from Modules.xp_manager import XPManager


def build_progression(database):
    streak = StreakManager(database)
    xp = XPManager(database)
    achievements = AchievementManager(database, streak, xp)
    milestones = MilestoneManager(database, streak, xp)
    characters = CharacterManager(database)
    service = ProgressionService(
        database,
        xp,
        streak,
        achievements,
        milestones,
        characters,
    )
    return service, xp, streak, achievements, milestones, characters


def add_completed(database, activity_date, name="Completed", minutes=30):
    database.add_activity(
        Activity(
            id=None,
            date=activity_date,
            activity_type="Coding",
            name=name,
            estimated_minutes=minutes,
        )
    )
    activity = database.get_activities_for_date(activity_date)[-1]
    activity.completed = True
    activity.actual_minutes = minutes
    database.update_activity(activity)
    return activity


class TestXPAndLevels:
    def test_v14_level_curve_is_preserved_and_rank_is_configured(self):
        assert XP_PER_LEVEL == 100
        assert level_for_xp(0) == 1
        assert level_for_xp(99) == 1
        assert level_for_xp(100) == 2
        assert level_for_xp(4820) == 49
        assert rank_for_level(1).name
        assert rank_for_level(50).minimum_level == 50

    def test_activity_xp_is_legitimate_keyed_and_duplicate_safe(self, database):
        activity = add_completed(database, date.today().isoformat())
        xp = XPManager(database)

        first = xp.award_activity_completion_result(activity.id)
        duplicate = xp.award_activity_completion_result(activity.id)

        assert first.awarded is True
        assert first.amount == 10
        assert first.total_xp == 10
        assert duplicate.awarded is False
        assert duplicate.total_xp == 10
        events = database.get_xp_events()
        assert len(events) == 1
        assert events[0]["event_key"] == (
            f"activity:{activity.id}:activity_completion"
        )

    def test_daily_goal_requires_real_goal_data_and_is_awarded_once(self, database):
        today = date.today().isoformat()
        database.set_daily_goal(30)
        activity = add_completed(database, today, minutes=29)
        service, xp, *_rest = build_progression(database)

        below_goal = service.process_activity_completion(activity.id, today)
        assert below_goal.activity_xp_awarded is True
        assert below_goal.daily_goal_xp_awarded is False
        assert xp.get_total_xp() == 10

        activity.actual_minutes = 30
        database.update_activity(activity)
        reached = service.process_activity_completion(activity.id, today)
        duplicate = service.process_activity_completion(activity.id, today)

        assert reached.activity_xp_awarded is False
        assert reached.daily_goal_xp_awarded is True
        assert reached.xp_earned == 50
        assert duplicate.xp_earned == 0
        assert xp.get_total_xp() == 60
        assert [event["event_type"] for event in database.get_xp_events()] == [
            "activity_completion",
            "daily_goal",
        ]

    def test_progression_reports_level_up_without_resetting_total(self, database):
        today = date.today().isoformat()
        database.set_setting("total_xp", 90)
        activity = add_completed(database, today)
        service, xp, *_rest = build_progression(database)

        update = service.process_activity_completion(activity.id, today)

        assert update.level_before == 1
        assert update.level_after == 2
        assert update.leveled_up is True
        assert update.xp_after == 100
        assert xp.get_total_xp() == 100

    def test_xp_and_event_guards_survive_restart(self, tmp_path):
        path = tmp_path / "gamification_restart.db"
        today = date.today().isoformat()
        first = Database(path)
        activity = add_completed(first, today)
        first_xp = XPManager(first)
        assert first_xp.award_activity_completion_result(activity.id).awarded
        first.close()

        second = Database(path)
        second_xp = XPManager(second)
        result = second_xp.award_activity_completion_result(activity.id)
        assert result.awarded is False
        assert result.total_xp == 10
        assert len(second.get_xp_events()) == 1
        second.close()


class TestAchievementsAndMilestones:
    def test_catalogue_is_structured_meaningful_and_stable(self):
        assert 15 <= len(ACHIEVEMENTS) <= 25
        identifiers = {achievement.identifier for achievement in ACHIEVEMENTS}
        assert len(identifiers) == len(ACHIEVEMENTS)
        assert {achievement.category for achievement in ACHIEVEMENTS} == {
            "Firsts",
            "Milestones",
            "Mastery",
        }
        assert all(achievement.threshold > 0 for achievement in ACHIEVEMENTS)

    def test_real_firsts_unlock_once_and_persist(self, tmp_path):
        path = tmp_path / "achievement_restart.db"
        today = date.today().isoformat()
        first = Database(path)
        activity = add_completed(first, today, minutes=30)
        first.record_focus_session(
            activity.id,
            f"{today}T09:00:00",
            f"{today}T09:30:00",
            30,
            actual_seconds=1800,
        )
        service, *_managers = build_progression(first)

        update = service.process_activity_completion(activity.id, today)
        identifiers = {item.identifier for item in update.achievements}
        assert "first_activity" in identifiers
        assert "first_focus" in identifiers
        assert service.snapshot().achievements[0].unlocked is True
        assert service.process_activity_completion(activity.id, today).achievements == ()
        timestamps = first.get_achievement_unlocks()
        assert timestamps["first_activity"].endswith("+00:00")
        first.close()

        second = Database(path)
        second_service, *_managers = build_progression(second)
        states = {
            state.definition.identifier: state
            for state in second_service.snapshot().achievements
        }
        assert states["first_activity"].unlocked is True
        assert states["first_focus"].unlocked is True
        second.close()

    def test_empty_user_has_no_fabricated_unlocks(self, database):
        service, *_managers = build_progression(database)
        snapshot = service.snapshot()

        assert snapshot.metrics.total_xp == 0
        assert snapshot.metrics.focus_minutes == 0
        assert snapshot.metrics.completed_activities == 0
        assert not any(state.unlocked for state in snapshot.achievements)
        assert not database.get_achievement_unlocks()

    def test_milestone_tier_is_derived_then_persisted(self, database):
        today = date.today().isoformat()
        for index in range(10):
            add_completed(database, today, name=f"Task {index}", minutes=1)
        service, *_managers = build_progression(database)

        snapshot = service.snapshot()
        completion = next(
            state for state in snapshot.milestones
            if state.track.identifier == "completion"
        )
        assert completion.completed_tiers == 1
        assert completion.next_threshold == 50
        assert "completion:tier_1" in database.get_milestone_unlocks()

        # Earned milestone state remains even if an activity is later removed.
        database.delete_activity(database.get_activities()[0].id)
        completion_after = next(
            state for state in service.snapshot().milestones
            if state.track.identifier == "completion"
        )
        assert completion_after.completed_tiers == 1


class TestStreaksAndCharacters:
    def test_goal_streak_and_best_survive_a_missed_day_and_restart(self, tmp_path):
        path = tmp_path / "streak_restart.db"
        database = Database(path)
        today = date.today()
        rows = [
            ((today - timedelta(days=3)).isoformat(), 1),
            ((today - timedelta(days=2)).isoformat(), 1),
            ((today - timedelta(days=1)).isoformat(), 1),
            (today.isoformat(), 0),
        ]
        for day, completed in rows:
            database.cursor.execute(
                "INSERT OR REPLACE INTO daily_history "
                "(date, study_minutes, completed_activities, total_activities, goal_completed) "
                "VALUES (?, ?, ?, ?, ?)",
                (day, 30 if completed else 10, 1, 1, completed),
            )
        database.connection.commit()
        streak = StreakManager(database)

        assert streak.get_current_streak() == 3
        assert streak.get_longest_streak() == 3
        database.cursor.execute("DELETE FROM daily_history")
        database.connection.commit()
        assert streak.get_longest_streak() == 3
        database.close()

        restarted = Database(path)
        assert StreakManager(restarted).get_longest_streak() == 3
        restarted.close()

    def test_default_selection_and_every_character_are_available(self, tmp_path):
        path = tmp_path / "character_restart.db"
        first = Database(path)
        manager = CharacterManager(first)
        assert manager.get_selected().identifier == CHARACTERS[0].identifier
        assert len(CHARACTERS) == 8
        assert manager.select(CHARACTERS[-1].identifier) is True
        first.set_setting("total_xp", 900)
        first.close()

        second = Database(path)
        assert CharacterManager(second).get_selected().identifier == (
            CHARACTERS[-1].identifier
        )
        service, *_managers = build_progression(second)
        assert service.snapshot().evolution_stage.identifier == "stage_3"
        second.close()

    def test_character_evolution_is_gradual_and_level_derived(self):
        assert evolution_stage_for_level(1).identifier == "stage_1"
        assert evolution_stage_for_level(5).identifier == "stage_2"
        assert evolution_stage_for_level(10).identifier == "stage_3"
        assert evolution_stage_for_level(20).identifier == "stage_4"
        assert evolution_stage_for_level(35).identifier == "stage_5"

    def test_every_character_has_five_distinct_bundled_sprite_stages(self):
        asset_root = Path(__file__).resolve().parents[1] / "Assets" / "characters"
        for character in CHARACTERS:
            hashes = []
            for stage in range(1, 6):
                path = asset_root / character.identifier / f"stage_{stage}.png"
                assert path.exists()
                assert path.stat().st_size > 20_000
                hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
            assert len(set(hashes)) == 5


class TestGamificationUI:
    def test_player_progress_renders_empty_and_populated_in_both_themes(
        self,
        database,
        qapp,
    ):
        from Modules.player_progress import PlayerProgressPage
        from UI.theme.design_system import ThemeManager

        service, _xp, _streak, _achievements, _milestones, characters = (
            build_progression(database)
        )
        page = PlayerProgressPage(service, characters)
        assert page.level_title.text() == "Level 1"
        assert page.rank_label.text() == "Starting Out"
        assert page.stat_cards["focus_time"].value_label.text() == "0m"
        assert page.character_sprite.character_id == CHARACTERS[0].identifier
        assert len(page.achievement_cards) == 4
        assert page.featured_achievement_ids == (
            "first_activity", "first_focus", "first_daily_goal", "focus_10_hours"
        )
        assert not hasattr(page, "rank_cards")
        assert set(page.milestone_rows) == {
            "focus", "completion", "consistency", "goal_days", "progression"
        }
        page.resize(900, 700)
        page.show()
        qapp.processEvents()
        assert page.compact_layout is True
        assert page.milestones_grid.getItemPosition(3)[0] == 1
        page.resize(1200, 800)
        qapp.processEvents()
        assert page.compact_layout is False

        activity = add_completed(database, date.today().isoformat(), minutes=75)
        service.process_activity_completion(activity.id, activity.date)
        page.refresh()
        assert page.stat_cards["focus_time"].value_label.text() == "1h 15m"
        assert page.stat_cards["completed_activities"].value_label.text() == "1"

        for theme in ("light", "dark"):
            ThemeManager.set_theme(theme)
            page.setStyleSheet(ThemeManager.app_stylesheet())
            page.refresh()
            page.show()
            qapp.processEvents()
            assert not page.character_buttons[CHARACTERS[0].identifier].icon().isNull()

        # Character cards use the real bundled stage and selection persists.
        page.character_buttons[CHARACTERS[1].identifier].click()
        assert characters.get_selected_id() == CHARACTERS[1].identifier
        assert page.character_sprite.character_id == CHARACTERS[1].identifier

        # The overview remains curated while the secondary catalogue exposes all.
        page.view_all_achievements_button.click()
        qapp.processEvents()
        assert page.achievements_dialog is not None
        assert page.achievements_dialog.isVisible()
        assert len(page.achievements_dialog.cards) == len(ACHIEVEMENTS)
        page.achievements_dialog.close()
        qapp.processEvents()
        page.close()

    def test_celebration_overlay_rejects_duplicate_events(self, qapp):
        from UI.components.celebrations import Celebration, CelebrationOverlay
        from PySide6.QtWidgets import QWidget

        parent = QWidget()
        overlay = CelebrationOverlay(parent)
        event = Celebration("achievement:first", "Achievement", "Real work.")
        assert overlay.enqueue(event) is True
        assert overlay.enqueue(event) is False
        assert overlay.played_events == ["achievement:first"]
        overlay.finish_immediately()
        parent.close()

    def test_daily_goal_flow_celebrates_once_and_not_after_restart(
        self,
        tmp_path,
        monkeypatch,
        qapp,
    ):
        from Modules.app_controller import AppController

        appdata = tmp_path / "appdata"
        monkeypatch.setenv("LOCALAPPDATA", str(appdata))
        today = date.today().isoformat()

        first = AppController()
        first.database.set_daily_goal(30)
        first.database.add_activity(
            Activity(None, today, "Study", "Daily goal", 30)
        )
        activity = first.database.get_activities_for_date(today)[0]
        first.show_dashboard()
        first.dashboard.session_engine.start(activity)
        first.dashboard.session_engine.elapsed_seconds = 1800
        first.dashboard.session_engine.complete()
        qapp.processEvents()

        assert first.xp_manager.get_total_xp() == 60
        assert first.shell.celebration_overlay.played_events[0] == (
            f"daily-goal:{today}"
        )
        first.shell.celebration_overlay.finish_immediately()
        first.close_database()
        first.shell.close()

        second = AppController()
        duplicate = second.progression_service.process_activity_completion(
            activity.id,
            today,
        )
        second.handle_progression_update(duplicate)
        assert duplicate.xp_earned == 0
        assert duplicate.has_celebration is False
        assert second.shell.celebration_overlay.played_events == []
        second.close_database()
        second.shell.close()


class TestGamificationMigration:
    def test_v3_schema_is_idempotent_and_preserves_existing_xp(
        self,
        v1_1_database_path,
    ):
        first = Database(v1_1_database_path)
        assert first.get_schema_version() == SCHEMA_VERSION == 3
        assert first.get_total_xp_setting() == 540
        columns = {
            row[1]
            for row in first.connection.execute("PRAGMA table_info(xp_events)")
        }
        tables = {
            row[0]
            for row in first.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "event_key" in columns
        assert {"achievement_unlocks", "milestone_unlocks"} <= tables
        before = first.get_xp_events()
        first.close()

        second = Database(v1_1_database_path)
        assert second.get_total_xp_setting() == 540
        assert second.get_xp_events() == before
        second.close()
