"""
PRAHARI Vision · ONNX export
════════════════════════════════════════════════════════════════════════════
Exports a checkpoint to the contract backend/app/vision_service.py expects:

    input   float32 [1, 3, 224, 224], ImageNet-normalised RGB, NCHW
    output  float32 [1, C] LOGITS (the backend applies the softmax)
    labels  labels.json next to the model, listing the C class ids in order

The export is verified by running both the PyTorch model and the ONNX model on
the same random tensor and comparing. An export that does not match is not
written — a silently wrong export is a model that quietly diagnoses the wrong
disease.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

LABELS = json.loads((Path(__file__).resolve().parent.parent / "labels.json")
                    .read_text())["labels"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--size", type=int, default=224)
    ap.add_argument("--opset", type=int, default=17)
    ap.add_argument("--tolerance", type=float, default=1e-4)
    args = ap.parse_args()

    import numpy as np
    import timm
    import torch

    ckpt = torch.load(args.checkpoint, map_location="cpu")
    model = timm.create_model(ckpt["arch"], pretrained=False, num_classes=len(LABELS))
    model.load_state_dict(ckpt["model"])
    model.eval()

    dummy = torch.randn(1, 3, args.size, args.size)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp.onnx")
    torch.onnx.export(
        model, dummy, str(tmp),
        input_names=["input"], output_names=["logits"],
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=args.opset, do_constant_folding=True)

    import onnx
    import onnxruntime as ort
    onnx.checker.check_model(onnx.load(str(tmp)))
    sess = ort.InferenceSession(str(tmp), providers=["CPUExecutionProvider"])
    onnx_out = sess.run(None, {"input": dummy.numpy()})[0]
    with torch.no_grad():
        torch_out = model(dummy).numpy()
    delta = float(np.abs(onnx_out - torch_out).max())
    if delta > args.tolerance:
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            f"export mismatch: max |onnx - torch| = {delta:.2e} > {args.tolerance:.0e}. "
            f"Not writing the model — a silently wrong export diagnoses the wrong disease.")
    tmp.replace(args.out)

    labels_path = args.out.parent / "labels.json"
    shutil.copy(Path(__file__).resolve().parent.parent / "labels.json", labels_path)

    card = args.checkpoint.parent / "run_card.json"
    if card.exists():
        shutil.copy(card, args.out.parent / f"{args.out.stem}.run_card.json")
    metrics = Path("evaluation/metrics.json")
    if metrics.exists():
        shutil.copy(metrics, args.out.parent / f"{args.out.stem}.metrics.json")
    else:
        print("\n  No evaluation/metrics.json found. The backend will report this model as "
              "having NO recorded evaluation, and will make no accuracy claim for it. "
              "That is the correct behaviour — run evaluation/evaluate.py.")

    size_mb = args.out.stat().st_size / 1e6
    print(f"wrote {args.out} ({size_mb:.1f} MB), max delta {delta:.2e}")
    print(f"labels: {labels_path}")
    print("\nPoint the backend at it:")
    print(f"  VISION_PROVIDER=onnx")
    print(f"  VISION_MODEL_PATH={args.out}")
    print(f"  VISION_MODEL_LABELS={labels_path}")
    print(f"  VISION_MODEL_VERSION=<the version you are deploying>")


if __name__ == "__main__":
    main()
