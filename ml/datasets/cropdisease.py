"""
PRAHARI Vision · Kaggle crop-disease adapter
════════════════════════════════════════════════════════════════════════════
Turns a folder-per-class crop-disease dataset into a PRAHARI training manifest.

Written for:

    Crop Disease Detection Dataset — snikhilrao (Kaggle)
    https://www.kaggle.com/datasets/snikhilrao/crop-disease-detection-dataset

and, by construction, for any dataset that uses the PlantVillage folder
convention — `Tomato___Late_blight`, `Corn_(maize)___Common_rust_`,
`Potato___healthy` and so on. That convention is near-universal in this corner
of Kaggle, which is why this adapter matches on the SHAPE of a folder name
rather than on a hard-coded list of the folders one particular download
happens to contain.

WHY IT DOES NOT SHIP A FIXED CLASS LIST
---------------------------------------
The dataset is behind a Kaggle account. This adapter was written without the
files in hand, and a hard-coded class list written blind would be a list of
guesses that silently drops whatever it guessed wrong. So instead:

  · it DISCOVERS the classes on disk,
  · normalises each folder name into (crop token, condition tokens),
  · resolves those tokens against PRAHARI's own labels through the explicit,
    reviewable alias table below,
  · and REPORTS every folder it could not map, by name and image count,
    instead of quietly skipping it.

Run it once and read the report. Anything in `unmapped_classes` is either a
crop PRAHARI does not model — in which case it becomes `unknown` training data
if you pass --unknown-from-unmapped, which is exactly what you want — or a
naming variant that needs one line added to ALIASES.

WHAT IT REFUSES TO DO
---------------------
1 · CROSS A CROP BOUNDARY. `Squash___Powdery_mildew` is Podosphaera xanthii.
    PRAHARI's `powdery_mildew` is Erysiphe necator on grape. Different
    organism, different host. The mapping is refused unless the crop matches,
    and a refusal is reported rather than hidden — inflating a class count by
    merging two pathogens is how a model learns to be confidently wrong.

2 · INVENT A LABEL PRAHARI HAS NO REFERENCE FOR. If a folder maps to a
    condition that is not in ml/labels.json, the adapter stops and tells you,
    rather than dropping the images or bending them into the nearest class.

3 · CLAIM A FIELD-GROUPED SPLIT IT CANNOT MAKE. Like PlantDoc, these datasets
    carry no field or plant identifier. The manifest groups by filename stem
    and records `field_grouping: "filename-stem (weak)"` so the number that
    comes out of evaluation is not read as something stronger than it is. Only
    photographs harvested from PRAHARI itself carry a real plot id.

Usage
-----
    pip install kaggle                      # then put your kaggle.json in ~/.kaggle/
    kaggle datasets download -d snikhilrao/crop-disease-detection-dataset \\
        -p data/raw --unzip

    python -m datasets.cropdisease --root data/raw --out datasets/manifest.json \\
        --unknown-from-unmapped
    python -m preprocessing.prepare --manifest datasets/manifest.json --out data/prepared
    python -m training.train --data data/prepared --out runs/v2
    python -m export.export_onnx --run runs/v2 --out ../backend/models/prahari-vision.onnx

Nothing in PRAHARI reads a model file that is not there. If you never run this,
the API keeps saying so — see app/vision_service.py — rather than pretending a
classifier exists.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LABELS = json.loads((ROOT / "labels.json").read_text())["labels"]

CITATION = ("Crop Disease Detection Dataset (snikhilrao), Kaggle. "
            "https://www.kaggle.com/datasets/snikhilrao/crop-disease-detection-dataset")

# ── crop tokens ─────────────────────────────────────────────────────────────
# The left side is what appears in a folder name; the right side is a PRAHARI
# crop id, or None for a crop PRAHARI does not model (which makes it useful
# out-of-distribution data, not useless data).
CROPS: dict[str, str | None] = {
    "tomato": "tomato",
    "grape": "grape", "grapes": "grape",
    "onion": "onion",
    "corn": "maize", "maize": "maize", "corn_maize": "maize",
    "cotton": "cotton",
    "soybean": "soybean", "soyabean": "soybean", "soy": "soybean",
    "pigeonpea": "pigeonpea", "pigeon_pea": "pigeonpea", "redgram": "pigeonpea",
    "tur": "pigeonpea", "arhar": "pigeonpea",
    # modelled by nobody here — deliberate `unknown` material
    "potato": None, "pepper": None, "pepper_bell": None, "bell_pepper": None,
    "apple": None, "blueberry": None, "cherry": None, "peach": None,
    "raspberry": None, "strawberry": None, "squash": None, "orange": None,
    "rice": None, "wheat": None, "sugarcane": None, "chilli": None, "chili": None,
    "banana": None, "cassava": None, "coffee": None, "cucumber": None,
    "guava": None, "lemon": None, "mango": None, "papaya": None, "groundnut": None,
}

# ── condition tokens ────────────────────────────────────────────────────────
# Each entry names the PRAHARI label AND the crop that label is defined for.
# `crop=None` means the label is crop-agnostic (healthy, a deficiency).
ALIASES: list[dict[str, Any]] = [
    {"match": ("late", "blight"), "label": "late_blight", "crop": "tomato",
     "note": "Phytophthora infestans. PRAHARI defines this label on tomato."},
    {"match": ("early", "blight"), "label": "early_blight", "crop": "tomato",
     "note": "Alternaria solani on tomato."},
    {"match": ("septoria",), "label": "septoria_tomato", "crop": "tomato",
     "note": "Septoria lycopersici."},
    {"match": ("leaf", "mold"), "label": None, "crop": "tomato",
     "note": "Passalora fulva — PRAHARI has no reference for tomato leaf mould."},
    {"match": ("yellow", "leaf", "curl"), "label": "leaf_curl_tomato", "crop": "tomato",
     "note": "Tomato yellow leaf curl virus."},
    {"match": ("mosaic", "virus"), "label": None, "crop": "tomato",
     "note": "Tobacco mosaic on tomato — no PRAHARI reference."},
    {"match": ("spider", "mites"), "label": None, "crop": "tomato",
     "note": "Mite damage, not a disease. PRAHARI handles mites through scouting."},
    {"match": ("target", "spot"), "label": None, "crop": "tomato",
     "note": "Corynespora cassiicola — no PRAHARI reference."},
    {"match": ("bacterial", "spot"), "label": None, "crop": "tomato",
     "note": "Xanthomonas on tomato — PRAHARI's bacterial blight label is COTTON's."},

    {"match": ("black", "rot"), "label": None, "crop": "grape",
     "note": "Guignardia bidwellii — no PRAHARI reference."},
    {"match": ("esca",), "label": None, "crop": "grape", "note": "Trunk disease complex."},
    {"match": ("anthracnose",), "label": "anthracnose_grape", "crop": "grape",
     "note": "Elsinoe ampelina."},
    {"match": ("downy", "mildew"), "label": "downy_mildew", "crop": "grape",
     "note": "Plasmopara viticola. The ONION downy mildew is a different organism "
             "and a different label — see the entry below."},
    {"match": ("powdery", "mildew"), "label": "powdery_mildew", "crop": "grape",
     "note": "Erysiphe necator."},

    {"match": ("purple", "blotch"), "label": "purple_blotch", "crop": "onion",
     "note": "Alternaria porri."},
    {"match": ("stemphylium",), "label": "stemphylium_blight_onion", "crop": "onion",
     "note": "Stemphylium vesicarium."},

    {"match": ("northern", "leaf", "blight"), "label": "turcicum_blight", "crop": "maize",
     "note": "Exserohilum turcicum — 'northern leaf blight' and 'turcicum' are the same."},
    {"match": ("turcicum",), "label": "turcicum_blight", "crop": "maize"},
    {"match": ("maydis",), "label": "maydis_blight_maize", "crop": "maize"},
    {"match": ("southern", "leaf", "blight"), "label": "maydis_blight_maize", "crop": "maize",
     "note": "Bipolaris maydis."},
    {"match": ("common", "rust"), "label": "common_rust_maize", "crop": "maize",
     "note": "Puccinia sorghi."},
    {"match": ("cercospora",), "label": None, "crop": "maize",
     "note": "Grey leaf spot on maize — PRAHARI's cercospora label is SOYBEAN's."},
    {"match": ("gray", "leaf", "spot"), "label": None, "crop": "maize"},

    {"match": ("bacterial", "blight"), "label": "bacterial_blight_cotton", "crop": "cotton",
     "note": "Xanthomonas citri pv. malvacearum."},
    {"match": ("grey", "mildew"), "label": "grey_mildew_cotton", "crop": "cotton"},
    {"match": ("gray", "mildew"), "label": "grey_mildew_cotton", "crop": "cotton"},
    {"match": ("areolate",), "label": "grey_mildew_cotton", "crop": "cotton",
     "note": "Areolate mildew is Ramularia areola — the same organism."},
    {"match": ("leaf", "curl"), "label": "leaf_curl_cotton", "crop": "cotton"},

    {"match": ("rust",), "label": "soybean_rust", "crop": "soybean",
     "note": "Phakopsora pachyrhizi. Matched only when the crop token is soybean."},
    {"match": ("frogeye",), "label": "cercospora_soybean", "crop": "soybean"},
    {"match": ("frog", "eye"), "label": "cercospora_soybean", "crop": "soybean"},
    {"match": ("cercospora",), "label": "cercospora_soybean", "crop": "soybean"},
    {"match": ("yellow", "mosaic"), "label": "yellow_mosaic_soybean", "crop": "soybean"},
    {"match": ("mosaic",), "label": "yellow_mosaic_soybean", "crop": "soybean"},

    {"match": ("wilt",), "label": "fusarium_wilt_pigeonpea", "crop": "pigeonpea"},
    {"match": ("fusarium",), "label": "fusarium_wilt_pigeonpea", "crop": "pigeonpea"},
    {"match": ("sterility", "mosaic"), "label": "sterility_mosaic_pigeonpea",
     "crop": "pigeonpea"},
    {"match": ("phytophthora",), "label": "phytophthora_blight_pigeonpea", "crop": "pigeonpea"},

    # crop-agnostic
    {"match": ("healthy",), "label": "healthy", "crop": None},
    {"match": ("nitrogen",), "label": "nitrogen_deficiency", "crop": None},
    {"match": ("deficiency",), "label": "nitrogen_deficiency", "crop": None},
]

_SPLIT = re.compile(r"[^a-z0-9]+")

# "leaf" appears in about half of these folder names and carries no information
# — `Tomato___Tomato_Yellow_Leaf_Curl_Virus` and `cotton_leaf_curl` are the same
# shape with and without it. It is dropped from BOTH the folder tokens and the
# alias match tuples, so an alias cannot fail to match because one dataset
# author wrote "leaf" and another did not.
_NOISE = {"leaf", "leaves"}
for _a in ALIASES:
    _a["match"] = tuple(t for t in _a["match"] if t not in _NOISE) or _a["match"]


def tokenise(folder: str) -> tuple[str | None, list[str], bool]:
    """`Corn_(maize)___Common_rust_` → ('maize', ['common', 'rust'], True).

    Returns (crop_id, condition tokens, crop_recognised). A crop that is
    recognised but not modelled comes back as (None, ..., True) — which is the
    difference between "we know this is a potato and we do not model potatoes"
    and "we have no idea what this folder is"."""
    raw = folder.strip().lower()
    head, sep, tail = raw.partition("___")
    if not sep:
        parts = _SPLIT.split(raw)
        head, tail = parts[0] if parts else "", " ".join(parts[1:])
    head_tokens = [t for t in _SPLIT.split(head) if t]
    tail_tokens = [t for t in _SPLIT.split(tail) if t]

    crop_id, recognised, used = None, False, 0
    for n in (3, 2, 1):
        key = "_".join(head_tokens[:n])
        if key in CROPS:
            crop_id, recognised, used = CROPS[key], True, n
            break
    conditions = head_tokens[used:] + tail_tokens
    return crop_id, [t for t in conditions if t not in _NOISE] or conditions, recognised


def resolve(crop_id: str | None, tokens: list[str]) -> dict[str, Any] | None:
    """First alias whose match-tokens are all present AND whose crop agrees."""
    tokenset = set(tokens)
    for alias in ALIASES:
        if not set(alias["match"]) <= tokenset:
            continue
        if alias["crop"] is not None and alias["crop"] != crop_id:
            continue
        return alias
    return None


def scan(root: Path, *, unknown_from_unmapped: bool = False) -> tuple[list[dict], dict]:
    dirs = _class_dirs(root)
    records: list[dict] = []
    skipped: collections.Counter = collections.Counter()
    unmapped: list[dict[str, Any]] = []
    per_label: collections.Counter = collections.Counter()

    for cls_dir in dirs:
        cls = cls_dir.name
        images = [p for p in sorted(cls_dir.rglob("*"))
                  if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
        if not images:
            continue
        crop_id, tokens, crop_known = tokenise(cls)
        alias = resolve(crop_id, tokens)

        label: str | None = None
        note = ""
        if alias and alias.get("label"):
            label = alias["label"]
            note = alias.get("note", "")
        elif crop_known and crop_id is None:
            # A crop PRAHARI does not model. This is the good kind of data.
            if unknown_from_unmapped:
                label, note = "unknown", (
                    f"'{cls}' is a crop PRAHARI does not model. Used as out-of-distribution "
                    f"training data so the model learns to answer 'unknown' rather than forcing "
                    f"this leaf into a tomato disease.")
            else:
                skipped[f"unmodelled crop: {cls}"] += len(images)
                continue
        else:
            unmapped.append({"class": cls, "images": len(images),
                             "crop": crop_id, "tokens": tokens,
                             "crop_recognised": crop_known,
                             "why": ("no alias matched these condition tokens"
                                     if crop_known else "crop token not recognised")})
            if unknown_from_unmapped and not crop_known:
                label, note = "unknown", f"unrecognised class '{cls}' used as unknown"
            else:
                skipped[f"unmapped: {cls}"] += len(images)
                continue

        if label not in LABELS:
            raise SystemExit(
                f"mapping error: folder '{cls}' resolves to label '{label}', which is not in "
                f"ml/labels.json.\n{LABELS}\n\nFix the alias or regenerate labels.json from "
                f"backend/data/problems.json — do not bend the images into a nearby class.")

        for img in images:
            records.append({
                "image": str(img),
                "crop": crop_id or "unmodelled",
                "label": label,
                "field_id": field_id(img, cls),
                "location": None, "captured_on": None, "crop_stage": None,
                "source": "kaggle:crop-disease-detection",
                "source_class": cls,
                "mapping_note": note,
                "expert_label": label,
                "expert_confidence": None,
                "verification_status": "dataset_label",
                "model_prediction": None, "model_version": None,
            })
            per_label[label] += 1

    return records, {
        "classes_seen": [d.name for d in dirs],
        "skipped": dict(skipped),
        "unmapped_classes": unmapped,
        "per_label": dict(per_label),
    }


def _class_dirs(root: Path) -> list[Path]:
    """Find the folder-per-class level, wherever the archive buried it.

    These downloads unzip into anything from `root/<class>/` to
    `root/dataset/train/<class>/`, so guessing one layout would make the adapter
    fail on a download that is perfectly fine."""
    candidates: list[Path] = []
    for base in [root, *[p for p in root.rglob("*") if p.is_dir()]]:
        children = [p for p in base.iterdir() if p.is_dir()] if base.is_dir() else []
        if len(children) < 2:
            continue
        # a class level is one whose children hold images directly
        if sum(1 for c in children
               if any(f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                      for f in c.iterdir() if f.is_file())) >= 2:
            candidates.extend(children)
    seen, out = set(), []
    for c in sorted(candidates):
        if c.name.lower() in ("train", "test", "valid", "validation"):
            continue
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def field_id(path: Path, cls: str) -> str:
    """Grouping key for the split. WEAK, and labelled as such in the manifest:
    these datasets carry no field or plant identifier, so the strongest honest
    grouping is the filename stem — which does catch augmented or cropped
    variants of one source photograph landing on both sides of a split."""
    stem = re.sub(r"[^A-Za-z0-9]+", "", path.stem)[:24] or path.stem
    return f"kaggle:{cls}:{stem}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True,
                    help="the unzipped dataset directory")
    ap.add_argument("--out", type=Path, default=Path("datasets/manifest.json"))
    ap.add_argument("--unknown-from-unmapped", action="store_true",
                    help="put images from crops PRAHARI does not model into the 'unknown' class "
                         "instead of discarding them. Recommended: a plant-disease model with no "
                         "unknown class answers confidently when shown anything.")
    ap.add_argument("--merge", type=Path, default=None,
                    help="a second manifest to merge in (e.g. datasets/plantdoc.json, or "
                         "datasets/confirmed.json exported from production)")
    args = ap.parse_args()

    if not args.root.exists():
        raise SystemExit(
            f"{args.root} does not exist.\n\n"
            f"  pip install kaggle    # and put kaggle.json in ~/.kaggle/\n"
            f"  kaggle datasets download -d snikhilrao/crop-disease-detection-dataset "
            f"-p {args.root.parent} --unzip\n")

    records, report = scan(args.root, unknown_from_unmapped=args.unknown_from_unmapped)
    if not records:
        raise SystemExit(
            "No images mapped. The report below lists every folder found — add the ones you "
            "want to ALIASES in this file rather than renaming the dataset.\n\n"
            + json.dumps(report, indent=2))

    merged_from = []
    if args.merge and args.merge.exists():
        other = json.loads(args.merge.read_text())
        records.extend(other.get("records", []))
        merged_from.append(str(args.merge))

    manifest = {
        "_note": ("One record per training image. `field_id` is what the split is made on — see "
                  "`field_grouping` for how strong that grouping actually is."),
        "version": "0.3.0",
        "sources": [CITATION] + merged_from,
        "field_grouping": ("filename-stem (WEAK). This dataset carries no field or plant "
                           "identifier, so images of the same plant can land on both sides of a "
                           "split and the reported accuracy is optimistic. Photographs harvested "
                           "from PRAHARI itself carry a real plot id and are grouped properly."),
        "labels": LABELS,
        "report": report,
        "records": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=1))

    print(f"wrote {args.out} — {len(records)} records")
    for label, n in sorted(report["per_label"].items(), key=lambda kv: -kv[1]):
        print(f"  {label:32} {n:6}")
    if report["skipped"]:
        print("\nskipped:")
        for k, n in report["skipped"].items():
            print(f"  {k:52} {n:6}")
    if report["unmapped_classes"]:
        print("\nUNMAPPED — read these, they are the adapter telling you what it did not "
              "recognise:")
        for u in report["unmapped_classes"]:
            print(f"  {u['class']:40} {u['images']:6}  tokens={u['tokens']}  ({u['why']})")


if __name__ == "__main__":
    main()
