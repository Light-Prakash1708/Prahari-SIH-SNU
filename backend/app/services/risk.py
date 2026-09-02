"""
PRAHARI · the risk service
════════════════════════════════════════════════════════════════════════════
PREDICT — the part that fires days before a symptom exists.

Inputs, all real:
    crop · variety · crop stage (from the active crop cycle)
    field coordinates
    observed weather + forecast (WeatherService — real provider, cached)
    trap counts recorded for this field
    threshold checks recorded for this field
    confirmed cases in this taluka (Getis-Ord Gi*)
    the field's own last intervention (resets the TOMCAST accumulator)

Outputs carry drivers, always. A risk score with no explanation is a number a
farmer cannot argue with, and one they will stop believing the first time it is
wrong.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from .. import forecast, health, reference, riskmodels, spatial
from ..clock import today as _today
from ..db import Database, dumps, loads
from ..weather import WeatherService, WeatherUnavailable


class RiskService:
    def __init__(self, db: Database, weather: WeatherService):
        self.db = db
        self.weather = weather

    # ── inputs ─────────────────────────────────────────────────────────────
    def weather_series(self, plot: dict[str, Any], back: int = 21,
                       forward: int = 6) -> dict[str, Any]:
        return self.weather.series(plot.get("lat"), plot.get("lng"), _today(),
                                   back=back, forward=forward)

    def crop_stage(self, plot: dict[str, Any]) -> dict[str, Any]:
        cycle = self.active_cycle(plot["id"])
        crop = (cycle or {}).get("crop") or plot["crop"]
        sown = (cycle or {}).get("sown_on") or plot.get("sown_on")
        return reference.crop_stage(crop, sown, _today())

    def active_cycle(self, plot_id: str) -> dict[str, Any] | None:
        return self.db.one(
            "SELECT * FROM crop_cycles WHERE plot_id = :p AND ended_on IS NULL"
            " ORDER BY sown_on DESC", {"p": plot_id})

    def spray_log(self, plot_id: str) -> list[dict[str, Any]]:
        return self.db.rows(
            "SELECT * FROM applications WHERE plot_id = :p AND kind='chemical'"
            " ORDER BY applied_on", {"p": plot_id})

    def _since_spray_index(self, days: list[dict], plot_id: str) -> int:
        log = self.spray_log(plot_id)
        if not log:
            return 0
        last = dt.date.fromisoformat(str(log[-1]["applied_on"])[:10])
        for i, d in enumerate(days):
            if dt.date.fromisoformat(d["date"]) >= last:
                return i
        return 0

    # ── the risk board ─────────────────────────────────────────────────────
    def board(self, plot: dict[str, Any], wx: dict[str, Any],
              stage: dict[str, Any]) -> tuple[list[dict], dict[str, bool]]:
        crop = plot["crop"]
        days = wx["days"]
        since_idx = self._since_spray_index(days, plot["id"])
        board: list[dict] = []
        fired: dict[str, bool] = {}

        for pid, p in reference.problems_for_crop(crop).items():
            model = p.get("model")
            base = {"kind": "disease", "id": pid, "name": p["name"], "name_mr": p["mr"],
                    "em": p["em"], "sci": p["sci"], "scout": p.get("scout"),
                    "scout_mr": p.get("mr_scout"), "speed": p.get("speed")}
            if not model:
                # A disease with no implementable published model is still on the
                # board — with NO risk level and the reason there is none. The
                # earlier version dropped it silently, which meant a cotton
                # grower opened a risk screen listing nothing at all and could
                # reasonably conclude their crop had no diseases.
                fired[pid] = False
                board.append({**base, "level": "unforecast", "fired": False,
                              "detail": p.get("no_model_note", ""),
                              "no_model_note": p.get("no_model_note", ""),
                              "provenance": {}})
                continue
            r = forecast._run(model, days, since_idx)
            if r is None:
                continue
            fired[pid] = r.fired
            prov = reference.MODEL_PROVENANCE.get(model, {})
            row = {**base, "provenance": prov, **r.dict()}
            if p.get("model_caveat"):
                # A model borrowed from a related pathogen says so, every time
                # it appears, not in a footnote somewhere else.
                row["model_caveat"] = p["model_caveat"]
            board.append(row)

        for pid, p in reference.pests_for_crop(crop).items():
            g = riskmodels.gdd_phenology(days, p["tbase"], p["dd_gen"], p["stages"])
            th = reference.threshold_for(pid, crop)
            board.append({"kind": "pest", "id": pid, "name": p["name"], "name_mr": p["mr"],
                          "em": p["em"], "sci": p["sci"], "scout": p["scout"],
                          "scout_mr": p["mr_scout"], "trap": p["trap"], "unit": p["unit"],
                          "etl": th["etl"] if th else None,
                          "etl_source": th["source"] if th else None,
                          "etl_status": (th or {}).get("status", "draft"),
                          "fired": g["damaging"], **g})

        order = {"high": 0, "rising": 1, "watch": 2, "low": 3}
        board.sort(key=lambda b: order.get(b.get("level", "low"), 9))
        return board, fired

    # ── the same board, when the weather it runs on is missing ─────────────
    WEATHER_UNAVAILABLE_NOTE = (
        "Weather for this field could not be retrieved, so the published infection model "
        "could not be run. PRAHARI does not know whether conditions are conducive. "
        "That is not the same as conditions being unfavourable.")
    WEATHER_UNAVAILABLE_NOTE_MR = (
        "या शेताचे हवामान मिळाले नाही, त्यामुळे संसर्ग मॉडेल चालवता आले नाही. परिस्थिती अनुकूल "
        "आहे की नाही हे प्रहरीला माहीत नाही — याचा अर्थ 'धोका नाही' असा नव्हे.")

    def board_without_weather(self, plot: dict[str, Any],
                              stage: dict[str, Any]) -> list[dict[str, Any]]:
        """Every problem this crop can have, with NO risk level attached.

        `level` and `fired` are None — never "low", never False. A missing input
        is not a reassuring input, and the screen must not be able to render the
        two the same way. Everything here comes from the reference tables, which
        need no weather: the problem list, the published thresholds and the
        scouting text are as true during an outage as outside one, and they are
        most of what the decision screen is for.
        """
        crop = plot["crop"]
        board: list[dict[str, Any]] = []

        for pid, p in reference.problems_for_crop(crop).items():
            board.append({
                "kind": "disease", "id": pid, "name": p["name"], "name_mr": p["mr"],
                "em": p["em"], "sci": p["sci"], "scout": p.get("scout"),
                "scout_mr": p.get("mr_scout"), "speed": p.get("speed"),
                "level": None, "fired": None, "risk_unavailable": True,
                "detail": self.WEATHER_UNAVAILABLE_NOTE,
                "detail_mr": self.WEATHER_UNAVAILABLE_NOTE_MR,
                "provenance": reference.MODEL_PROVENANCE.get(p.get("model", ""), {}),
            })

        for pid, p in reference.pests_for_crop(crop).items():
            th = reference.threshold_for(pid, crop)
            board.append({
                "kind": "pest", "id": pid, "name": p["name"], "name_mr": p["mr"],
                "em": p["em"], "sci": p["sci"], "scout": p["scout"],
                "scout_mr": p["mr_scout"], "trap": p["trap"], "unit": p["unit"],
                "etl": th["etl"] if th else None,
                "etl_source": th["source"] if th else None,
                "etl_status": (th or {}).get("status", "draft"),
                # The growing-degree-day model needs the same weather, so the
                # life stage is unknown too. `damaging: None` is what every
                # caller already treats as "we do not know".
                "level": None, "fired": None, "damaging": None, "stage": None,
                "risk_unavailable": True,
                "detail": self.WEATHER_UNAVAILABLE_NOTE,
                "detail_mr": self.WEATHER_UNAVAILABLE_NOTE_MR,
            })

        board.sort(key=lambda b: (b["kind"] != "pest", b["name"]))
        return board

    # ── trap state ─────────────────────────────────────────────────────────
    def trap_state(self, plot: dict[str, Any], days: list[dict],
                   stage: dict[str, Any]) -> list[dict]:
        out = []
        crop = plot["crop"]
        for pid, p in reference.pests_for_crop(crop).items():
            row = reference.threshold_for(pid, crop)
            if not row:
                continue
            g = riskmodels.gdd_phenology(days, p["tbase"], p["dd_gen"], p["stages"])
            last = self.db.one(
                "SELECT count, etl_effective, band, checked_on FROM threshold_checks"
                " WHERE plot_id = :p AND pest = :pest ORDER BY checked_at DESC, id DESC LIMIT 1",
                {"p": plot["id"], "pest": pid})
            eff = (last["etl_effective"] if last else
                   round(row["etl"] * (row.get("stage_factor") or {}).get(stage.get("stage") or "", 1.0), 2))
            trend = self.db.rows(
                "SELECT counted_on, count FROM trap_observations t JOIN traps tr ON tr.id = t.trap_id"
                " WHERE t.plot_id = :p AND tr.pest = :pest ORDER BY counted_on DESC, t.created_at DESC LIMIT 8",
                {"p": plot["id"], "pest": pid})
            out.append({
                "id": pid, "name": p["name"], "name_mr": p["mr"], "em": p["em"],
                "unit": row["unit"], "etl": eff, "etl_base": row["etl"],
                "etl_source": row.get("source"), "etl_status": row.get("status", "draft"),
                "count": last["count"] if last else None,
                "band": last["band"] if last else None,
                "last_checked": str(last["checked_on"]) if last else None,
                "damaging": g["damaging"], "stage": g["stage"], "trap": p["trap"],
                "trend": [{"on": str(t["counted_on"]), "count": t["count"]}
                          for t in reversed(trend)],
            })
        return out

    def damaging_stage(self, plot: dict[str, Any], pest: str) -> bool | None:
        """Whether the growing-degree-day model says this pest is currently at a
        life stage a spray could reach. None when weather is unavailable — and
        None must never be read as False, because "we do not know" and "no" lead
        to opposite advice.

        Every caller that asks "should I spray?" resolves this the same way, so
        the decision card and the IPM ladder cannot disagree with each other.
        """
        p = reference.PESTS.get(pest)
        if not p:
            return None
        try:
            wx = self.weather_series(plot)
        except WeatherUnavailable:
            return None
        return riskmodels.gdd_phenology(
            wx["days"], p["tbase"], p["dd_gen"], p["stages"])["damaging"]

    # ── nearby pressure ────────────────────────────────────────────────────
    def nearby_z(self, taluka: str, crop: str, problem: str = "late_blight",
                 days: int = 21) -> tuple[float | None, list[dict]]:
        since = (_today() - dt.timedelta(days=days)).isoformat()
        counts = {r["taluka"]: r["n"] for r in self.db.rows(
            "SELECT o.taluka AS taluka, COUNT(*) AS n FROM observations o"
            " JOIN diagnoses d ON d.observation_id = o.id"
            " WHERE substr(o.observed_at,1,10) >= :since AND o.status <> 'rejected'"
            " AND (d.top_problem = :prob OR d.confirmed = :prob)"
            " GROUP BY o.taluka", {"since": since, "prob": problem})}
        hs = spatial.getis_ord(reference.TALUKAS, counts)
        me = next((h for h in hs if h["taluka"] == taluka), None)
        return (me["z"] if me else None), hs

    # ── the whole picture, as the Today screen needs it ────────────────────
    def field_health(self, plot: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        wx = self.weather_series(plot)
        stage = self.crop_stage(plot)
        days = wx["days"]
        board, fired = self.board(plot, wx, stage)
        since_idx = self._since_spray_index(days, plot["id"])
        fc = forecast.by_day(days, reference.problems_for_crop(plot["crop"]),
                             horizon=4, since_idx=since_idx)
        traps = self.trap_state(plot, days, stage)
        z, _ = self.nearby_z(plot["taluka"], plot["crop"])
        h = health.compute(board, fc, traps, z)
        h["weather_source"] = wx.get("source")
        h["weather_kind"] = wx.get("source_kind")

        day = _today().isoformat()
        prev = self._previous_snapshot(plot["id"], day)
        if persist:
            self._save_snapshot(plot["id"], day, h, wx.get("source", "unknown"))
            self._save_forecast(plot["id"], day, fc, wx.get("source", "unknown"))
        days_since = None
        if prev:
            days_since = (_today() - dt.date.fromisoformat(prev["day"])).days
        changed = health.diff(h, prev, days_since)
        head = forecast.headline(fc, stage)
        return {"health": h, "forecast": fc, "headline": head, "changed": changed,
                "board": board, "traps": traps, "weather": wx, "crop_stage": stage,
                "nearby_z": z, "fired": fired}

    # ── snapshots ──────────────────────────────────────────────────────────
    def _previous_snapshot(self, plot_id: str, before_day: str) -> dict[str, Any] | None:
        r = self.db.one(
            "SELECT * FROM health_snapshots WHERE plot_id = :p AND day < :d"
            " ORDER BY day DESC LIMIT 1", {"p": plot_id, "d": before_day})
        if not r:
            return None
        drivers = loads(r["drivers"], {})
        return {"day": r["day"], "score": r["score"], "terms": drivers.get("terms", []),
                "components": drivers.get("components", {
                    "disease": {"penalty": r["disease"]}, "pest": {"penalty": r["pest"]},
                    "weather": {"penalty": r["weather"]}, "nearby": {"penalty": r["nearby"]}})}

    def _save_snapshot(self, plot_id: str, day: str, h: dict[str, Any], source: str) -> None:
        from ..clock import now_iso
        c = h["components"]
        self.db.execute(
            "INSERT INTO health_snapshots (plot_id, day, score, disease, pest, weather, nearby,"
            " drivers, weather_source, created_at)"
            " VALUES (:p,:d,:s,:dis,:pes,:wea,:nea,:dr,:src,:now)"
            " ON CONFLICT (plot_id, day) DO UPDATE SET score=excluded.score,"
            " disease=excluded.disease, pest=excluded.pest, weather=excluded.weather,"
            " nearby=excluded.nearby, drivers=excluded.drivers,"
            " weather_source=excluded.weather_source",
            {"p": plot_id, "d": day, "s": h["score"], "dis": c["disease"]["penalty"],
             "pes": c["pest"]["penalty"], "wea": c["weather"]["penalty"],
             "nea": c["nearby"]["penalty"],
             "dr": dumps({"terms": h["terms"], "components": c}),
             "src": source, "now": now_iso()})

    def _save_forecast(self, plot_id: str, made_on: str, fc: list[dict], source: str) -> None:
        from ..clock import now_iso
        self.db.execute("DELETE FROM risk_forecasts WHERE plot_id = :p AND made_on = :d",
                        {"p": plot_id, "d": made_on})
        stamp = now_iso()
        for f in fc:
            self.db.execute(
                "INSERT INTO risk_forecasts (plot_id, made_on, for_day, level, drivers,"
                " weather_source, created_at) VALUES (:p,:m,:f,:l,:dr,:s,:now)",
                {"p": plot_id, "m": made_on, "f": f["date"], "l": f["level"],
                 "dr": dumps(f.get("drivers")), "s": source, "now": stamp})

    def snapshot_history(self, plot_id: str, limit: int = 30) -> list[dict[str, Any]]:
        return self.db.rows(
            "SELECT day, score, disease, pest, weather, nearby, weather_source"
            " FROM health_snapshots WHERE plot_id = :p ORDER BY day DESC LIMIT :n",
            {"p": plot_id, "n": limit})

    def forecast_accuracy(self, plot_id: str) -> dict[str, Any]:
        """What yesterday's forecast said about today, next to what today's
        observed weather actually produced. Only computable once the app has run
        for more than a day — it says so rather than showing zeros."""
        rows = self.db.rows(
            "SELECT made_on, for_day, level FROM risk_forecasts WHERE plot_id = :p"
            " ORDER BY for_day DESC LIMIT 60", {"p": plot_id})
        by_day: dict[str, dict[str, str]] = {}
        for r in rows:
            by_day.setdefault(r["for_day"], {})[r["made_on"]] = r["level"]
        checked = agreed = 0
        for day, made in by_day.items():
            stamps = sorted(made)
            if len(stamps) < 2 or day not in made:
                continue
            checked += 1
            if made[stamps[0]] == made[day]:
                agreed += 1
        if checked == 0:
            return {"comparable_days": 0,
                    "note": ("Not enough history yet to compare a forecast against what the "
                             "observed weather later produced. This fills in as the field is used.")}
        return {"comparable_days": checked, "agreed": agreed,
                "agreement_rate": round(agreed / checked, 2),
                "note": ("Agreement between the level forecast for a day and the level the "
                         "observed weather produced on that day. It is a self-consistency check "
                         "on the weather feed, not a validated accuracy figure for the models.")}
