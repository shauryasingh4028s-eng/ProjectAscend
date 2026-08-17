# Project Ascend Changelog

---

# v1.4 - Actionable Intelligence
Status: 🔄 In progress

### Added
- Interactive Time Distribution: a temporary Tomorrow Planner what-if tool for adjusting per-activity allocations and seeing the immediate available-time fit. Allocations seed from existing Smart Expected Durations, never modify saved activities, and disappear when the app closes.
- Smart Activity Estimates: when adding or editing an activity, Ascend
  can suggest a more realistic duration learned from the user's own
  history ("Ascend suggests ~70 min", "You typically take ~10 min
  longer.", "Based on 12 previous \"Algebra Test\" sessions.").
- Personalized evidence hierarchy: exact activity (same category and
  same normalized name, 5+ completed sessions) → category (10+) →
  overall personal history (10+) → no recommendation. The first
  reliable tier wins; tiers are never blended, and the supporting copy
  always states exactly which evidence was used.
- The learned statistic is the user's typical absolute time
  difference - median(actual − original estimate) - so behaviour like
  "Coding usually runs +10 min" is expressed in concrete minutes at
  any plan size, both for overruns and for finishing early.
- Relevance window: a tier's learned bias only applies when the
  entered estimate is within the range of that tier's observed
  original estimates (±5 min); Ascend refuses to extrapolate beyond
  its own evidence instead of guessing.
- The suggestion is strictly optional: Keep leaves the user's estimate
  untouched, Use applies the suggested value to the input field only,
  and nothing is saved until the existing Save action. Manual edits
  always win.
- Accepting a suggestion never triggers a follow-up suggestion derived
  from the accepted value (no recommendation chaining); a later manual
  edit re-anchors normally.

### Design decisions
- Smart Estimates is an additive intelligence layer beside the v1.2
  calibration engine: observation validity is single-sourced through
  the engine's make_observations(), original-estimate semantics
  prevent the model from ever learning from its own accepted
  recommendations, and the engine's multiplier model, thresholds and
  Planning Accuracy/Insights behaviour are untouched.
- Activity identity is deliberately strict: exact match on category
  plus whitespace/case-normalized name. "Maths Test 2" or "Maths Test
  (Final)" never contribute to "Maths Test" evidence - no fuzzy
  matching, so exact-activity evidence is never fabricated.
- With insufficient evidence the dialog remains exactly as clean as
  before - no placeholder, no invented numbers.
- A suggestion that rounds back to the entered value is suppressed as
  noise, and a recommendation outside the dialog's valid 5-600 min
  range is hidden rather than clamped, so the learned number is never
  misrepresented.
- Actionable copy is time-first (concrete minutes, never percentages
  or multipliers).
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