"""
PRAHARI · the parts of the loop that close it
════════════════════════════════════════════════════════════════════════════
PREDICT → DETECT → VERIFY → ACT → MONITOR → LEARN.

v0.9 had PREDICT, DETECT and ACT. This module supplies the three that make it
a loop rather than a line:

  VERIFY   contextual questions that move a posterior when the image alone is
           not decisive — and the expert case a farmer can watch a status on
  MONITOR  the follow-up rescan, and a comparison that is qualitative because
           the underlying measurement is qualitative
  LEARN    already lives in store.bump_prior(); what is added here is the
           field timeline that makes the learning visible to the farmer whose
           field taught it

Nothing here invents an agronomic fact. The contextual questions re-weight
candidates that the diagnosis engine already ranked, using multipliers that are
declared in one table below and shown to the user.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

# ── VERIFY · contextual questions ───────────────────────────────────────────
# Each question exists because it separates two candidates that look alike in a
# photograph. The multiplier is a likelihood ratio, deliberately modest — a
# question is evidence, not a verdict. `for_pairs` records WHICH confusion the
# question is meant to resolve, so the UI can explain why it is being asked.
QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "onset",
        "q": "When did you first notice this?",
        "q_mr": "हे पहिल्यांदा कधी दिसले?",
        "options": [
            {"v": "today", "t": "Today or yesterday", "t_mr": "आज किंवा काल",
             "boost": {"late_blight": 1.6, "downy_mildew": 1.5}},
            {"v": "week", "t": "About a week ago", "t_mr": "साधारण आठवडाभरापूर्वी",
             "boost": {"early_blight": 1.4, "purple_blotch": 1.3, "turcicum_blight": 1.3}},
            {"v": "longer", "t": "Longer than that", "t_mr": "त्याहून जुने",
             "boost": {"nitrogen_deficiency": 1.7, "early_blight": 1.2}},
        ],
        "why": "Late blight moves in days. Early blight and nutrient problems take weeks.",
        "for_pairs": [["late_blight", "early_blight"]],
    },
    {
        "id": "spread",
        "q": "Has it spread in the last three days?",
        "q_mr": "गेल्या तीन दिवसांत पसरले आहे का?",
        "options": [
            {"v": "fast", "t": "Yes, quickly", "t_mr": "होय, वेगाने",
             "boost": {"late_blight": 1.8, "downy_mildew": 1.6}},
            {"v": "slow", "t": "A little", "t_mr": "थोडेसे",
             "boost": {"early_blight": 1.3, "powdery_mildew": 1.3}},
            {"v": "none", "t": "No", "t_mr": "नाही",
             "boost": {"nitrogen_deficiency": 1.8, "healthy": 1.4}},
        ],
        "why": "A problem that is not spreading is usually not infectious.",
        "for_pairs": [["late_blight", "nitrogen_deficiency"]],
    },
    {
        "id": "which_leaves",
        "q": "Which leaves are affected?",
        "q_mr": "कोणत्या पानांवर दिसते?",
        "options": [
            {"v": "lower", "t": "Older, lower leaves", "t_mr": "जुनी, खालची पाने",
             "boost": {"early_blight": 1.6, "nitrogen_deficiency": 1.6, "purple_blotch": 1.4}},
            {"v": "upper", "t": "New, upper leaves", "t_mr": "नवी, वरची पाने",
             "boost": {"late_blight": 1.5, "downy_mildew": 1.4, "powdery_mildew": 1.3}},
            {"v": "all", "t": "All over", "t_mr": "सगळीकडे",
             "boost": {"late_blight": 1.2}},
        ],
        "why": "Early blight and nitrogen deficiency both start at the bottom of the plant. "
               "Late blight does not.",
        "for_pairs": [["early_blight", "late_blight"]],
    },
    {
        "id": "rain",
        "q": "Was there rain or heavy dew in the last three days?",
        "q_mr": "गेल्या तीन दिवसांत पाऊस किंवा जास्त दव पडले का?",
        "options": [
            {"v": "yes", "t": "Yes", "t_mr": "होय",
             "boost": {"late_blight": 1.4, "downy_mildew": 1.5, "purple_blotch": 1.2}},
            {"v": "no", "t": "No", "t_mr": "नाही",
             "boost": {"powdery_mildew": 1.4, "nitrogen_deficiency": 1.2}},
        ],
        "why": "Powdery mildew is the one that prefers dry weather. Everything else here wants "
               "leaf wetness.",
        "for_pairs": [["powdery_mildew", "downy_mildew"]],
    },
    {
        "id": "sprayed",
        "q": "Have you sprayed anything in the last ten days?",
        "q_mr": "गेल्या दहा दिवसांत काही फवारले का?",
        "options": [
            {"v": "yes", "t": "Yes", "t_mr": "होय", "boost": {}},
            {"v": "no", "t": "No", "t_mr": "नाही", "boost": {}},
        ],
        "why": "This does not change the diagnosis. It changes what you may safely use next, "
               "because of the resistance rotation and the pre-harvest interval.",
        "for_pairs": [],
        "affects": "prescription",
    },
]

QUESTION_BY_ID = {q["id"]: q for q in QUESTIONS}


def pick_questions(ranked: list[dict], reason: str | None, limit: int = 3) -> list[dict]:
    """Ask only what could change the answer.

    A question that cannot separate the two leading candidates is a question
    that wastes a farmer's time, and the fastest way to lose a user is to make
    them tap through five of them.
    """
    if not ranked:
        return []
    top_ids = [r["id"] for r in ranked[:3]]
    scored = []
    for q in QUESTIONS:
        if q.get("affects") == "prescription":
            relevance = 0.4                       # always mildly useful, never the priority
        else:
            # A question is relevant if any option pushes the leaders apart.
            spreads = []
            for o in q["options"]:
                vals = [o["boost"].get(pid, 1.0) for pid in top_ids]
                spreads.append(max(vals) - min(vals))
            relevance = max(spreads) if spreads else 0.0
        if relevance > 0.05:
            scored.append((relevance, q))
    scored.sort(key=lambda x: -x[0])
    out = []
    for rel, q in scored[:limit]:
        out.append({k: v for k, v in q.items() if k != "for_pairs"} | {"relevance": round(rel, 2)})
    return out


def apply_answers(ranked: list[dict], answers: dict[str, str]) -> dict[str, Any]:
    """Re-weight the posterior with the farmer's answers. Returns the new
    ranking and — the part that matters — exactly which answer moved what."""
    moves = []
    weights = {r["id"]: 1.0 for r in ranked}
    for qid, val in (answers or {}).items():
        q = QUESTION_BY_ID.get(qid)
        if not q:
            continue
        opt = next((o for o in q["options"] if o["v"] == val), None)
        if not opt or not opt["boost"]:
            continue
        for pid, mult in opt["boost"].items():
            if pid in weights:
                weights[pid] *= mult
                moves.append({"question": q["q"], "answer": opt["t"], "candidate": pid,
                              "multiplier": mult})
    total = sum(r["posterior"] * weights[r["id"]] for r in ranked) or 1.0
    updated = []
    for r in ranked:
        # Same cap as diagnose.CONFIDENCE_CAP — re-weighting must not be a
        # back door to the certainty the diagnosis itself refuses to print.
        p = min(0.99, r["posterior"] * weights[r["id"]] / total)
        updated.append({**r, "posterior_before": r["posterior"], "posterior": round(p, 4)})
    updated.sort(key=lambda r: -r["posterior"])
    return {"ranked": updated, "moves": moves,
            "shifted": bool(moves) and updated[0]["id"] != ranked[0]["id"]}


# ── MONITOR · the follow-up comparison ──────────────────────────────────────
def compare_scans(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare two scans of the same plot.

    Deliberately QUALITATIVE. The feature extractor measures lesion count and
    symptomatic area on a hand-held photograph of a different leaf, in different
    light, at a different distance — reporting "severity fell 23%" from that
    would be a fabricated precision. Direction is defensible; magnitude is not.
    """
    def sev(f):
        return (f.get("necrosis", 0) + f.get("chlorosis", 0) + f.get("powder", 0)) \
            + min(1.0, f.get("lesions", 0) / 25) * 0.5

    b, a = sev(before), sev(after)
    lesion_delta = after.get("lesions", 0) - before.get("lesions", 0)
    rel = (a - b) / max(b, 0.02)

    if rel < -0.25 or lesion_delta <= -3:
        outcome, label, mr = "better", "Improving", "सुधारत आहे"
        say = ("Less symptomatic tissue and fewer lesions than the last scan. The action you took "
               "appears to be working — finish the course and scan once more in five days.")
    elif rel > 0.30 or lesion_delta >= 4:
        outcome, label, mr = "worse", "Worsening", "बिघडत आहे"
        say = ("More symptomatic tissue than the last scan. Either the diagnosis was wrong or the "
               "treatment is not reaching the pathogen. This case has been escalated to the block "
               "extension officer rather than offering you a second spray.")
    else:
        outcome, label, mr = "same", "Stable", "स्थिर"
        say = ("About the same as the last scan. Hold the current action and re-check in three days "
               "before changing anything.")

    return {
        "outcome": outcome, "label": label, "label_mr": mr,
        "lesions_before": before.get("lesions", 0), "lesions_after": after.get("lesions", 0),
        "lesion_delta": lesion_delta,
        "direction_only": True,
        "say": say,
        "method": ("Direction only, on purpose. These are two hand-held photographs of different "
                   "leaves in different light — the direction of change survives that, a percentage "
                   "does not. Anything more precise would be invented."),
        "escalate": outcome == "worse",
    }


# ── the field timeline ──────────────────────────────────────────────────────
SEVERITY_OF = {"risk": "watch", "scan": "info", "count": "watch", "advice": "info",
               "apply": "rising", "followup": "good", "expert": "info", "officer": "info"}


def log_event(con, plot_id: str, kind: str, title: str, detail: str = "",
              severity: str | None = None, ref: str | None = None,
              at: dt.date | None = None) -> None:
    con.execute("""INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref)
                   VALUES (?,?,?,?,?,?,?)""",
                (plot_id, (at or dt.date.today()).isoformat(), kind,
                 severity or SEVERITY_OF.get(kind, "info"), title, detail, ref))
    con.commit()


def notify(con, plot_id: str, kind: str, title: str, body: str = "",
           severity: str = "watch", at: dt.date | None = None,
           title_mr: str | None = None, body_mr: str | None = None) -> None:
    """A message to a farmer, stored in both languages.

    The Marathi is passed in by the caller — the same deterministic engine that
    produced the English — never generated at read time. A notification can
    carry a spray decision, and a translation layer that could paraphrase one is
    a translation layer that could change it."""
    con.execute("""INSERT INTO notifications (plot_id, at, kind, severity, title, body,
                   title_mr, body_mr) VALUES (?,?,?,?,?,?,?,?)""",
                (plot_id, (at or dt.date.today()).isoformat(), kind, severity, title, body,
                 title_mr, body_mr))
    con.commit()


def next_case_id(con) -> str:
    n = con.execute("SELECT COUNT(*) c FROM expert_cases").fetchone()["c"]
    return f"PRH-2026-{n + 1:04d}"
