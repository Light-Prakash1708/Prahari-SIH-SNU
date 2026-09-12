"""
PRAHARI · where a field is heading, and when to stop guessing
════════════════════════════════════════════════════════════════════════════
Four derivations, and not one of them is a new engine.

Everything here reads rows the existing engines already wrote — health
snapshots, diagnoses, follow-up outcomes, the ordered agenda, case counts by
taluka — and does the one thing those engines deliberately do not do: name the
conclusion a farmer or an officer was left to infer.

    trajectory()        is this field getting better or worse, and why
    escalation()        does this need a human, how badly, and why
    next_best_action()  of everything due, the ONE thing to do first
    early_signals()     what changed in a district since the week before

The discipline is the same in all four, and it is the reason this file is
small: a derivation may only state what the rows support. Two snapshots make a
direction; one makes none, and a flat arrow drawn for a field seen once is an
invented reading. Every function therefore has an honest empty answer, and
returns it rather than reaching for a default that looks like information.

No language model is anywhere near this file. No number here is new — each one
is carried through from the row that produced it, so a farmer who asks "how do
you know" can be shown the record.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from .clock import today as _today
from .db import Database

# ── how much movement counts as movement ───────────────────────────────────
# The health score is 0-100 with four capped penalty terms, so day-to-day
# wobble of a point or two is the weather term breathing, not the field
# changing. Six points is roughly the smallest move that survives a change of
# one penalty term, which is why it is the threshold for naming a direction.
MATERIAL_MOVE = 6.0

STATES = ("improving", "stable", "watch", "worsening", "unknown")


def trajectory(db: Database, plot_id: str,
               history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """IMPROVING · STABLE · WATCH · WORSENING — or UNKNOWN, said plainly.

    Built from three streams that already exist: the crop-health score series,
    the follow-up outcomes a farmer reported, and whether a diagnosis landed
    since the last snapshot. A field with one snapshot and no follow-up has no
    trajectory, and this says so instead of calling it stable — "stable" is a
    claim, and it is the most dangerous one to make about a field nobody has
    looked at twice.
    """
    rows = history if history is not None else db.rows(
        "SELECT day, score FROM health_snapshots WHERE plot_id = :p"
        " ORDER BY day DESC LIMIT 30", {"p": plot_id})
    # Callers hand this in oldest-first (the health endpoint reverses it for
    # charting); normalise to newest-first rather than trusting the order.
    series = sorted([r for r in rows if r.get("score") is not None],
                    key=lambda r: str(r["day"]), reverse=True)

    outcomes = db.rows(
        "SELECT outcome, done_on FROM followups WHERE plot_id = :p AND outcome IS NOT NULL"
        " ORDER BY done_on DESC LIMIT 5", {"p": plot_id})
    latest_outcome = outcomes[0]["outcome"] if outcomes else None

    reasons: list[dict[str, str]] = []

    def because(en: str, mr: str, kind: str = "record") -> None:
        reasons.append({"kind": kind, "text": en, "text_mr": mr})

    # ── the score series ───────────────────────────────────────────────────
    delta: float | None = None
    if len(series) >= 2:
        newest, oldest = series[0], series[-1]
        delta = round(float(newest["score"]) - float(oldest["score"]), 1)
        span = f"{oldest['day']} → {newest['day']}"
        if delta >= MATERIAL_MOVE:
            because(f"The crop-health score has risen {abs(delta):g} points ({span}). "
                    f"A higher score means fewer penalties.",
                    f"पीक-आरोग्य गुण {abs(delta):g} ने वाढले ({span}).", "score")
        elif delta <= -MATERIAL_MOVE:
            because(f"The crop-health score has fallen {abs(delta):g} points ({span}).",
                    f"पीक-आरोग्य गुण {abs(delta):g} ने घटले ({span}).", "score")
        else:
            because(f"The crop-health score has moved less than {MATERIAL_MOVE:g} points "
                    f"({span}), which is not a change this score can distinguish from noise.",
                    "पीक-आरोग्य गुणात लक्षणीय बदल नाही.", "score")

    # ── what the farmer reported after acting ──────────────────────────────
    if latest_outcome == "worse":
        because("Your own follow-up recorded the field as WORSE after the last action.",
                "शेवटच्या कृतीनंतर तुमच्या पुनर्तपासणीत स्थिती बिघडल्याची नोंद आहे.", "followup")
    elif latest_outcome == "better":
        because("Your own follow-up recorded the field as BETTER after the last action.",
                "शेवटच्या कृतीनंतर तुमच्या पुनर्तपासणीत सुधारणा नोंदली आहे.", "followup")
    elif latest_outcome == "same":
        because("Your own follow-up recorded no change after the last action.",
                "शेवटच्या कृतीनंतर बदल नाही अशी नोंद आहे.", "followup")

    # ── a diagnosis since the last snapshot ────────────────────────────────
    fresh = db.one(
        "SELECT top_problem, created_at FROM diagnoses WHERE plot_id = :p"
        " AND abstained = 0 AND top_problem IS NOT NULL"
        " ORDER BY created_at DESC LIMIT 1", {"p": plot_id})
    recent_dx = False
    if fresh:
        age = _age_days(fresh["created_at"])
        if age is not None and age <= 7:
            recent_dx = True
            from . import reference
            because(f"A scan in the last {age} day{'s' if age != 1 else ''} identified "
                    f"{reference.problem_name(fresh['top_problem'])}.",
                    "अलीकडच्या तपासणीत समस्या आढळली.", "diagnosis")

    # ── the call ───────────────────────────────────────────────────────────
    if len(series) < 2 and latest_outcome is None:
        return {"state": "unknown", "reasons": reasons, "delta": None,
                "snapshots": len(series),
                "note": ("Not enough field history yet. Two crop-health readings, or one "
                         "follow-up you have answered, are needed before PRAHARI will say "
                         "which way this field is going."),
                "note_mr": ("शेताचा पुरेसा इतिहास नाही. दिशा सांगण्यासाठी दोन नोंदी किंवा "
                            "एक पुनर्तपासणी आवश्यक आहे.")}

    if latest_outcome == "worse" or (delta is not None and delta <= -MATERIAL_MOVE):
        state = "worsening"
    elif latest_outcome == "better" and (delta is None or delta > -MATERIAL_MOVE) or delta is not None and delta >= MATERIAL_MOVE:
        state = "improving"
    elif recent_dx:
        # Flat, but something was found and nothing has been reported since.
        state = "watch"
    else:
        state = "stable"

    return {"state": state, "reasons": reasons, "delta": delta,
            "snapshots": len(series), "note": None, "note_mr": None}


def escalation(*, decision: dict[str, Any] | None, diagnosis: dict[str, Any] | None,
               traj: dict[str, Any] | None, chemical_available: bool | None,
               open_followups: int = 0) -> dict[str, Any]:
    """LOW · MEDIUM · HIGH need for a human, and the reasons that hold.

    Deliberately not a probability. Every input here is categorical — a band, an
    abstention, a reported outcome — and averaging categories into a number
    would manufacture a precision none of them has. So the level is the highest
    band any single reason reaches, which is also the rule a person would use.

    The same verdict is shown to the farmer and attached to the expert's case
    brief, from this one function, so the two can never disagree about why a
    case was sent.
    """
    reasons: list[dict[str, str]] = []

    def add(level: str, en: str, mr: str) -> None:
        reasons.append({"level": level, "text": en, "text_mr": mr})

    if decision and (decision.get("decision") == "expert_review"
                     or decision.get("reason_code") == "low_confidence"):
        add("high", "PRAHARI is not confident enough to recommend a management action.",
            "शिफारस करण्याइतकी प्रहरीला खात्री नाही.")
    if diagnosis:
        if diagnosis.get("abstained"):
            add("high", "The camera declined to name what this is.",
                "हे काय आहे हे कॅमेऱ्याने सांगितलेले नाही.")
        elif diagnosis.get("confidence_band") == "low":
            add("medium", "The scan is only low-confidence about what this is.",
                "हे काय आहे याबद्दल स्कॅनची खात्री कमी आहे.")
    if traj and traj.get("state") == "worsening":
        add("high", "This field's own records show it getting worse.",
            "या शेताच्या नोंदी स्थिती बिघडत असल्याचे दाखवतात.")
    elif traj and traj.get("state") == "watch":
        add("medium", "Something was found and no follow-up has been recorded since.",
            "समस्या आढळली आहे आणि त्यानंतर पुनर्तपासणी नोंदलेली नाही.")
    if chemical_available is False:
        add("medium", "PRAHARI holds no verified chemical option for this crop and target, "
                      "so a chemical decision needs a person.",
            "या पिकासाठी तपासलेला रासायनिक पर्याय प्रहरीकडे नाही.")
    if open_followups >= 2:
        add("medium", f"{open_followups} follow-ups on this field are still unanswered.",
            f"या शेताच्या {open_followups} पुनर्तपासण्या अजून बाकी आहेत.")

    level = "high" if any(r["level"] == "high" for r in reasons) else \
            "medium" if reasons else "low"
    return {
        "level": level,
        "reasons": reasons,
        "note": ("Nothing here needs an expert right now. You can still ask if the field "
                 "looks worse than this screen says."
                 if level == "low" else None),
        "note_mr": ("सध्या तज्ज्ञांची गरज नाही. शेत यापेक्षा वाईट दिसत असेल तर विचारू शकता."
                    if level == "low" else None),
        "basis": ("The highest band any single reason reaches. These are categorical "
                  "findings, not a score — PRAHARI does not average them into a number it "
                  "cannot defend."),
    }


def next_best_action(agenda_out: dict[str, Any] | None) -> dict[str, Any] | None:
    """The ONE thing to do first, out of everything already due.

    agenda() assembles the day's work in order of consequence — pre-harvest
    intervals, overdue follow-ups, threshold crossings, infection models,
    community signals, then routine scouting. So the first item already IS the
    answer; what was missing was anything that said so. A farmer holding a phone
    at the edge of a field reads one instruction, not six.

    Returns None when the agenda is empty, which the caller renders as "nothing
    needs doing" rather than as a blank card.
    """
    items = (agenda_out or {}).get("items") or []
    if not items:
        return None
    first = items[0]
    return {
        "key": first.get("key"),
        "tone": first.get("tone"),
        "icon": first.get("icon"),
        "title": first.get("title"),
        "title_mr": first.get("title_mr"),
        "detail": first.get("detail"),
        "detail_mr": first.get("detail_mr"),
        "action": first.get("action"),
        "evidence": first.get("evidence") or [],
        "also_due": max(0, len(items) - 1),
        "basis": ("The highest-consequence item on today's agenda, which is already ordered "
                  "by consequence. Nothing was re-ranked to produce this."),
    }


def early_signals(db: Database, talukas: list[str], *, days: int = 7,
                  min_cases: int = 3) -> dict[str, Any]:
    """What changed in this district since the week before — and nothing more.

    A change is only reportable when there is something to compare against, so
    this counts open cases per (taluka, problem) in the recent window and again
    in the window immediately before it. A pair that clears `min_cases` and has
    grown is a signal; everything else is silence, which is reported as
    insufficient data rather than dressed up as "normal".

    Deliberately NOT epidemiology. It states a count, a place, a date and what
    to go and look at. The grading of clusters is outbreak.py's job and is not
    duplicated here.
    """
    if not talukas:
        return {"signals": [], "window_days": days,
                "note": "No talukas are assigned to your account yet."}

    day = _today()
    recent_from = (day - dt.timedelta(days=days)).isoformat()
    base_from = (day - dt.timedelta(days=days * 2)).isoformat()
    ph = ", ".join(f":t{i}" for i in range(len(talukas)))
    params: dict[str, Any] = {f"t{i}": t for i, t in enumerate(talukas)}

    def counts(since: str, until: str | None) -> dict[tuple[str, str], int]:
        clause = " AND substr(o.observed_at,1,10) >= :since"
        if until:
            clause += " AND substr(o.observed_at,1,10) < :until"
        rows = db.rows(
            f"SELECT o.taluka, d.top_problem, COUNT(*) AS n"
            f" FROM observations o JOIN diagnoses d ON d.observation_id = o.id"
            f" WHERE o.taluka IN ({ph}) AND d.abstained = 0 AND d.top_problem IS NOT NULL"
            f"{clause} GROUP BY o.taluka, d.top_problem",
            {**params, "since": since, **({"until": until} if until else {})})
        return {(r["taluka"], r["top_problem"]): int(r["n"]) for r in rows}

    now = counts(recent_from, None)
    before = counts(base_from, recent_from)

    from . import reference
    signals = []
    for (taluka, problem), n in sorted(now.items(), key=lambda kv: -kv[1]):
        was = before.get((taluka, problem), 0)
        if n < min_cases or n <= was:
            continue
        first = db.one(
            "SELECT MIN(substr(o.observed_at,1,10)) AS d FROM observations o"
            " JOIN diagnoses d ON d.observation_id = o.id"
            " WHERE o.taluka = :tk AND d.top_problem = :pb"
            " AND substr(o.observed_at,1,10) >= :since",
            {"tk": taluka, "pb": problem, "since": recent_from})
        # Confidence is about the SIZE of the comparison, not about the
        # pathology: a jump from 0 to 3 is a weaker reading than 4 to 9, and
        # saying so is the whole point of showing a confidence at all.
        confidence = "high" if (n >= 6 and was >= 2) else "moderate" if n >= 4 else "low"
        signals.append({
            "taluka": taluka,
            "taluka_name": reference.taluka_name(taluka),
            "problem": problem,
            "problem_name": reference.problem_name(problem),
            "cases_now": n,
            "cases_before": was,
            "what_changed": (f"{n} diagnosed case{'s' if n != 1 else ''} in the last {days} "
                             f"days, against {was} in the {days} days before."),
            "since": (first or {}).get("d"),
            "confidence": confidence,
            "confidence_basis": (f"Based on {n} recent and {was} prior cases. A signal built on "
                                 f"few reports is a weak signal and is labelled as one."),
            "check": (f"Visit the highest-priority {reference.problem_name(problem)} cases in "
                      f"{reference.taluka_name(taluka)} and confirm the diagnosis in the field."),
        })

    if not signals:
        return {"signals": [], "window_days": days,
                "note": ("Insufficient data for a reliable signal. A signal needs at least "
                         f"{min_cases} diagnosed cases of one problem in one taluka within "
                         f"{days} days, and more than the {days} days before it."),
                "note_mr": "विश्वासार्ह संकेतासाठी पुरेशी माहिती नाही."}
    return {"signals": signals, "window_days": days, "note": None,
            "basis": (f"Diagnosed, non-abstained cases per taluka and problem in the last "
                      f"{days} days, compared with the {days} days before. Cluster GRADING is "
                      f"outbreak.py's separate and stricter test.")}


def _age_days(stamp: Any) -> int | None:
    try:
        return (_today() - dt.date.fromisoformat(str(stamp)[:10])).days
    except Exception:
        return None
