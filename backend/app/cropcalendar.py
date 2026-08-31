"""
PRAHARI · the crop journey — stage, threat windows, prevention window, history
════════════════════════════════════════════════════════════════════════════
This module COMPOSES. It owns no agronomy of its own.

Every number it returns is produced by a service that already existed and is
already tested: `risk.crop_stage`, `risk.board`, `risk.trap_state`,
`forecast.by_day`, `agenda`, `risk.snapshot_history`. Nothing here re-derives a
risk level, re-runs an infection model, or invents a date. If a value cannot be
obtained from those services it is returned as null with a reason, never as a
plausible-looking default.

THE ONE HONESTY PROBLEM THIS MODULE HAD TO SOLVE
------------------------------------------------
A "threat window" timeline wants to say: at flowering, worry about X; at
fruiting, worry about Y. For PESTS that is answerable from data we hold — every
threshold row in thresholds.json carries a `stage_factor` per crop stage, with
an ICAR source attached. A factor below 1.0 lowers the economic threshold at
that stage, which is precisely a statement that the crop is more vulnerable
then. So pest vulnerability per stage is read straight off a sourced table.

For DISEASES there is no such table, and there is no honest way to invent one.
A disease fires when the weather satisfies a published infection model — Hutton,
Smith, and the rest. Whether late blight will threaten the fruiting stage six
weeks from now is a question about weather that does not exist yet. So this
module does NOT paint disease bands across future stages. It reports disease
pressure only for the window the weather record actually covers, and says in
`disease_note` why the later stages are blank.

That asymmetry is the finding, not a gap to be filled with colour.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from . import forecast as fc_mod
from . import reference
from .agenda import agenda

# A stage_factor is a multiplier on the economic threshold: 0.7 means act at
# 70% of the usual count, which is a statement that the crop is more vulnerable
# at that stage.
#
# The first version of this banded the factor against fixed cutoffs — under 0.8
# was "high", and so on. That reads plausibly and is useless in practice: the
# tomato tables put whitefly at 0.5–0.6 through the seedling and vegetative
# stages and Tuta at 0.7 through fruiting, so almost every stage came back red
# and the timeline said nothing. A screen where everything is urgent is a screen
# nobody reads.
#
# The factors are only meaningful RELATIVE TO THE SAME PEST. 0.7 is Tuta's worst
# stage; 0.7 for whitefly is close to its average. So each pest is banded
# against its own range across this crop's stages, which is the question a
# farmer is actually asking — "is this the part of the season when this
# particular pest bites hardest?" The absolute factor and the adjusted
# threshold are still returned alongside, so the arithmetic stays checkable.
_REL_BANDS = ((0.15, "high"), (0.50, "watch"), (0.85, "normal"))


def _band_relative(factor: float, lo: float, hi: float) -> str:
    """Band one stage_factor against the pest's own min and max for this crop."""
    if hi <= lo:
        # A pest whose threshold does not vary by stage has no peak season to
        # report. Saying "normal" everywhere is the honest answer.
        return "normal"
    rel = (factor - lo) / (hi - lo)
    for ceiling, band in _REL_BANDS:
        if rel <= ceiling:
            return band
    return "tolerant"


def _stage_dates(stages: list, sown: dt.date | None) -> list[dict[str, Any]]:
    """Turn the crop's day-bands into real dates for THIS sowing.

    The bands live in crops.json as (key, first_day, last_day, label). With a
    sowing date they become calendar dates; without one they stay as day
    numbers and `from`/`to` are null, because a timeline with invented dates on
    it is worse than a timeline with none.
    """
    out = []
    for key, lo, hi, label in stages:
        row = {
            "stage": key,
            "label": label,
            "label_mr": reference.STAGE_MR.get(key, label),
            "day_from": lo,
            "day_to": hi,
            "from": None,
            "to": None,
        }
        if sown:
            row["from"] = (sown + dt.timedelta(days=lo)).isoformat()
            row["to"] = (sown + dt.timedelta(days=hi)).isoformat()
        out.append(row)
    return out


def _threat_windows(crop: str, timeline: list[dict[str, Any]],
                    board: list[dict[str, Any]],
                    current_stage: str | None) -> list[dict[str, Any]]:
    """Per crop stage: which pests the published thresholds treat as more
    dangerous there, and — for the stages the weather record reaches — which
    diseases are actually firing.

    Pest rows come from thresholds.json `stage_factor`, each carrying its own
    ICAR source. Disease rows are only ever attached to the CURRENT stage,
    because that is the only stage the infection models have weather for.
    """
    fired_now = [b for b in board
                 if b["kind"] == "disease" and b.get("level") in ("high", "rising")]

    stage_keys = [st["stage"] for st in timeline]

    # Each pest is banded against its OWN range over this crop's stages, so
    # the range is computed once here rather than per stage.
    ranges: dict[str, tuple[float, float]] = {}
    for pid in reference.pests_for_crop(crop):
        row = reference.threshold_for(pid, crop)
        vals = [float(v) for k, v in ((row or {}).get("stage_factor") or {}).items()
                if k in stage_keys]
        if vals:
            ranges[pid] = (min(vals), max(vals))

    windows = []
    for st in timeline:
        pests = []
        for pid, p in reference.pests_for_crop(crop).items():
            row = reference.threshold_for(pid, crop)
            if not row:
                continue
            factors = row.get("stage_factor") or {}
            # A pest whose threshold table has no entry for this stage is not
            # assigned a made-up one; it simply does not appear here.
            if st["stage"] not in factors:
                continue
            factor = float(factors[st["stage"]])
            lo, hi = ranges.get(pid, (factor, factor))
            pests.append({
                "id": pid,
                "name": p["name"],
                "name_mr": p["mr"],
                "em": p["em"],
                "band": _band_relative(factor, lo, hi),
                "stage_factor": factor,
                "peak_factor": lo,          # this pest's worst stage on this crop
                "etl": row["etl"],
                "etl_at_this_stage": round(row["etl"] * factor, 2),
                "unit": row["unit"],
                "source": row.get("source"),
                "status": row.get("status", "draft"),
            })
        pests.sort(key=lambda x: x["stage_factor"])

        # The stage's own band counts how many pests are at THEIR peak here,
        # rather than taking the worst single pest. Taking the worst put four
        # of tomato's five stages at "high" — true of some pest in every case,
        # and therefore no help in deciding which weeks matter most.
        highs = sum(1 for p in pests if p["band"] == "high")
        watches = sum(1 for p in pests if p["band"] == "watch")
        band = ("high" if highs >= 2
                else "watch" if highs == 1 or watches >= 2
                else "normal")

        windows.append({
            "stage": st["stage"],
            "label": st["label"],
            "label_mr": st["label_mr"],
            "from": st["from"],
            "to": st["to"],
            "band": band,
            "pests": pests,
            # Diseases are attached by the caller only to the current stage.
            "diseases": [],
        })

    current = next((w for w in windows if w["stage"] == current_stage), None)
    if current is not None:
        current["diseases"] = [
            {"id": b["id"], "name": b["name"], "name_mr": b["name_mr"],
             "em": b["em"], "level": b["level"],
             "model": (b.get("provenance") or {}).get("model") or b.get("model"),
             "source": (b.get("provenance") or {}).get("source")}
            for b in fired_now
        ]
        if current["diseases"]:
            current["band"] = "high"
    return windows



def _prevention_window(series: list[dict[str, Any]], head: dict[str, Any],
                       traps: list[dict[str, Any]], stage: dict[str, Any],
                       nearby: dict[str, Any] | None) -> dict[str, Any]:
    """The "act before the symptom" card.

    Its factors are assembled only from evidence that exists. A factor is
    omitted entirely rather than reported as "no data" — a farmer reading five
    bullet points, three of which say nothing is known, learns less than one
    reading the two that do.
    """
    factors: list[dict[str, Any]] = []

    # 1 — the infection models, on this field's own weather
    drivers = []
    for day in series:
        for d in day.get("drivers") or []:
            if d.get("name") and d["name"] not in drivers:
                drivers.append(d["name"])
    if head.get("level") in ("high", "rising") and drivers:
        factors.append({
            "kind": "weather",
            "em": "🌧",
            "text": f"Infection models firing on this field's weather: {', '.join(drivers[:3])}",
            "text_mr": f"या शेताच्या हवामानावर संसर्ग मॉडेल सक्रिय: {', '.join(drivers[:3])}",
        })
    for reason in (head.get("reasons") or [])[:2]:
        factors.append({"kind": "weather", "em": "💧", "text": reason, "text_mr": None})

    # 2 — crop stage, only when the stage itself lowers a threshold
    tight = [t for t in traps if t.get("etl") and t.get("etl_base")
             and t["etl"] < t["etl_base"]]
    if tight and stage.get("label"):
        names = ", ".join(t["name"] for t in tight[:2])
        factors.append({
            "kind": "stage",
            "em": "🌱",
            "text": (f"At {stage['label'].lower()}, the economic threshold for {names} is lower "
                     f"than usual — the crop is more vulnerable now"),
            "text_mr": None,
        })

    # 3 — trap activity actually recorded
    for t in traps:
        if t.get("count") is not None and t.get("etl") and t["count"] >= t["etl"] * 0.6:
            factors.append({
                "kind": "trap",
                "em": "🪤",
                "text": (f"{t['name']} trap at {t['count']} {t['unit']} against a threshold of "
                         f"{t['etl']} — last counted {t.get('last_checked') or 'unknown'}"),
                "text_mr": None,
            })

    # 4 — regional corroboration, when the surveillance layer has any
    if nearby and nearby.get("level") and nearby["level"] != "none":
        factors.append({
            "kind": "regional",
            "em": "📍",
            "text": nearby.get("summary") or f"Nearby pressure: {nearby['level']}",
            "text_mr": None,
        })

    level = head.get("level", "low")
    open_days = len(series)
    return {
        "open": level in ("high", "rising", "watch"),
        "level": level,
        "days": open_days,
        "title": head.get("title"),
        "title_mr": head.get("title_mr"),
        "factors": factors,
        "method": ("The window is the forecast horizon of the published infection models — the "
                   "days on which acting is still prevention rather than treatment. Factors are "
                   "listed only where a record exists; none are inferred."),
        "method_mr": ("ही मुदत प्रकाशित संसर्ग मॉडेलच्या अंदाज कालावधीएवढी आहे — ज्या दिवसांत "
                      "केलेली कृती अजून प्रतिबंध ठरते, उपचार नाही. जिथे नोंद आहे तेच घटक "
                      "दाखवले आहेत; काहीही गृहीत धरलेले नाही."),
    }


def _history(db, rt, plot: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    """Field health history, drawn from records that already exist.

    Deliberately reads five existing tables rather than writing a sixth. Nothing
    is created here, so nothing can drift out of step with the record it came
    from.
    """
    pid = plot["id"]
    out: list[dict[str, Any]] = []

    for snap in rt.risk.snapshot_history(pid, limit):
        score = snap.get("score")
        out.append({
            "on": str(snap.get("day") or snap.get("created_at"))[:10],
            "kind": "health",
            "em": "📊",
            "title": f"Health score {int(round(float(score)))}" if score is not None
                     else "Health score recorded",
            "detail": None,
            "score": score,
        })

    for o in db.rows(
            "SELECT o.id, o.created_at, d.top_problem, d.top_posterior, d.abstained,"
            " d.abstain_reason FROM observations o"
            " LEFT JOIN diagnoses d ON d.observation_id = o.id"
            " WHERE o.plot_id = :p ORDER BY o.created_at DESC LIMIT :n",
            {"p": pid, "n": limit}):
        # An abstention is a real, reportable outcome — "the model declined to
        # name this" is information a farmer acted on, so it stays in the
        # history rather than being smoothed into a blank scan.
        if o.get("abstained"):
            title, detail = "Scan — not confidently identified", o.get("abstain_reason")
        elif o.get("top_problem"):
            title = reference.problem_name(o["top_problem"])
            detail = (f"confidence {round(float(o['top_posterior']) * 100)}%"
                      if o.get("top_posterior") is not None else None)
        else:
            title, detail = "Scan recorded", None
        out.append({
            "on": str(o["created_at"])[:10],
            "kind": "diagnosis",
            "em": "📸",
            "title": title,
            "detail": detail,
            "ref": {"observation_id": o["id"]},
        })

    for t in db.rows(
            "SELECT t.counted_on, t.count, tr.pest FROM trap_observations t"
            " JOIN traps tr ON tr.id = t.trap_id WHERE tr.plot_id = :p"
            " ORDER BY t.counted_on DESC LIMIT :n", {"p": pid, "n": limit}):
        out.append({
            "on": str(t["counted_on"])[:10],
            "kind": "trap",
            "em": "🪤",
            "title": f"{reference.problem_name(t['pest'])} count: {t['count']}",
            "detail": None,
        })

    for a in db.rows(
            "SELECT applied_on, product, kind, target FROM applications"
            " WHERE plot_id = :p ORDER BY applied_on DESC LIMIT :n", {"p": pid, "n": limit}):
        out.append({
            "on": str(a["applied_on"])[:10],
            "kind": "application",
            "em": "🧪",
            "title": f"{a['kind'].title()}: {a['product']}",
            "detail": (f"against {reference.problem_name(a['target'])}"
                       if a.get("target") else None),
        })

    for f in db.rows(
            "SELECT due_on, done_observation, outcome FROM followups"
            " WHERE plot_id = :p ORDER BY due_on DESC LIMIT :n", {"p": pid, "n": limit}):
        out.append({
            "on": str(f["due_on"])[:10],
            "kind": "followup",
            "em": "🔁",
            "title": ("Follow-up: " + str(f["outcome"])) if f.get("outcome")
                     else ("Follow-up done" if f.get("done_observation") else "Follow-up due"),
            "detail": None,
        })

    out.sort(key=lambda r: r["on"], reverse=True)
    return out[:limit * 2]


def build(db, rt, plot: dict[str, Any], *, lang: str = "en") -> dict[str, Any]:
    """Assemble the crop journey for one field.

    Raises WeatherUnavailable — the router converts it to 503 exactly as every
    other risk endpoint does. A calendar with no weather is not a degraded
    calendar; the prevention window is the point of the screen and it cannot be
    computed without it.
    """
    cycle = rt.risk.active_cycle(plot["id"])
    crop = (cycle or {}).get("crop") or plot["crop"]
    sown_on = (cycle or {}).get("sown_on") or plot.get("sown_on")
    c = reference.CROPS.get(crop) or {}

    sown = None
    if sown_on:
        try:
            sown = dt.date.fromisoformat(str(sown_on)[:10])
        except ValueError:
            sown = None

    stage = rt.risk.crop_stage(plot)
    timeline = _stage_dates(c.get("stages") or [], sown)

    # mark the current stage and work out what comes next
    next_stage = None
    for i, st in enumerate(timeline):
        st["current"] = (st["stage"] == stage.get("stage"))
        if st["current"] and i + 1 < len(timeline):
            nxt = timeline[i + 1]
            next_stage = {
                "stage": nxt["stage"], "label": nxt["label"], "label_mr": nxt["label_mr"],
                "from": nxt["from"],
                "in_days": (max(0, nxt["day_from"] - stage["days"])
                            if stage.get("days") is not None else None),
            }

    wx = rt.risk.weather_series(plot)
    board, _fired = rt.risk.board(plot, wx, stage)
    traps = rt.risk.trap_state(plot, wx["days"], stage)

    since = rt.risk._since_spray_index(wx["days"], plot["id"])
    series = fc_mod.by_day(wx["days"], reference.problems_for_crop(crop),
                           horizon=4, since_idx=since)
    head = fc_mod.headline(series, stage)

    nearby = None
    try:
        z, _hot = rt.risk.nearby_z(plot["taluka"], crop)
        assess = rt.outbreak.assess(plot["taluka"], "late_blight", crop=crop, days=21, gi_z=z)
        if assess:
            nearby = {"level": assess.get("level"), "summary": assess.get("summary")}
    except Exception:
        # Surveillance is a corroborating signal, never a blocker. A field with
        # no neighbours reporting still gets its own calendar.
        nearby = None

    windows = _threat_windows(crop, timeline, board, stage.get("stage"))

    watchlist = [
        {"id": b["id"], "kind": b["kind"], "name": b["name"], "name_mr": b["name_mr"],
         "em": b["em"], "level": b.get("level"), "fired": b.get("fired"),
         "scout": b.get("scout"), "scout_mr": b.get("scout_mr")}
        for b in board
        if b.get("level") in ("high", "rising", "watch") or b.get("fired")
    ][:6]

    return {
        "plot_id": plot["id"],
        "field": {
            "id": plot["id"], "name": plot["name"], "area_acre": plot.get("area_acre"),
            "taluka": plot.get("taluka"), "village": plot.get("village"),
        },
        "crop": {
            "id": crop, "name": c.get("name") or crop, "name_mr": c.get("mr"),
            "em": c.get("em"), "variety": (cycle or {}).get("variety") or plot.get("variety"),
            "sown_on": str(sown_on)[:10] if sown_on else None,
        },
        "cycle_id": (cycle or {}).get("id"),
        "crop_stage": stage,
        "next_stage": next_stage,
        "timeline": timeline,
        "threat_windows": windows,
        "disease_note": (
            "Disease bands are shown only for the current stage. A disease fires when weather "
            "satisfies a published infection model, so whether one will threaten a stage six "
            "weeks away is a question about weather that does not exist yet. PRAHARI leaves "
            "those stages blank rather than colouring them in."),
        "disease_note_mr": (
            "रोगाची पातळी फक्त सध्याच्या अवस्थेसाठी दाखवली जाते. हवामान प्रकाशित संसर्ग "
            "मॉडेलच्या अटी पूर्ण करते तेव्हाच रोग सुरू होतो, त्यामुळे सहा आठवड्यांनंतरच्या "
            "अवस्थेचा धोका हा अजून अस्तित्वात नसलेल्या हवामानाचा प्रश्न आहे. प्रहरी त्या "
            "अवस्था रंगवण्याऐवजी रिकाम्या ठेवते."),
        "prevention_window": _prevention_window(series, head, traps, stage, nearby),
        "weather_context": {
            "source": wx.get("source"), "generated": wx.get("generated", False),
            "warning": wx.get("warning"), "observed_through": wx.get("observed_through"),
            "forecast_from": wx.get("forecast_from"),
            "freshness": wx.get("freshness"),
            "days": series,
        },
        "watchlist": watchlist,
        "traps": traps,
        "mission": agenda(db, rt, plot),
        "history": _history(db, rt, plot),
        "method": (
            "Composed from services that already produce these numbers: crop stage from the "
            "sowing date and the crop's own stage table, disease levels from published infection "
            "models run on this field's weather, pest vulnerability per stage from the ICAR "
            "threshold tables' stage factors, and history from the field's own records. "
            "Nothing on this screen is generated prose."),
        "method_mr": (
            "हे आकडे आधीच तयार होणाऱ्या सेवांमधून एकत्र केले आहेत: पेरणीच्या तारखेवरून व "
            "पिकाच्या अवस्था तक्त्यावरून पीक अवस्था, तुमच्या शेतावरील हवामानावर चालवलेल्या "
            "प्रकाशित संसर्ग मॉडेलमधून रोगाची पातळी, ICAR उंबरठा तक्त्यांतील अवस्था-घटकांवरून "
            "प्रत्येक अवस्थेतील किडीचा धोका, आणि शेताच्या स्वतःच्या नोंदींवरून इतिहास. "
            "या पडद्यावरील काहीही मजकूर आपोआप लिहिलेले नाही."),
    }
