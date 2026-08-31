"""
PRAHARI Vision · dataset preparation
════════════════════════════════════════════════════════════════════════════
Reads datasets/manifest.json, validates every record, and writes a split that
is grouped BY FIELD.

The field split is the whole point. Two photographs of the same leaf on the
same afternoon are not independent samples; splitting by image lets the model
memorise a leaf and then score itself on that leaf, and it inflates every number
you report. This script refuses to emit a split where a field_id appears in more
than one of train / val / test.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Dict, List

LABELS = json.loads((Path(__file__).resolve().parent.parent / "labels.json")
                    .read_text())["labels"]


def load(manifest: Path) -> List[Dict[str, Any]]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    records = data["records"]
    problems = []
    for i, r in enumerate(records):
        for key in ("image", "crop", "label", "field_id", "source"):
            if not r.get(key):
                problems.append(f"record {i}: missing {key}")
        if r.get("label") not in LABELS:
            problems.append(f"record {i}: label {r.get('label')!r} is not in labels.json")
    if problems:
        raise SystemExit("manifest is not usable:\n  " + "\n  ".join(problems[:40]))
    return records


def split_by_field(records: List[Dict[str, Any]], ratios=(0.7, 0.15, 0.15),
                   seed: int = 20260827) -> Dict[str, List[Dict[str, Any]]]:
    by_field: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for r in records:
        by_field[r["field_id"]].append(r)
    fields = sorted(by_field)
    rng = random.Random(seed)
    rng.shuffle(fields)
    n = len(fields)
    n_train = int(n * ratios[0])
    n_val = int(n * ratios[1])
    assign = {}
    for i, f in enumerate(fields):
        assign[f] = "train" if i < n_train else ("val" if i < n_train + n_val else "test")
    out: Dict[str, List[Dict[str, Any]]] = {"train": [], "val": [], "test": []}
    for f, rows in by_field.items():
        for r in rows:
            out[assign[f]].append({**r, "split": assign[f]})
    return out


def verify_no_leakage(splits: Dict[str, List[Dict[str, Any]]]) -> None:
    seen: Dict[str, str] = {}
    for name, rows in splits.items():
        for r in rows:
            prev = seen.get(r["field_id"])
            if prev and prev != name:
                raise SystemExit(
                    f"FIELD LEAKAGE: {r['field_id']} appears in both {prev} and {name}. "
                    f"Every number computed from this split would be inflated.")
            seen[r["field_id"]] = name
    # Images can repeat inside a split (augmentation manifests) but never across.
    hashes: Dict[str, str] = {}
    for name, rows in splits.items():
        for r in rows:
            h = hashlib.sha1(r["image"].encode()).hexdigest()
            prev = hashes.get(h)
            if prev and prev != name:
                raise SystemExit(f"IMAGE LEAKAGE: {r['image']} in {prev} and {name}")
            hashes[h] = name


def report(splits: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, rows in splits.items():
        counts = collections.Counter(r["label"] for r in rows)
        sources = collections.Counter(r["source"] for r in rows)
        out[name] = {"images": len(rows),
                     "fields": len({r["field_id"] for r in rows}),
                     "by_label": dict(counts), "by_source": dict(sources)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=20260827)
    args = ap.parse_args()

    records = load(args.manifest)
    splits = split_by_field(records, seed=args.seed)
    verify_no_leakage(splits)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        (args.out / f"{name}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    summary = report(splits)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    plantvillage_in_test = sum(1 for r in splits["test"] if r["source"] == "plantvillage")
    if plantvillage_in_test:
        print(f"\n  WARNING: {plantvillage_in_test} PlantVillage images are in the TEST split.\n"
              f"  A number reported from those is a laboratory number, not a field number.\n"
              f"  Move PlantVillage to pre-training only.")


if __name__ == "__main__":
    main()
