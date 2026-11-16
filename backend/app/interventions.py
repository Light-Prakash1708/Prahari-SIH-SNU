"""
PRAHARI · what happened after each kind of action
════════════════════════════════════════════════════════════════════════════
Every logged application creates a follow-up five days later. When that
follow-up closes, PRAHARI has the one piece of ground truth it gets for free:
did the field get better, stay the same or get worse after the action?

This module counts those outcomes. It does three things deliberately:

  · groups by KIND of action (cultural, mechanical, biological, chemical) and
    target, never by product or supplier — this is not a ranking of what to
    buy, and nothing here feeds the chemical gate
  · keeps MEASURED outcomes (two photographs compared) apart from the
    farmer's own account, and never adds them together
  · gives a share only when at least MIN_BASE measured outcomes exist; below
    that it says "2 of 3", because 67% of three fields is not a finding

No new table: this reads `applications` and `followups` only.
"""
from __future__ import annotations

from typing import Any

from . import reference
from .db import Database, loads

MIN_BASE = 5
OUTCOMES = ("better", "same", "worse")
KIND_ORDER = ("cultural", "mechanical", "biological", "chemical")
KIND_LABEL = {
    "cultural": ("Cultural practice", "मशागत पद्धत"),
    "mechanical": ("Mechanical removal", "यांत्रिक उपाय"),
    "biological": ("Biological control", "जैविक नियंत्रण"),
    "chemical": ("Chemical application", "रासायनिक फवारणी"),
}


def _rows(db: Database, *, plot_ids: list[str] | None = None,
          talukas: list[str] | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    where = []
    if plot_ids is not None:
        if not plot_ids:
            return []
        ph = ",".join(f":p{i}" for i in range(len(plot_ids)))
        where.append(f"f.plot_id IN ({ph})")
        params.update({f"p{i}": p for i, p in enumerate(plot_ids)})
    if talukas is not None:
        if not talukas:
            return []
        ph = ",".join(f":t{i}" for i in range(len(talukas)))
        where.append(f"p.taluka IN ({ph})")
        params.update({f"t{i}": t for i, t in enumerate(talukas)})
    sql = ("SELECT a.kind, a.target, f.outcome, f.comparison, f.done_observation"
           " FROM followups f JOIN applications a ON a.id = f.application_id"
           " JOIN plots p ON p.id = f.plot_id")
    if where:
        sql += " WHERE " + " AND ".join(where)
    return db.rows(sql, params)


def _method(row: dict[str, Any]) -> str | None:
    """'measured', 'self_reported', or None for a follow-up still open."""
    out = row.get("outcome")
    if not out:
        return None
    if out in OUTCOMES:
        cmp = loads(row.get("comparison"), {}) or {}
        if cmp.get("method") == "self_reported" or not row.get("done_observation"):
            return "self_reported"
        return "measured"
    return "other"          # unmeasurable | not_done


def _empty() -> dict[str, Any]:
    return {"followups": 0, "open": 0,
            "measured": dict.fromkeys(OUTCOMES, 0),
            "self_reported": dict.fromkeys(OUTCOMES, 0),
            "not_measurable": 0}


def _finish(g: dict[str, Any]) -> dict[str, Any]:
    m = g["measured"]
    base = sum(m.values())
    g["measured_total"] = base
    g["self_reported_total"] = sum(g["self_reported"].values())
    if base >= MIN_BASE:
        g["better_share"] = round(100 * m["better"] / base)
        g["statement"] = (f"Better in {m['better']} of {base} measured follow-ups "
                          f"({g['better_share']}%).")
        g["statement_mr"] = (f"मोजलेल्या {base} पैकी {m['better']} पुनर्तपासण्यांत सुधारणा "
                             f"({g['better_share']}%).")
    else:
        g["better_share"] = None
        g["statement"] = (f"Better in {m['better']} of {base} measured follow-ups — too few "
                          f"to give a share (needs {MIN_BASE})." if base else
                          "No measured follow-up yet.")
        g["statement_mr"] = (f"मोजलेल्या {base} पैकी {m['better']} मध्ये सुधारणा — टक्केवारीसाठी "
                             f"किमान {MIN_BASE} लागतात." if base else
                             "अजून एकही मोजलेली पुनर्तपासणी नाही.")
    return g


def summarise(db: Database, *, plot_ids: list[str] | None = None,
              talukas: list[str] | None = None) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    total = _empty()
    for r in _rows(db, plot_ids=plot_ids, talukas=talukas):
        key = (r.get("kind") or "chemical", r.get("target") or "")
        g = groups.setdefault(key, _empty())
        method = _method(r)
        for bucket in (g, total):
            bucket["followups"] += 1
            if method is None:
                bucket["open"] += 1
            elif method == "other":
                bucket["not_measurable"] += 1
            else:
                bucket[method][r["outcome"]] += 1

    rows = []
    for (kind, target), g in groups.items():
        en, mr = KIND_LABEL.get(kind, (kind, kind))
        rows.append({"kind": kind, "kind_label": en, "kind_label_mr": mr,
                     "target": target or None,
                     "target_label": reference.problem_name(target) if target else None,
                     "target_label_mr": reference.problem_name(target, "mr") if target else None,
                     **_finish(g)})
    rows.sort(key=lambda x: (KIND_ORDER.index(x["kind"]) if x["kind"] in KIND_ORDER else 9,
                             x["target"] or ""))
    return {
        "groups": rows,
        "total": _finish(total),
        "min_base": MIN_BASE,
        "method": ("Counts of closed follow-ups after each logged action. Measured means two "
                   "photographs were compared; self-reported is the farmer's own account and "
                   "is never added to the measured count. Grouped by kind of action, never by "
                   "product or supplier, and nothing here can authorise a chemical."),
        "method_mr": ("प्रत्येक नोंदवलेल्या उपायानंतरच्या पुनर्तपासण्यांची संख्या. 'मोजलेले' म्हणजे "
                      "दोन फोटोंची तुलना; शेतकऱ्याचे स्वतःचे सांगणे वेगळे ठेवले आहे. उत्पादन "
                      "किंवा विक्रेत्यानुसार क्रम नाही."),
    }
