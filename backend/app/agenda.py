"""
PRAHARI · "What should I do today?"
════════════════════════════════════════════════════════════════════════════
The home screen used to be five cards, each answering a different question,
and a farmer had to synthesise them. This module does the synthesis on the
server, where the evidence is, and returns a LIST OF INSTRUCTIONS in priority
order.

Every item carries the row it came from. Nothing here is generated prose: an
item exists because a follow-up is overdue, a pre-harvest interval is still
running, a threshold was crossed, an infection model fired, or a community
signal was corroborated. If none of those is true the list says so, in one
line, rather than inventing busywork — an app that always has five urgent
tasks is an app that gets ignored on the day it matters.

Order is by consequence, not by recency:

    1  a pre-harvest interval still running        (food safety)
    2  a follow-up that is overdue                 (did the treatment work?)
    3  a threshold crossed and not acted on        (the field is losing money)
    4  an infection model firing in the next days  (act BEFORE the symptom)
    5  a corroborated community signal nearby      (others are seeing it)
    6  routine: scan, count, look
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from . import reference
from .clock import today as _today
from .db import Database

TONE_URGENT, TONE_ACT, TONE_CALM = "urgent", "act", "calm"


def agenda(db: Database, rt, plot: dict[str, Any], *, health: dict[str, Any] | None = None,
           lang: str = "mr") -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    day = _today()
    pid = plot["id"]

    # 1 ── a pre-harvest interval still running ─────────────────────────────
    for app in db.rows(
            "SELECT * FROM applications WHERE plot_id = :p AND clears_on >= :day"
            " ORDER BY clears_on DESC", {"p": pid, "day": day.isoformat()}):
        days = (dt.date.fromisoformat(app["clears_on"]) - day).days
        items.append(_item(
            "phi", TONE_URGENT, "🚫",
            f"Do not harvest for {days} more day{'s' if days != 1 else ''}",
            f"आणखी {days} दिवस काढणी करू नका",
            f"{app['product']} was applied on {app['applied_on']}. Its pre-harvest interval "
            f"({app['phi_days']} days) runs to {app['clears_on']}. Harvesting before that leaves "
            f"residue above the permitted limit.",
            f"{app['applied_on']} रोजी {app['product']} फवारले. काढणी {app['clears_on']} नंतरच.",
            {"do": "history"},
            [{"kind": "application", "detail": f"{app['product']} · PHI {app['phi_days']} d"}]))

    # 2 ── follow-ups ───────────────────────────────────────────────────────
    for fu in db.rows(
            "SELECT * FROM followups WHERE plot_id = :p"
            " AND done_observation IS NULL AND outcome IS NULL"
            " ORDER BY due_on", {"p": pid}):
        late = (day - dt.date.fromisoformat(fu["due_on"])).days
        if late < 0:
            continue
        items.append(_item(
            "followup", TONE_URGENT if late >= 1 else TONE_ACT, "🔁",
            ("Re-scan the treated area — " + (f"{late} day{'s' if late != 1 else ''} overdue"
                                              if late else "due today")),
            "उपचार केलेला भाग पुन्हा स्कॅन करा",
            "PRAHARI will compare this photograph with the first one and tell you the direction "
            "— better, same or worse. If it is worse, it goes to an officer, not to a second "
            "spray.",
            "प्रहरी हा फोटो पहिल्या फोटोशी तुलना करेल आणि दिशा सांगेल.",
            {"do": "rescan", "followup_id": fu["id"]},
            [{"kind": "followup", "detail": f"due {fu['due_on']}"}]))

    # 3 ── a threshold crossed and nothing recorded since ───────────────────
    for tc in db.rows(
            "SELECT * FROM threshold_checks WHERE plot_id = :p AND chemical_authorised = 1"
            " AND acted = 0 AND checked_on >= :since ORDER BY checked_at DESC LIMIT 3",
            {"p": pid, "since": (day - dt.timedelta(days=10)).isoformat()}):
        name = reference.problem_name(tc["pest"])
        items.append(_item(
            "threshold", TONE_ACT, "⚖️",
            f"{name} is over the economic threshold",
            f"{reference.problem_name(tc['pest'], 'mr')} आर्थिक मर्यादेच्या वर आहे",
            f"Your count of {tc['count']:g} is above the threshold of {tc['etl_effective']:g} for "
            f"{tc['crop_stage'] or 'this stage'}. That is the gate a chemical has to pass — open "
            f"the ladder and start at the top rung, not the bottom.",
            f"तुमची मोजणी {tc['count']:g}, मर्यादा {tc['etl_effective']:g}.",
            {"do": "decide", "target": tc["pest"]},
            [{"kind": "threshold_check", "detail": f"{tc['count']:g} vs ETL {tc['etl_effective']:g}"}]))

    # 4 ── the weather models, which fire before a symptom exists ───────────
    fired: dict[str, bool] = {}
    try:
        stage = rt.risk.crop_stage(plot)
        wx = rt.risk.weather_series(plot)
        _board, fired = rt.risk.board(plot, wx, stage)
    except Exception:
        fired = {}
    for problem, hit in (fired or {}).items():
        if not hit:
            continue
        p = reference.problem(problem) or {}
        items.append(_item(
            "model", TONE_ACT, p.get("em", "🍂"),
            f"Scout for {reference.problem_name(problem)} this week",
            f"या आठवड्यात {reference.problem_name(problem, 'mr')} साठी तपासणी करा",
            (p.get("scout") or "Walk the field and look closely at the lower leaves.")
            + " The infection model fired on this field's own weather — that happens days before "
              "anything is visible, which is the only useful time to look.",
            p.get("mr_scout") or "शेतात फिरून खालच्या पानांची बारकाईने पाहणी करा.",
            {"do": "scan"},
            [{"kind": "model",
              "detail": (reference.MODEL_PROVENANCE.get(p.get("model", ""), {}) or {})
              .get("name", "infection model")}]))

    # 5 ── what the neighbours are reporting, as an aggregate ───────────────
    try:
        for s in rt.signals.open_signals([plot["taluka"]]):
            if s.get("crop") and s["crop"] != plot["crop"]:
                continue
            if (s.get("rank") or 0) < 2:
                continue
            items.append(_item(
                "community", TONE_ACT, "👥",
                f"{s['distinct_authors']} farmers near you report {s['problem_name']}",
                f"जवळच्या {s['distinct_authors']} शेतकऱ्यांनी {s['problem_name_mr']} नोंदवले आहे",
                f"{s['label']} in {s['taluka_name']} — {s['means']} PRAHARI does not tell you "
                f"whose fields these are. Scout your own this week; the spray decision is still "
                f"about your field and still needs a count.",
                f"{s['label_mr']} — {s['taluka_name']}. या आठवड्यात स्वतःचे शेत तपासा.",
                {"do": "community"},
                [{"kind": "community_signal", "detail": s["label"]}]))
    except Exception:
        pass

    # 6 ── routine ──────────────────────────────────────────────────────────
    last_scan = db.scalar(
        "SELECT MAX(observed_at) FROM observations WHERE plot_id = :p AND kind = 'leaf'",
        {"p": pid})
    scan_age = _age(last_scan, day)
    if scan_age is None or scan_age >= 7:
        items.append(_item(
            "scan", TONE_CALM, "📷",
            "Scan the crop" if scan_age is None else f"Scan the crop — {scan_age} days since the last one",
            "पीक स्कॅन करा",
            "One clear photograph of an affected leaf, filling the frame. PRAHARI refuses a "
            "photograph it cannot judge rather than guessing from it.",
            "एका बाधित पानाचा स्पष्ट फोटो घ्या.",
            {"do": "scan"},
            [{"kind": "field_record",
              "detail": f"last leaf scan {last_scan or 'never'}"}]))

    for trap in db.rows("SELECT * FROM traps WHERE plot_id = :p AND active = 1", {"p": pid}):
        last = db.one(
            "SELECT counted_on FROM trap_observations WHERE trap_id = :t"
            " ORDER BY counted_on DESC, created_at DESC LIMIT 1", {"t": trap["id"]})
        age = _age((last or {}).get("counted_on"), day)
        if age is None or age >= 4:
            items.append(_item(
                "trap", TONE_CALM, "🪤",
                f"Count the {reference.problem_name(trap['pest'])} trap",
                f"{reference.problem_name(trap['pest'], 'mr')} सापळा मोजा",
                "A count is the only thing that can authorise a chemical. A diagnosis cannot — "
                "knowing what it is does not tell you whether there is enough of it to spray.",
                "मोजणी हीच फवारणीला परवानगी देऊ शकते.",
                {"do": "traps"},
                [{"kind": "trap", "detail": f"last counted {(last or {}).get('counted_on', 'never')}"}]))

    order = {TONE_URGENT: 0, TONE_ACT: 1, TONE_CALM: 2}
    items.sort(key=lambda i: order[i["tone"]])

    return {
        "plot_id": pid, "day": day.isoformat(), "items": items[:6],
        "count": len(items),
        "all_clear": not any(i["tone"] in (TONE_URGENT, TONE_ACT) for i in items),
        "all_clear_note": (
            "Nothing needs a decision today. That is a finding, not an empty screen — PRAHARI "
            "checked the weather models, your counts, your follow-ups and what farmers near you "
            "are reporting, and none of them asked for anything."),
        "all_clear_note_mr": (
            "आज कोणताही निर्णय घेण्याची गरज नाही. प्रहरीने हवामान मॉडेल, तुमच्या मोजण्या, "
            "पुनर्तपासणी आणि जवळपासच्या नोंदी तपासल्या — कशातूनही कृती आवश्यक नाही."),
        "method": ("Assembled from records, in order of consequence: pre-harvest intervals, "
                   "overdue follow-ups, threshold crossings, infection models firing on this "
                   "field's weather, corroborated community signals, then routine scouting. "
                   "Every item names the row it came from."),
    }


def _item(key: str, tone: str, icon: str, title: str, title_mr: str, detail: str,
          detail_mr: str, action: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {"key": key, "tone": tone, "icon": icon, "title": title, "title_mr": title_mr,
            "detail": detail, "detail_mr": detail_mr, "action": action, "evidence": evidence}


def _age(stamp: Any, day: dt.date) -> int | None:
    if not stamp:
        return None
    try:
        return (day - dt.date.fromisoformat(str(stamp)[:10])).days
    except ValueError:
        return None
