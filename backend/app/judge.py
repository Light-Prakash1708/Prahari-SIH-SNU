"""
PRAHARI · judge mode — a repeatable demonstration, on a STAGING service only
════════════════════════════════════════════════════════════════════════════
A judge has eight minutes. In that time PRAHARI has to show eight things it
does — and two of them (refusing a bad photograph, saying "do not spray") are
things it does NOT do, which is the point. This module makes that sequence
repeatable without bending a single engine:

  · It exists only where the demo router exists: DEMO_MODE=true, which
    config.py refuses when APP_ENV=production. Production never mounts it.
  · Every case runs through the REAL code path — the photo-quality gate, the
    diagnosis engine, the threshold engine, the outbreak grading, the officer
    queue, the FPO summary. Nothing here writes a diagnosis, a weather value,
    an expert verdict or a decision.
  · What it controls is INPUT and STARTING STATE: which weather story the
    labelled demo generator tells, and a fresh field for the demo farmer.
  · Reset never deletes a farmer record. The demo farmer's earlier fields are
    ARCHIVED (the normal archive flag) and a fresh one is created through the
    same create_plot every farmer uses. Only the fixed @prahari.demo console
    account is touched.

The synthetic seeded farmers (9000000001–5, created only in demo mode) join the
demo producer organisation through the same join path a farmer uses, so the
FPO console has the three members its small-cell rule needs before it shows
any count. They are synthetic accounts; the guide says so.
"""
from __future__ import annotations

from typing import Any

from .clock import now_iso
from .db import Database

DEMO_FARMER_EMAIL = "farmer@prahari.demo"

CASES: list[dict[str, Any]] = [
    {
        "n": 1, "key": "weather_risk", "role": "farmer", "route": "forecast",
        "title": "Weather-linked risk, before any symptom",
        "do": "Open the farmer console → Risk Forecast.",
        "expect": ("A published infection model (Hutton / TOMCAST) fires on the field's weather and "
                   "names the days. The DEMO banner says the weather is generated."),
        "honesty": ("Staging weather is the labelled deterministic generator, not an observation. "
                    "The infection models are the production models, unchanged."),
    },
    {
        "n": 2, "key": "bad_photo", "role": "farmer", "route": "scan",
        "title": "A poor photograph is refused",
        "do": "Scan → Gallery → samples/bad_photo.jpg.",
        "expect": "No diagnosis. The quality gate names what is wrong and what to fix.",
        "honesty": "This is the production quality gate. Nothing is diagnosed from the image.",
    },
    {
        "n": 3, "key": "usable_photo", "role": "farmer", "route": "scan",
        "title": "A usable photograph gets a differential, not a verdict",
        "do": "Scan → Gallery → samples/late_blight.jpg.",
        "expect": ("Ranked candidates with confidence, the evidence measured, the engine named — "
                   "or an abstention when the engine is not confident enough."),
        "honesty": ("The engine is whatever VISION_PROVIDER says on this service — the symptom-"
                    "feature engine is not a trained neural network and is never called one. "
                    "No field accuracy is claimed."),
    },
    {
        "n": 4, "key": "no_spray", "role": "farmer", "route": "decide",
        "title": "Below the threshold: do not spray",
        "do": "What should I do? → Fruit borer → type 2 on the counter → Save count.",
        "expect": ("The preview and the saved decision agree: below the published threshold, no "
                   "chemical, a rupee saving and a re-count date."),
        "honesty": "The count is typed by the presenter and is labelled as a count, not a measurement of a real field.",
    },
    {
        "n": 5, "key": "expert_review", "role": "expert", "route": "expert",
        "title": "An uncertain case goes to a person",
        "do": "From case 3, tap Request expert review, then open the expert console.",
        "expect": "The case brief shows the photo, the weather at the field, its history and why it was escalated.",
        "honesty": "No expert verdict is pre-filled. The confirmation, if any, is made live.",
    },
    {
        "n": 6, "key": "community_signal", "role": "farmer", "route": "hotspots",
        "title": "Community reports are graded, not believed",
        "do": "Nearby hotspots.",
        "expect": ("Reports appear as a graded signal (conversation vs evidence-backed). A possible "
                   "cluster is never called a confirmed outbreak."),
        "honesty": "The seeded reports are synthetic and belong to synthetic demo farmers.",
    },
    {
        "n": 7, "key": "officer_queue", "role": "officer", "route": "officer",
        "title": "The officer gets a ranked queue, not a map of dots",
        "do": "Open the officer console.",
        "expect": "Cases ordered by stated reasons, Gi* hotspots with z-scores, outbreak grades with their basis.",
        "honesty": "Computed from the synthetic surveillance history seeded on this staging service.",
    },
    {
        "n": 8, "key": "fpo_view", "role": "fpo", "route": "fpo",
        "title": "The FPO sees counts across consenting members — never a field",
        "do": "Open the FPO console.",
        "expect": "Members, crops, fields needing attention, overdue follow-ups. Any count under 3 shows as 'fewer than 3'.",
        "honesty": "Members are synthetic demo farmers who joined through the farmer's own join path.",
    },
]


def guide(db: Database) -> dict[str, Any]:
    """The eight cases, plus what the staging data can actually show right now,
    so a presenter learns before the judges do that a case will come up empty."""
    from .routers.auth import DEMO_FPO
    members = db.scalar("SELECT COUNT(*) FROM fpo_members WHERE fpo_id = :f",
                        {"f": DEMO_FPO[0]}) or 0
    posts = db.scalar("SELECT COUNT(*) FROM community_posts") or 0
    obs = db.scalar("SELECT COUNT(*) FROM observations") or 0
    return {
        "judge_mode": True,
        "environment": "staging — synthetic data, generated weather",
        "cases": CASES,
        "readiness": {
            "fpo_members": int(members),
            "fpo_view_has_counts": int(members) >= 3,
            "community_posts": int(posts),
            "surveillance_observations": int(obs),
        },
        "rules": [
            "Never run judge mode on the production service.",
            "Every diagnosis, decision, grade and queue on screen is produced live by the production engines.",
            "Weather on staging is generated and labelled; say so out loud.",
            "A possible cluster is never described as a confirmed outbreak.",
        ],
    }


def reset(db: Database, rt) -> dict[str, Any]:
    """Put staging back to the judge starting state. Idempotent."""
    from . import scenarios_v2 as scenarios
    from .routers.auth import DEMO_FPO, _ensure_demo_field, _link_demo_fpo

    out: dict[str, Any] = {"scenario": scenarios.set_scenario(db, "emerging")["scenario"]}

    # 1 · a fresh field for the fixed demo farmer. Older ones are archived,
    #     never deleted, through the same flag a farmer's own "archive" sets.
    user = db.one("SELECT id FROM users WHERE email = :e", {"e": DEMO_FARMER_EMAIL})
    archived = 0
    if user:
        farmer = db.one("SELECT id FROM farmers WHERE user_id = :u", {"u": user["id"]})
        if farmer:
            archived = db.execute(
                "UPDATE plots SET archived = 1, updated_at = :now WHERE farmer_id = :f AND archived = 0",
                {"f": farmer["id"], "now": now_iso()}) or 0
            _ensure_demo_field(db, user["id"])
    out["demo_farmer_fields_archived"] = archived
    out["demo_farmer_present"] = bool(user)

    # 2 · the FPO has three consenting members, so its counts are not all
    #     suppressed. Synthetic farmers only, through the farmer's join path.
    fid = DEMO_FPO[0]
    if not db.one("SELECT id FROM fpos WHERE id = :i", {"i": fid}):
        staff = db.one("SELECT id FROM users WHERE email = 'fpo@prahari.demo'")
        if staff:
            _link_demo_fpo(db, staff["id"])
        else:
            db.execute("INSERT INTO fpos (id, name, name_mr, district, created_at)"
                       " VALUES (:i,:n,:nm,'nashik',:now)",
                       {"i": fid, "n": DEMO_FPO[1], "nm": DEMO_FPO[2], "now": now_iso()})
    joined = 0
    for row in db.rows(
            "SELECT f.id FROM farmers f JOIN users u ON u.id = f.user_id"
            " WHERE u.phone LIKE '900000000%' ORDER BY u.phone LIMIT 3"):
        if not db.one("SELECT 1 AS x FROM fpo_members WHERE fpo_id = :f AND farmer_id = :m",
                      {"f": fid, "m": row["id"]}):
            db.execute("INSERT INTO fpo_members (fpo_id, farmer_id, consented_at)"
                       " VALUES (:f,:m,:now)", {"f": fid, "m": row["id"], "now": now_iso()})
            joined += 1
    out["synthetic_members_joined"] = joined
    out["note"] = ("Starting state restored. Nothing was deleted: earlier demo fields are archived, "
                   "and no diagnosis, decision, weather value or expert verdict was written.")
    return out
