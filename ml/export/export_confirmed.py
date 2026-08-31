"""
PRAHARI Vision · harvest expert-confirmed observations into a training manifest.

This is the loop back from production. It exports ONLY observations an expert
actually confirmed, with the model's prediction at the time and the model
version that made it — so the next training run can be told what the previous
one got wrong.

It does not retrain anything. Retraining is a separate, deliberate, human act.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("datasets/confirmed.json"))
    ap.add_argument("--images-dir", type=Path, default=Path("data/raw/prahari"))
    ap.add_argument("--min-confidence", default="moderate",
                    choices=["low", "moderate", "high"])
    args = ap.parse_args()

    from app.db import Database, loads
    db = Database()
    order = {"low": 0, "moderate": 1, "high": 2}
    rows = db.rows(
        "SELECT d.id AS diagnosis_id, d.confirmed, d.top_problem, d.model_version, d.engine,"
        " o.id AS observation_id, o.crop, o.crop_stage, o.taluka, o.observed_at, o.plot_id,"
        " i.storage_key, r.confidence"
        " FROM diagnoses d"
        " JOIN observations o ON o.id = d.observation_id"
        " JOIN observation_images i ON i.observation_id = o.id"
        " LEFT JOIN expert_cases c ON c.observation_id = o.id"
        " LEFT JOIN expert_reviews r ON r.case_id = c.id"
        " WHERE d.confirmed IS NOT NULL AND o.kind = 'leaf'")

    records = []
    for r in rows:
        conf = r.get("confidence") or "moderate"
        if order.get(conf, 1) < order[args.min_confidence]:
            continue
        records.append({
            "image": str(args.images_dir / Path(r["storage_key"]).name),
            "storage_key": r["storage_key"],
            "crop": r["crop"],
            "label": r["confirmed"],
            # The FIELD is the split key. Several photographs of one plot are one
            # sample as far as an honest test split is concerned.
            "field_id": f"prahari:{r['plot_id']}",
            "location": {"taluka": r["taluka"]},
            "captured_on": str(r["observed_at"])[:10],
            "crop_stage": r["crop_stage"],
            "source": "prahari_production",
            "expert_label": r["confirmed"],
            "expert_confidence": conf,
            "verification_status": "expert_confirmed",
            "model_prediction": r["top_problem"],
            "model_version": r["model_version"],
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"version": "harvested", "records": records,
         "_note": ("Expert-confirmed observations only. Download the images named by "
                   "storage_key from object storage into --images-dir, then merge this into "
                   "datasets/manifest.json and run preprocessing.prepare. A HUMAN reviews "
                   "this file before it becomes training data.")},
        indent=1), encoding="utf-8")
    disagreed = sum(1 for r in records if r["model_prediction"] != r["label"])
    print(f"{len(records)} expert-confirmed observations exported to {args.out}")
    print(f"{disagreed} of them are cases the model got wrong — the most valuable rows here.")


if __name__ == "__main__":
    main()
