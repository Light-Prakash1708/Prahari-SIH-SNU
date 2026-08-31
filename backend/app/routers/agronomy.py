"""
PRAHARI · /api/agronomy — soil, water and weeds.

Three capabilities that are not disease detection but are all upstream of it:

  SOIL     a spade-and-a-mug self-test any farmer can do, plus the nutrient gap
           for whoever has a Soil Health Card. No brands, no purchases, and the
           arithmetic shown so the shopkeeper's sum can be checked.
  WATER    an FAO-56 water balance. It is a MODEL, and every response says so —
           the useful output is "go and push an auger in", with a number.
  WEEDS    the excess-green index on a photograph of the ground between rows.
           Cover and pattern, never a species and never a herbicide.

Nothing on this router can authorise a chemical. That path runs through the
economic threshold and the verified label claim, and it always will.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile

from .. import irrigation as irr
from .. import reference, soil, vision
from .. import storage as storage_mod
from ..clock import now_iso
from ..clock import today as _today
from ..config import get_settings
from ..db import Database, dumps, loads
from ..deps import current_user, db_dep, owned_plot, visible_plot
from ..errors import bad_request
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import IrrigationIn, SoilLabIn, SoilSelfTestIn
from ..weather import WeatherUnavailable

router = APIRouter(prefix="/api/agronomy", tags=["agronomy"])


# ── soil ────────────────────────────────────────────────────────────────────
@router.get("/soil/reference", summary="The self-test questions and the rating classes")
def soil_reference(user: dict[str, Any] = Depends(current_user)):
    return {
        "questions": soil.questions(),
        "ratings": soil.RATINGS,
        "crops_with_doses": sorted(soil.RDF),
        "straights": soil.STRAIGHTS,
        "sources": soil.SOURCES,
        "disclaimer": soil.DISCLAIMER, "disclaimer_mr": soil.DISCLAIMER_MR,
        "self_test_note": soil.SELF_TEST_NOTE, "self_test_note_mr": soil.SELF_TEST_NOTE_MR,
    }


@router.post("/soil/self-test", status_code=201,
             summary="Score a visual soil assessment",
             description=("Six observations a farmer makes with a spade and a mug of water, "
                          "scored 0-2 each. It measures STRUCTURE and biology and says nothing "
                          "about nutrients — the response repeats that, because a soil can score "
                          "full marks here and still be short of potassium."))
def self_test(data: SoilSelfTestIn, user: dict[str, Any] = Depends(current_user),
              db: Database = Depends(db_dep)):
    plot = owned_plot(db, user, data.plot_id)
    result = soil.score_self_test(data.answers)
    sid = "SL-" + uuid.uuid4().hex[:10].upper()
    day = (data.tested_on or _today()).isoformat()
    db.execute(
        "INSERT INTO soil_tests (id, plot_id, kind, tested_on, answers, score, out_of, band,"
        " findings, created_at)"
        " VALUES (:id,:p,'self_test',:on,:a,:s,:o,:b,:f,:now)",
        {"id": sid, "p": plot["id"], "on": day, "a": dumps(data.answers),
         "s": result["score"], "o": result["out_of"], "b": result["band"],
         "f": dumps(result["findings"]), "now": now_iso()})
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
        " VALUES (:p,:at,'soil',:sev,:t,:d,:ref,:now)",
        {"p": plot["id"], "at": day,
         "sev": {"good": "info", "moderate": "watch", "poor": "rising"}[result["band"]],
         "t": f"Soil self-test — {result['label']}",
         "d": f"{result['score']} of {result['out_of']}.", "ref": sid, "now": now_iso()})
    audit("soil.self_test", entity="soil_test", entity_id=sid, user_id=user["id"])
    return {"id": sid, "tested_on": day, **result}


@router.post("/soil/lab", status_code=201,
             summary="Record soil-test values and get the nutrient gap",
             description=("Give PRAHARI whatever your Soil Health Card actually has. Every field "
                          "is optional and a missing value stays MISSING — it is never treated as "
                          "zero, because zero is a reading and a very alarming one.\n\n"
                          "The response shows the general recommended dose for the crop in the "
                          "ground, moved up a quarter where your soil tests low and down a "
                          "quarter where it tests high, and the arithmetic converting nutrient "
                          "kilograms into bag kilograms. No brand is named and no purchase is "
                          "recommended."))
def soil_lab(data: SoilLabIn, user: dict[str, Any] = Depends(current_user),
             db: Database = Depends(db_dep)):
    plot = owned_plot(db, user, data.plot_id)
    values = {k: getattr(data, k) for k in
              ("organic_carbon_pct", "nitrogen_kg_ha", "phosphorus_kg_ha",
               "potassium_kg_ha", "ph")}
    if all(v is None for v in values.values()):
        raise bad_request(
            "no_values",
            "Enter at least one soil-test value. PRAHARI will not produce a nutrient plan from "
            "no measurements — the general dose is already in the reference screen.",
            "किमान एक तपासणी आकडा नोंदवा.")
    out = soil.report(plot["crop"], values, float(plot.get("area_acre") or 1.0))
    sid = "SL-" + uuid.uuid4().hex[:10].upper()
    day = (data.tested_on or _today()).isoformat()
    db.execute(
        "INSERT INTO soil_tests (id, plot_id, kind, tested_on, organic_carbon_pct,"
        " nitrogen_kg_ha, phosphorus_kg_ha, potassium_kg_ha, ph, lab_name, report_ref,"
        " findings, created_at)"
        " VALUES (:id,:p,'lab',:on,:oc,:n,:ph_,:k,:ph,:lab,:ref,:f,:now)",
        {"id": sid, "p": plot["id"], "on": day,
         "oc": data.organic_carbon_pct, "n": data.nitrogen_kg_ha,
         "ph_": data.phosphorus_kg_ha, "k": data.potassium_kg_ha, "ph": data.ph,
         "lab": data.lab_name, "ref": data.report_ref,
         "f": dumps(out.get("plan")), "now": now_iso()})
    audit("soil.lab", entity="soil_test", entity_id=sid, user_id=user["id"])
    return {"id": sid, "tested_on": day, **out}


@router.get("/soil/{plot_id}", summary="This field's soil record")
def soil_history(plot_id: str, user: dict[str, Any] = Depends(current_user),
                 db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rows = db.rows("SELECT * FROM soil_tests WHERE plot_id = :p ORDER BY tested_on DESC",
                   {"p": plot_id})
    for r in rows:
        r["answers"] = loads(r.get("answers"))
        r["findings"] = loads(r.get("findings"))
    latest_lab = next((r for r in rows if r["kind"] == "lab"), None)
    current = None
    if latest_lab:
        current = soil.report(plot["crop"], {
            k: latest_lab.get(k) for k in
            ("organic_carbon_pct", "nitrogen_kg_ha", "phosphorus_kg_ha",
             "potassium_kg_ha", "ph")}, float(plot.get("area_acre") or 1.0))
    return {"tests": rows, "current_plan": current,
            "trend_note": ("Two tests a year apart are the only way to find out whether the "
                           "manure worked. PRAHARI keeps every test rather than overwriting the "
                           "last one.")}


# ── water ───────────────────────────────────────────────────────────────────
@router.get("/irrigation/{plot_id}", summary="Should I irrigate, and how much?",
            description=("An FAO-56 water balance: Hargreaves-Samani ET0 from this field's own "
                         "coordinates, the crop coefficient for its current stage, effective "
                         "rainfall, and the depletion since the last wetting event PRAHARI knows "
                         "about.\n\nIt is a MODEL, not a moisture sensor. Every response says so "
                         "and asks you to check the root zone with an auger before opening a "
                         "valve. Errors: 503 weather_unavailable."))
def irrigation(plot_id: str, user: dict[str, Any] = Depends(current_user),
               db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rt = get_runtime()
    try:
        wx = rt.risk.weather_series(plot)
    except WeatherUnavailable as exc:
        from ..errors import unavailable
        raise unavailable("weather_unavailable",
                          "Weather could not be retrieved for this field, so PRAHARI will not "
                          "estimate its water use. It does not substitute an average.",
                          "हवामान माहिती मिळाली नाही, त्यामुळे पाण्याचा अंदाज देता येत नाही.",
                          detail={"provider": exc.provider, "reason": exc.reason}) from exc
    last = db.one(
        "SELECT applied_on FROM irrigation_events WHERE plot_id = :p"
        " ORDER BY applied_on DESC, id DESC LIMIT 1", {"p": plot_id})
    import datetime as dt
    last_date = dt.date.fromisoformat(last["applied_on"]) if last else None
    out = irr.advise(plot, wx, rt.risk.crop_stage(plot), last_date, _today())
    out["last_irrigation"] = last["applied_on"] if last else None
    out["soil_options"] = irr.soil_options()
    out["method_options"] = irr.method_options()
    return out


@router.post("/irrigation/{plot_id}", status_code=201,
             summary="Record that you irrigated",
             description=("This is what keeps the water balance honest. Without it the model "
                          "accumulates depletion for ever and starts telling a well-watered "
                          "field that it is parched."))
def log_irrigation(plot_id: str, data: IrrigationIn,
                   user: dict[str, Any] = Depends(current_user),
                   db: Database = Depends(db_dep)):
    plot = owned_plot(db, user, plot_id)
    day = (data.applied_on or _today()).isoformat()
    rid = db.insert_returning_id(
        "INSERT INTO irrigation_events (plot_id, applied_on, method, mm_applied, hours, note,"
        " source, created_at) VALUES (:p,:on,:m,:mm,:h,:n,'farmer',:now)",
        {"p": plot_id, "on": day, "m": data.method or plot.get("irrigation"),
         "mm": data.mm_applied, "h": data.hours, "n": data.note, "now": now_iso()})
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, created_at)"
        " VALUES (:p,:at,'water','info',:t,:d,:now)",
        {"p": plot_id, "at": day, "t": "Irrigated",
         "d": (f"{data.mm_applied} mm" if data.mm_applied else
               f"{data.hours} hours" if data.hours else "recorded by the farmer"),
         "now": now_iso()})
    return {"id": rid, "applied_on": day,
            "effect": "The water balance is reset to zero from this date."}


# ── weeds ───────────────────────────────────────────────────────────────────
@router.post("/weeds", status_code=201,
             summary="Green cover between the rows, from a photograph",
             description=("The excess-green index (ExG = 2g − r − b, Woebbecke et al. 1995) on a "
                          "photograph of the ground between two rows.\n\nIt reports COVER and "
                          "PATTERN. It does not identify a species, does not estimate weeds per "
                          "square metre — PRAHARI does not know the camera height — and never "
                          "recommends a herbicide. Its value is the SERIES: the same field "
                          "photographed the same way, week to week."))
async def weeds(plot_id: str = Form(...), image: UploadFile = File(...),
                user: dict[str, Any] = Depends(current_user),
                db: Database = Depends(db_dep)):
    plot = owned_plot(db, user, plot_id)
    rt = get_runtime()
    s = get_settings()
    raw = await image.read()
    storage_mod.validate_image(raw, s.max_upload_bytes)
    clean = storage_mod.sanitize(raw)
    key = storage_mod.make_key(f"weeds/{plot_id}")
    rt.storage.put(key, clean, "image/jpeg")

    result = vision.weed_cover(clean)
    wid = "WD-" + uuid.uuid4().hex[:10].upper()
    day = _today().isoformat()
    db.execute(
        "INSERT INTO weed_checks (id, plot_id, checked_on, cover_fraction, band, pattern,"
        " patches, usable, reason, detail, created_at)"
        " VALUES (:id,:p,:on,:c,:b,:pat,:n,:u,:r,:d,:now)",
        {"id": wid, "p": plot_id, "on": day,
         "c": result.get("green_cover_fraction"), "b": result.get("band"),
         "pat": result.get("pattern"), "n": result.get("patches"),
         "u": 1 if result.get("usable") else 0, "r": result.get("reason"),
         "d": dumps(result), "now": now_iso()})

    series = db.rows(
        "SELECT checked_on, cover_fraction, band, pattern FROM weed_checks"
        " WHERE plot_id = :p AND usable = 1 ORDER BY checked_on DESC LIMIT 10", {"p": plot_id})
    out = {"id": wid, "checked_on": day, **result, "series": list(reversed(series))}
    if result.get("usable"):
        out["advice"] = _weed_advice(result, plot)
    return out


@router.get("/weeds/{plot_id}", summary="The weed-cover series for a field")
def weed_series(plot_id: str, user: dict[str, Any] = Depends(current_user),
                db: Database = Depends(db_dep)):
    visible_plot(db, user, plot_id)
    rows = db.rows(
        "SELECT id, checked_on, cover_fraction, band, pattern, patches, usable, reason"
        " FROM weed_checks WHERE plot_id = :p ORDER BY checked_on DESC LIMIT 40", {"p": plot_id})
    return {"checks": rows,
            "note": ("Cover from a hand-held photograph is a weak ABSOLUTE measurement and a "
                     "strong RELATIVE one. Compare the same field week to week and the frame "
                     "geometry mostly cancels out.")}


def _weed_advice(r: dict[str, Any], plot: dict[str, Any]) -> dict[str, Any]:
    """Non-chemical, and about crop health rather than tidiness. Weeds are the
    green bridge that carries whitefly, thrips and the viruses they vector from
    one season into the next — which is why this belongs in PRAHARI at all."""
    band, pattern = r["band"], r["pattern"]
    hosts = [reference.problem_name(p) for p in ("whitefly", "thrips")
             if plot["crop"] in (reference.PESTS.get(p, {}) or {}).get("crops", [])]
    bridge = (f" Weedy inter-rows are where {' and '.join(hosts)} sit between crops, and the "
              f"viruses they carry sit with them." if hosts else "")
    if band == "clean":
        return {"tone": "ok", "say": "Inter-row is clean. Nothing to do." + bridge}
    if pattern == "clumped":
        return {"tone": "watch",
                "say": ("The weed is in one or two patches rather than spread out. That is ten "
                        "minutes with a khurpi, and doing it now stops it seeding." + bridge)}
    if band in ("light", "moderate"):
        return {"tone": "watch",
                "say": ("Weed is spread through the inter-row. Inter-cultivation now, before "
                        "flowering, prevents the seed set that makes next season worse." + bridge)}
    return {"tone": "act",
            "say": ("Heavy cover. At this level the weeds are competing with the crop for water "
                    "and nitrogen, which shows up as poor vigour that looks like a deficiency."
                    + bridge + " PRAHARI does not recommend herbicides from a photograph — ask "
                    "your Krishi Sahayak what is registered for this crop and this weed.")}
