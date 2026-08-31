# PRAHARI Vision — the model pipeline

This directory is the honest half of the "AI" in PRAHARI. It exists so the
vision seam in `backend/app/vision_service.py` can be filled by a model that
was actually trained and actually evaluated — and so that nobody, including us,
can quote an accuracy number that no evaluation produced.

## The one number that matters

> A model trained on PlantVillage scores **99% on PlantVillage** and
> **19.73% on real field photographs** (PlantDoc, arXiv:1911.10317).
> A model shown eight background pixels and **no leaf at all** still scores
> **49%** on PlantVillage (arXiv:2206.04374) — the label is partly recoverable
> from the laboratory backdrop.
> The best published result on the largest in-the-wild benchmark, PlantWild,
> is **67.20%**.

So: **do not train on PlantVillage and report the PlantVillage number.** The
pipeline below is built to make that mistake hard.

## The PlantDoc adapter

`datasets/plantdoc.py` is the entry point, and it does three things a plain
folder-loader would not.

**It refuses to silently cross crops.** PlantDoc has *Squash Powdery mildew
leaf*. PRAHARI's `powdery_mildew` is *Erysiphe necator* on grape; *Podosphaera
xanthii* on squash is a different organism on a different host. Labelling one as
the other to inflate a class count is how a model learns to be confidently
wrong, so cross-crop mappings are marked and **excluded by default**.

**It builds the `unknown` class from real photographs.** PlantDoc's apple,
cherry, peach, raspberry, strawberry and bell-pepper classes are crops PRAHARI
does not model — perfect out-of-distribution training data. So are the *tomato*
problems PRAHARI deliberately does not model: Septoria leaf spot, bacterial
spot, leaf mould, TYLCV, mosaic virus, spider mites. Those are the hardest and
most valuable rows in the set — a real tomato leaf, with a real disease, that is
not one of the four PRAHARI knows. Without them the model has no way to learn
*"this is a tomato problem I was not taught"*, and it will hand a farmer the
closest thing it does know. On a full PlantDoc run `unknown` is roughly two
thirds of the corpus.

**It is honest about the split it can support.** PlantDoc carries no plant or
field identifier, so a *true* field-grouped split is not constructible from it.
The adapter groups on filename stem, writes that limitation into the manifest,
and says any accuracy from a PlantDoc-only split is an upper bound. Production
rows harvested by `export/export_confirmed.py` carry a real `plot_id` — those
give a genuine field split, and they are what a reported number should
eventually rest on.

Every mapping decision, with its reason, is written into the manifest under
`mapping.table` so a reviewer can argue with it.

## The Kaggle crop-disease adapter

`datasets/cropdisease.py` reads the [Crop Disease Detection
Dataset](https://www.kaggle.com/datasets/snikhilrao/crop-disease-detection-dataset)
and any dataset using the PlantVillage folder convention
(`Tomato___Late_blight`, `Corn_(maize)___Common_rust_`, …).

It was written **without the files in hand** — the dataset is behind a Kaggle
account — so it does not ship a hard-coded class list, which would be a list of
guesses that silently drops whatever it guessed wrong. Instead it discovers the
folders on disk, tokenises each name into a crop and a condition, resolves those
against an explicit alias table you can read and argue with, and **reports every
folder it could not map, by name and image count.** Run it once and read the
report; anything in `unmapped_classes` is either a crop PRAHARI does not model
(good `unknown` training data) or a naming variant that needs one line adding.

Three refusals are built in and each has a test in
`backend/tests/test_ml_adapters.py`:

* **It will not cross a crop boundary.** `Squash___Powdery_mildew` is
  *Podosphaera xanthii*; PRAHARI's `powdery_mildew` is *Erysiphe necator* on
  grape. Merging them adds several hundred images to a class, makes every
  metric look better, and teaches the model that squash mildew is grape mildew.
  Nothing downstream can detect that — not the validation split, not the
  confusion matrix, not a demo.
* **It will not invent a label** PRAHARI has no reference for. It stops and
  tells you.
* **It will not claim a field-grouped split it cannot make.** These datasets
  carry no field identifier, so the manifest records
  `field_grouping: "filename-stem (WEAK)"`. Only photographs harvested from
  PRAHARI itself carry a real plot id.

```bash
pip install kaggle                       # kaggle.json in ~/.kaggle/
kaggle datasets download -d snikhilrao/crop-disease-detection-dataset \
    -p data/raw --unzip
python -m datasets.cropdisease --root data/raw --out datasets/manifest.json \
    --unknown-from-unmapped --merge datasets/plantdoc.json
```

`--unknown-from-unmapped` puts potato, apple, squash and the rest into the
`unknown` class rather than discarding them. Take it: a plant-disease model
with no `unknown` class answers confidently when shown a photograph of a hand.

## Crop coverage

`ml/labels.json` is generated from `backend/data/problems.json` and is the
model's output order — a contract with the exported ONNX file. There is a test
asserting the two stay in step, because adding a disease to `problems.json` and
forgetting `labels.json` makes a deployed model return the wrong class *name*
for every prediction while every metric stays green.

All seven crops now carry a reference set of at least two real candidates plus
`healthy` and `nitrogen_deficiency`. Before this, cotton, soybean and pigeonpea
had `vision: false` and the camera abstained on them with `crop-not-covered` —
three of the seven crops PRAHARI claims to serve. Diseases with no implementable
published infection model carry `no_model_note` saying **why** there is no
forecast (vector-borne, soil-borne, or no rule that can be run on a public
weather feed), and they stay on the risk board marked `unforecast` rather than
vanishing from it — an empty risk screen reads as "this crop has no diseases".
Where a model is borrowed from a related pathogen (TOMCAST on onion and maize;
Hutton on pigeonpea *Phytophthora*) the entry carries `model_caveat`, and the
caveat is shown wherever the model fires.

## Datasets

| Dataset | Licence | Use |
|---|---|---|
| Crop Disease Detection (snikhilrao) | see the Kaggle page | folder-per-class training data, via `datasets/cropdisease.py` |
| PlantDoc | CC BY 4.0 | field photographs — primary training and test |
| PlantWild | CC BY-NC-ND 4.0 | in-the-wild benchmark — **check the licence before any commercial claim** |
| IP102 (subset) | research use | insect classes |
| PlantVillage | CC0 | *pre-training only, never the reported test set* |
| PRAHARI field corpus | collected in production | expert-confirmed observations (see below) |

`datasets/manifest.example.json` shows the record shape. Every training record
carries image, crop, label, location, date, crop stage, source, expert label,
expert confidence, verification status, the model prediction at the time and
the model version that made it.

**The test split is by FIELD, not by image.** Two photographs of the same leaf
on the same afternoon are not independent samples, and splitting by image
inflates every number you report by ten points or more.

## The loop back from production

    expert confirmation                (API: POST /api/expert/cases/{id}/review)
            ↓
    verified observation dataset       (export/export_confirmed.py)
            ↓
    quality review by a human          — manual, and deliberately so
            ↓
    training dataset version           (datasets/manifest.json, versioned)
            ↓
    periodic retraining                (training/train.py)
            ↓
    evaluation on a held-out FIELD split (evaluation/evaluate.py)
            ↓
    approval                           — a human decision, recorded
            ↓
    deployment                         (export/export_onnx.py → VISION_MODEL_PATH)

A production model is **never** updated from a single expert confirmation. The
only thing that moves at request time is one integer in the taluka's Dirichlet
prior, and that is visible, auditable and reversible.

## Commands

```bash
pip install -r requirements.txt          # torch, timm, onnx, onnxruntime

# 1 · get the field photographs and turn them into a PRAHARI manifest
git clone https://github.com/pratikkayal/PlantDoc-Dataset data/raw/plantdoc
python -m datasets.plantdoc --root data/raw/plantdoc --out datasets/plantdoc.json

# 1a · add the Kaggle crop-disease set, and keep the unmodelled crops as `unknown`
kaggle datasets download -d snikhilrao/crop-disease-detection-dataset -p data/raw --unzip
python -m datasets.cropdisease --root data/raw --merge datasets/plantdoc.json \
       --unknown-from-unmapped --out datasets/manifest.json

# 1b · (later) fold in what your own experts have confirmed in production
python -m export.export_confirmed --out datasets/confirmed.json
python -m datasets.plantdoc --root data/raw/plantdoc \
       --merge datasets/confirmed.json --out datasets/manifest.json

# 2 · split, train, evaluate, export
python -m preprocessing.prepare  --manifest datasets/manifest.json --out data/prepared
python -m training.train         --data data/prepared --arch mobilenetv4_conv_small --epochs 30
python -m evaluation.evaluate    --checkpoint runs/latest/best.pt --split test
python -m export.export_onnx     --checkpoint runs/latest/best.pt --out models/prahari-vision-0.2.onnx
```

Then point the backend at it:

```bash
VISION_PROVIDER=onnx
VISION_MODEL_PATH=/models/prahari-vision-0.2.onnx
VISION_MODEL_LABELS=/models/labels.json
VISION_MODEL_VERSION=0.2
```

## What the model must output

Classes use the **same ids as `backend/data/problems.json`**, plus two that are
not diseases:

    late_blight early_blight downy_mildew powdery_mildew purple_blotch
    turcicum_blight nitrogen_deficiency healthy unknown

`unknown` is trained on out-of-distribution images (other crops, soil, hands,
sky, packaging) and is the model's own escape hatch. It is *not* a substitute
for the abstention logic in `diagnose.py`, which runs on top of it — the two are
independent, and both have to agree before a diagnosis is shown.

## What you may claim

* Nothing, until `evaluation/evaluate.py` has run on a field-split test set.
* Then: exactly the number it printed, with the split it printed it for.
* `model_versions.metrics` in the database is where that number lives. The UI
  reads it from there, and prints *"no evaluation recorded"* when it is null.

Anything else — a badge, a pitch deck, a slide — is a fabrication.

---

## Training the model — the exact path

The pipeline below has been **run end to end and works**. What it has not been
run on is real data, because the Kaggle dataset is behind an account and the
build environment this was assembled in had no route to it. So there are **no
trained weights in this repository, and no accuracy is claimed anywhere in the
product.** `VISION_PROVIDER` ships as `none`; the app says "no evaluated model"
rather than dressing the symptom-feature engine up as a neural network.

To produce weights:

```bash
pip install -r ml/requirements.txt

# 1 · get the dataset (needs a Kaggle account and ~/.kaggle/kaggle.json)
kaggle datasets download -d snikhilrao/crop-disease-detection-dataset \
  -p data/raw --unzip

# 2 · build a manifest. The adapter discovers the classes on disk, maps folder
#     names through the reviewable alias table, and REPORTS what it could not
#     map instead of dropping it silently. Read that report.
python -m datasets.cropdisease --root data/raw --out data/manifest.json

# 3 · split, grouped by field so no field appears in two splits
python -m preprocessing.prepare --manifest data/manifest.json --out data/prepared

# 4 · train
python -m training.train --data data/prepared --epochs 30

# 5 · evaluate on the held-out FIELD split — this is the only number to publish
python -m evaluation.evaluate --checkpoint runs/latest/best.pt --data data/prepared

# 6 · export, with parity against the torch model checked
python -m export.export_onnx --checkpoint runs/latest/best.pt \
  --out models/prahari-vision-1.0.0.onnx

# 7 · register, so the API can report the metrics alongside every diagnosis
python -m export.register_model --onnx models/prahari-vision-1.0.0.onnx \
  --metrics evaluation/metrics.json --version 1.0.0
```

Then:

```
VISION_PROVIDER=onnx
VISION_MODEL_PATH=models/prahari-vision-1.0.0.onnx
VISION_MODEL_LABELS=ml/labels.json
VISION_MODEL_VERSION=1.0.0
```

### `--no-pretrained`

`training.train` takes ImageNet initialisation from `timm`, which is fetched over
the network the first time an architecture is seen. `--no-pretrained` skips it so
an air-gapped box or a CI runner with no egress can still exercise the pipeline.
A model trained from scratch on a few thousand leaves is markedly worse, so the
run card records `pretrained_init` and `deployable` — a from-scratch checkpoint is
a pipeline test and the card says so, rather than leaving the two
indistinguishable on disk.

### What the pipeline was verified to do

Run on a synthetic 450-image manifest (25 classes × 6 synthetic "fields"), with
`--no-pretrained`:

- `preprocessing.prepare` produced a field-grouped train/val/test split and
  refused to let a field appear in two splits;
- `training.train` trained and wrote a run card carrying the dataset version, the
  split policy, the seed and the git commit, and printed *"Do NOT quote the
  validation number"*;
- `evaluation.evaluate` produced per-class precision/recall/F1, a confusion
  matrix and an abstention/coverage curve;
- `export.export_onnx` exported and checked numerical parity against the torch
  model (max delta 2.05e-05);
- the backend loaded the resulting `.onnx` through `VISION_PROVIDER=onnx`,
  reported `engine: onnx · is_neural_model: true`, ran inference on a real
  upload, and **abstained** — *"No candidate reaches the 46% confidence floor.
  The strongest is Late blight at 44%."*

That last line is the seam working exactly as intended. The numbers themselves
are meaningless — the images were synthetic — and no figure from that run appears
anywhere in the product.
