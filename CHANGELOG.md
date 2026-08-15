# Project Ascend Changelog

---

# v1.4 - Actionable Intelligence
Status: 🔄 In progress

### Added
- Smart Activity Estimates: when adding or editing an activity, Ascend
  can suggest a more realistic duration based on the user's own
  historical calibration evidence ("Ascend suggests ~90 min", "About
  30 min more than your estimate.", "Based on 14 completed Coding
  activities.").
- Evidence selection prefers the selected category's calibration
  multiplier when that category alone has enough completed
  observations, otherwise falls back to the overall multiplier - the
  supporting copy always states exactly which evidence was used.
- The suggestion is strictly optional: Keep leaves the user's estimate
  untouched, Use applies the suggested value to the input field only,
  and nothing is saved until the existing Save action. Manual edits
  always win.
- Accepting a suggestion never triggers a follow-up suggestion derived
  from the accepted value (no recommendation chaining); a later manual
  edit re-anchors normally.

### Design decisions
- All evidence and thresholds come from the existing v1.2
  CalibrationService; the suggestion value is the unmodified output of
  the existing recommended_estimate() helper. No calibration
  mathematics was duplicated and no threshold was changed.
- With insufficient evidence the dialog remains exactly as clean as
  before - no placeholder, no invented numbers.
- A suggestion equal to the entered value is suppressed as noise, and
  a recommendation outside the dialog's valid 5-600 min range is
  hidden rather than clamped, so the engine's output is never
  misrepresented.
- Actionable copy is time-first (concrete minutes, never percentages).
- No schema changes, no migrations, no new database writes; the
  feature reads through the existing calibration query only.
- The suggestion card reuses the frozen v1.3 visual system
  (LearnedInsight surface, accent glyph, ghost buttons); no new visual
  language.

---

# v1.3 - Insights Experience
Status: ✅ Completed

### Added
- Insights hero header with a clear narrative: "Understand your
  productivity. Improve it."
- Period selector extended to Today / 7 Days / 30 Days / 3 Months /
  All Time, with honest comparisons against the previous equivalent
  period (never invented when no previous data exists).
- Productivity Overview with comparison deltas (+18% focus, +7 pts
  completion, +4 activities), each hidden when no previous data exists.
- Focus Trend improvements: denser grid, value captions, strongest
  period highlighted, granularity-aware labels, richer tooltips.
- "Where Your Time Goes": ranked horizontal-bar chart of focus time by
  activity category with hover tooltips; extra categories merge into an
  honest "Other" bar.
- "When You Work Best": day-of-week x time-of-day focus heatmap built
  from timestamped sessions, with a strongest-window interpretation
  that only appears with enough evidence ("We're still learning your
  rhythm." otherwise).
- "What Ascend Learned": evidence-backed observations (focus window,
  estimate bias per category, best day, growing consistency, sharper
  estimates), each following OBSERVATION + EVIDENCE + CONFIDENCE with
  documented thresholds. No LLM, no invented patterns.
- Personal Highlights: best day, longest focus session, biggest
  improvement - all calculated from real data.
- Long-range trend aggregation (weekly/monthly buckets) so 3 Months and
  All Time stay readable.
- Light theme improvements: washed soft tints for chips, selected
  states and heatmaps on white surfaces.

### Design decisions
- Every new number is derived from persisted data; empty and
  insufficient-data states are deliberate and explicit.
- The v1.2 calibration engine, formulas, thresholds, schema and
  migrations are untouched.
- No new dependencies; charts remain custom-painted PySide6 widgets.

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