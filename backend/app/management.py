"""
PRAHARI · the management screen, composed.

One call behind "Should I spray?", because the screen needs seven things that
already exist in seven services and a phone on a village network should not
make seven round trips to assemble one answer.

This module owns **no agronomy**. Every number in the response is produced by
the service that already produces it for some other screen — the decision by
`services/decisions.py`, the ladder and the chemical screen by `prescribe.py`,
the prevention window and history by `cropcalendar.py`, the day's work by
`agenda.py`. `backend/app/cropcalendar.py` is the model this file copies: if a
threshold comparison ever appears below, it is in the wrong file.

One thing it will not do: disappear because weather is unavailable. Most of
this screen needs no weather at all — the count, the threshold it is measured
against, the published scouting text, the IPM ladder, the verified label
claims, the follow-up and the history are as true during an Open-Meteo outage
as outside one, and they are what a farmer standing in a field opened the
screen for. So a weather failure removes the parts that genuinely depend on
weather, names itself where those parts were, and leaves the rest standing.

What it must never do is let a missing forecast read as a calm one. `level` and
`fired` are None rather than "low" and False, and the disease decision has its
own branch for "the model could not be run" that is worded nothing like "the
weather is not conducive".

Two things it does decide, and both are about presentation rather than agronomy:

  · which targets are offerable at all. The old screen listed only pests with an
    economic threshold, so a farmer arriving from a DISEASE diagnosis found
    their problem missing from the chips and the API answering "record a count"
    about something nobody counts. Diseases are now first-class here.
  · the order of the sections, which is the order the questions get asked in a
    field: what is happening, how do you know, what do I do today, and only then
    what may be sprayed.
"""
from __future__ import annotations

import logging
from typing import Any

from . import agenda as agenda_mod
from . import cropcalendar, reference
from .clock import today as _today
from .db import Database
from .services.decisions import chemical_rung_open
from .weather import WeatherUnavailable, status_of

log = logging.getLogger("prahari.management")

_NOT_MANAGEABLE = {"healthy", "nitrogen_deficiency", "potassium_deficiency",
                   "magnesium_deficiency", "abiotic", "unknown"}


def _targets(board: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Everything on this field's risk board a farmer could ask about.

    Pests first and only when they have a threshold to be weighed against;
    then diseases, including those with no implementable model, which carry
    their own reason for having no forecast rather than being dropped.
    """
    out = []
    for b in board:
        if b["kind"] == "pest" and b.get("etl") is None:
            continue
        # `healthy` is a diagnosis outcome, not a problem, and a nutrient
        # disorder is not managed by the IPM ladder or by any threshold. Both
        # sit on the risk board legitimately; neither can be "acted on" here,
        # and offering them would be offering a decision that cannot be made.
        if b["id"] in _NOT_MANAGEABLE:
            continue
        out.append({"id": b["id"], "kind": b["kind"], "name": b["name"],
                    "name_mr": b.get("name_mr"), "em": b.get("em"),
                    "level": b.get("level"), "fired": b.get("fired")})
    return sorted(out, key=lambda t: (t["kind"] != "pest", t["name"]))


def incidence(row: dict[str, Any]) -> dict[str, Any]:
    """A disease assessment, with its arithmetic shown.

    `incidence_pct` is affected ÷ inspected, rounded to one place. It is a
    measurement, and the two numbers behind it travel with it so a farmer or an
    agronomist can redo the division.
    """
    inspected = max(int(row["plants_inspected"]), 1)
    affected = int(row["plants_affected"])
    return {
        **{k: row[k] for k in ("id", "problem", "plants_inspected", "plants_affected",
                               "spread_band", "part", "note")},
        "assessed_on": str(row["assessed_on"]),
        "incidence_pct": round(affected * 100.0 / inspected, 1),
        "arithmetic": f"{affected} ÷ {inspected} plants",
    }


def latest_assessment(db: Database, plot_id: str, problem: str) -> dict[str, Any] | None:
    row = db.one("SELECT * FROM disease_assessments WHERE plot_id = :p AND problem = :q"
                 " ORDER BY assessed_on DESC, created_at DESC LIMIT 1",
                 {"p": plot_id, "q": problem})
    return incidence(row) if row else None


def _trend(db: Database, plot: dict[str, Any], target: str, kind: str) -> dict[str, Any]:
    """Recent measurements, in order, with a direction — or a plain statement
    that there are not enough of them.

    Never interpolated and never smoothed. Two points are two points; the word
    "rising" is only used where the series actually rises.
    """
    if kind == "pest":
        rows = db.rows(
            "SELECT count AS value, checked_on AS on_day FROM threshold_checks"
            " WHERE plot_id = :p AND pest = :t ORDER BY checked_on DESC LIMIT 6",
            {"p": plot["id"], "t": target})
        unit = "per trap"
    else:
        rows = db.rows(
            "SELECT plants_affected, plants_inspected, assessed_on AS on_day"
            "  FROM disease_assessments WHERE plot_id = :p AND problem = :t"
            "  ORDER BY assessed_on DESC LIMIT 6", {"p": plot["id"], "t": target})
        for r in rows:
            r["value"] = round(r["plants_affected"] * 100.0
                               / max(r["plants_inspected"], 1), 1)
        unit = "% of plants"

    points = [{"value": r["value"], "on": str(r["on_day"])} for r in reversed(rows)]
    if len(points) < 2:
        return {"points": points, "unit": unit, "direction": None,
                "note": ("Not enough observations yet to say which way this is going. "
                         "Two measurements are the minimum."),
                "note_mr": "दिशा सांगण्यासाठी पुरेशा नोंदी नाहीत. किमान दोन नोंदी हव्यात."}
    first, last = points[0]["value"], points[-1]["value"]
    direction = "rising" if last > first else "falling" if last < first else "flat"
    say = {"rising": "Activity has increased across these observations.",
           "falling": "Activity has decreased across these observations.",
           "flat": "Activity has not changed across these observations."}[direction]
    say_mr = {"rising": "या नोंदींमध्ये प्रादुर्भाव वाढला आहे.",
              "falling": "या नोंदींमध्ये प्रादुर्भाव कमी झाला आहे.",
              "flat": "या नोंदींमध्ये फारसा बदल नाही."}[direction]
    return {"points": points, "unit": unit, "direction": direction,
            "note": say, "note_mr": say_mr}


def _field_evidence(db: Database, plot: dict[str, Any], target: str,
                    kind: str) -> dict[str, Any]:
    """What has actually been observed in this field about this problem.

    The diagnosis and the field measurement sit side by side here and are never
    merged. A model's confidence is a statement about the identification; a
    count or an incidence is a statement about the infestation. Reading one as
    the other is the single easiest way to turn a cautious system into a
    reckless one, so they are separate keys, separately labelled, and the
    screen prints them under separate headings.
    """
    dx = db.one(
        "SELECT id, top_problem, top_posterior, abstained, abstain_reason, explain,"
        "       observation_id, created_at FROM diagnoses"
        " WHERE plot_id = :p AND (top_problem = :t OR confirmed = :t)"
        " ORDER BY created_at DESC LIMIT 1", {"p": plot["id"], "t": target})
    image = None
    if dx and dx.get("observation_id"):
        img = db.one("SELECT id, storage_key, thumb_key, role, created_at"
                     "  FROM observation_images WHERE observation_id = :o"
                     "  ORDER BY created_at LIMIT 1", {"o": dx["observation_id"]})
        if img:
            image = {"id": img["id"], "role": img["role"],
                     "taken_at": str(img["created_at"])}

    out: dict[str, Any] = {"diagnosis": None, "image": image, "measurement": None}
    if dx:
        conf = dx["top_posterior"]
        out["diagnosis"] = {
            "id": dx["id"],
            "problem": dx["top_problem"],
            "problem_name": reference.problem_name(dx["top_problem"]),
            "abstained": bool(dx["abstained"]),
            "abstain_reason": dx["abstain_reason"],
            # A band, not a percentage on the decision screen. The exact
            # posterior stays available for the expert view; a farmer reading
            # "62%" next to a count of 4 will do arithmetic with them.
            "confidence_band": ("low" if conf is None or conf < 0.5
                                else "moderate" if conf < 0.7 else "high"),
            "confidence_value": conf,
            "means": ("How sure PRAHARI is about WHAT this is. It says nothing about how "
                      "much of it is in the field."),
            "means_mr": ("हे काय आहे याबद्दलची खात्री. शेतात किती आहे याबद्दल हे काहीही सांगत नाही."),
            "at": str(dx["created_at"]),
        }
    return out


def _weather_context(wx: dict[str, Any] | None,
                     err: WeatherUnavailable | None) -> dict[str, Any]:
    """What the screen may say about weather — including that it has none.

    Stated as context, never as a cause. Weather reaches the decision only
    through a published infection model for a disease; for a pest it is not an
    input at all, and this screen must not imply it is.
    """
    if wx is None:
        # The provider's own words stay in the log. `err.reason` says things
        # like "Open-Meteo rate limited the request", which is a sentence for
        # whoever runs the deployment, not for a farmer holding a phone.
        if err is not None:
            log.warning("weather unavailable on the management screen",
                        extra={"provider": err.provider, "reason": err.reason})
        return {
            **status_of(None),
            "source": None,
            "days": [],
            "note": ("Weather for this field could not be retrieved, so no infection model "
                     "was run and no risk level is shown. Nothing on this screen has been "
                     "estimated to fill the gap. Everything below that does not depend on "
                     "weather — your count, the published threshold it is measured against, "
                     "what to look for and what you can do — is unchanged."),
            "note_mr": ("या शेताचे हवामान मिळाले नाही, त्यामुळे कोणतेही संसर्ग मॉडेल चालवलेले नाही "
                        "आणि धोक्याची पातळी दाखवलेली नाही. काहीही अंदाजाने भरलेले नाही. "
                        "हवामानावर अवलंबून नसलेली माहिती — तुमची मोजणी, प्रकाशित मर्यादा, "
                        "काय पहावे आणि काय करता येईल — जशीच्या तशी आहे."),
        }
    return {
        **status_of(wx),
        "source": wx.get("source"),
        "generated": wx.get("generated", False),
        "warning": wx.get("warning"),
        # `stale` comes from status_of above and stays a real boolean —
        # re-setting it from the payload put None back, and the screen then had
        # to decide for itself what a null meant. `stale_reason` is dropped
        # entirely: it carried the provider's sentence.
        "freshness": wx.get("freshness"),
        "note": ("Field conditions, shown so you can plan when to walk the field. "
                 "For a disease, weather reaches the decision only through the "
                 "published infection model named in the evidence."),
        "note_mr": ("शेतातील परिस्थिती — कधी पाहणी करायची हे ठरवण्यासाठी. "
                    "रोगाच्या बाबतीत हवामान फक्त प्रकाशित मॉडेलमार्फतच निर्णयात येते."),
        "days": (wx.get("days") or [])[-1:],
    }


def build(db: Database, rt, plot: dict[str, Any], target: str | None,
          lang: str = "mr") -> dict[str, Any]:
    """Everything the management screen renders, in one call."""
    stage = rt.risk.crop_stage(plot)

    # The one call on this screen that can fail for an external reason. It is
    # caught HERE rather than at the router, because the router's only options
    # are the whole screen or none of it, and none of it is the wrong answer.
    wx: dict[str, Any] | None = None
    weather_error: WeatherUnavailable | None = None
    try:
        wx = rt.risk.weather_series(plot)
    except WeatherUnavailable as exc:
        weather_error = exc
    except Exception as exc:
        # A broad catch, deliberately, and only around this one call. Weather
        # is an external I/O boundary: a provider can return a shape nobody
        # anticipated, a JSON library can raise, a DNS lookup can fail in a way
        # httpx does not wrap. None of that is a reason to answer 500 and blank
        # a screen whose count, threshold, ladder and history are all sitting
        # right here. It is logged at exception level so it is not lost.
        log.exception("weather failed unexpectedly; the screen degrades instead",
                      extra={"plot_id": plot["id"]})
        weather_error = WeatherUnavailable("unknown", f"{type(exc).__name__}")

    if wx is not None:
        board, _fired = rt.risk.board(plot, wx, stage)
    else:
        board = rt.risk.board_without_weather(plot, stage)
    targets = _targets(board)

    if not targets:
        return {"plot_id": plot["id"], "targets": [], "target": None,
                "empty": ("PRAHARI has no problems on file for this crop yet. Scan the crop "
                          "to start, or record a trap count.")}

    chosen = target if any(t["id"] == target for t in targets) else targets[0]["id"]
    row = next(t for t in targets if t["id"] == chosen)
    kind = row["kind"]
    board_row = next((b for b in board if b["id"] == chosen), None)

    dxrow = db.one("SELECT * FROM diagnoses WHERE plot_id = :p"
                   " AND (top_problem = :t OR confirmed = :t)"
                   " ORDER BY created_at DESC LIMIT 1", {"p": plot["id"], "t": chosen})
    dx = ({"abstained": bool(dxrow["abstained"]), "abstain_reason": dxrow["abstain_reason"],
           "explain": dxrow["explain"], "id": dxrow["id"]} if dxrow else None)

    threshold = assessment = None
    if kind == "pest":
        check = db.one(
            "SELECT * FROM threshold_checks WHERE plot_id = :p AND pest = :t"
            " ORDER BY checked_at DESC, id DESC LIMIT 1", {"p": plot["id"], "t": chosen})
        if check:
            from . import etl
            tr = reference.threshold_for(chosen, plot["crop"])
            threshold = etl.decide(tr, check["count"], check["crop_stage"],
                                   reference.CROPS[plot["crop"]], plot["area_acre"]) if tr else None
            if threshold:
                threshold["check_id"] = check["id"]
                threshold["counted_on"] = str(check["checked_on"])
                threshold["etl_provenance"] = {"source": (tr or {}).get("source"),
                                               "status": (tr or {}).get("status", "draft")}
        # A pest decision is weather-independent by design: only a count
        # against a published threshold authorises anything. `damaging_stage`
        # already answers None when it cannot know, and None is never read as
        # False, so this path is unchanged during an outage.
        decision = rt.decisions.spray_decision(
            plot, chosen, threshold=threshold, diagnosis=dx,
            damaging_stage=rt.risk.damaging_stage(plot, chosen))
        decision["target_kind"] = "pest"
    else:
        assessment = latest_assessment(db, plot["id"], chosen)
        decision = rt.decisions.disease_decision(
            plot, chosen, assessment=assessment, board_row=board_row, diagnosis=dx,
            weather_available=wx is not None)

    # The monitoring rung. Its content is the problem's OWN published scouting
    # text plus what a farmer must physically do to produce the measurement this
    # decision is waiting for — a count for a pest, an inspection for a disease.
    prob = reference.problem(chosen) or {}
    # Bilingual, from the problem's own published scouting text. `mr_scout` is
    # already in the knowledge base; an earlier version printed the English one
    # into a Marathi interface, which is the one paragraph a farmer most needs
    # to be able to read.
    scout_items = [x for x in [
        ({"text": prob.get("scout"), "text_mr": prob.get("mr_scout")}
         if prob.get("scout") else None),
        ({"text": "Count the trap and record it — the decision cannot move without a number.",
          "text_mr": "सापळा मोजा आणि नोंदवा — आकड्याशिवाय निर्णय पुढे जात नाही."}
         if kind == "pest" else
         {"text": "Inspect a set number of plants and record how many show it.",
          "text_mr": "ठराविक झाडे तपासा आणि किती झाडांवर लक्षणे आहेत ते नोंदवा."}),
        {"text": "Photograph it again if it has visibly spread since the last look.",
         "text_mr": "मागच्या वेळेपेक्षा पसरले असेल तर पुन्हा फोटो काढा."},
    ] if x]
    prescription = rt.decisions.prescription(
        plot, chosen, stage, chemical_authorised=chemical_rung_open(decision),
        scout={"items": scout_items, "recheck_on": decision.get("recheck_on")})

    # The prevention window, the day's work and the history all come from the
    # services that already build them for the crop journey and the home screen.
    # The prevention window is built by the crop journey from exactly these
    # inputs; it is called here rather than reimplemented so the two screens can
    # never disagree about whether a window is open.
    # The prevention window is the one section that is weather ALL THE WAY
    # DOWN — it exists to say "the models say act before you can see anything",
    # which is a sentence only a model run on real weather may produce. With no
    # weather there is no window, and it is null rather than an empty-looking
    # calm one.
    prevention = None
    if wx is not None:
        from . import forecast as fc_mod
        traps = rt.risk.trap_state(plot, wx["days"], stage)
        since = rt.risk._since_spray_index(wx["days"], plot["id"])
        series = fc_mod.by_day(wx["days"], reference.problems_for_crop(plot["crop"]),
                               horizon=4, since_idx=since)
        head = fc_mod.headline(series, stage)
        nearby = None
        try:
            z, _hot = rt.risk.nearby_z(plot["taluka"], plot["crop"])
            assess = rt.outbreak.assess(plot["taluka"], "late_blight", crop=plot["crop"],
                                        days=21, gi_z=z)
            if assess:
                nearby = {"level": assess.get("level"), "summary": assess.get("summary")}
        except Exception:
            nearby = None
        prevention = cropcalendar._prevention_window(series, head, traps, stage, nearby)

    mission = agenda_mod.agenda(db, rt, plot)
    followup = db.one(
        "SELECT id, due_on, application_id FROM followups WHERE plot_id = :p"
        "   AND done_observation IS NULL AND outcome IS NULL"
        " ORDER BY due_on LIMIT 1", {"p": plot["id"]})

    return {
        "plot_id": plot["id"],
        "plot_name": plot["name"],
        "crop": plot["crop"],
        "crop_stage": stage,
        "targets": targets,
        "target": chosen,
        "target_kind": kind,
        "target_name": row["name"],
        "target_name_mr": row.get("name_mr"),
        "decision": decision,
        "threshold": threshold,
        "assessment": assessment,
        "evidence": _field_evidence(db, plot, chosen, kind),
        "trend": _trend(db, plot, chosen, kind),
        "prevention_window": prevention,
        "mission": mission,
        "followup": ({"id": followup["id"], "due_on": str(followup["due_on"]),
                      "application_id": followup["application_id"]} if followup else None),
        "history": cropcalendar._history(db, rt, plot, limit=8),
        "weather_available": wx is not None,
        "weather_context": _weather_context(wx, weather_error),
        **prescription,
        "day": _today().isoformat(),
    }
