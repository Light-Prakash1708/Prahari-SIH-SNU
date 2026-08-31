"""
PRAHARI Vision · PlantDoc adapter
════════════════════════════════════════════════════════════════════════════
Turns the PlantDoc dataset into a PRAHARI training manifest.

    PlantDoc: A Dataset for Visual Plant Disease Detection
    Singh, Jain, Jain, Kayal, Kumawat, Batra — CoDS-COMAD 2020
    https://github.com/pratikkayal/PlantDoc-Dataset  ·  CC BY 4.0
    2,482–2,598 field photographs, 13 species, 29 folder classes

PlantDoc is used rather than PlantVillage for one reason: its photographs were
taken in the field, on real plants, in real light. PlantVillage's were taken on
a laboratory backdrop, and a model trained on it scores 99% there and 19.73% on
PlantDoc (arXiv:1911.10317). One of those two numbers is the one a farmer
experiences.

Three things this adapter does that a plain folder-loader would not:

1 · IT REFUSES TO SILENTLY CROSS CROPS.
    PlantDoc has "Squash Powdery mildew leaf". PRAHARI's `powdery_mildew` is
    Erysiphe necator on grape. Podosphaera xanthii on squash is a different
    organism with a different host, and labelling one as the other to inflate a
    class count is exactly how a model learns to be confidently wrong. Mappings
    that cross a crop boundary are marked and EXCLUDED by default.

2 · IT BUILDS THE `unknown` CLASS FROM REAL PHOTOGRAPHS.
    PlantDoc's apple, cherry, peach, raspberry, strawberry and blueberry classes
    are crops PRAHARI does not model at all. They are perfect out-of-distribution
    training data — a leaf, photographed in a field, that the model must learn to
    put in `unknown` rather than force into a tomato disease. Most published
    plant-disease models have no such class, which is why they answer confidently
    when shown a photograph of a hand.

3 · IT GROUPS THE SPLIT HONESTLY.
    PlantDoc carries no field or plant identifier, so a true field-grouped split
    is not constructible from it. The adapter groups by filename stem (several
    crops of one source photograph share one) and SAYS SO in the manifest, rather
    than implying a rigour the dataset cannot support. Production photographs
    harvested from PRAHARI itself DO carry a real plot id, and those are the rows
    the reported number should eventually rest on.

Usage
-----
    git clone https://github.com/pratikkayal/PlantDoc-Dataset data/raw/plantdoc
    python -m datasets.plantdoc --root data/raw/plantdoc --out datasets/manifest.json
    python -m preprocessing.prepare --manifest datasets/manifest.json --out data/prepared
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path
from typing import Any

LABELS = json.loads((Path(__file__).resolve().parent.parent / "labels.json")
                    .read_text())["labels"]

CITATION = (
    "Singh, Jain, Jain, Kayal, Kumawat & Batra, 'PlantDoc: A Dataset for Visual "
    "Plant Disease Detection', CoDS-COMAD 2020. CC BY 4.0.")

# ── the mapping ─────────────────────────────────────────────────────────────
# label      the PRAHARI problem id (must exist in labels.json)
# crop       the PRAHARI crop this row is evidence for
# cross_crop the pathogen or host differs from PRAHARI's definition of `label`
# note       why, in one line, for anyone auditing the mapping later
MAPPING: dict[str, dict[str, Any]] = {
    # ── same pathogen, crop PRAHARI models ──────────────────────────────────
    "Tomato leaf late blight": {
        "label": "late_blight", "crop": "tomato", "cross_crop": False,
        "note": "Phytophthora infestans on tomato — exactly PRAHARI's definition."},
    "Tomato Early blight leaf": {
        "label": "early_blight", "crop": "tomato", "cross_crop": False,
        "note": "Alternaria solani on tomato — exactly PRAHARI's definition."},
    "Corn leaf blight": {
        "label": "turcicum_blight", "crop": "maize", "cross_crop": False,
        "note": "Northern corn leaf blight, Exserohilum turcicum — PRAHARI's maize model."},

    # ── same pathogen, a crop PRAHARI does not model ────────────────────────
    # Included by default: the ORGANISM is the same, and a lesion of P. infestans
    # on potato is the same lesion the model must recognise on tomato. Both are
    # Solanaceae and the symptom morphology is the textbook match.
    "Potato leaf late blight": {
        "label": "late_blight", "crop": "potato", "cross_crop": False,
        "note": "Phytophthora infestans on potato — same organism, same lesion, sister host."},
    "Potato leaf early blight": {
        "label": "early_blight", "crop": "potato", "cross_crop": False,
        "note": "Alternaria solani on potato — same organism, sister host."},

    # ── healthy tissue, crops PRAHARI models ────────────────────────────────
    "Tomato leaf": {"label": "healthy", "crop": "tomato", "cross_crop": False,
                    "note": "Healthy tomato foliage."},
    "Grape leaf": {"label": "healthy", "crop": "grape", "cross_crop": False,
                   "note": "Healthy grape foliage."},
    "Soyabean leaf": {"label": "healthy", "crop": "soybean", "cross_crop": False,
                      "note": "Healthy soybean foliage (PlantDoc spells it 'Soyabean')."},
    "Potato leaf": {"label": "healthy", "crop": "potato", "cross_crop": False,
                    "note": "Healthy potato foliage."},

    # ── CROSS-CROP: excluded unless --allow-cross-crop ──────────────────────
    "Squash Powdery mildew leaf": {
        "label": "powdery_mildew", "crop": "squash", "cross_crop": True,
        "note": ("Podosphaera xanthii on squash. PRAHARI's powdery_mildew is Erysiphe "
                 "necator on GRAPE — a different organism on a different host. Useful only "
                 "for a crop-agnostic 'white powdery coating' symptom model.")},
    "Grape leaf black rot": {
        "label": "unknown", "crop": "grape", "cross_crop": True,
        "note": ("Guignardia bidwellii. PRAHARI does not model black rot, so this is an "
                 "in-crop problem the model must decline rather than force into downy or "
                 "powdery mildew — which makes it valuable OOD data for grape.")},

    # ── the `unknown` class, built from real field photographs ──────────────
    # Crops PRAHARI does not model at all. A model with no `unknown` class
    # answers confidently when shown a leaf it has never met; these teach it not to.
    "Apple Scab Leaf": {"label": "unknown", "crop": "apple", "cross_crop": False,
                        "note": "Crop outside PRAHARI's scope — out-of-distribution training."},
    "Apple leaf": {"label": "unknown", "crop": "apple", "cross_crop": False,
                   "note": "Crop outside PRAHARI's scope — out-of-distribution training."},
    "Apple rust leaf": {"label": "unknown", "crop": "apple", "cross_crop": False,
                        "note": "Crop outside PRAHARI's scope — out-of-distribution training."},
    "Blueberry leaf": {"label": "unknown", "crop": "blueberry", "cross_crop": False,
                       "note": "Crop outside PRAHARI's scope — out-of-distribution training."},
    "Cherry leaf": {"label": "unknown", "crop": "cherry", "cross_crop": False,
                    "note": "Crop outside PRAHARI's scope — out-of-distribution training."},
    "Peach leaf": {"label": "unknown", "crop": "peach", "cross_crop": False,
                   "note": "Crop outside PRAHARI's scope — out-of-distribution training."},
    "Raspberry leaf": {"label": "unknown", "crop": "raspberry", "cross_crop": False,
                       "note": "Crop outside PRAHARI's scope — out-of-distribution training."},
    "Strawberry leaf": {"label": "unknown", "crop": "strawberry", "cross_crop": False,
                        "note": "Crop outside PRAHARI's scope — out-of-distribution training."},
    "Bell_pepper leaf": {"label": "unknown", "crop": "bell_pepper", "cross_crop": False,
                         "note": "Crop outside PRAHARI's scope — out-of-distribution training."},
    "Bell_pepper leaf spot": {"label": "unknown", "crop": "bell_pepper", "cross_crop": False,
                              "note": "Crop outside PRAHARI's scope — out-of-distribution training."},

    # ── in-crop problems PRAHARI deliberately does not model ────────────────
    # These are the hardest and most valuable OOD rows: a tomato leaf, with a
    # real disease, that is NOT one of the four tomato problems PRAHARI knows.
    # Without them the model has no way to learn "this is a tomato problem I was
    # not taught", and will hand a farmer the closest thing it does know.
    "Tomato Septoria leaf spot": {
        "label": "unknown", "crop": "tomato", "cross_crop": False,
        "note": "Septoria lycopersici — a real tomato disease PRAHARI does not model. "
                "The most valuable OOD rows in the set."},
    "Tomato leaf bacterial spot": {
        "label": "unknown", "crop": "tomato", "cross_crop": False,
        "note": "Xanthomonas spp. — bacterial, not fungal, and not modelled. Must not be "
                "diagnosed as early blight."},
    "Tomato mold leaf": {
        "label": "unknown", "crop": "tomato", "cross_crop": False,
        "note": "Passalora fulva (leaf mould) — not modelled."},
    "Tomato leaf yellow virus": {
        "label": "unknown", "crop": "tomato", "cross_crop": False,
        "note": "TYLCV — viral, vectored by whitefly. Not modelled, and a fungicide would "
                "be actively harmful advice."},
    "Tomato leaf mosaic virus": {
        "label": "unknown", "crop": "tomato", "cross_crop": False,
        "note": "ToMV — viral. Not modelled."},
    "Tomato two spotted spider mites leaf": {
        "label": "unknown", "crop": "tomato", "cross_crop": False,
        "note": "Tetranychus urticae — a mite, not a disease. Not modelled."},
    "Corn rust leaf": {
        "label": "unknown", "crop": "maize", "cross_crop": False,
        "note": "Puccinia sorghi — not modelled; must not be called turcicum blight."},
    "Corn Gray leaf spot": {
        "label": "unknown", "crop": "maize", "cross_crop": False,
        "note": "Cercospora zeae-maydis — not modelled; visually close to turcicum blight, "
                "which is precisely why the model needs to see it."},
}


def field_id(path: Path, cls: str) -> str:
    """PlantDoc has no plant or field identifier.

    Several crops of one source photograph share a filename stem, so grouping on
    the stem at least keeps *those* out of two different splits. It is weaker
    than a true field split and the manifest says so — production rows harvested
    from PRAHARI carry a real plot id and are the ones a reported number should
    eventually rest on.
    """
    stem = re.sub(r"[-_ ]?\(?\d+\)?$", "", path.stem).strip().lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or path.stem.lower()
    return f"plantdoc:{cls.lower().replace(' ', '-')}:{stem}"


def scan(root: Path, allow_cross_crop: bool = False) -> tuple[list[dict], dict]:
    records: list[dict] = []
    seen_classes: set[str] = set()
    skipped: collections.Counter = collections.Counter()

    for split_dir in ("train", "test"):
        base = root / split_dir
        if not base.is_dir():
            continue
        for cls_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            cls = cls_dir.name
            seen_classes.add(cls)
            m = MAPPING.get(cls)
            if m is None:
                skipped[f"unmapped: {cls}"] += len(list(cls_dir.glob("*")))
                continue
            if m["cross_crop"] and not allow_cross_crop:
                skipped[f"cross-crop (excluded): {cls}"] += len(list(cls_dir.glob("*")))
                continue
            if m["label"] not in LABELS:
                raise SystemExit(
                    f"mapping error: '{cls}' maps to '{m['label']}', which is not in "
                    f"ml/labels.json ({LABELS})")
            for img in sorted(cls_dir.iterdir()):
                if img.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                    continue
                records.append({
                    "image": str(img),
                    "crop": m["crop"],
                    "label": m["label"],
                    "field_id": field_id(img, cls),
                    "location": None,
                    "captured_on": None,
                    "crop_stage": None,
                    "source": "plantdoc",
                    "source_class": cls,
                    "cross_crop": m["cross_crop"],
                    "mapping_note": m["note"],
                    "expert_label": m["label"],
                    "expert_confidence": None,
                    "verification_status": "dataset_label",
                    "model_prediction": None,
                    "model_version": None,
                })

    unmapped = sorted(seen_classes - set(MAPPING))
    return records, {"skipped": dict(skipped), "unmapped_classes": unmapped,
                     "classes_seen": sorted(seen_classes)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True,
                    help="a clone of pratikkayal/PlantDoc-Dataset (has train/ and test/)")
    ap.add_argument("--out", type=Path, default=Path("datasets/manifest.json"))
    ap.add_argument("--allow-cross-crop", action="store_true",
                    help="include mappings whose pathogen or host differs from PRAHARI's "
                         "definition of the label. Off by default, and off is correct "
                         "unless you are deliberately training a crop-agnostic symptom model.")
    ap.add_argument("--merge", type=Path, default=None,
                    help="a second manifest (e.g. datasets/confirmed.json from production) "
                         "to merge in")
    args = ap.parse_args()

    if not args.root.exists():
        raise SystemExit(
            f"{args.root} does not exist.\n\n"
            f"  git clone https://github.com/pratikkayal/PlantDoc-Dataset {args.root}\n")

    records, report = scan(args.root, args.allow_cross_crop)
    if not records:
        raise SystemExit(
            f"No usable images under {args.root}. Expected {args.root}/train/<class>/*.jpg")

    merged_from = None
    if args.merge and args.merge.exists():
        extra = json.loads(args.merge.read_text())["records"]
        records += extra
        merged_from = {"path": str(args.merge), "records": len(extra)}

    by_label = collections.Counter(r["label"] for r in records)
    by_crop = collections.Counter(r["crop"] for r in records)
    by_source = collections.Counter(r["source"] for r in records)

    payload = {
        "version": "plantdoc-1.0",
        "records": records,
        "provenance": {
            "dataset": "PlantDoc",
            "url": "https://github.com/pratikkayal/PlantDoc-Dataset",
            "licence": "CC BY 4.0 — attribution required in any published result",
            "citation": CITATION,
            "why_not_plantvillage": (
                "PlantVillage photographs sit on a laboratory backdrop. A model trained on "
                "it scores 99% on PlantVillage and 19.73% on PlantDoc (arXiv:1911.10317), and "
                "a model shown eight background pixels and no leaf at all still scores 49% on "
                "PlantVillage (arXiv:2206.04374). PlantDoc's photographs are of real plants in "
                "real fields, which is the only setting PRAHARI is ever used in."),
        },
        "split_policy": {
            "grouping": "filename stem within a class",
            "honest_limitation": (
                "PlantDoc carries no plant or field identifier, so a TRUE field-grouped split "
                "is not constructible from it. Grouping on the filename stem keeps crops of one "
                "source photograph together, which is the strongest guarantee this dataset "
                "supports. Any accuracy reported from a PlantDoc-only split is therefore an "
                "upper bound. Production rows harvested by ml/export/export_confirmed.py carry "
                "a real plot id and give a genuine field split."),
        },
        "mapping": {
            "cross_crop_included": args.allow_cross_crop,
            "rule": (
                "A PlantDoc class maps to a PRAHARI label only when the ORGANISM matches "
                "PRAHARI's definition of that label. Squash powdery mildew (Podosphaera "
                "xanthii) is not grape powdery mildew (Erysiphe necator) and is excluded by "
                "default. Crops and in-crop problems PRAHARI does not model become `unknown` — "
                "the class that lets the model decline instead of guessing."),
            "table": {k: v for k, v in MAPPING.items()},
        },
        "summary": {
            "records": len(records),
            "by_label": dict(by_label),
            "by_crop": dict(by_crop),
            "by_source": dict(by_source),
            "unknown_share": round(by_label.get("unknown", 0) / len(records), 3),
            "merged_from": merged_from,
        },
        "report": report,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"wrote {args.out}  ·  {len(records)} records")
    print("\nby label:")
    for k, v in by_label.most_common():
        print(f"  {k:<22} {v:>5}")
    print(f"\n`unknown` is {payload['summary']['unknown_share']:.0%} of the corpus — that is the "
          f"class that lets the model say 'I was not taught this'.")
    if report["skipped"]:
        print("\nskipped:")
        for k, v in report["skipped"].items():
            print(f"  {k}  ({v} files)")
    if report["unmapped_classes"]:
        print(f"\n  {len(report['unmapped_classes'])} PlantDoc classes have no mapping. "
              f"Add them to MAPPING in this file if you extend PRAHARI's crop list.")
    print("\nNext:  python -m preprocessing.prepare --manifest "
          f"{args.out} --out data/prepared")


if __name__ == "__main__":
    main()
