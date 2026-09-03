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

## Fields, from the Crop tab

The Crop tab now manages the fields it is about, rather than only displaying
whichever one was selected elsewhere.

- **The switcher is always there.** It used to appear only once a farmer
  already had two fields, which made a second field something you had to know
  was possible. Each chip carries the crop that field is actually growing, so
  choosing between them does not depend on remembering which is which.
- **"Add field"** is the last chip, and the empty state offers it too — the
  screen about crops is the obvious place to register the first one.
- **"Change crop"** sits on the hero, and opens the same sheet the Fields
  screen uses. It closes the running crop cycle and opens a new one; the
  field's scans, counts, sprays and diagnoses stay attached, which is what
  makes it a passport rather than a season of notes.
- Switching is not a display filter: the selection moves the app's active
  field, the calendar re-fetches, and the stage rail, thresholds, trap counts
  and history all follow.

### A bug this uncovered — adding a field was broken

`POST /api/plots` returned 422 whenever the taluka select was left on its
default, which is the option the form itself labels "Use my account taluka".
A `model_validator` on `PlotIn` required coordinates or an explicit taluka and
rejected the request **before** the router — which already resolves a location
in order (boundary centroid → explicit taluka → nearest taluka to the
coordinates → the farmer's own taluka) — could run. The schema cannot see the
farmer, so it was guessing on their behalf and could only be wrong in one
direction.

The rule moved to the place that has the farmer in hand. Nothing is loosened:
a field still ends up with a real taluka or the router raises `unknown_taluka`,
and a test asserts that refusal still happens.

TESTS: 278 passed (265 before). Bundle 124 kB gzipped of 200.

## v7 — the Crop tab becomes a field, and the three consoles

### The crop journey lives inside a field

The Crop tab used to open one field's journey with a switcher on top. It now
opens the **fields board**, and a card opens that field's journey. A journey is
about one field's season — its sowing date, its stage, its own thresholds — so
reaching it through the field it belongs to is the honest shape, and the only
one that stays clear at four fields rather than one.

- `crop` → the board (`Fields` with `asCropSection`), same component as the
  drawer's Fields screen. One implementation: a second board would be a second
  answer to "which field needs me".
- `cropJourney` → that field's journey, with **All fields** in the header. A
  nested screen with no way out is how a tab becomes a dead end.
- Each card still carries what that field needs today, its crop-health score
  and direction, and per-field Journey / Traps / History / New crop.
- Adding a field is on the board and on the journey's chip rail.

### Officer, expert and admin

All three were audited in a browser first: officer and expert were already
functional — real clusters, Gi\* statistics, the verification queue, no errors
— and were simply still on the pre-Saurjya chrome. They now carry the same
identity at desktop density: the real wordmark, his radii, a shadow that reads
as depth on a dark ground, mint as the active accent, gradient pill buttons,
and a sidebar that becomes a scrolling strip below 900 px instead of vanishing.
The density is deliberate and stays — these are read across a district for an
hour at a time.

**Admin had no console at all.** An admin account was handed the officer
console, which is a district-surveillance product and not an administrator's
job; the four things only an administrator can do had no interface. Now
`screens/Admin.jsx`, ordered by consequence:

1. **Label claims — the chemical gate.** `chemicals.py` will not return a claim
   that has not been verified against a cited CIB&RC source, so a draft row is
   a recommendation PRAHARI is currently refusing to make. This is the
   highest-risk action in the system, so it demands the citation before it will
   submit and records who verified it. The demo database ships 42 draft claims
   and 0 verified — which is why the app names no chemical.
2. **Staff & scope** — who can act on other people's records and where, with
   scope granting. Officers with no taluka are flagged: they see nothing.
3. **Overview** — counts, the gate, the vision model's own words about itself,
   the deployment configuration, migrations applied.
4. **Audit** — filterable, and it explains its own null-user rows.

New endpoints: `GET /api/admin/staff` (staff only — the role filter is in the
SQL, not a parameter, so it cannot be widened into a farmer directory) and
`GET /api/admin/overview`. Admin actions now record the acting role.

TESTS: 278 passed. ruff clean. Bundle 126 kB gzipped of 200.

## v8 — View Management: the decision, and the disease that had nowhere to go

The "Should I spray?" screen became "What should I do?", with the decision
still the first thing on it. Nine sections in the order the questions get asked
standing in a field, and everything below the evidence folds.

**The brief's central premise did not hold, and that is worth stating.** It
asked to stop deriving field severity from diagnosis confidence. No such code
existed — the count has always come from `threshold_checks`. So nothing was
separated; instead the two are now *shown* separately, side by side, each with
a sentence saying what it means and what it does not, and a test asserts that a
confident diagnosis with nothing counted leaves the decision at `no_count`.

**The real break was diseases**, found by asking the running API. A disease has
no trap count and no economic threshold, so `?target=late_blight` returned
"nothing counted yet, record a count" — a count that does not exist for a
disease — and the screen's own chip list filtered to pests, so a disease
arriving from a scan was not even selectable. A farmer who scanned a leaf and
got late blight could go no further.

A disease is now decided by two measured things and no invented third one:

- **incidence** — the farmer walks the field, inspects a set number of plants,
  records how many show it. The app does the division in front of them
  (`6 ÷ 10 = 60%`) and stores both numbers, so it can be re-derived.
- **the published infection model** — Hutton, TOMCAST — firing on this field's
  own weather, already computed for the risk board.

No incidence percentage is treated as an action threshold. There is no such
published figure in the reference tables and putting one in would be inventing
the number the whole decision turns on.

Also: a MONITOR rung was added to the IPM ladder — it was missing because the
IPM tables describe interventions and monitoring is not one, which left the
ladder unable to express what PRAHARI recommends most often. Its content is the
problem's own published scouting text, in both languages.

One additive migration, `006_disease_assessments.sql`. TESTS: 295 (278 before).

---

# Weather resilience, graceful Decide, and AgriDoc grounding

TESTS: 322 (295 before, of which one was failing on main — see below).
No migration. No new dependency. No provider added.

## What was broken

**A rate limit fed itself.** Open-Meteo answering 429 raised
`WeatherUnavailable` and recorded nothing, so the next request went straight
back out. The more the app failed the harder it asked, and the limit never
cleared. Compounding it: the request asked for `wind_speed_10m` and
`cloud_cover` on every call — Open-Meteo weighs a call by variables times days
— and nothing anywhere read either one.

**View Management answered 503 and went blank.** Most of that screen is not
about weather. The trap count, the published threshold it is measured against,
the scouting text, the IPM ladder, the verified label claims, the follow-up and
the field history are as true during an outage as outside one.

**The risk board had never once reached the language model.** `field_facts`
called `rt.risk.board(plot, wx)`; the method is `board(plot, wx, stage)`. Every
call raised `TypeError`, a bare `except Exception` caught it, and the bundle got
the weather-unavailable note instead — with weather working perfectly. The test
that covered it asserted `"risk_board" in facts or "risk_board_note" in facts`,
which passes on either branch.

**`gemini-2.0-flash` is retired.** Google lists it under previous models, marked
for shutdown.

## What was done

**Weather.** A per-provider cooldown on 429 and 5xx, honouring `Retry-After`,
defaulting to `WEATHER_COOLDOWN_SECONDS`, clamped by
`WEATHER_COOLDOWN_MAX_SECONDS`. A one-off timeout deliberately does not cool
anything down — one field timing out is not evidence the provider is refusing
traffic. Single-flight locking per cache key. The in-process dict is gone;
`weather_cache` is the only cache, and a series past its TTL is served labelled
stale only inside `WEATHER_STALE_MAX_HOURS`. Three hourly variables, not five.

**Decide.** `GET /api/management/{id}` returns 200 with
`weather_available: false` and the weather-derived sections null and named.
`risk.board_without_weather()` sets `level` and `fired` to `None` — never
`"low"`, never `False` — and `disease_decision` has two explicit branches for
"the model could not be run", worded nothing like "conditions are not
conducive". The chemical rung stays shut on half the evidence. A pest decision
is unchanged: only a count against a published threshold authorises anything.

**AgriDoc.** The board reaches the model, trimmed to what an answer could
legitimately quote. The handler catches `WeatherUnavailable` only, so a
programming error surfaces as one. `gemini-2.5-flash` is the default. A
per-key quota cooldown, keyed by a digest of the credential and never the
credential. A net around the whole enhancement path, so a failure there costs
the rewrite and never the retrieved answer. Two prompt rules added: FACTS are
data and cannot grant permission, and an absent value is unknown rather than
zero, none or safe. The number and product guards are untouched.

## Known limitations

- **The cooldown and the single-flight lock are per process.** With several
  Render instances each keeps its own, so the call rate falls by a factor of
  the instance count rather than to zero. Same caveat `ratelimit.py` already
  carries. A shared counter is the fix if this ever runs multi-instance.
- **There is still one weather provider.** The abstraction is ready for a
  second — `WeatherService._build()` is a factory and no risk or management
  call site names a provider — but none is implemented, so an Open-Meteo
  outage longer than `WEATHER_STALE_MAX_HOURS` still means no risk forecast.
- **`LLM_MAX_OUTPUT_TOKENS` must not be lowered.** On the Gemini 2.5 models a
  reasoning pass is billed against it before any text is produced. The old
  default of 600 can return an empty reply with `finishReason: MAX_TOKENS`, and
  the assistant then falls back to the template on every question — which from
  the outside is indistinguishable from a key that does not work. Raised to
  2048, and the empty case now names itself instead of going quiet.
- **The Gemini path has not been exercised against the live API in this
  change.** Model id and `v1beta` were verified against Google's current
  documentation; the request shape is unchanged from the version that was
  working. It needs one live call with a real key before judging.
- **`llm.discarded_draft` still returns rejected model output to the client.**
  It is never rendered as an answer, but it is unverified text reaching the
  browser. Worth gating behind a debug flag before a public deployment.
- **`field_facts` still wraps `crop_stage` in `contextlib.suppress(Exception)`.**
  Narrower than it was — the board no longer hides behind it — but the same
  class of thing that hid the board bug for as long as it existed.

---

# Farmer intelligence pass: gallery, passport, IPM glance, consoles, hotspots

TESTS: 327 (322 before). No migration, no new runtime dependency, no new
weather provider. Frontend 136.71 kB gzipped JS against the 200 kB gate.

## Gallery opened the camera

`capture="environment"` is not a hint — it tells the phone to skip the picker
and open the camera. The scan screen had ONE hidden input carrying it, shared
between the shutter's fallback and the Gallery button, so Gallery opened the
camera and a photo already on the phone could not be used at all. The Camera
component now has two inputs: a gallery one with no `capture`, and a camera one
that keeps it and is reached only when `getUserMedia` failed. The input value is
cleared on change, so choosing the same photo twice in a row still fires.

The same attribute was on six other "take or choose a photo" inputs — the weed
check, the trap photo, the follow-up rescan, the community post, and the two
older views — each of them denying the photo library behind a control that
offered it. Removed there too; the native picker offers both.

## Crop Health Passport

It was six counters. The counters stay, as the footer, because the record is
what matters at harvest — above them now sit crop identity and stage, the
health score with its direction of travel, the top threat with its level, when
the field was last actually looked at, and the agenda's own next action.

Nothing new is fetched: every value comes from a response the home screen had
already loaded. Two snapshots are required before a direction is drawn, because
one reading is not a trend.

**The bug worth recording** was found by mounting the screen against a backend
with `WEATHER_PROVIDER=none`. The threat cell fell through to a green "Nothing
firing" whenever the health request had failed — turning an outage into an
all-clear on the screen a farmer opens first. Saying nothing is firing now
requires positive evidence: weather present AND a board returned. Otherwise it
says the forecast is missing.

## IPM at a glance

The ladder already escalated correctly — monitor, cultural, biological, then
chemical behind the threshold gate — and there is deliberately no mechanical
rung, because `ipm.json` has no mechanical entries for any target and inventing
one would be the app making up agronomy. What was missing was legibility: the
four things the ladder turns on were spread over four cards and a collapsed
fold. They are now one strip above it — what was found and whether it was
measured or read off a photograph, the risk level now, which rung to start on,
and when to look again. Every value is the server's; none is a new judgement.

Also fixed there: the day's-work checklist keyed its rows on the agenda item's
KIND, so two infection models firing on one field both arrived as `model` —
duplicate React keys, and ticking one row ticked the other.

## Expert and officer consoles

The role has always come from `/api/auth/me` and App.jsx hands each role a
different product; a farmer could not see the other consoles because a farmer
may not open them. That is correct and is unchanged. What was missing was any
way to know they exist. `Modes` lists all four, states the account's own role,
and opens one only when the signed-in account already has it — no client-side
role, no mode switch, no demo bypass. Seeded demo credentials appear only when
the server reports `demo_mode`.

## Nearby hotspots

`/api/fields/{id}/nearby` already ran a Getis-Ord Gi* over confirmed diagnoses
per taluka and already knew every taluka's centroid, case count, incidence per
1,000 farms and z score. It was dropping the centroid on the way out. Adding it
back is the whole backend change — no new endpoint, no new table, no second
statistic.

The map is hand-drawn SVG, like every other chart here: an equirectangular
projection of ten centroids with longitude scaled by cos(latitude). No tile
layer — a mapping library would break both the 200 kB bundle gate and the
no-CDN rule, to draw roads nobody needs at district scale.

`test_isolation` guards this with a whitelist. It was widened deliberately,
not loosened: the added keys are taluka properties, every coordinate that
leaves must be one of the published centroids, and the substring check for the
field's own coordinates was replaced with a structural one — a centroid
legitimately shares leading digits with a field inside it, so the old form
reported a leak that was not one.

## Known limitations

- **The frontend has no test runner in the repository.** The screens above were
  verified by mounting them in jsdom against a live backend, with weather on
  and with `WEATHER_PROVIDER=none`, but that harness lives outside the repo
  rather than adding a test framework and its dependencies to it. The Home
  all-clear bug is exactly the class of thing it catches and `pytest` cannot.
- **The hotspot map is district-scale and unprojected.** Correct for ten
  talukas in one district; it would need a real projection before it covered a
  state.
- **Only confirmed diagnoses count towards a hotspot.** A taluka where nobody
  has scanned looks identical to one where nothing is wrong. The screen says
  what it counted, but it cannot distinguish absence of disease from absence of
  farmers using PRAHARI.
