# Project Ascend Changelog

---

# v1.2 - Calibration Foundation
Status: ✅ Completed

### Added
- CalibrationService: measures planned vs actual duration for completed
  activities, overall and per category (difference, relative error,
  absolute percentage error, bias, sample counts).
- Evidence levels (insufficient_data / early_signal / moderate_confidence /
  high_confidence) so the app never presents a recommendation without
  enough completed observations.
- Transparent planning multiplier (median actual/estimated) with a
  recommended estimate helper, exposed only at moderate confidence or
  higher.
- Explicit, repeatable database migrations with schema-version tracking
  (SQLite `user_version`). v1.1 and legacy databases upgrade in place with
  all data, IDs, XP and history preserved.
- `activities.original_estimate_minutes`: the original planning estimate is
  preserved separately, so calibration compares the ORIGINAL plan against
  the actual result even after the estimate is edited post-completion.
- `focus_sessions.actual_seconds`: precise elapsed execution seconds are
  recorded (pauses never counted) while the existing minute-level
  `actual_minutes` semantics stay unchanged.
- "Planning Accuracy" section on the Insights page: Estimate Bias, Typical
  Error, Confidence, best/most-variable categories, and a planning
  multiplier note - or an explicit "Not enough data yet" state.
- pytest test suite: calibration math, evidence thresholds, category
  isolation, migration safety (v1.1 and legacy), restart persistence,
  session persistence, real-data validation on a copy of the legacy
  database, and full application regression.

### Design decisions
- No machine learning, no external AI, no new dependencies. Every number
  is a plain, documented statistic.
- Invalid records (zero estimates, missing actuals, incomplete work) are
  excluded and counted, never replaced with invented values.
- Evidence thresholds are product safeguards, documented in code as such -
  not scientific claims.

---

# v0.1 - Foundation
Status: ✅ Completed

### Added
- Python project setup
- Virtual environment
- PySide6 installation
- VS Code workspace
- Project folder structure
- Main application window
- Live clock

---

# v0.2 - Tomorrow Planner
Status: ✅ Completed

### Added
- Tomorrow Planner window
- Add Activity dialog
- Activity dataclass
- Activity Manager
- Dynamic activity list

### Features
- Create activities
- Categorize activities
- Estimated study time

---

# v0.3 - Persistent Activities
Status: ✅ Completed

### Added
- SQLite database
- Automatic table creation
- Persistent activity storage
- Activity loading on startup
- Date-based planning
- AppController foundation

### Features
- Activities survive app restarts
- Tomorrow planning
- Local-first storage
- Database migration support

---

# v0.4 - Session Engine
Status: ✅ Completed

### Added
- Dashboard
- Session Engine
- Start activity
- Pause activity
- Resume activity
- Complete activity
- Live timer
- Current activity display

### Improvements
- Completed activities show a ✅
- Actual study time saved
- Dashboard ↔ Planner navigation
- QTimer-based timing

---

# v0.5 - Dashboard 2.0
Status: 🚧 In Progress

### Planned
- Modern dashboard
- Progress bar
- Study time card
- Completed / Total counter
- Better layout
- Cleaner UI

---

# Future Roadmap

## v0.6
- Focus Mode
- Fullscreen Study Mode
- Keyboard shortcuts

## v0.7
- Statistics
- Daily reports
- Weekly reports
- Productivity graph

## v0.8
- AI Coach
- Habit analysis
- Personalized suggestions

## v0.9
- Distraction detection
- Active application tracking
- Website monitoring

## v1.0
- Stable release
- Installer
- Settings
- Themes
- Export reports