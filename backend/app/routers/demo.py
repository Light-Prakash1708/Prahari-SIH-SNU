"""PRAHARI · /api/demo — mounted ONLY when DEMO_MODE=true."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import reference
from .. import scenarios_v2 as scenarios
from ..clock import now_iso
from ..clock import today as _today
from ..db import Database
from ..deps import current_user, db_dep, owned_plot
from ..errors import bad_request
from ..runtime import get_runtime

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/scenarios", summary="The demo scenarios available")
def list_scenarios(db: Database = Depends(db_dep)):
    return scenarios.listing(db)


@router.post("/scenario", summary="Put the system into a known state",
             description=("Changes the INPUTS the engines are fed — the weather story, and for the "
                          "threshold scenario a series of real trap counts written through the "
                          "real threshold engine. It never changes what the engines conclude."))
def set_scenario(key: str = Query(...), plot_id: str = Query(None),
                 user: dict[str, Any] = Depends(current_user),
                 db: Database = Depends(db_dep)):
    try:
        out = scenarios.set_scenario(db, key)
    except ValueError as exc:
        raise bad_request("unknown_scenario", str(exc)) from exc
    rt = get_runtime()
    applied: dict[str, Any] = {"weather_profile": out["weather"]}

    if key == "threshold" and plot_id:
        plot = owned_plot(db, user, plot_id)
        counts = scenarios.SCENARIOS["threshold"]["trap_counts"]
        pest = next((p for p in reference.PESTS
                     if reference.threshold_for(p, plot["crop"])), None)
        if pest:
            db.execute("DELETE FROM threshold_checks WHERE plot_id = :p AND demo = 1",
                       {"p": plot_id})
            trap = db.one("SELECT * FROM traps WHERE plot_id = :p AND pest = :pest",
                          {"p": plot_id, "pest": pest})
            if not trap:
                tid = "T-" + uuid.uuid4().hex[:10].upper()
                db.execute(
                    "INSERT INTO traps (id, plot_id, pest, trap_type, installed_on, active, created_at)"
                    " VALUES (:id,:p,:pest,'pheromone',:on,1,:now)",
                    {"id": tid, "p": plot_id, "pest": pest,
                     "on": (_today() - dt.timedelta(days=6)).isoformat(), "now": now_iso()})
                trap = db.one("SELECT * FROM traps WHERE id = :id", {"id": tid})
            stage = rt.risk.crop_stage(plot)
            for i, c in enumerate(counts):
                day = _today() - dt.timedelta(days=len(counts) - 1 - i)
                toid = "TO-" + uuid.uuid4().hex[:10].upper()
                db.execute(
                    "INSERT INTO trap_observations (id, trap_id, plot_id, counted_on, count,"
                    " count_source, nights, created_at) VALUES (:id,:t,:p,:on,:n,'manual',1,:now)",
                    {"id": toid, "t": trap["id"], "p": plot_id, "on": day.isoformat(),
                     "n": float(c), "now": now_iso()})
                d = rt.decisions.check_threshold(plot, pest, float(c), stage, trap_obs_id=toid)
                db.execute("UPDATE threshold_checks SET demo = 1, checked_on = :on WHERE id = :id",
                           {"on": day.isoformat(), "id": d["check_id"]})
            applied["pest"] = pest
            applied["counts"] = counts
            applied["note"] = ("These counts were written through the REAL threshold engine — the "
                               "band, the saving and the decision are what the engine produced, "
                               "not values typed into a fixture.")
    return {"scenario": out, "applied": applied, "demo": True}


@router.post("/reset", summary="Remove everything a scenario wrote")
def reset(plot_id: str = Query(...), user: dict[str, Any] = Depends(current_user),
          db: Database = Depends(db_dep)):
    owned_plot(db, user, plot_id)
    n = db.execute("DELETE FROM threshold_checks WHERE plot_id = :p AND demo = 1", {"p": plot_id})
    return {"removed_threshold_checks": n, "demo": True,
            "note": ("Scenario rows carry a `demo` column. Provenance lives in its own column and "
                     "is never smuggled into a value another query reads.")}
