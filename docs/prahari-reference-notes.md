# Reference notes — external projects

Ideas only. No code, assets or datasets copied. Written once so later sessions
do not need to re-read the sources.

## Plant-Disease-Detection (zawrabh)
- **Idea worth taking:** none we do not already have. A single CNN → class name
  is the architecture PRAHARI deliberately rejects, because it cannot abstain.
- **Keep from it:** the simplicity of the inference path — load once, warm the
  session, one forward pass. `vision_service.OnnxClassifier` already does this.
- **Verdict:** no action. Our gap is weights, not architecture.

## Kaggle crop-disease-detection (snikhilrao) — the Phase 4 baseline
- PlantVillage-derived, folder-per-class (`Tomato___Late_blight`).
- `ml/datasets/cropdisease.py` **already adapts it**: discovers classes on
  disk, normalises folder names to (crop, condition), resolves through a
  reviewable alias table, and reports unmapped folders rather than dropping
  them silently.
- **The number that governs Phase 4:** PlantVillage-trained models score ~99%
  on PlantVillage and **19.73%** on real field photos (PlantDoc,
  arXiv:1911.10317). A model shown 8 background pixels and no leaf still scores
  49% (arXiv:2206.04374). Best in-the-wild result on PlantWild: 67.20%.
- **Therefore:** train on it, but never report its accuracy as field accuracy.
  Report per-crop metrics on a held-out real-photo set, and say plainly where
  the model is weak.

## InstanceSegmentation_Sentinel2 (chrieke)
- Concept: field-boundary delineation from Sentinel-2 via instance segmentation.
- **Relevant only to:** officer surveillance-gap mapping and auto field
  boundaries (`plots.boundary` column already exists and is unused).
- **Verdict:** defer. Adds a raster pipeline and tile storage for a benefit the
  officer console does not currently lack. Revisit only if boundary drawing
  becomes the bottleneck. Not a Phase 1–9 item.

## OpenWeedLocator (geezacoleman)
- Concept: cheap on-device CV for weed detection, with GPS-tagged hits.
- **Already partly ours:** `vision.weed_cover()` + `/api/agronomy/weeds` +
  `weed_checks` table exist and work.
- **Worth taking:** the *spatial* half — attach lat/lng and severity to each
  weed/pest check so a within-field hotspot map becomes possible. Cheap:
  observations already carry a plot, and plots carry lat/lng.
- **Do not take:** the Raspberry Pi hardware path. Phone-first.

## FS25_SoilFertilizer (Realistic-Farming)
- Game mod. **Check the licence before reading its code at all**; we have not,
  and do not need to — the idea alone is enough.
- Concept worth translating: soil as *persistent per-field state* that depletes
  with cropping, is replenished by fertiliser, and is modified by weather —
  rather than a one-off test result.
- **For PRAHARI this becomes FIELD SOIL HISTORY:** `soil_tests` already stores
  a row per test with a date. The extension is a per-plot timeline plus
  application events, so a farmer sees the trend, not a snapshot. No game-style
  simulation, no invented depletion coefficients.

## precision-agriculture-using-machine-learning (atharval1)
- Crop recommendation from N-P-K-temp-humidity-pH-rainfall via random forest.
- **Explicitly rejected**, and `backend/app/soil.py` already documents why: the
  training table is synthetic with untraceable provenance, the output is a crop
  name with no reasoning, and a farmer who has already sown cannot act on it.
- **Taken instead:** the nutrient-gap framing — what the soil has vs. what the
  crop in the ground needs, with the arithmetic visible.

## AgriTech (omroy07)
- Useful only as a deployment-shape reference; ours is further along
  (Docker + Render single-origin + CI already in place).
- **One idea worth keeping:** farmer-to-farmer collaboration as a first-class
  surface. PRAHARI's community already exists; the improvement is routing it
  into the risk engine as a regional signal, which Phase 7 covers.

## Harvestify (Gladiator07)
- Same crop-recommendation architecture as above. Same rejection.
- **Nothing to take.** PRAHARI's objective is disease and pest *prevention*,
  not crop selection.

## Standing rule extracted from all seven
Every one of these projects reports a single headline accuracy from a clean
dataset. PRAHARI's differentiator is the opposite discipline: per-crop metrics,
an abstention path, and a stated provenance for every number. Where a reference
conflicts with that, the reference loses.
