# PRAHARI · roadmap

Work that is ready to be picked up, sized honestly, with the files to open. Take
one, open an issue with the same title, branch, and go.

Sizes are for someone who has read `CONTRIBUTING.md` and run the app once:
**S** ≈ an evening · **M** ≈ a weekend · **L** ≈ a week or more.

---

## Highest value first

### 1 · Train the vision model — **L** · nothing else unlocks as much
The single biggest gap. Every part of the pipeline is built and verified end to
end; there are no weights because the Kaggle dataset needs an account this build
environment could not reach.

`ml/README.md` has the seven commands. Needs a Kaggle account and a machine with
a GPU or patience.

**Do not** report the PlantVillage accuracy as field accuracy — the README
explains why (99% on PlantVillage, 19.73% on real photographs). Publish the
per-crop numbers from the held-out field split, and say plainly which crops the
model is bad at. A model that is honest about its weak crops is a better demo
than one that quotes a single inflated figure.

*Files:* `ml/`, then `export/register_model.py` and `VISION_PROVIDER=onnx`.

### 2 · Officer and expert consoles on the Saurjya identity — **M**
The farmer app was restyled; these two were deliberately left on the older
chrome because they are desktop-first. The backend is complete — hotspots,
outbreaks, queue, route planning, assignments, audit, the review workflow — so
this is presentation only.

*Files:* `frontend/src/screens/Officer.jsx`, `Expert.jsx`. Reuse the tokens in
`brand.css` and the patterns in `shell/shell.css`; do not invent a third look.

### 3 · The regional hotspot map — **M**
`outbreak.py` and `spatial.py` compute real clusters and the officer console
lists them. What is missing is the map: what, where, how fast, how confident,
confirmed or not.

Use aggregated taluka centroids, never field coordinates — the privacy boundary
is deliberate and `test_isolation.py` guards it. A decorative map with invented
markers is worse than the current list.

*Files:* `screens/Officer.jsx`, `GET /api/officer/hotspots`.

---

## Good second issues

### 4 · Community reports into the risk engine — **M**
`signals.py` and `community_cluster_signals` already grade corroborated reports
into regional signals, and the risk board reads them. The loop that is missing
is the farmer-facing half: when your neighbours report the same pest, your
prevention window should say so by name.

*Files:* `services/risk.py` (the `nearby` term), `screens/CropJourney.jsx`.

### 5 · Voice input for AgriDoc — **M** · high impact for low-literacy users
The literacy field on the farmer profile exists (`literacy: reads | voice_only`)
and is currently unused. Web Speech API for input, and read answers back.

Marathi recognition quality is the open question — test it before committing to
it, and fall back to the keyboard rather than shipping something that mishears
a pest name.

*Files:* `screens/Saathi.jsx`, `accounts.py`.

### 6 · Push notifications for a prevention window — **M**
`notifications` and `notification_deliveries` tables exist and the API writes to
them; delivery is currently in-app only. A window that opens while the farmer is
not looking at the app is the case the product exists for.

Web Push first, SMS second (`ivr_opt_in` / `sms_opt_in` are already on the
profile). Rate-limit it — an app that notifies daily gets muted before the day
it matters.

*Files:* `notify.py`, `routers/misc.py`.

### 7 · More crops — **S each** · no code required
Seven crops today. Each new one is a `crops.json` stage table, `problems.json`
entries for its diseases and pests, `thresholds.json` rows **with citations**,
and an `ipm.json` ladder.

Sorghum, chickpea, wheat, sugarcane and banana are the obvious next ones for
Maharashtra. Use the agronomy issue template; a row without a source will not be
merged.

*Files:* `backend/app/data/*.json` only.

### 8 · Crop-adaptive soil questions — **S**
`soil.py` asks the same six visual-assessment questions regardless of crop. A
paddy field and a grape vineyard do not have the same drainage question.

Keep the scoring transparent — the current version is a rule engine whose
arithmetic is visible, and that is a feature. Do not replace it with a model.

*Files:* `soil.py`, `screens/Soil.jsx`.

---

## Smaller, well-scoped

### 9 · Field boundary drawing — **M**
`plots.boundary` exists in the schema and is unused. Draw a polygon on a map,
compute the area from it instead of trusting a declared figure, and use it for
per-acre arithmetic.

### 10 · Export the season as a PDF — **S**
The crop health passport is the record a farmer needs at harvest and for any
residue question. `GET /api/plots/{id}/history` already returns all of it.

### 11 · One ordered history query — **S** · a known wart
`cropcalendar._history` queries five tables with a per-source limit, so a busy
field can return up to 2× the limit. Harmless, but a single `UNION ALL` ordered
by date would be correct.

### 12 · Marathi coverage audit — **S**
Every user-facing string should have an `_mr`. Some newer screens fall back to
English. Write the script that finds the gaps, then fill them.

### 13 · Officer bulk assignment — **S**
`POST /api/officer/assignments` takes one at a time. An officer with 14 field
visits wants to plan a route and assign them in one action; `routeplan.py`
already computes the route.

---

## Deliberately not doing

Recording these so nobody spends a weekend on them and finds out at the PR.

- **Crop recommendation** ("which crop should I plant"). Rejected in
  `soil.py`'s own docstring: the published versions train on a synthetic table
  with untraceable provenance, and a farmer who has already sown cannot act on
  the answer. PRAHARI is about protecting the crop in the ground.
- **Yield prediction.** No dataset behind it, and a wrong number here changes
  what someone borrows against.
- **Sentinel-2 field segmentation.** Assessed and deferred — see
  `prahari-reference-notes.md`. A raster pipeline and tile storage for a benefit
  the officer console does not currently lack.
- **A second chatbot.** AgriDoc exists and is grounded. Anything that answers
  from a general model rather than from field records is a different product.
- **A social feed.** Community is crop-health reporting that becomes a regional
  signal. Likes and follows do not serve early detection.

---

## Before the demo

- [ ] Trained model registered, per-crop metrics visible in the diagnosis response
- [ ] Officer console on the Saurjya identity
- [ ] A real hotspot map with confirmed and unconfirmed markers distinguished
- [ ] One rehearsed four-minute walkthrough (`README.md` has a suggested script)
- [ ] A deployed URL that is not localhost, on real weather, with `DEMO_MODE=false`
- [ ] Someone who did not write it can install and run it from `CONTRIBUTING.md` alone
