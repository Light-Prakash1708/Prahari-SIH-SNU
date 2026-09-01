# View Management upgrade

CURRENT STAGE: 12 of 12 — complete.
STATUS: 295 backend tests pass (278 before), ruff clean, frontend builds,
walked through a browser on a 380 px viewport for both a pest and a disease.

## COMPLETED
- Decision card with five states, the two numbers it turned on, and next review
- "Why PRAHARI says this" — evidence rows, each labelled and sourced, folded
- Field evidence: AI confidence and field measurement side by side, never merged
- **Disease path** — the real gap. A disease had no count, so the screen asked
  for one that does not exist. It now takes a field assessment instead.
- Prevention window, today's action, trend, actionable ladder with a MONITOR
  rung, chemical gate, expert escalation, follow-up, field history
- Everything below the decision folds; only the decision and the evidence open

## THE ONE THING THE BRIEF ASKED FOR THAT WAS NOT THERE
§7 asked to stop deriving a field severity from diagnosis confidence. **No such
code existed.** The count has always come from `threshold_checks`. Nothing was
"separated" because nothing was joined; instead the two are now *shown*
separately, each with a sentence saying what it does and does not mean, and
`test_management.py` asserts a confident diagnosis with no count leaves the
decision at `no_count`.

## FILES MODIFIED
backend: `management.py` (new, composition only), `routers/management.py` (new),
`services/decisions.py` (+`disease_decision`, shared `_HEADLINE`),
`prescribe.py` (+monitor rung), `schemas.py`, `main.py`,
`schema/006_disease_assessments.sql` (new)
frontend: `screens/Decide.jsx` (rewritten body, sub-components kept),
`screens/saurjya.css` (+`.mg-*`), `api.js`, `App.jsx` (deep-linkable `decide`)

## APIS USED
Existing: `/should-i-spray`, `/recommendations`, `/applications`, `/followups`,
`/plots/{id}/history`, `expert-review`, `risk.board`, `agenda`, prevention
window. New: `GET /api/management/{plot_id}` (aggregates the above — it owns no
agronomy and a test asserts its verdict equals `/should-i-spray`'s) and
`POST /api/management/{plot_id}/assessment`.

## NEW LOGIC
`disease_decision()` — a disease is decided by measured incidence AND the
published infection model firing on this field's weather. **No incidence
percentage is treated as an action threshold**: no such published figure exists
in the reference tables, and inventing one would be inventing the number the
whole decision turns on. States: not present + not conducive → monitor;
not present + conducive → prevention window; present + not conducive →
non-chemical; present + conducive → act, chemical only if a verified claim
exists, else expert review.

## DATABASE
One additive migration, `006_disease_assessments.sql`. Reason: a disease needs
incidence and `threshold_checks` is a pest-count table whose every other column
would be null and later misread as a measurement. Backward compatible — a plot
with no row behaves exactly as before. Nothing dropped, renamed or reseeded.

## TESTS
`test_management.py`, 17: confidence is never a measurement; a disease is never
asked for a count; a confident diagnosis alone never opens the chemical rung;
incidence shows its arithmetic; a ready-made percentage is refused (422); more
affected than inspected is refused (400); assessments are idempotent; one
observation is never called a trend; the ladder leads with monitoring; the new
screen agrees with the endpoint it composes; the old endpoint still works;
cross-farmer and anonymous access refused.

## KNOWN ISSUES
- Prevention-window factor strings and some infection-model detail are English
  only. They come from the forecast engine and are shared with the crop journey;
  translating generated agronomic text is a separate, deliberate piece of work.
- No mechanical rung: `ipm.json` has no mechanical entries for these targets.
  Inventing them would be inventing agronomy, so the rung is absent, not empty.

NEXT EXACT ACTION: none — the upgrade is complete.
