"""Register an evaluated model version in the database so the UI can show it."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", required=True)
    ap.add_argument("--provider", default="onnx")
    ap.add_argument("--metrics", type=Path, default=Path("evaluation/metrics.json"))
    ap.add_argument("--run-card", type=Path, default=None)
    args = ap.parse_args()

    from app.clock import now_iso
    from app.db import Database, dumps

    metrics = json.loads(args.metrics.read_text()) if args.metrics.exists() else None
    if metrics is None:
        print("No metrics file. Registering with metrics = NULL — the UI will correctly "
              "report that no evaluation exists for this version.")
    card = json.loads(args.run_card.read_text()) if args.run_card and args.run_card.exists() else {}
    db = Database()
    mid = f"vision:{args.provider}:{args.version}"
    db.execute("DELETE FROM model_versions WHERE id = :id", {"id": mid})
    db.execute(
        "INSERT INTO model_versions (id, kind, name, version, provider, trained_on, eval_set,"
        " metrics, deployed_at, active, notes)"
        " VALUES (:id,'vision','prahari-vision',:v,:p,:trained,:eval,:m,:at,1,:notes)",
        {"id": mid, "v": args.version, "p": args.provider,
         "trained": json.dumps(card.get("dataset")) if card else None,
         "eval": (metrics or {}).get("split"),
         "m": dumps(metrics), "at": now_iso(),
         "notes": (metrics or {}).get("honesty")})
    print(f"registered {mid}")


if __name__ == "__main__":
    main()
