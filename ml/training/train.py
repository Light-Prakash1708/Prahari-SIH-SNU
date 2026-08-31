"""
PRAHARI Vision · training
════════════════════════════════════════════════════════════════════════════
A lightweight classifier for mobile and web inference. MobileNetV4-Conv-S by
default: 4–6 MB at INT8, roughly 2.4 ms on a Pixel 6 CPU, which is the budget a
farmer's phone actually has.

Two things here are not decoration:

  · the `unknown` class is trained on genuine out-of-distribution images, so the
    model has somewhere to put a photograph of a hand, the sky or a fertiliser
    bag — the single most common thing a farmer actually photographs by mistake;
  · every run writes a run card with the dataset version, the field split, the
    seed and the git commit. A checkpoint with no run card cannot be deployed,
    because nobody can say what it saw.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

LABELS = json.loads((Path(__file__).resolve().parent.parent / "labels.json")
                    .read_text())["labels"]


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def build_dataset(rows: List[Dict[str, Any]], train: bool):
    import torch
    from PIL import Image
    from torch.utils.data import Dataset
    from torchvision import transforms

    aug = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.6, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.RandomApply([transforms.ColorJitter(0.35, 0.35, 0.35, 0.06)], p=0.8),
        transforms.RandomApply([transforms.GaussianBlur(5, (0.1, 2.0))], p=0.3),
        transforms.RandomRotation(25),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        transforms.RandomErasing(p=0.25, scale=(0.02, 0.15)),
    ])
    plain = transforms.Compose([
        transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    class Leaves(Dataset):
        def __init__(self, rows, tf):
            self.rows, self.tf = rows, tf

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, i):
            r = self.rows[i]
            img = Image.open(r["image"]).convert("RGB")
            return self.tf(img), LABELS.index(r["label"])

    return Leaves(rows, aug if train else plain)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, required=True, help="output of preprocessing.prepare")
    ap.add_argument("--arch", default="mobilenetv4_conv_small")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--seed", type=int, default=20260827)
    ap.add_argument("--runs", type=Path, default=Path("runs"))
    args = ap.parse_args()

    import timm
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader

    torch.manual_seed(args.seed)
    train_rows = json.loads((args.data / "train.json").read_text())
    val_rows = json.loads((args.data / "val.json").read_text())
    if not train_rows:
        raise SystemExit("no training records — run preprocessing.prepare first")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = timm.create_model(args.arch, pretrained=True, num_classes=len(LABELS)).to(device)

    # Class weights, because a field corpus is never balanced and an unweighted
    # loss quietly learns to predict the commonest disease.
    counts = [max(1, sum(1 for r in train_rows if r["label"] == l)) for l in LABELS]
    weights = torch.tensor([sum(counts) / (len(counts) * c) for c in counts],
                           dtype=torch.float32, device=device)
    criterion = nn.CrossEntropyLoss(weight=weights, label_smoothing=0.05)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.05)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)

    dl_train = DataLoader(build_dataset(train_rows, True), batch_size=args.batch_size,
                          shuffle=True, num_workers=4, drop_last=True)
    dl_val = DataLoader(build_dataset(val_rows, False), batch_size=args.batch_size,
                        num_workers=4)

    run_dir = args.runs / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    best = 0.0
    history = []
    for epoch in range(args.epochs):
        model.train()
        total = correct = 0
        loss_sum = 0.0
        for x, y in dl_train:
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            out = model(x)
            loss = criterion(out, y)
            loss.backward()
            opt.step()
            loss_sum += loss.item() * y.size(0)
            correct += (out.argmax(1) == y).sum().item()
            total += y.size(0)
        sched.step()

        model.eval()
        v_total = v_correct = 0
        with torch.no_grad():
            for x, y in dl_val:
                x, y = x.to(device), y.to(device)
                v_correct += (model(x).argmax(1) == y).sum().item()
                v_total += y.size(0)
        val_acc = v_correct / max(1, v_total)
        history.append({"epoch": epoch, "train_loss": loss_sum / max(1, total),
                        "train_acc": correct / max(1, total), "val_acc": val_acc})
        print(f"epoch {epoch:>3}  train {correct/max(1,total):.3f}  val {val_acc:.3f}")
        if val_acc > best:
            best = val_acc
            torch.save({"model": model.state_dict(), "arch": args.arch,
                        "labels": LABELS}, run_dir / "best.pt")

    card = {
        "run": run_dir.name,
        "arch": args.arch,
        "epochs": args.epochs,
        "seed": args.seed,
        "git_commit": git_commit(),
        "dataset": json.loads((args.data / "summary.json").read_text()),
        "split_policy": "grouped by field_id — no field appears in two splits",
        "best_val_accuracy": best,
        "history": history,
        "claim_policy": (
            "VALIDATION accuracy only. It is NOT the number to publish. Run "
            "evaluation/evaluate.py on the held-out FIELD test split and publish that, "
            "with the split it was computed on."),
    }
    (run_dir / "run_card.json").write_text(json.dumps(card, indent=1), encoding="utf-8")
    latest = args.runs / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(run_dir.name)
    print(f"\nrun card: {run_dir / 'run_card.json'}")
    print("Do NOT quote the validation number. Run evaluation/evaluate.py next.")


if __name__ == "__main__":
    main()
