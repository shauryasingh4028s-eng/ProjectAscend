"""Declarative configuration for Project Ascend's progression layer.

This module contains product copy and thresholds only. It performs no database
or UI work, which keeps ranks, achievements, milestones and character options
centralized and easy to extend without scattering progression rules.
"""

from dataclasses import dataclass


# v1.5 deliberately preserves the established v1.4 level curve so existing
# users keep exactly the same XP and level. A future curve can replace these
# helpers without changing persisted totals.
XP_PER_LEVEL = 100
ACTIVITY_COMPLETION_XP = 10
DAILY_GOAL_XP = 50


@dataclass(frozen=True)
class RankDefinition:
    minimum_level: int
    name: str


# Restrained, productivity-oriented rank copy. The ordered configuration is
# the only source of rank names in the application.
RANKS = (
    RankDefinition(1, "Starting Out"),
    RankDefinition(5, "Building Momentum"),
    RankDefinition(10, "Consistent"),
    RankDefinition(20, "Established"),
    RankDefinition(35, "Advanced"),
    RankDefinition(50, "Enduring"),
)


def level_for_xp(total_xp):
    """Return the v1.4-compatible level for a non-negative XP total."""
    return (max(0, int(total_xp)) // XP_PER_LEVEL) + 1


def xp_into_level(total_xp):
    return max(0, int(total_xp)) % XP_PER_LEVEL


def rank_for_level(level):
    level = max(1, int(level))
    current = RANKS[0]
    for rank in RANKS:
        if rank.minimum_level > level:
            break
        current = rank
    return current


@dataclass(frozen=True)
class EvolutionStage:
    identifier: str
    minimum_level: int


# Identifiers intentionally remain implementation-safe rather than assigning
# unapproved narrative labels to character evolution stages.
EVOLUTION_STAGES = (
    EvolutionStage("stage_1", 1),
    EvolutionStage("stage_2", 5),
    EvolutionStage("stage_3", 10),
    EvolutionStage("stage_4", 20),
    EvolutionStage("stage_5", 35),
)


def evolution_stage_for_level(level):
    level = max(1, int(level))
    current = EVOLUTION_STAGES[0]
    for stage in EVOLUTION_STAGES:
        if stage.minimum_level > level:
            break
        current = stage
    return current


@dataclass(frozen=True)
class CharacterDefinition:
    identifier: str
    name: str
    archetype: str
    primary: str
    accent: str


# Eight original Ascend archetypes. These definitions drive vector artwork
# drawn by Qt; no third-party or franchise assets are used.
CHARACTERS = (
    CharacterDefinition("trailfinder", "Trailfinder", "explorer", "#D89A56", "#3B82F6"),
    CharacterDefinition("lumen", "Lumen", "mage", "#7C5CFF", "#60A5FA"),
    CharacterDefinition("aegis", "Aegis", "knight", "#7890A8", "#F59E0B"),
    CharacterDefinition("veil", "Veil", "shinobi", "#40516A", "#7C5CFF"),
    CharacterDefinition("circuit", "Circuit", "android", "#607D8B", "#22C55E"),
    CharacterDefinition("ember", "Ember", "fox", "#E47D47", "#F7C65C"),
    CharacterDefinition("moss", "Moss", "forestling", "#4D8B62", "#9BCB65"),
    CharacterDefinition("nova", "Nova", "space_explorer", "#E6EAF2", "#3B82F6"),
)
DEFAULT_CHARACTER_ID = CHARACTERS[0].identifier
CHARACTER_BY_ID = {character.identifier: character for character in CHARACTERS}


@dataclass(frozen=True)
class AchievementDefinition:
    identifier: str
    name: str
    description: str
    category: str
    metric: str
    threshold: int
    symbol: str


# Twenty evidence-based achievements across Firsts, Milestones and Mastery.
# Every criterion maps to a value in ProgressMetrics; there are no UI-only or
# click-based unlocks.
ACHIEVEMENTS = (
    AchievementDefinition(
        "first_activity", "First Step", "Complete your first activity.",
        "Firsts", "completed_activities", 1, "01",
    ),
    AchievementDefinition(
        "first_focus", "Focused Start", "Complete your first meaningful focus session.",
        "Firsts", "focus_sessions", 1, "02",
    ),
    AchievementDefinition(
        "first_daily_goal", "Goal Reached", "Reach your daily focus goal for the first time.",
        "Firsts", "goal_days", 1, "03",
    ),
    AchievementDefinition(
        "focus_10_hours", "Ten Focused Hours", "Accumulate 10 hours of focused work.",
        "Milestones", "focus_minutes", 600, "10H",
    ),
    AchievementDefinition(
        "focus_50_hours", "Fifty Focused Hours", "Accumulate 50 hours of focused work.",
        "Milestones", "focus_minutes", 3000, "50H",
    ),
    AchievementDefinition(
        "activities_10", "Ten Completed", "Complete 10 activities.",
        "Milestones", "completed_activities", 10, "10",
    ),
    AchievementDefinition(
        "activities_50", "Fifty Completed", "Complete 50 activities.",
        "Milestones", "completed_activities", 50, "50",
    ),
    AchievementDefinition(
        "activities_100", "Century of Work", "Complete 100 activities.",
        "Milestones", "completed_activities", 100, "100",
    ),
    AchievementDefinition(
        "streak_3", "Three Consistent Days", "Reach a 3-day daily-goal streak.",
        "Milestones", "best_streak", 3, "3D",
    ),
    AchievementDefinition(
        "streak_7", "Seven Consistent Days", "Reach a 7-day daily-goal streak.",
        "Milestones", "best_streak", 7, "7D",
    ),
    AchievementDefinition(
        "streak_14", "Two Consistent Weeks", "Reach a 14-day daily-goal streak.",
        "Milestones", "best_streak", 14, "14D",
    ),
    AchievementDefinition(
        "goal_days_10", "Ten Goal Days", "Meet your daily goal on 10 days.",
        "Milestones", "goal_days", 10, "10G",
    ),
    AchievementDefinition(
        "level_5", "Progress Established", "Reach Level 5 through productive work.",
        "Milestones", "level", 5, "L5",
    ),
    AchievementDefinition(
        "focus_100_hours", "Focused Mastery", "Accumulate 100 hours of focused work.",
        "Mastery", "focus_minutes", 6000, "100H",
    ),
    AchievementDefinition(
        "focus_250_hours", "Enduring Focus", "Accumulate 250 hours of focused work.",
        "Mastery", "focus_minutes", 15000, "250H",
    ),
    AchievementDefinition(
        "activities_250", "Sustained Completion", "Complete 250 activities.",
        "Mastery", "completed_activities", 250, "250",
    ),
    AchievementDefinition(
        "streak_30", "Thirty Consistent Days", "Reach a 30-day daily-goal streak.",
        "Mastery", "best_streak", 30, "30D",
    ),
    AchievementDefinition(
        "goal_days_50", "Fifty Goal Days", "Meet your daily goal on 50 days.",
        "Mastery", "goal_days", 50, "50G",
    ),
    AchievementDefinition(
        "level_10", "Long-Term Progress", "Reach Level 10 through productive work.",
        "Mastery", "level", 10, "L10",
    ),
    AchievementDefinition(
        "level_25", "Proven Practice", "Reach Level 25 through productive work.",
        "Mastery", "level", 25, "L25",
    ),
)
ACHIEVEMENT_BY_ID = {achievement.identifier: achievement for achievement in ACHIEVEMENTS}


@dataclass(frozen=True)
class MilestoneTrack:
    identifier: str
    name: str
    description: str
    metric: str
    thresholds: tuple[int, ...]
    unit: str


# Milestones are broad tracks rather than isolated badges. Each crossed tier
# receives a stable persisted identifier such as ``focus:tier_2``.
MILESTONE_TRACKS = (
    MilestoneTrack(
        "focus", "Focus", "Long-term focused time", "focus_minutes",
        (600, 3000, 6000, 15000), "minutes",
    ),
    MilestoneTrack(
        "completion", "Completion", "Activities brought to completion", "completed_activities",
        (10, 50, 100, 250), "activities",
    ),
    MilestoneTrack(
        "consistency", "Consistency", "Best daily-goal streak", "best_streak",
        (3, 7, 14, 30), "days",
    ),
    MilestoneTrack(
        "goal_days", "Goal Success", "Total days the daily goal was met", "goal_days",
        (1, 10, 50, 100), "days",
    ),
    MilestoneTrack(
        "progression", "Progression", "Levels earned through real work", "level",
        (2, 5, 10, 25), "levels",
    ),
)
MILESTONE_BY_ID = {track.identifier: track for track in MILESTONE_TRACKS}
