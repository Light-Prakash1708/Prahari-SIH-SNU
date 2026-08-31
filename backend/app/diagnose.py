"""
PRAHARI · diagnosis, and the right to refuse
════════════════════════════════════════════════════════════════════════════
    posterior ∝ prior(taluka, 28 days) × L(image features) × L(weather model)

Three independent sources of evidence, combined by Bayes, with every term
visible on screen. Nothing here is a black box.

The part that matters most is when this function declines to answer. There are
four separate reasons it will:

  photo-quality      the image failed its quality gate — a bad photograph is
                     rejected, never diagnosed
  unfamiliar-pattern NO candidate's absolute fit clears the out-of-distribution
                     floor. A posterior is a ratio and always sums to one, so it
                     always names a winner even when nothing in the reference set
                     resembles what was photographed. This checks whether anything
                     actually fits, not merely which fits least badly.
  evidence-conflict  something fits well, but it is not the winner. The image
                     points one way and the district prior plus the weather model
                     point another. That is a real disagreement between two honest
                     sources, not a bad photograph — and unlike the two failures
                     above, contextual questions CAN settle it.
  no-clear-candidate no candidate reaches the confidence floor
  two-way-tie        the top two are within a few points and need OPPOSITE
                     treatments, so guessing is worse than not answering

Supporting literature for the reject option: post-hoc OOD scoring on plant
disease (energy / max-logit, Scientific Reports 14, 2024, AUROC 97.6-98.3%) and
conformal prediction with a reject option (arXiv:2506.21802), which gives a
distribution-free marginal-coverage guarantee. The energy score belongs on the
CNN logits once vision.classify() is filled in; today the same role is played by
the absolute feature likelihood below.
"""
from __future__ import annotations

import math
from typing import Any

# Confidence floors. Deliberately conservative — an app that guesses here causes
# a wrong spray, which is the specific harm this whole system exists to prevent.
POSTERIOR_FLOOR = 0.46
MARGIN_FLOOR = 0.12
# Calibrated against the reference set rather than picked: a correct answer
# scores 0.31-0.99 on absolute fit, while a symptom pattern that belongs to a
# DIFFERENT crop's disease list scores 0.03-0.11. 0.12 sits in that gap, so
# "this is not something I know for this crop" is separated from "this is."
OOD_FLOOR = 0.12

# Nothing here is ever certain, so nothing here ever prints certainty.
# A posterior is a ratio over the candidates we happen to have templates for; a
# pattern outside that set can push the winner to a rounded 100%, which reads as
# a guarantee to a farmer and as a calibration failure to anyone who works with
# classifiers. The cap costs a rounding error and buys an honest number.
CONFIDENCE_CAP = 0.99


def _cap(p: float) -> float:
    return min(CONFIDENCE_CAP, p)


# Feature bandwidths. Wide on purpose: each feature is weak evidence on its own
# and pretending otherwise is how you get a confident wrong answer.
_SIGMA = {"necrosis": 0.11, "chlorosis": 0.11, "powder": 0.09, "dark": 0.11,
          "edge": 0.20, "lesions": 0.16, "spread": 0.26}

# Weather is strong evidence but must never override the image on its own.
# 1.9 against 0.65 is about a 3:1 odds shift — a clearly healthy leaf still wins.
# An earlier 2.4/0.55 could diagnose blight on a photograph of a healthy leaf,
# purely because it had rained.
WX_FIRED, WX_QUIET = 1.9, 0.65


def feature_likelihood(feat: dict[str, Any], template: dict[str, float]) -> float:
    terms = [
        (feat["necrosis"], template["necrosis"], _SIGMA["necrosis"]),
        (feat["chlorosis"], template["chlorosis"], _SIGMA["chlorosis"]),
        (feat["powder"], template["powder"], _SIGMA["powder"]),
        (feat["dark"], template["dark"], _SIGMA["dark"]),
        (min(1.0, feat["lesions"] / 25), min(1.0, template["lesions"] / 25), _SIGMA["lesions"]),
        (feat["spread"], template["spread"], _SIGMA["spread"]),
    ]
    # Border sharpness is only evidence when there are discrete lesions to have a
    # border. On a uniformly chlorotic leaf the measured "border" is the leaf
    # outline against the soil, and including it made the engine reject a textbook
    # nitrogen deficiency as an unfamiliar pattern.
    if feat.get("edge_valid", True):
        terms.append((feat["edge"], template["edge"], _SIGMA["edge"]))
    log_l = sum(-0.5 * ((x - t) / s) ** 2 for x, t, s in terms)
    # Averaging the log-likelihood over all terms made every template look
    # plausible: a candidate that missed on every single feature still scored
    # 0.33, which the district prior then happily overrode — and the engine
    # diagnosed blight on a photograph of a healthy leaf. Scaling by
    # len(terms)/3.2 keeps each feature weak individually while letting a wholly
    # wrong template be rejected on the combined weight of all of them, and keeps
    # the scale stable whether or not the border term is included.
    return math.exp(log_l / (len(terms) / 3.2))


def _sanity(problem_id: str, feat: dict[str, Any], likelihood: float) -> float:
    """One hard rule on top of the soft ones. "No disease detected" is not a
    conclusion you can reach from a leaf carrying six distinct lesions, however
    well the remaining features happen to fit. A Gaussian kernel will cheerfully
    do it; an agronomist would not."""
    if problem_id == "healthy" and (feat["lesions"] >= 3 or feat["necrosis"] > 0.08
                                    or feat["powder"] > 0.10 or feat["chlorosis"] > 0.15):
        return likelihood * 0.02
    return likelihood


def diagnose(feat: dict[str, Any], crop: str, prior: dict[str, float],
             problems: dict[str, dict], model_fired: dict[str, bool],
             cnn: dict[str, float] | None = None) -> dict[str, Any]:
    """prior maps problem_id -> probability. model_fired maps problem_id -> whether
    that problem's published infection model has fired on current weather."""
    candidates = [pid for pid, p in problems.items() if crop in p["crops"]]
    if not candidates:
        return {"abstain": True, "reason": "crop-not-covered", "ranked": [],
                "explain": ("No image reference set exists for this crop. There is no open "
                            "field-realistic image dataset for cotton, pigeonpea, chickpea or "
                            "sugarcane in India — so the camera abstains and the weather and "
                            "threshold engines carry the advisory instead.")}

    rows, total = [], 0.0
    for pid in candidates:
        p = problems[pid]
        pr = prior.get(pid, 1.0 / len(candidates))
        img = cnn.get(pid) if cnn else feature_likelihood(feat, p["feat"])
        img = _sanity(pid, feat, img)
        wx = (WX_FIRED if model_fired.get(pid) else WX_QUIET) if p.get("model") else 1.0
        v = pr * img * wx
        rows.append({"id": pid, "name": p["name"], "name_mr": p["mr"], "em": p["em"],
                     "sci": p["sci"], "prior": pr, "image": img, "weather": wx, "raw": v})
        total += v

    for r in rows:
        r["posterior"] = _cap(r["raw"] / total if total else 0.0)
    rows.sort(key=lambda r: -r["posterior"])
    top, second = rows[0], (rows[1] if len(rows) > 1 else {"posterior": 0.0})
    margin = top["posterior"] - second["posterior"]
    q = feat["quality"]

    best_fit = max(r["image"] for r in rows)
    fits_best = max(rows, key=lambda r: r["image"])

    reason = None
    if not q["ok"]:
        reason = "photo-quality"
    elif best_fit < OOD_FLOOR:
        # Nothing in this crop's reference set resembles what was photographed.
        reason = "unfamiliar-pattern"
    elif top["image"] < OOD_FLOOR:
        # Something fits well — just not the candidate the prior and the weather
        # pushed to the top. Two honest sources disagreeing is a different
        # failure from a bad photograph, and it is one questions can settle.
        reason = "evidence-conflict"
    elif top["posterior"] < POSTERIOR_FLOOR:
        reason = "no-clear-candidate"
    elif margin < MARGIN_FLOOR:
        reason = "two-way-tie"

    explain = {
        "photo-quality": " ".join(f["msg"] for f in q["failures"]),
        "unfamiliar-pattern": (
            f"The measured symptoms do not resemble anything in this crop's reference set. The "
            f"closest is {fits_best['name']}, and even that fits at {best_fit*100:.1f}% against a "
            f"floor of {OOD_FLOOR*100:.0f}%. A posterior always adds up to 100%, so it will always "
            f"name a winner — this check asks whether anything actually fits."),
        "evidence-conflict": (
            f"The photograph looks most like {fits_best['name']} ({fits_best['image']*100:.0f}% fit), "
            f"but this taluka's confirmed-case history and the weather models point to "
            f"{top['name']}. Two honest sources disagree, and they need different treatments — so "
            f"a few questions about the plant will settle it faster than guessing."),
        "no-clear-candidate": (
            f"No candidate reaches the {POSTERIOR_FLOOR*100:.0f}% confidence floor. The strongest is "
            f"{top['name']} at {top['posterior']*100:.0f}%."),
        "two-way-tie": (
            f"{top['name']} and {second.get('name','the runner-up')} are within "
            f"{margin*100:.0f} percentage points. They need opposite treatments, so guessing is "
            f"worse than not answering."),
    }.get(reason, "")

    return {
        "abstain": reason is not None,
        "reason": reason,
        "explain": explain,
        "ranked": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
                   for r in rows],
        "top": rows[0], "margin": round(margin, 4),
        "top_fit": round(top["image"], 4), "best_fit": round(best_fit, 4),
        "best_fitting": {"id": fits_best["id"], "name": fits_best["name"],
                         "image": round(fits_best["image"], 4)},
        "ood_floor": OOD_FLOOR,
        "engine": "cnn+features" if cnn else "features-only",
        "floors": {"posterior": POSTERIOR_FLOOR, "margin": MARGIN_FLOOR, "ood": OOD_FLOOR},
    }


def dirichlet_prior(confirmed_counts: dict[str, int], candidates: list[str],
                    alpha0: float = 1.0) -> dict[str, Any]:
    """The entire learning mechanism, and it is one integer per confirmation.

    Each taluka carries a Dirichlet over problems. α starts at 1 for every
    candidate — a uniform prior that assumes nothing — and each EXPERT-CONFIRMED
    case adds 1. No gradient, no retraining, no unverifiable claim that the model
    improves over time. An agriculture officer can audit it by counting cases.
    """
    alpha = {c: alpha0 + confirmed_counts.get(c, 0) for c in candidates}
    total = sum(alpha.values()) or 1.0
    return {"alpha": alpha, "total": total,
            "p": {c: alpha[c] / total for c in candidates}}
