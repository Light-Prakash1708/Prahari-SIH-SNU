# PRAHARI · upgrade status

PHASE: all — delivered in one pass
STATUS: complete. 237 backend tests pass, frontend builds, walked through a browser.

## What was built

**Saurjya UI integration** — brand tokens, bundled Plus Jakarta Sans, and the
header / drawer / account-sheet / floating-bar chrome as React components over
the existing design tokens. Font Awesome and Google Fonts inlined and bundled,
because the app is offline-first. The mock farmer in Saurjya's markup (Ramesh
Kumar, 14 reports, 98% accuracy) was replaced by `/api/auth/me`.

**Crop Journey** — `GET /api/crop-calendar/{plot_id}`, one aggregation over
services that already existed. Stage rail from this field's sowing date,
prevention window with factor-by-factor evidence, today's mission (the existing
agenda, verbatim), threat-by-stage, and history from five existing tables.

**Farm ledger** — `/api/farm-ledger`, the only new table (`farm_entries`,
migration `004_ledger.sql`). Expense and income, category breakdown, cost per
acre, idempotent on `client_ref` for the offline queue.

**Multi-image diagnosis** — `POST /api/observations/{id}/images` with five
roles, same quality gate, diagnosis re-run.

**Follow-up self-report** — `POST /api/followups/{id}/outcome` for a farmer who
cannot retake a comparable photograph.

**Quick Tools hub + Fertilizer Guide** — Saurjya's bento over the tools that
exist, plus a screen for the nutrient-gap API that had none.

**ML pipeline** — verified end to end; `--no-pretrained` added for offline runs;
`pretrained_init`/`deployable` recorded in the run card.

## The four properties that are enforced by tests, not by intention

1. **Disease bands never appear on a future stage.** Weather beyond the forecast
   horizon does not exist, so those stages stay blank with the reason on screen.
2. **Money never reaches the agronomic engines.** A test records costs and
   asserts the risk board, threat windows, prevention window and agenda are
   byte-identical before and after.
3. **Repetition cannot manufacture confidence.** The same leaf uploaded four
   times must not talk the engine out of an abstention.
4. **A self-reported outcome is never presented as a measured one.** Both close
   the loop; only a rescan produces evidence a treatment worked.

## Two corrections worth remembering

**Threat banding.** The first version compared each `stage_factor` to fixed
cutoffs. Tomato's tables put whitefly at 0.5–0.6 early and Tuta at 0.7 late, so
four of five stages came back red — true of some pest in every case, and no help
at all. Factors are only meaningful relative to the same pest, so each pest is
now banded against its own range and a stage is judged by how many pests peak
there. Tomato reads watch / watch / watch / HIGH / normal.

**Open follow-ups.** Adding the self-report path exposed a live bug: "open" was
defined as *no rescan observation*, so a follow-up closed by a report would have
been asked for forever. Now *no observation AND no outcome*, in all five places
that ask — the due list, the day's agenda and the field-health card included.

FILES ADDED
- backend: `app/cropcalendar.py`, `app/routers/cropcalendar.py`,
  `app/routers/ledger.py`, `app/schema/004_ledger.sql`
- tests: `test_crop_calendar.py` (14), `test_farm_ledger.py` (10),
  `test_multi_image.py` (7), `test_followup_outcome.py` (7)
- frontend: `brand.css`, `shell/{shell,auth}.css`, `shell/Icon.jsx`,
  `shell/Chrome.jsx`, `screens/CropJourney.jsx`, `screens/crop-journey.css`,
  `screens/Tools.jsx`, `screens/tools.css`, `public/brand/*`

DATABASE: one additive migration. Nothing dropped, truncated, reseeded or
renamed. No primary ID changed.

TESTS: 237 passed (199 before this work). `npm run build` clean.

## UI pass — Saurjya's surfaces, after review

Six things came back from a look at the running app against Saurjya's site:

1. **The calendar read as static.** The Crop tab was already the dynamic
   journey; what looked static was a SECOND, date-less copy of the stage bar on
   the Crop *record* screen. That copy now shows each stage's day band and the
   current stage, and links to the journey instead of pretending to be it.
2. **Quick Actions** now sit on Home in Saurjya's exact bento — mint hero tile
   spanning two rows, two compacts beside it, two below, one wide at the foot,
   with "View All". Every tile routes somewhere that works.
3. **AgriDoc** rebuilt as his AI-agronomist sheet: forest header with avatar and
   live dot, bubble thread, suggestion rail, pill composer with a round send
   button. The grounding is unchanged — an ungrounded answer still renders as a
   visibly different bubble and every source is printed under the bubble.
4. **"How PRAHARI works"** added to Home. His version is five marketing claims
   side by side; ours is the seven-step loop in order, numbered, with a
   connector rail, because the sequence is the argument. Each step names what
   in the app performs it and links to it.
5. **The scanner** got his viewfinder: dimmed surround, mint corner brackets,
   travelling scanline, mint shutter ring. The scanline is decoration and says
   nothing about the frame — the honest verdict is the server-side quality gate
   that runs after the shutter.
6. **Soil** got his score dial on the self-test and his N/P/K/pH/OC nutrient
   cards on the lab tab. The plan itself was already correct — verified against
   the API and in the browser — so this was presentation, and a nutrient the
   farmer did not enter now reads "not measured" rather than being coloured as
   though it were adequate.

New files: `screens/Sections.jsx` (QuickActions, HowItWorks), `screens/saurjya.css`.

## Known limitations — stated, not hidden

- **No trained vision weights.** The Kaggle dataset is behind an account and
  this build environment had no route to it. The pipeline is verified end to end
  and `ml/README.md` carries the exact commands; `VISION_PROVIDER` ships as
  `none` and the app claims no accuracy anywhere.
- **Officer and Expert consoles** still use the older chrome. They are
  desktop-first and were deliberately left alone.
- **`_history` in the crop calendar** limits per source, so a very busy field can
  return up to 2× the limit. Harmless; a single ordered query would be tidier.
- **Sentinel-2 field segmentation** was assessed and deferred — see
  `prahari-reference-notes.md`. It adds a raster pipeline for a benefit the
  officer console does not currently lack.

## Team workspace

The repository is now set up for more than one person. `CONTRIBUTING.md` is the
five-minute setup plus the five rules; `docs/ARCHITECTURE.md` traces one request
end to end and says where every file lives; `docs/ROADMAP.md` carries 13 sized
issues with the files to open, and — as important — the five things we have
decided not to build, so nobody spends a weekend on one and finds out at the PR.
`CLAUDE.md` gives an AI assistant the same rules plus the traps in this codebase
that a model gets wrong on its own. `.github/` holds the PR template (its
checklist is the five rules), three issue templates — the agronomy one will not
accept a threshold without a citation — and CODEOWNERS marking `data/`,
`schema/`, `security.py` and `config.py` as needing review.

`origin` is set to the GitHub repository. The push has to be run from a machine
with GitHub credentials; this build environment has none.

## Your data — deletion, and closing an account

`/api/privacy` in four routes: what is held (counted by category, bilingual),
an export of all of it as JSON, deletion by category, and closing the account.
`app/privacy.py` owns the rules; the router only authenticates and confirms.

Three decisions worth knowing about:

- **The confirmation is two guards, not one.** The password proves who is
  holding the phone; a typed DELETE (or डिलीट / हटवा) proves they meant this
  particular thing. Either alone is refused, and a test asserts each.
- **Community posts are the farmer's choice.** A post three neighbours
  corroborated is at once their writing and the evidence behind a regional
  signal. Delete removes it entirely; keep re-points it at a shared tombstone
  account so it survives as "Deleted account" with no farmer link. There is no
  quiet default — the sheet asks, and states the consequence of each.
- **"It is gone" is measured, not asserted.** The server re-counts after the
  deletion and returns the counts; the receipt shows them, and a non-zero row
  is displayed as a failure rather than hidden.

Regional signals are NOT reversed, and the screen says so: those rows hold
counts by taluka and problem — no name, no field, no location — and they are
what an officer's outbreak response was based on.

Staff accounts cannot self-delete: an expert's verdicts are the basis of other
farmers' records.

## AgriDoc · an optional language-model key

A farmer (or a teammate) can paste a Gemini or OpenAI key. What it buys is
**fluency, not knowledge**:

```
retrieval (unchanged) ─▶ FACTS ─▶ model rewrites the FACTS as prose
                          │
                          └─ nothing retrieved ─▶ refusal, model never called
```

The model is never asked a question. It is handed what PRAHARI already
retrieved and asked to phrase it. Three guards, all tested:

1. **No context, no call.** An empty retrieval returns the refusal directly.
2. **Every number must already exist in the facts.** A dose, threshold or PHI
   the model produced on its own fails the check and its whole answer is
   discarded — the retrieved one, which was always correct, is shown instead.
3. **No new product names.** A capitalised word that is not in the facts and
   not in PRAHARI's own vocabulary is treated as invented.

A discarded rewrite is visible in the response (`llm.discarded_draft`) and
marked on screen, so a silent fallback cannot hide the one event worth seeing.
Keys are verified against the provider before storage, encrypted with a key
derived from `JWT_SECRET`, never returned by any endpoint, and deleted with the
account. Default is `VISION_PROVIDER`-style off: `LLM_PROVIDER=none`.

## Mobile pass — what moved, and why

Nothing was removed. Home was 7 500 px on a 400 px phone; it is now ~2 700.

- **"How PRAHARI works"** — the seven-step loop — became its own screen with a
  one-line door on Home. It is a good explanation and it was pushing the day's
  actions under a wall of text nobody re-reads.
- **Method paragraphs fold.** The app must always be able to show its working;
  it does not have to shout it every morning. Four of them (`agenda`, the
  forecast headline, the prevention window, the disease note) are now
  `<details>` — and are in Marathi, which they were not: the one paragraph a
  farmer most needs to audit was the one they could not read.
- **The drawer is grouped** — My field / Tools / Account — instead of twelve
  flat rows, which read as "nothing here".
- **AgriDoc's limits fold** into a summary, and the four refusals are bilingual.
- **Hash routing.** Routing was in-memory only: a refresh dropped a farmer on
  Home, the back button left the app, and no one could send a teammate a link
  to a screen. The hash mirrors state; a hash that cannot be honoured degrades
  to its base screen.

Checked at 360 px: no horizontal overflow on any screen.

TESTS: 265 passed (260 before this work). Bundle 121 kB gzipped, ceiling 200.
DATABASE: one additive migration, `005_llm_keys.sql`. Nothing dropped, renamed
or reseeded.

## Several fields, each with its own crop — and a way to track them

The app could always hold more than one field; what it could not do was let a
farmer see them together, or change the crop in one.

**`GET /api/plots/board`** (`app/fieldboard.py`) — one call that returns, per
field: what is growing and how far into the season, the crop-health score and
which way it moved, what that field is asking for today, and when it was last
actually looked at. Ordered by consequence, so the top card is the field to
walk to.

The board owns no agronomy. Every number comes from the same services that
produce that field's own screen — `risk.field_health` and `agenda` — and
`test_field_board.py` asserts the two agree, which is the assertion that stops
this becoming a second implementation that drifts.

Two rules carried through unchanged:

- **A field with no weather gets no score.** Not zero, not the last one, not
  borrowed from the field beside it. The card shows its records and says why
  there is no number, and one such field does not take the board down.
- **Last seen counts scouting**, not app opens. Opening the app is not walking
  the field.

**A new crop in the same field.** `POST /api/plots/{id}/cycles` existed and
nothing in the UI reached it, so the only way to record a changed crop was to
register the field twice — which splits its history and quietly ends the
passport. There is now a sheet on each field card: pick the crop, give the
sowing date, and the running cycle closes while every scan, count, spray and
diagnosis stays attached to the field. A test asserts the previous season's
records survive and that the stage recounts from the new date.

**Reaching them.** "My Fields" is now a tile on Home's Quick Actions — several
fields with different crops is the normal case, not the advanced one — as well
as in the drawer under My field.

TESTS: 275 passed (265 before). ruff clean.
