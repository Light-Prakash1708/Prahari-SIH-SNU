"""Command-line inference against an exported ONNX model — the same code path
the backend uses, so a discrepancy shows up here first."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--crop", default="tomato")
    args = ap.parse_args()

    import os
    os.environ.update(VISION_PROVIDER="onnx", VISION_MODEL_PATH=str(args.model),
                      VISION_MODEL_LABELS=str(args.labels), VISION_MODEL_VERSION="cli")
    from app.config import reload_settings
    from app.reference import problems_for_crop
    from app.vision_service import VisionService

    s = reload_settings()
    v = VisionService(s)
    if not v.neural_available:
        raise SystemExit(f"model not loaded: {v.health()}")
    data = args.image.read_bytes()
    feats = v.analyse(data)
    print("quality gate:", "PASS" if feats["quality"]["ok"] else "FAIL")
    for f in feats["quality"]["failures"]:
        print("   ", f["msg"])
    if not feats["quality"]["ok"]:
        print("\nPRAHARI would NOT diagnose this photograph.")
        return
    out = v.classify(data, args.crop, list(problems_for_crop(args.crop)))
    print(json.dumps({"engine": out.engine, "version": out.model_version,
                      "probs": {k: round(p, 4) for k, p in
                                sorted((out.probs or {}).items(), key=lambda kv: -kv[1])},
                      "note": out.note}, indent=1))


if __name__ == "__main__":
    main()
