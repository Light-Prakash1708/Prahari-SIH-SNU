"""PRAHARI · /api/plots — field onboarding and the field record."""
from __future__ import annotations

import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import reference
from ..clock import now_iso
from ..clock import today as _today
from ..db import Database, bit, dumps, loads
from ..deps import current_user, db_dep, farmer_of, officer_talukas, owned_plot, visible_plot
from ..errors import bad_request
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import CropCycleIn, PlotIn, PlotPatch

router = APIRouter(prefix="/api/plots", tags=["fields"])


def _polygon_area_acres(boundary: dict[str, Any]) -> float | None:
    """Spherical excess is overkill for a two-acre field; an equirectangular
    projection about the polygon's own centroid is accurate to well under a
    percent at this scale. The response says approximate, because a drawn
    boundary is a farmer's finger on a phone, not a survey."""
    try:
        ring = boundary["coordinates"][0]
    except (KeyError, IndexError, TypeError):
        return None
    if len(ring) < 4:
        return None
    lat0 = sum(p[1] for p in ring) / len(ring)
    k = math.cos(math.radians(lat0))
    pts = [(p[0] * k * 111_320.0, p[1] * 111_320.0) for p in ring]
    area = 0.0
    for i in range(len(pts) - 1):
        area += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
    m2 = abs(area) / 2.0
    return round(m2 / 4046.8564224, 3)


def _centroid(boundary: dict[str, Any]):
    try:
        ring = boundary["coordinates"][0]
    except (KeyError, IndexError, TypeError):
        return None, None
    return (sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring))


@router.post("", status_code=201, summary="Register a field",
             description=("Creates the field and opens its first crop cycle. Location may be a GPS "
                          "fix, a map placement or a taluka choice; a drawn GeoJSON boundary also "
                          "yields an approximate area, which is reported as approximate and never "
                          "as survey-grade.\n\nErrors: 400 unknown_crop · 400 unknown_taluka"))
def create_plot(data: PlotIn, user: dict[str, Any] = Depends(current_user),
                db: Database = Depends(db_dep)):
    if user["role"] != "farmer":
        from ..errors import forbidden
        raise forbidden("field registration — only a farmer account owns fields")
    farmer = farmer_of(db, user)
    if data.crop not in reference.CROPS:
        raise bad_request("unknown_crop",
                          f"PRAHARI does not yet carry agronomic models for '{data.crop}'. "
                          f"Covered crops: {', '.join(reference.CROPS)}.")

    lat, lng = data.lat, data.lng
    area = data.area_acre
    area_source = "declared"
    boundary = data.boundary
    if boundary:
        derived = _polygon_area_acres(boundary)
        if derived and derived > 0:
            area, area_source = derived, "polygon"
        if lat is None or lng is None:
            lat, lng = _centroid(boundary)

    taluka = data.taluka
    if not taluka:
        taluka = reference.nearest_taluka(lat, lng) if lat is not None else farmer["taluka"]
    if taluka not in reference.TALUKA_IDS:
        raise bad_request("unknown_taluka",
                          f"'{taluka}' is not a taluka PRAHARI covers.")
    if lat is None or lng is None:
        t = reference.TALUKA_BY_ID[taluka]
        lat, lng = t["lat"], t["lng"]

    pid = "P-" + uuid.uuid4().hex[:10].upper()
    stamp = now_iso()
    db.execute(
        "INSERT INTO plots (id, farmer_id, name, crop, variety, area_acre, area_source, sown_on,"
        " expected_harvest, lat, lng, location_source, taluka, village, soil, irrigation,"
        " tank_litres, boundary, archived, created_at, updated_at)"
        " VALUES (:id,:f,:n,:crop,:var,:area,:asrc,:sown,:harv,:lat,:lng,:lsrc,:tk,:vil,:soil,"
        " :irr,:tank,:bnd,0,:now,:now)",
        {"id": pid, "f": farmer["id"], "n": data.name, "crop": data.crop, "var": data.variety,
         "area": area, "asrc": area_source, "sown": data.sown_on.isoformat(),
         "harv": data.expected_harvest.isoformat() if data.expected_harvest else None,
         "lat": lat, "lng": lng, "lsrc": data.location_source, "tk": taluka,
         "vil": data.village or farmer.get("village"), "soil": data.soil,
         "irr": data.irrigation, "tank": data.tank_litres,
         "bnd": dumps(boundary), "now": stamp})
    cycle_id = "C-" + uuid.uuid4().hex[:10].upper()
    db.execute(
        "INSERT INTO crop_cycles (id, plot_id, crop, variety, sown_on, created_at)"
        " VALUES (:id,:p,:crop,:var,:sown,:now)",
        {"id": cycle_id, "p": pid, "crop": data.crop, "var": data.variety,
         "sown": data.sown_on.isoformat(), "now": stamp})
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, title_mr, detail, ref, created_at)"
        " VALUES (:p,:at,'field','info',:t,:tmr,:d,:ref,:now)",
        {"p": pid, "at": _today().isoformat(),
         "t": f"Field registered — {data.crop} sown {data.sown_on.isoformat()}",
         "tmr": f"शेत नोंदवले — {data.sown_on.isoformat()} रोजी पेरणी",
         "d": f"{area} acres, {area_source} area, located by {data.location_source}.",
         "ref": cycle_id, "now": stamp})
    audit("plot.create", entity="plot", entity_id=pid, user_id=user["id"], role=user["role"])
    return _decorate(db, db.one("SELECT * FROM plots WHERE id = :id", {"id": pid}))


@router.get("", summary="List the fields you may see",
            description=("A farmer receives their own fields and no others. An officer receives "
                          "fields in their authorised talukas, with the farmer's contact details "
                          "removed. Nothing here is filtered in the browser."))
def list_plots(user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep),
               include_archived: bool = Query(False)):
    role = user["role"]
    if role == "farmer":
        farmer = farmer_of(db, user)
        sql = "SELECT * FROM plots WHERE farmer_id = :f"
        params: dict[str, Any] = {"f": farmer["id"]}
        if not include_archived:
            sql += " AND archived = 0"
        rows = db.rows(sql + " ORDER BY created_at", params)
    elif role in ("officer", "admin"):
        scopes = officer_talukas(db, user)
        if not scopes:
            return {"plots": [], "note": "No talukas are assigned to your account yet."}
        placeholders = ",".join(f":t{i}" for i in range(len(scopes)))
        rows = db.rows(
            f"SELECT p.*, f.name AS farmer_name FROM plots p JOIN farmers f ON f.id = p.farmer_id"
            f" WHERE p.taluka IN ({placeholders}) AND p.archived = 0 ORDER BY p.taluka, p.name",
            {f"t{i}": t for i, t in enumerate(scopes)})
        for r in rows:
            r.pop("farmer_id", None)
    else:
        rows = []
    return {"plots": [_decorate(db, r) for r in rows]}


@router.get("/{plot_id}", summary="One field")
def get_plot(plot_id: str, user: dict[str, Any] = Depends(current_user),
             db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    from ..deps import redact_for
    return _decorate(db, redact_for(user["role"], plot))


@router.patch("/{plot_id}", summary="Update a field you own")
def patch_plot(plot_id: str, data: PlotPatch, user: dict[str, Any] = Depends(current_user),
               db: Database = Depends(db_dep)):
    owned_plot(db, user, plot_id)
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        raise bad_request("nothing_to_update", "No changes were supplied.")
    if "archived" in fields:
        fields["archived"] = bit(fields["archived"])
    if "expected_harvest" in fields:
        fields["expected_harvest"] = fields["expected_harvest"].isoformat()
    if "area_acre" in fields:
        fields["area_source"] = "declared"
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    db.execute(f"UPDATE plots SET {sets}, updated_at = :now WHERE id = :id",
               {**fields, "now": now_iso(), "id": plot_id})
    audit("plot.update", entity="plot", entity_id=plot_id, user_id=user["id"],
          detail={"fields": list(fields)})
    return _decorate(db, db.one("SELECT * FROM plots WHERE id = :id", {"id": plot_id}))


@router.post("/{plot_id}/cycles", status_code=201, summary="Start a new crop cycle",
             description="Closes the running cycle and opens a new one. The field's history "
                         "survives the change — that is what makes it a Field Health Passport "
                         "rather than a season of notes.")
def new_cycle(plot_id: str, data: CropCycleIn, user: dict[str, Any] = Depends(current_user),
              db: Database = Depends(db_dep)):
    owned_plot(db, user, plot_id)
    if data.crop not in reference.CROPS:
        raise bad_request("unknown_crop", f"PRAHARI has no models for '{data.crop}'.")
    stamp = now_iso()
    if data.end_previous:
        db.execute("UPDATE crop_cycles SET ended_on = :d WHERE plot_id = :p AND ended_on IS NULL",
                   {"d": _today().isoformat(), "p": plot_id})
    cid = "C-" + uuid.uuid4().hex[:10].upper()
    db.execute(
        "INSERT INTO crop_cycles (id, plot_id, crop, variety, sown_on, created_at)"
        " VALUES (:id,:p,:c,:v,:s,:now)",
        {"id": cid, "p": plot_id, "c": data.crop, "v": data.variety,
         "s": data.sown_on.isoformat(), "now": stamp})
    db.execute("UPDATE plots SET crop = :c, variety = :v, sown_on = :s, updated_at = :now"
               " WHERE id = :id",
               {"c": data.crop, "v": data.variety, "s": data.sown_on.isoformat(),
                "now": stamp, "id": plot_id})
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
        " VALUES (:p,:at,'field','info',:t,:d,:ref,:now)",
        {"p": plot_id, "at": _today().isoformat(),
         "t": f"New crop cycle — {data.crop}",
         "d": f"Sown {data.sown_on.isoformat()}. Previous cycle closed.",
         "ref": cid, "now": stamp})
    return {"cycle_id": cid, "plot": _decorate(db, db.one("SELECT * FROM plots WHERE id=:id",
                                                          {"id": plot_id}))}


@router.get("/{plot_id}/history", summary="Field Health Passport",
            description="Everything that has happened to this field, in order, across crop cycles.")
def history(plot_id: str, limit: int = Query(80, le=300),
            user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rt = get_runtime()
    events = db.rows(
        "SELECT * FROM field_events WHERE plot_id = :p ORDER BY at DESC, id DESC LIMIT :n",
        {"p": plot_id, "n": limit})
    cycles = db.rows("SELECT * FROM crop_cycles WHERE plot_id = :p ORDER BY sown_on DESC",
                     {"p": plot_id})
    scores = rt.risk.snapshot_history(plot_id, 60)
    applications = db.rows(
        "SELECT id, kind, product, target, applied_on, clears_on, phi_days FROM applications"
        " WHERE plot_id = :p ORDER BY applied_on DESC", {"p": plot_id})
    checks = db.rows(
        "SELECT pest, count, etl_effective, band, acted, checked_on FROM threshold_checks"
        " WHERE plot_id = :p ORDER BY checked_at DESC LIMIT 40", {"p": plot_id})
    seasons = []
    for c in cycles:
        seasons.append({
            **c,
            "events": [e for e in events
                       if str(e["at"]) >= str(c["sown_on"])
                       and (c["ended_on"] is None or str(e["at"]) <= str(c["ended_on"]))],
        })
    return {
        "plot": _decorate(db, plot),
        "timeline": events,
        "cycles": cycles,
        "seasons": seasons,
        "health_scores": list(reversed(scores)),
        "applications": applications,
        "threshold_checks": checks,
        "note": ("The passport is the field's own record. Last season's confirmed problems raise "
                 "this taluka's prior for the same crop — a correlation PRAHARI uses as a weak "
                 "signal, never as proof that the same problem will recur."),
    }


def _decorate(db: Database, plot: dict[str, Any]) -> dict[str, Any]:
    out = dict(plot)
    out["boundary"] = loads(out.get("boundary"))
    out["archived"] = bool(out.get("archived"))
    out["crop_stage"] = reference.crop_stage(out["crop"], out.get("sown_on"), _today())
    out["crop_label"] = reference.CROPS.get(out["crop"], {}).get("name", out["crop"])
    out["taluka_name"] = reference.taluka_name(out.get("taluka") or "")
    if out.get("area_source") == "polygon":
        out["area_note"] = ("Area calculated from the boundary you drew. Approximate — not a "
                            "survey measurement, and not suitable for a land record.")
    return out
