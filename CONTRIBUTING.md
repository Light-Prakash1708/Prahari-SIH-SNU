# Contributing to PRAHARI

Welcome. This file is short on ceremony and specific about the few things that
are not negotiable.

---

## Get running in five minutes

```bash
git clone https://github.com/Light-Prakash1708/PRAHARI-SIH-2026.git
cd PRAHARI-SIH-2026
cp .env.example .env          # then set JWT_SECRET (any 32+ random chars locally)

./run.sh --demo               # migrates, seeds, serves the API on :8000
```

In a second terminal, for live frontend reloading:

```bash
cd frontend && npm install && npm run dev     # :5173, proxies /api to :8000
```

`--demo` turns on generated weather and demo scenarios. Use it — the real
weather provider needs outbound network and will refuse to invent data without
it, which is correct behaviour and a confusing first experience.

Run the tests before you push:

```bash
cd backend && python -m pytest tests -q      # 237 tests, ~100s
cd frontend && npm run build                 # must be clean
```

---

## The five rules

Everything else is style. These five are the product.

### 1. Never fabricate a number a farmer might act on

If the data is not there, the screen says it is not there. A missing weather
reading is an error, not a default. A blank nutrient field is **not measured**,
never zero — zero is a reading, and an alarming one.

There is a test asserting each of these. If you find yourself deleting one to
make a feature work, the feature is wrong.

### 2. Every number carries its source

A threshold shows its ICAR citation. A risk level names the infection model
that produced it. A dose shows the arithmetic, so a farmer can check the
shopkeeper's sum. `<Prov>` in `frontend/src/ui.jsx` is where "who says so"
lives; use it.

### 3. The model is allowed to say "I don't know"

An abstention is an answer. Low confidence routes to a human expert; it does
not pick the least-bad label. Do not add a code path that turns an abstention
into a guess, and do not let repeated uploads of the same leaf talk the engine
out of one — `backend/tests/test_multi_image.py` guards this.

### 4. Cost never touches an agronomic decision

The farm ledger is bookkeeping. It is not read by the risk engine, the economic
threshold, or the IPM ladder, and `test_farm_ledger.py` asserts that recording
costs changes none of them. The moment a cheap intervention can outscore a
correct one, the app is giving agricultural advice on financial grounds.

### 5. Nothing authorises a chemical except a count against a threshold

Knowing what a disease is does not permit a spray. A count does, measured
against the economic threshold for that pest at that crop stage, and only after
the IPM ladder has been climbed from the bottom. Chemistry is the last rung.

---

## Where things live

```
backend/app/
  routers/        HTTP only — validate, call a service, shape the response
  services/       risk, diagnosis, decisions — the agronomy lives here
  data/*.json     the knowledge base: crops, problems, thresholds, IPM, labels
  schema/*.sql    migrations, applied in order, never edited once merged
frontend/src/
  api.js          the ONE place that talks to the backend
  screens/        one file per screen
  shell/          header, drawer, account sheet, bottom bar, icons
  ui.jsx          primitives — Card, Gauge, Camera, Prov…
ml/               dataset adapters, training, evaluation, ONNX export
docs/             status, architecture, roadmap, reference notes
```

**Routers hold no agronomy.** If you are writing a threshold comparison inside
a router, it belongs in a service. `backend/app/cropcalendar.py` is the model to
copy: it composes services and owns no logic of its own.

**One API layer.** Do not add `fetch()` calls inside components. Add a method to
`frontend/src/api.js` — it handles the token, the offline cache and the retry
queue, and a component that bypasses it silently loses all three.

---

## Adding a feature

Work in this order. It is faster than it looks, because most of the backend
already exists.

1. **Search before you build.** `grep -rn "keyword" backend/app/routers` first.
   Most "missing" endpoints are already there under a different name.
2. **Reuse → extend → build.** In that order. A new table needs a reason that
   fits in one sentence; `schema/004_ledger.sql` has one at the top explaining
   why the money ledger could not live in `applications`.
3. **Write the test that would catch you being wrong.** Not the happy path —
   the one asserting the thing that must never happen.
4. **Then the screen.** Loading, empty, error and retry states are required, not
   polish. A screen that shows a spinner forever on a dead connection is broken.

### Adding a crop, disease, pest or threshold

Most agronomy work needs no code at all — it is a JSON edit in
`backend/app/data/`. Every threshold row **must** carry a `source` naming the
ICAR / SAU / package-of-practice publication it came from. A row without a
citation will not be merged, because a farmer cannot audit it and neither can a
judge.

---

## Branches and pull requests

```
main                      always deployable; CI green
feat/<short-name>         a feature
fix/<short-name>          a bug
data/<crop-or-pest>       knowledge-base additions
```

Branch from `main`, keep it small, open a PR. The template asks four questions;
answer them honestly — "I did not test this on a phone" is a useful answer.

CI runs backend lint + 237 tests, applies the migrations to a real PostgreSQL,
checks the production config guards actually refuse bad settings, builds the
frontend, **fails if the gzipped bundle exceeds 200 kB**, and builds and boots
the Docker image. All of it must pass.

---

## Things that will get a PR sent back

- A number on screen with no source behind it
- A new `fetch()` outside `api.js`
- Business logic in a router
- A migration that alters or drops an existing column
- A test deleted to make something pass
- An accuracy figure that no evaluation produced
- `console.log` left in, or a commented-out block "for later"
- A dependency added to do something the standard library does

---

## The offline rule

This app is built for a phone with no signal in a field at midday. Fonts and
icons are **bundled, never fetched** — the Marathi interface renders as empty
boxes if its font comes from a CDN that is unreachable. Do not add a Google
Fonts link, a Font Awesome CDN, or a charting library. Icons go in
`shell/Icon.jsx` as inline SVG; charts are hand-drawn SVG in `ui.jsx`.

---

## Questions worth asking before you start

- Does this make the app better at **early detection and prevention of crop
  disease and pest infestation**? That is the problem statement. A feature that
  makes PRAHARI a more general farming app makes it a worse answer to it.
- Would an agronomist be able to argue with the output? If not, it is not
  showing enough of its working.
- What does this screen do when the server is down?
