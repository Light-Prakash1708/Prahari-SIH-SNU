"""
PRAHARI · /api/traps — pest trap monitoring, including image-assisted counting.

The trap image path is honest about what it can and cannot do. Counting sticky
insects from a phone photograph is a detection problem the shipped model is not
trained for, so unless a trap-counting model is configured the response says the
estimate is unavailable and asks for the farmer's own count. It does NOT invent
a number, and it never claims species-level identification the model cannot do.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from .. import reference
from .. import storage as storage_mod
from ..clock import now_iso
from ..clock import today as _today
from ..config import get_settings
from ..db import Database
from ..deps import current_user, db_dep, owned_plot, visible_plot
from ..errors import bad_request, not_found
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import TrapCountIn, TrapIn

router = APIRouter(prefix="/api/traps", tags=["traps"])

SPIKE_FACTOR = 1.8


@router.post("", status_code=201, summary="Install a trap in a field")
def create_trap(data: TrapIn, user: dict[str, Any] = Depends(current_user),
                db: Database = Depends(db_dep)):
    plot = owned_plot(db, user, data.plot_id)
    if data.pest not in reference.PESTS:
        raise bad_request("unknown_pest", f"'{data.pest}' is not a pest PRAHARI tracks.")
    if not reference.threshold_for(data.pest, plot["crop"]):
        raise bad_request(
            "no_threshold_for_crop",
            f"PRAHARI has no published economic threshold for "
            f"{reference.problem_name(data.pest)} on {plot['crop']}, so counts from this trap "
            f"could not be judged against anything.")
    tid = "T-" + uuid.uuid4().hex[:10].upper()
    db.execute(
        "INSERT INTO traps (id, plot_id, pest, trap_type, installed_on, active, created_at)"
        " VALUES (:id,:p,:pest,:type,:on,1,:now)",
        {"id": tid, "p": plot["id"], "pest": data.pest, "type": data.trap_type,
         "on": (data.installed_on or _today()).isoformat(), "now": now_iso()})
    audit("trap.create", entity="trap", entity_id=tid, user_id=user["id"])
    return db.one("SELECT * FROM traps WHERE id = :id", {"id": tid})


@router.get("", summary="Traps in a field, with their count history")
def list_traps(plot_id: str = Query(...), user: dict[str, Any] = Depends(current_user),
               db: Database = Depends(db_dep)):
    visible_plot(db, user, plot_id)
    traps = db.rows("SELECT * FROM traps WHERE plot_id = :p ORDER BY installed_on DESC",
                    {"p": plot_id})
    for t in traps:
        t["pest_name"] = reference.problem_name(t["pest"])
        t["pest_name_mr"] = reference.problem_name(t["pest"], "mr")
        t["counts"] = db.rows(
            "SELECT id, counted_on, count, count_source, image_confidence, nights"
            " FROM trap_observations WHERE trap_id = :t ORDER BY counted_on DESC, created_at DESC LIMIT 20",
            {"t": t["id"]})
        t["trend"] = _trend(t["counts"])
        row = reference.threshold_for(t["pest"], _crop(db, plot_id))
        t["etl"] = (row or {}).get("etl")
        t["etl_unit"] = (row or {}).get("unit")
        t["etl_source"] = (row or {}).get("source")
    return {"traps": traps}


@router.post("/{trap_id}/counts", status_code=201,
             summary="Record a trap count",
             description="Detects a rapid rise and a threshold crossing across the recorded series.")
def record_count(trap_id: str, data: TrapCountIn,
                 user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    trap = db.one("SELECT * FROM traps WHERE id = :id", {"id": trap_id})
    if not trap:
        raise not_found("trap", trap_id)
    plot = owned_plot(db, user, trap["plot_id"])
    return _store_count(db, trap, plot, data.count, "manual",
                        data.counted_on or _today(), data.nights)


@router.post("/{trap_id}/scan", status_code=201,
             summary="Photograph a sticky trap for an assisted count",
             description=(
                 "Stores the trap photograph against an observation and, IF a trap-counting model "
                 "is configured, returns an estimate with its confidence. Without such a model the "
                 "response says the estimate is unavailable and asks for the farmer's own count — "
                 "it does not produce a number.\n\nPRAHARI never claims species-level identification "
                 "from a trap photograph unless the configured model supports it, because a "
                 "misidentified species means the wrong economic threshold."))
async def scan_trap(trap_id: str, image: UploadFile = File(...),
                    manual_count: float | None = Form(None),
                    nights: int = Form(1),
                    user: dict[str, Any] = Depends(current_user),
                    db: Database = Depends(db_dep)):
    trap = db.one("SELECT * FROM traps WHERE id = :id", {"id": trap_id})
    if not trap:
        raise not_found("trap", trap_id)
    plot = owned_plot(db, user, trap["plot_id"])
    rt = get_runtime()
    s = get_settings()

    raw = await image.read()
    storage_mod.validate_image(raw, s.max_upload_bytes)
    clean = storage_mod.sanitize(raw)
    key = storage_mod.make_key(f"traps/{trap_id}")
    rt.storage.put(key, clean, "image/jpeg")

    oid = "O-" + uuid.uuid4().hex[:10].upper()
    stamp = now_iso()
    db.execute(
        "INSERT INTO observations (id, plot_id, farmer_id, kind, taluka, crop, crop_stage,"
        " observed_at, source, status, created_at)"
        " VALUES (:id,:p,:f,'trap',:tk,:crop,:cs,:at,'app','open',:now)",
        {"id": oid, "p": plot["id"], "f": plot["farmer_id"], "tk": plot["taluka"],
         "crop": plot["crop"], "cs": rt.risk.crop_stage(plot).get("stage"),
         "at": stamp, "now": stamp})
    db.execute(
        "INSERT INTO observation_images (id, observation_id, role, storage_key, content_type,"
        " bytes, sha256, created_at)"
        " VALUES (:id,:o,'trap',:k,'image/jpeg',:b,:sha,:now)",
        {"id": "I-" + uuid.uuid4().hex[:10].upper(), "o": oid, "k": key,
         "b": len(clean), "sha": storage_mod.sha256(clean), "now": stamp})

    estimate = None
    confidence = "unavailable"
    note = (
        "No trap-counting model is configured on this instance, so PRAHARI cannot estimate the "
        "catch from this photograph. The photograph is stored against the trap record — enter the "
        "count you made yourself and PRAHARI will judge it against the economic threshold.")
    if manual_count is None:
        return {
            "observation_id": oid, "trap_id": trap_id,
            "image_estimate": None, "image_confidence": confidence,
            "count_recorded": False, "note": note,
            "next": "Count the insects on the trap and submit that number.",
            "next_mr": "सापळ्यावरील किडे मोजा आणि तो आकडा नोंदवा.",
        }
    out = _store_count(db, trap, plot, manual_count, "image_assisted", _today(), nights,
                       observation_id=oid, image_estimate=estimate, confidence=confidence)
    out["note"] = note
    return out


@router.get("/{trap_id}/series", summary="The recorded count series for a trap")
def series(trap_id: str, user: dict[str, Any] = Depends(current_user),
           db: Database = Depends(db_dep)):
    trap = db.one("SELECT * FROM traps WHERE id = :id", {"id": trap_id})
    if not trap:
        raise not_found("trap", trap_id)
    visible_plot(db, user, trap["plot_id"])
    counts = db.rows(
        "SELECT counted_on, count, count_source, nights FROM trap_observations"
        " WHERE trap_id = :t ORDER BY counted_on, created_at", {"t": trap_id})
    row = reference.threshold_for(trap["pest"], _crop(db, trap["plot_id"]))
    return {"trap": trap, "counts": counts, "trend": _trend(list(reversed(counts))),
            "etl": (row or {}).get("etl"), "etl_unit": (row or {}).get("unit"),
            "etl_source": (row or {}).get("source")}


# ── helpers ─────────────────────────────────────────────────────────────────
def _crop(db: Database, plot_id: str) -> str:
    row = db.one("SELECT crop FROM plots WHERE id = :id", {"id": plot_id})
    return (row or {}).get("crop", "")


def _trend(counts_desc: list[dict[str, Any]]) -> dict[str, Any]:
    """counts_desc is newest-first."""
    if len(counts_desc) < 2:
        return {"direction": "unknown", "say": "Not enough counts yet to show a trend."}
    latest, prev = counts_desc[0]["count"], counts_desc[1]["count"]
    delta = latest - prev
    direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
    out = {"direction": direction, "delta": round(delta, 2),
           "say": (f"Up from {prev:g} at the last count." if delta > 0 else
                   f"Down from {prev:g} at the last count." if delta < 0 else
                   "Unchanged since the last count.")}
    if prev > 0 and latest >= prev * SPIKE_FACTOR:
        out["spike"] = True
        out["say"] += (f" That is a {latest/prev:.1f}× rise in one interval — count again "
                       f"tomorrow rather than in five days.")
    rising = all(counts_desc[i]["count"] > counts_desc[i + 1]["count"]
                 for i in range(min(2, len(counts_desc) - 1)))
    out["consecutive_rises"] = bool(rising and len(counts_desc) >= 3)
    return out


def _store_count(db: Database, trap: dict[str, Any], plot: dict[str, Any], count: float,
                 source: str, on: dt.date, nights: int,
                 observation_id: str | None = None,
                 image_estimate: float | None = None,
                 confidence: str = "unavailable") -> dict[str, Any]:
    rt = get_runtime()
    tid = "TO-" + uuid.uuid4().hex[:10].upper()
    db.execute(
        "INSERT INTO trap_observations (id, trap_id, plot_id, observation_id, counted_on, count,"
        " count_source, image_estimate, image_confidence, nights, created_at)"
        " VALUES (:id,:t,:p,:o,:on,:n,:src,:est,:conf,:nights,:now)",
        {"id": tid, "t": trap["id"], "p": plot["id"], "o": observation_id,
         "on": on.isoformat(), "n": count, "src": source, "est": image_estimate,
         "conf": confidence, "nights": nights, "now": now_iso()})
    counts = db.rows(
        "SELECT counted_on, count FROM trap_observations WHERE trap_id = :t"
        " ORDER BY counted_on DESC, created_at DESC LIMIT 10", {"t": trap["id"]})
    trend = _trend(counts)
    stage = rt.risk.crop_stage(plot)
    decision = rt.decisions.check_threshold(plot, trap["pest"], count, stage, trap_obs_id=tid)
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
        " VALUES (:p,:at,'count',:sev,:t,:d,:ref,:now)",
        {"p": plot["id"], "at": on.isoformat(),
         "sev": "high" if decision.get("chemical_authorised") else "watch",
         "t": f"{reference.problem_name(trap['pest'])} trap — {count:g} {decision.get('unit','')}",
         "d": trend["say"], "ref": tid, "now": now_iso()})
    return {"trap_observation_id": tid, "count": count, "trend": trend,
            "threshold": decision, "count_recorded": True,
            "counts": list(reversed(counts))}
