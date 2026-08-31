"""
PRAHARI · demo scenarios
════════════════════════════════════════════════════════════════════════════
Demo mode exists because a hackathon demonstration cannot depend on a venue's
wifi or on the weather in Nashik that morning. It is redesigned here so that it
CANNOT leak into production:

  · every endpoint in this module is mounted only when DEMO_MODE=true
  · config.py refuses DEMO_MODE=true when APP_ENV=production
  · the demo weather provider is not even constructed outside demo mode
  · every response from a demo-affected path carries demo: true, and the UI
    shows a persistent DEMO MODE banner

What a scenario changes is the INPUT to the engines — the weather story, the
trap counts, the confirmed cases nearby. It never changes what the engines
CONCLUDE. That is the whole design: a presenter can put the system into a known
state without the system behaving differently than it would in a real field.
"""
from __future__ import annotations

from typing import Any

from .clock import now_iso
from .db import Database

SCENARIOS: dict[str, dict[str, Any]] = {
    "healthy": {
        "title": "Healthy crop, dry weather",
        "title_mr": "निरोगी पीक, कोरडे हवामान",
        "weather": "dry",
        "shows": "No infection threshold crossed, low risk, action = continue monitoring.",
        "expect": ["Crop health score stays high",
                   "No published model fires",
                   "Should I spray? → NO, and the reason is 'nothing to treat'"],
    },
    "emerging": {
        "title": "Early warning — weather turns favourable",
        "title_mr": "पूर्वसूचना — हवामान अनुकूल होत आहे",
        "weather": "rising",
        "shows": ("Risk rises on the forecast BEFORE any symptom exists. This is the scenario that "
                  "distinguishes an early-warning platform from a photo classifier."),
        "expect": ["Today is low, day 3 is high",
                   "The driver is named: Hutton criteria met on the forecast",
                   "Recommended action = increase scouting, not spray"],
    },
    "threshold": {
        "title": "Pest threshold crossed",
        "title_mr": "किडीची आर्थिक मर्यादा ओलांडली",
        "weather": "monsoon",
        "trap_counts": [8, 14, 21, 33],
        "shows": "Trap counts rise across four days and cross the ETL; the IPM ladder opens rung 3.",
        "expect": ["The count series is visible and rising",
                   "Should I spray? flips to ACTION REQUIRED",
                   "Chemical options appear ONLY if a verified label claim exists"],
    },
    "uncertain": {
        "title": "Uncertain diagnosis",
        "title_mr": "अनिश्चित निदान",
        "weather": "monsoon",
        "shows": "The image conflicts with local context; the model abstains and asks questions.",
        "expect": ["An abstention with a named reason",
                   "Contextual questions that could settle it",
                   "An expert case the farmer can watch"],
    },
    "recovery": {
        "title": "Treatment worked — follow-up",
        "title_mr": "उपचार लागू पडला — पुन्हा तपासणी",
        "weather": "monsoon",
        "shows": "A re-scan after an intervention, compared with the first, reported as a DIRECTION.",
        "expect": ["Before / after comparison",
                   "Direction only — no invented severity percentage",
                   "The Field Health Passport shows the whole arc"],
    },
}

DEFAULT = "emerging"


def current(db: Database) -> str:
    row = db.one("SELECT scenario FROM demo_state WHERE id = 1")
    return (row or {}).get("scenario", DEFAULT)


def set_scenario(db: Database, key: str) -> dict[str, Any]:
    if key not in SCENARIOS:
        raise ValueError(f"unknown scenario '{key}'")
    if db.one("SELECT id FROM demo_state WHERE id = 1"):
        db.execute("UPDATE demo_state SET scenario = :s, set_at = :now WHERE id = 1",
                   {"s": key, "now": now_iso()})
    else:
        db.execute("INSERT INTO demo_state (id, scenario, set_at) VALUES (1, :s, :now)",
                   {"s": key, "now": now_iso()})
    return {"scenario": key, **SCENARIOS[key]}


def listing(db: Database) -> dict[str, Any]:
    return {
        "demo_mode": True,
        "current": current(db),
        "scenarios": [{"key": k, **v} for k, v in SCENARIOS.items()],
        "banner": "DEMO MODE — weather is generated, not observed.",
        "banner_mr": "डेमो मोड — हवामान माहिती तयार केलेली आहे, प्रत्यक्ष निरीक्षण नाही.",
        "separation": ("Demo mode is a deployment setting, not a code path. A production instance "
                       "cannot reach these endpoints: they are not mounted, the demo weather "
                       "provider is not constructed, and APP_ENV=production refuses DEMO_MODE=true "
                       "at startup."),
    }
