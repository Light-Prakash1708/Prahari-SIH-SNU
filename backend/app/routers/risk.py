"""PRAHARI · /api/risk and /api/fields — PREDICT, and What Changed / What Is Coming."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import reference
from ..clock import today as _today
from ..db import Database
from ..deps import current_user, db_dep, visible_plot
from ..runtime import get_runtime
from ..weather import WeatherUnavailable, forecast_view, status_of, to_http_error

log = logging.getLogger("prahari.risk")

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
        " AND done_observation IS NULL AND outcome IS NULL ORDER BY due_on", {"p": plot_id})
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


@router.get("/fields/{plot_id}/weather", summary="Current conditions and the short forecast",
            description=(
                "The WEATHER card, which is a different question from the RISK board and is "
                "answered separately.\n\n"
                "The infection models accumulate over three weeks, so the risk board needs "
                "three weeks of history and says so when it cannot get them. A farmer asking "
                "what the weather is doing needs today and the days ahead — about a week — "
                "and that window is one almost any plan can serve. Tying the two together is "
                "what made a history limit look like a broken forecast.\n\n"
                "Answers 200 while ANY tier can produce a series: live, then cache, then the "
                "generated fallback when a deployment has armed it. `status.code` says which "
                "— ok, demo, insufficient_history or provider_unavailable — and `generated` "
                "is true whenever the numbers were not observed."))
def weather(plot_id: str, days: int = Query(7, ge=1, le=14),
            user: dict[str, Any] = Depends(current_user),
            db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rt = get_runtime()
    try:
        # A SHORT window on purpose. Asking for the models' twenty-one days
        # here is what made the card fail on a plan that holds one: the card
        # never needed them.
        wx = rt.weather.series(plot.get("lat"), plot.get("lng"), _today(),
                               back=1, forward=max(1, days - 1))
    except WeatherUnavailable as exc:
        # Even now this is not an error the screen should wear. There is a real
        # reading behind an insufficient-history refusal; where there is not,
        # the card says so quietly and the rest of the dashboard is untouched.
        if exc.code == "insufficient_history" and exc.payload:
            return forecast_view(exc.payload, plot, days_ahead=days)
        log.warning("weather card unavailable",
                    extra={"plot_id": plot_id, "provider": exc.provider,
                           "reason": exc.reason, "code": exc.code})
        return forecast_view(None, plot, days_ahead=days)
    return forecast_view(wx, plot, days_ahead=days)


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
        # The taluka CENTROID and the Getis-Ord statistic, which is what the
        # hotspot map draws. Both were already computed here; only the centroid
        # and the rate were being dropped on the way out, which is why the map
        # needed no new endpoint and no new query.
        "nearby_talukas": [
            {"taluka": h["taluka"], "name": h.get("name"), "name_mr": h.get("name_mr"),
             "lat": h.get("lat"), "lng": h.get("lng"),
             "z": h["z"], "class": h["class"], "cases": h.get("cases"),
             "incidence_per_1000": h.get("incidence_per_1000")}
            for h in hotspots],
        "problem": problem,
        "problem_name": reference.problem_name(problem),
        "problem_name_mr": reference.problem_name(problem, "mr"),
        "window_days": days,
        "total_cases": sum(int(h.get("cases") or 0) for h in hotspots),
        "privacy": ("Counts are aggregated to taluka level and positioned on the taluka's own "
                    "centroid. PRAHARI never shows another farmer's field, name or "
                    "coordinates on this screen."),
        "privacy_mr": ("संख्या तालुका पातळीवर एकत्रित केली आहे. दुसऱ्या शेतकऱ्याचे शेत, नाव किंवा "
                       "ठिकाण प्रहरी कधीही दाखवत नाही."),
    }


def _weather_view(wx: dict[str, Any]) -> dict[str, Any]:
    """What the UI must display about weather provenance, every time."""
    return {
        # One flat object the UI can branch on without reading five fields and
        # deciding for itself what "stale plus fresh false" means.
        "status": status_of(wx),
        "source": wx.get("source"),
        # Which provider supplied which part of the window. The series can be
        # assembled from two of them — the primary for current conditions and
        # the forecast, the historical provider for the older days the
        # infection models accumulate over — so a number is always traceable
        # to whoever reported it. Every day row also carries its own `src`.
        "sources": wx.get("sources"),
        "history_days": wx.get("history_days"),
        "history_days_requested": wx.get("history_days_requested"),
        "kind": wx.get("source_kind"),
        "source_url": wx.get("source_url"),
        "generated": wx.get("source_kind") == "generated",
        "warning": wx.get("warning"),
        "note": wx.get("note"),
        "fetched_at": wx.get("fetched_at"),
        "freshness": wx.get("freshness"),
        "cached": wx.get("cached"),
        "stale": bool(wx.get("stale")),
        # `stale_reason` was the provider's own sentence and is not sent. The
        # reason a reading is stale is in the log; what the screen needs is in
        # `status` above.
        "observed_through": wx.get("observed_through"),
        "forecast_from": wx.get("forecast_from"),
        "profile": wx.get("profile"),
        "profile_label": wx.get("profile_label"),
        "days": wx.get("days"),
    }
