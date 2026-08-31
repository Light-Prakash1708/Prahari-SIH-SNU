"""
PRAHARI · agronomic reference data
════════════════════════════════════════════════════════════════════════════
Crops, problems, thresholds, IPM ladders, talukas. Loaded once at import from
backend/data/*.json, which is version-controlled and reviewable — an agronomist
can open a pull request against a threshold without touching Python.

Every record carries provenance: `source`, `source_url` where one exists, and a
`status` of draft or verified. Nothing in this module decides whether a draft
record may be shown; chemicals.py does that, and it is the only place that can.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


CROPS: dict[str, Any] = _load("crops.json")["crops"]
_P = _load("problems.json")
DISEASES: dict[str, Any] = _P["diseases"]
PESTS: dict[str, Any] = _P["pests"]
THRESHOLDS: list[dict] = _load("thresholds.json")["thresholds"]
_LC = _load("label_claims.json")
CLAIMS: list[dict] = _LC["claims"]
RESTRICTED: list[dict] = _LC["restricted_maharashtra"]["entries"]
IPM: dict[str, Any] = _load("ipm.json")["ladders"]
TALUKAS: list[dict] = _load("talukas.json")["talukas"]
TALUKA_BY_ID = {t["id"]: t for t in TALUKAS}
TALUKA_IDS = [t["id"] for t in TALUKAS]

STAGE_MR = {
    "sowing": "पेरणी", "nursery": "रोपवाटिका", "seedling": "रोप",
    "vegetative": "वाढीची अवस्था", "earlywhorl": "सुरुवातीची पोंगा अवस्था",
    "latewhorl": "उशिराची पोंगा अवस्था", "tassel": "तुरा",
    "shoot": "फूट", "pruning": "छाटणी", "flowering": "फुलोरा",
    "berry": "मणी धरणे", "fruiting": "फळधारणा", "pod": "शेंगा धरणे",
    "boll": "बोंड धरणे", "bulb": "कांदा पोसणे", "grain": "दाणे भरणे",
    "maturity": "पक्वता", "harvest": "काढणी",
}

# Provenance for the four published infection models. These are citations to
# real, published criteria — not a claim that our implementation is certified.
MODEL_PROVENANCE = {
    "hutton": {
        "name": "Hutton Criteria",
        "for": "Phytophthora infestans (late blight)",
        "rule": "Two consecutive days with minimum temperature ≥ 10 °C and ≥ 6 hours at RH ≥ 90%.",
        "source": "James Hutton Institute — successor to the Smith Period, adopted by AHDB Fight Against Blight",
        "source_type": "published criteria",
        "note": "Implemented from the published rule. Not an endorsement by the issuing body.",
    },
    "tomcast": {
        "name": "TOMCAST (DSV accumulation)",
        "for": "Alternaria solani (early blight), Septoria, anthracnose",
        "rule": "Daily severity values from leaf-wetness hours in four temperature bands; spray interval at 15–20 accumulated DSV.",
        "source": "Pitblado (Ridgetown) / Ohio State University Extension TOMCAST",
        "source_type": "published model",
        "note": "Leaf wetness is approximated by hours at RH ≥ 90% — see weather.py.",
    },
    "gubler": {
        "name": "Gubler-Thomas Powdery Mildew Risk Index",
        "for": "Erysiphe necator (grape powdery mildew)",
        "rule": "Index 0–100 from consecutive days with 6+ hours in 21–30 °C; ≥ 60 is high risk.",
        "source": "Gubler & Thomas, UC Davis / UC IPM",
        "source_type": "published index",
        "note": "Implemented from the published index definition.",
    },
    "three_ten": {
        "name": "3-10 Rule",
        "for": "Plasmopara viticola (grape downy mildew) primary infection",
        "rule": "Shoots ≥ 10 cm, ≥ 10 mm rain in 24–48 h, mean temperature ≥ 10 °C.",
        "source": "Baldacci / widely used European viticulture rule of thumb",
        "source_type": "published rule",
        "note": "A primary-infection trigger, not a season-long model.",
    },
}


def crop_stage(crop: str, sown_on: str | None,
               today: dt.date | None = None) -> dict[str, Any]:
    """Crop stage scales the economic threshold, decides whether a spray can
    reach the pest, and is one of the inputs the problem statement names."""
    if today is None:
        from .clock import today as _t
        today = _t()
    c = CROPS.get(crop)
    if not c or not sown_on:
        return {"stage": None, "days": None, "label": "unknown",
                "label_mr": "माहिती नाही", "progress": None, "days_to_harvest": None}
    try:
        sown = dt.date.fromisoformat(str(sown_on)[:10])
    except ValueError:
        return {"stage": None, "days": None, "label": "unknown",
                "label_mr": "माहिती नाही", "progress": None, "days_to_harvest": None}
    days = (today - sown).days
    for key, lo, hi, label in c["stages"]:
        if lo <= days <= hi:
            span = max(1, hi - lo)
            return {"stage": key, "days": days, "label": label,
                    "label_mr": STAGE_MR.get(key, label),
                    "progress": round((days - lo) / span, 2),
                    "days_to_harvest": max(0, c["stages"][-1][2] - days)}
    last = c["stages"][-1]
    return {"stage": last[0], "days": days, "label": last[3],
            "label_mr": STAGE_MR.get(last[0], last[3]), "progress": 1.0,
            "days_to_harvest": 0}


def threshold_for(pest: str, crop: str) -> dict | None:
    for row in THRESHOLDS:
        if row["pest"] == pest and row["crop"] == crop:
            return row
    return None


def problems_for_crop(crop: str) -> dict[str, dict]:
    return {k: v for k, v in DISEASES.items() if crop in v["crops"]}


def pests_for_crop(crop: str) -> dict[str, dict]:
    return {k: v for k, v in PESTS.items() if crop in v["crops"]}


def problem(pid: str) -> dict | None:
    return DISEASES.get(pid) or PESTS.get(pid)


def problem_name(pid: str, lang: str = "en") -> str:
    p = problem(pid)
    if not p:
        return pid
    return p.get("mr", p["name"]) if lang == "mr" else p["name"]


def taluka_name(tid: str, lang: str = "en") -> str:
    t = TALUKA_BY_ID.get(tid)
    if not t:
        return tid
    return t.get("mr", t["name"]) if lang == "mr" else t["name"]


def crop_has_vision_reference(crop: str) -> bool:
    """Whether an image reference set exists for this crop at all. When it does
    not, the camera abstains and says why — that is a finding about Indian open
    agricultural data, not a gap being hidden."""
    return bool(CROPS.get(crop, {}).get("vision"))


def nearest_taluka(lat: float, lng: float) -> str:
    """Field coordinates are mapped to an administrative unit for surveillance
    aggregation. Approximate by design: the officer console works at taluka
    resolution and publishing anything finer would expose individual farms."""
    best, best_d = TALUKAS[0]["id"], float("inf")
    for t in TALUKAS:
        d = (t["lat"] - lat) ** 2 + (t["lng"] - lng) ** 2
        if d < best_d:
            best, best_d = t["id"], d
    return best
