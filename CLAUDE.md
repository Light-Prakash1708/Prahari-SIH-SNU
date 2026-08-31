# PRAHARI — notes for an AI assistant working in this repo

Read this before changing anything. It exists because the rules below are easy
to break helpfully.

## What this is

An early-warning system for crop disease and pest infestation, built for SIH
2026 (Maharashtra State Innovation Society). FastAPI + React/Vite + an ONNX
vision seam. Not a general farming app.

## Read first, in this order

1. `docs/prahari-upgrade-status.md` — current state and known limitations
2. `docs/ARCHITECTURE.md` — where everything lives
3. `CONTRIBUTING.md` — the five rules
4. `docs/ROADMAP.md` — what is worth doing next

Do not audit the whole repository to answer a question. Grep for the thing.

## The five rules, restated for a model

These are enforced by tests. If a test blocks you, the code is wrong.

1. **Never fabricate a number a farmer might act on.** Missing weather is a 503,
   not a default. A blank soil field is "not measured", never zero.
2. **Every number carries its source.** Thresholds cite ICAR. Risk levels name
   the infection model. Doses show the arithmetic.
3. **The model may abstain.** Never add a path that turns low confidence into a
   guess, or lets repeated uploads produce a diagnosis by persistence.
4. **Cost never reaches an agronomic decision.** The ledger is bookkeeping.
5. **Only a count against a threshold authorises a chemical.**

## Before writing code

- **Search first.** `grep -rn "keyword" backend/app/routers`. Most "missing"
  endpoints already exist. Reuse → extend → build, in that order.
- **Routers hold no agronomy.** `backend/app/cropcalendar.py` is the model: it
  composes services and owns nothing.
- **One API layer.** Add to `frontend/src/api.js`. Never `fetch()` in a component.
- **Never edit a merged migration.** Add a new numbered file.
- **Never drop, truncate or reseed.** Farmer, diagnosis and trap records are not
  recreatable.

## Traps specific to this codebase

- `plots.area_acre` and `crop_cycles.sown_on` are NOT NULL. The "unknown" case
  is a missing cycle, not a null column.
- `trap_observations` has no `plot_id` — join through `traps`.
- Diagnoses use `top_problem` / `top_posterior` / `abstained`, not
  `problem` / `confidence`.
- The observation view nests under `observation` and calls the ranked list
  `differential`, with `confidence`, not `posterior`.
- A follow-up is open when it has **neither** a `done_observation` **nor** an
  `outcome`. Getting this wrong leaves a closed follow-up on the home screen
  forever.
- `stage_factor` values only mean anything **relative to the same pest**.
  Banding them against fixed cutoffs makes almost every stage red and says
  nothing. This was fixed once; do not reintroduce it.

## Offline is not optional

Fonts and icons are bundled, never fetched — a CDN font renders the Marathi
interface as empty boxes on the phone this was built for. No Google Fonts link,
no Font Awesome CDN, no charting library. Icons are inline SVG in
`shell/Icon.jsx`; charts are hand-drawn SVG in `ui.jsx`. CI fails above 200 kB
gzipped.

## Testing

```bash
cd backend && python -m pytest tests -q     # 237 tests, ~100s
cd frontend && npm run build                # must be clean
```

Run the full suite before saying something works. When adding a feature, write
the test that would catch you being wrong — not the happy path.

## Honesty about the model

There are no trained vision weights in this repo. `VISION_PROVIDER=none`.
**Never write an accuracy figure that an evaluation did not produce**, and never
present a PlantVillage number as field performance — the gap is 99% vs 19.73%.
`ml/README.md` has the details.

## When you finish a piece of work

Update `docs/prahari-upgrade-status.md` — keep it short, and record what is
known to be broken as well as what works. A limitation stated is worth more than
a limitation discovered during judging.
