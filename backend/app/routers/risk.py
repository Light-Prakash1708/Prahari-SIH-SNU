"""PRAHARI · /api/risk and /api/fields — PREDICT, and What Changed / What Is Coming."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import reference
from ..db import Database
from ..deps import current_user, db_dep, visible_plot
from ..runtime import get_runtime
from ..weather import WeatherUnavailable, to_http_error

router = APIRouter(prefix="/api", tags=["risk"])


@router.get("/risk/{plot_id}", summary="The risk board for a field",
            description=("Every entry is computed from weather alone, which is why it can warn "
                          "before a symptom exists. Each disease carries the published infection "
                          "model that produced it and a citation for that model.\n\n"
                          "Errors: 503 weather_unavailable — PRAHARI returns an error rather than "
                          "generated weather."))
def risk_board(plot_id: str, user: dict[str, Any] = Depends(current_user),
               db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rt = get_runtime()
    try:
        wx = rt.risk.weather_series(plot)
    except WeatherUnavailable as exc:
        raise to_http_error(exc) from exc
    stage = rt.risk.crop_stage(plot)
    board, fired = rt.risk.board(plot, wx, stage)
    return {
        "plot_id": plot_id, "crop": plot["crop"], "crop_stage": stage,
        "weather": _weather_view(wx),
        "board": board, "fired": fired,
        "lead_time_note": ("Nothing above needs a photograph. That is what makes it early warning "
                           "rather than detection."),
        "model_provenance": reference.MODEL_PROVENANCE,
    }


@router.get("/risk/{plot_id}/forecast", summary="What is coming — four days",
            description="Each day is scored by running the same published infection models on the "
                        "weather record ending that day: observed weather for today, forecast "
                        "weather beyond.")
def forecast(plot_id: str, horizon: int = Query(4, ge=1, le=7),
             user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rt = get_runtime()
    from .. import forecast as fc_mod
    try:
        wx = rt.risk.weather_series(plot)
    except WeatherUnavailable as exc:
        raise to_http_error(exc) from exc
    stage = rt.risk.crop_stage(plot)
    since = rt.risk._since_spray_index(wx["days"], plot_id)
    series = fc_mod.by_day(wx["days"], reference.problems_for_crop(plot["crop"]),
                           horizon=horizon, since_idx=since)
    return {"forecast": series, "headline": fc_mod.headline(series, stage),
            "crop_stage": stage, "weather": _weather_view(wx),
            "self_consistency": rt.risk.forecast_accuracy(plot_id)}


@router.get("/fields/{plot_id}/health", summary="Crop-health score and What Changed",
            description=("score = 100 − disease − pest − weather − nearby, capped 40/30/16/14, "
                          "with every term naming what cost the points.\n\n"
                          "This is a composite crop-health RISK indicator. It is NOT an estimated "
                          "yield percentage and the response says so."))
def health(plot_id: str, user: dict[str, Any] = Depends(current_user),
           db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rt = get_runtime()
    try:
        out = rt.risk.field_health(plot, persist=(user["role"] == "farmer"))
    except WeatherUnavailable as exc:
        raise to_http_error(exc) from exc
    out["weather"] = _weather_view(out["weather"])
    out["score_meaning"] = (
        "A composite crop-health RISK indicator on a 0–100 scale, not an estimate of yield, "
        "not a percentage of the crop, and not a probability of disease. It is the sum of four "
        "penalties, each shown with its own arithmetic.")
    out["history"] = list(reversed(rt.risk.snapshot_history(plot_id, 30)))
    open_followups = db.rows(
        "SELECT id, due_on, application_id FROM followups WHERE plot_id = :p"
        " AND done_observation IS NULL ORDER BY due_on", {"p": plot_id})
    out["followups_due"] = open_followups
    return out


@router.get("/fields/{plot_id}/today", summary="What should I do today?",
            description=("The home screen's action list, assembled server-side from records in "
                          "order of consequence — pre-harvest intervals, overdue follow-ups, "
                          "threshold crossings, infection models firing, corroborated community "
                          "signals, then routine scouting.\n\nEvery item names the row it came "
                          "from in `evidence`. When nothing needs doing the list says so; it does "
                          "not invent busywork."))
def today(plot_id: str, user: dict[str, Any] = Depends(current_user),
          db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    from ..agenda import agenda
    return agenda(db, get_runtime(), plot)


@router.get("/fields/{plot_id}/nearby", summary="Nearby pressure, aggregated",
            description=("Aggregated to taluka resolution. Individual farmers are never "
                          "identified, and no coordinates finer than the taluka centroid are "
                          "returned on this endpoint."))
def nearby(plot_id: str, problem: str = Query("late_blight"),
           days: int = Query(21, ge=3, le=90),
           user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rt = get_runtime()
    z, hotspots = rt.risk.nearby_z(plot["taluka"], plot["crop"], problem, days)
    assessment = rt.outbreak.assess(plot["taluka"], problem, crop=plot["crop"],
                                    days=days, gi_z=z)
    return {
        "taluka": plot["taluka"], "taluka_name": reference.taluka_name(plot["taluka"]),
        "gi_z": z, "assessment": assessment,
        "nearby_talukas": [
            {"taluka": h["taluka"], "name": h.get("name"), "z": h["z"], "class": h["class"],
             "cases": h.get("cases")}
            for h in hotspots],
        "privacy": ("Counts are aggregated to taluka level. PRAHARI never shows another farmer's "
                    "field, name or coordinates on this screen."),
    }


def _weather_view(wx: dict[str, Any]) -> dict[str, Any]:
    """What the UI must display about weather provenance, every time."""
    return {
        "source": wx.get("source"),
        "kind": wx.get("source_kind"),
        "source_url": wx.get("source_url"),
        "generated": wx.get("source_kind") == "generated",
        "warning": wx.get("warning"),
        "note": wx.get("note"),
        "fetched_at": wx.get("fetched_at"),
        "freshness": wx.get("freshness"),
        "cached": wx.get("cached"),
        "stale": wx.get("stale"),
        "stale_reason": wx.get("stale_reason"),
        "observed_through": wx.get("observed_through"),
        "forecast_from": wx.get("forecast_from"),
        "profile": wx.get("profile"),
        "profile_label": wx.get("profile_label"),
        "days": wx.get("days"),
    }
