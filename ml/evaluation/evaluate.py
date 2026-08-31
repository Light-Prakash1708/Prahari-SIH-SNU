"""
PRAHARI Vision · evaluation
════════════════════════════════════════════════════════════════════════════
The only place a number PRAHARI is allowed to publish comes from.

It reports, on the held-out FIELD split:

  accuracy                  overall and per class
  macro F1                  the honest headline for an imbalanced field corpus
  confusion matrix          which diseases the model confuses, which is what an
                            agronomist actually wants to know
  calibration (ECE)         does "68% confident" mean right 68% of the time
  risk-coverage curve       accuracy at each abstention rate — because PRAHARI
                            is allowed to decline, and a system that answers 70%
                            of cases at 85% beats one that answers all at 67%
  OOD detection AUROC       can it tell a leaf it knows from one it does not

It writes model_versions-compatible JSON. The backend reads metrics from that
table and prints "no evaluation recorded" when it is null — so a model that has
not been through this script cannot acquire an accuracy claim anywhere.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

LABELS = json.loads((Path(__file__).resolve().parent.parent / "labels.json")
                    .read_text())["labels"]


def expected_calibration_error(confidences, correct, bins: int = 10) -> float:
    import numpy as np
    conf = np.asarray(confidences)
    corr = np.asarray(correct, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.sum() == 0:
            continue
        ece += (m.sum() / len(conf)) * abs(corr[m].mean() - conf[m].mean())
    return float(ece)


def risk_coverage(confidences, correct) -> List[Dict[str, float]]:
    """Accuracy at each coverage level, when the least confident predictions are
    abstained on. This is the curve that justifies the reject option."""
    import numpy as np
    order = np.argsort(-np.asarray(confidences))
    corr = np.asarray(correct, dtype=float)[order]
    out = []
    for frac in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):
        k = max(1, int(len(corr) * frac))
        out.append({"coverage": frac, "accuracy": float(corr[:k].mean()),
                    "abstention_rate": round(1 - frac, 2)})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--data", type=Path, default=Path("data/prepared"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--ood", type=Path, default=None,
                    help="optional JSON list of out-of-distribution image paths")
    ap.add_argument("--out", type=Path, default=Path("evaluation/metrics.json"))
    args = ap.parse_args()

    import numpy as np
    import timm
    import torch
    from sklearn.metrics import confusion_matrix, f1_score
    from torch.utils.data import DataLoader
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from training.train import build_dataset

    ckpt = torch.load(args.checkpoint, map_location="cpu")
    model = timm.create_model(ckpt["arch"], pretrained=False, num_classes=len(LABELS))
    model.load_state_dict(ckpt["model"])
    model.eval()

    rows = json.loads((args.data / f"{args.split}.json").read_text())
    if not rows:
        raise SystemExit(f"no rows in the {args.split} split")
    fields = {r["field_id"] for r in rows}
    dl = DataLoader(build_dataset(rows, False), batch_size=32)

    ys, ps, confs = [], [], []
    with torch.no_grad():
        for x, y in dl:
            probs = torch.softmax(model(x), dim=1)
            conf, pred = probs.max(1)
            ys += y.tolist(); ps += pred.tolist(); confs += conf.tolist()

    correct = [int(a == b) for a, b in zip(ys, ps)]
    acc = float(np.mean(correct))
    macro_f1 = float(f1_score(ys, ps, average="macro", zero_division=0))
    cm = confusion_matrix(ys, ps, labels=list(range(len(LABELS)))).tolist()
    per_class = {}
    for i, label in enumerate(LABELS):
        n = sum(1 for y in ys if y == i)
        if n:
            hit = sum(1 for y, p in zip(ys, ps) if y == i and p == i)
            per_class[label] = {"support": n, "recall": round(hit / n, 4)}

    ood_auroc = None
    if args.ood and args.ood.exists():
        from PIL import Image
        from torchvision import transforms
        tf = transforms.Compose([
            transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
        ood_paths = json.loads(args.ood.read_text())
        ood_conf = []
        with torch.no_grad():
            for p in ood_paths:
                x = tf(Image.open(p).convert("RGB")).unsqueeze(0)
                ood_conf.append(float(torch.softmax(model(x), 1).max().item()))
        from sklearn.metrics import roc_auc_score
        scores = confs + ood_conf
        labels = [1] * len(confs) + [0] * len(ood_conf)
        ood_auroc = float(roc_auc_score(labels, scores))

    metrics: Dict[str, Any] = {
        "split": args.split,
        "images": len(rows),
        "fields": len(fields),
        "split_policy": "grouped by field_id — no field appears in two splits",
        "sources": sorted({r["source"] for r in rows}),
        "accuracy": round(acc, 4),
        "macro_f1": round(macro_f1, 4),
        "per_class_recall": per_class,
        "confusion_matrix": {"labels": LABELS, "matrix": cm},
        "expected_calibration_error": round(expected_calibration_error(confs, correct), 4),
        "risk_coverage": risk_coverage(confs, correct),
        "ood_auroc": ood_auroc,
        "checkpoint": str(args.checkpoint),
        "honesty": (
            "These figures are for THIS test split only, and the split is grouped by field. "
            "If any source above is 'plantvillage', the accuracy is a laboratory number and "
            "must not be presented as field performance — see ml/README.md."),
    }
    if any(s == "plantvillage" for s in metrics["sources"]):
        metrics["WARNING"] = ("PlantVillage images are in this test split. The published "
                              "laboratory-to-field gap is 99% → 19.73%. Do not quote this number.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in metrics.items()
                      if k not in ("confusion_matrix", "per_class_recall")}, indent=1))
    print(f"\nwritten to {args.out}")
    print("Load it into model_versions.metrics with export/register_model.py before deploying.")


if __name__ == "__main__":
    main()
