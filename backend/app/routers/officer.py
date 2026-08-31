"""
PRAHARI · /api/officer — the command centre.

Everything here is scoped to the talukas this officer is authorised for. An
empty scope returns nothing, never everything. Farmer contact details appear
only on a case the officer has been assigned.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import reference, spatial
from ..clock import now_iso
from ..clock import today as _today
from ..db import Database
from ..deps import db_dep, officer_of, officer_talukas, require_roles
from ..errors import bad_request, forbidden, not_found
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import AssignIn, AssignmentCloseIn

router = APIRouter(prefix="/api/officer", tags=["officer"])


def _scope(db: Database, user: dict[str, Any]) -> list[str]:
    scopes = officer_talukas(db, user)
    return scopes


def _in(scopes: list[str], prefix: str = "t"):
    return ",".join(f":{prefix}{i}" for i in range(len(scopes))), \
           {f"{prefix}{i}": t for i, t in enumerate(scopes)}


@router.get("/summary", summary="The overview panel",
            description="Active cases, high-risk fields, emerging clusters, cases awaiting "
                        "verification, and cases that got worse after treatment.")
def summary(days: int = Query(14, ge=1, le=90),
            user: dict[str, Any] = Depends(require_roles("officer")),
            db: Database = Depends(db_dep)):
    scopes = _scope(db, user)
    if not scopes:
        return {"scope": [], "note": "No talukas are assigned to your account yet."}
    ph, params = _in(scopes)
    since = (_today() - dt.timedelta(days=days)).isoformat()
    rt = get_runtime()

    open_cases = db.scalar(
        f"SELECT COUNT(*) FROM observations WHERE taluka IN ({ph}) AND status = 'open'"
        f" AND substr(observed_at,1,10) >= :since", {**params, "since": since}) or 0
    abstentions = db.scalar(
        f"SELECT COUNT(*) FROM diagnoses d JOIN observations o ON o.id = d.observation_id"
        f" WHERE o.taluka IN ({ph}) AND d.abstained = 1 AND d.confirmed IS NULL"
        f" AND substr(o.observed_at,1,10) >= :since", {**params, "since": since}) or 0
    awaiting = db.scalar(
        f"SELECT COUNT(*) FROM expert_cases WHERE taluka IN ({ph})"
        f" AND status IN ('submitted','reviewing')", params) or 0
    worsening = db.rows(
        f"SELECT f.id, f.plot_id, f.done_on, p.name AS plot_name, p.crop, p.taluka"
        f" FROM followups f JOIN plots p ON p.id = f.plot_id"
        f" WHERE p.taluka IN ({ph}) AND f.outcome = 'worse' ORDER BY f.done_on DESC LIMIT 20",
        params)
    high_risk = db.rows(
        f"SELECT h.plot_id, h.day, h.score, p.name AS plot_name, p.crop, p.taluka"
        f" FROM health_snapshots h JOIN plots p ON p.id = h.plot_id"
        f" WHERE p.taluka IN ({ph}) AND h.day >= :since AND h.score < 50"
        f" ORDER BY h.score LIMIT 20", {**params, "since": since})
    clusters = list(rt.outbreak.open_events(scopes))
    # Community signals sit BESIDE the diagnosed clusters, never merged into
    # them. They are a different kind of evidence — earlier, cheaper, weaker —
    # and an officer needs to see which of the two a number came from before
    # deciding whether to spend a visit on it.
    rt.signals.sweep(talukas=scopes)
    community_signals = rt.signals.open_signals(scopes)
    community_activity = db.scalar(
        f"SELECT COUNT(*) FROM community_posts WHERE taluka IN ({ph})"
        f" AND status = 'published' AND signal_eligible = 1"
        f" AND substr(created_at,1,10) >= :since", {**params, "since": since}) or 0
    unanswered = db.scalar(
        f"SELECT COUNT(*) FROM community_posts WHERE taluka IN ({ph})"
        f" AND status = 'published' AND verification = 'UNVERIFIED' AND comment_count = 0"
        f" AND substr(created_at,1,10) >= :since", {**params, "since": since}) or 0
    by_crop = db.rows(
        f"SELECT crop, COUNT(*) AS n FROM observations WHERE taluka IN ({ph})"
        f" AND substr(observed_at,1,10) >= :since GROUP BY crop ORDER BY n DESC",
        {**params, "since": since})
    by_problem = db.rows(
        f"SELECT d.top_problem AS problem, COUNT(*) AS n FROM diagnoses d"
        f" JOIN observations o ON o.id = d.observation_id"
        f" WHERE o.taluka IN ({ph}) AND substr(o.observed_at,1,10) >= :since"
        f" AND d.top_problem IS NOT NULL GROUP BY d.top_problem ORDER BY n DESC",
        {**params, "since": since})
    for r in by_problem:
        r["problem_name"] = reference.problem_name(r["problem"])

    return {
        "scope": scopes,
        "scope_names": [reference.taluka_name(t) for t in scopes],
        "window_days": days,
        "active_cases": open_cases,
        "awaiting_verification": awaiting,
        "model_abstentions": abstentions,
        "high_risk_fields": high_risk,
        "worsening_after_treatment": worsening,
        "clusters": clusters,
        "community_signals": community_signals,
        "community_posts": community_activity,
        "community_unanswered": unanswered,
        "community_note": ("A community signal is what farmers are SAYING. A cluster is what has "
                           "been diagnosed. PRAHARI keeps them apart on this screen because they "
                           "justify different actions — a signal justifies a visit, a confirmed "
                           "cluster justifies an advisory."),
        "by_crop": by_crop,
        "by_problem": by_problem,
        "generated_at": now_iso(),
    }


@router.get("/hotspots", summary="Getis-Ord Gi* hotspots and the spread front")
def hotspots(problem: str = Query("late_blight"), crop: str | None = Query(None),
             days: int = Query(21, ge=3, le=120), band_km: float = Query(22.0, ge=5, le=100),
             user: dict[str, Any] = Depends(require_roles("officer")),
             db: Database = Depends(db_dep)):
    scopes = _scope(db, user)
    rt = get_runtime()
    return rt.outbreak.hotspots(problem, crop=crop, days=days, band_km=band_km,
                                talukas=scopes or None)


@router.get("/outbreaks", summary="Graded clusters in your scope",
            description=("emerging cluster → suspected hotspot → confirmed hotspot. The grade is "
                          "set by the evidence that exists, and 'confirmed' requires expert "
                          "confirmations, not photograph counts."))
def outbreaks(problem: str | None = Query(None),
              user: dict[str, Any] = Depends(require_roles("officer")),
              db: Database = Depends(db_dep)):
    scopes = _scope(db, user)
    rt = get_runtime()
    if problem:
        assessments = [rt.outbreak.assess(t, problem) for t in scopes]
        return {"assessments": [a for a in assessments if a["grade"] != "none"],
                "all": assessments}
    return {"events": rt.outbreak.open_events(scopes)}


@router.get("/queue", summary="The priority queue for this week",
            description=("Ranked by uncertainty × area at risk × spatial urgency × escalation — "
                          "deliberately NOT by confidence. A case the model is sure about does not "
                          "need a human; an uncertain case inside a hotspot does."))
def queue(capacity: int = Query(5, ge=1, le=50), days: int = Query(14, ge=1, le=90),
          user: dict[str, Any] = Depends(require_roles("officer")),
          db: Database = Depends(db_dep)):
    scopes = _scope(db, user)
    if not scopes:
        return {"queue": [], "capacity": capacity,
                "note": "No talukas are assigned to your account yet."}
    ph, params = _in(scopes)
    since = (_today() - dt.timedelta(days=days)).isoformat()
    cases = db.rows(
        f"SELECT o.id, o.plot_id, o.taluka, o.crop, o.observed_at, o.status,"
        f" d.top_problem, d.top_posterior AS posterior, d.abstained, d.abstain_reason,"
        f" p.area_acre, p.name AS plot_name, p.lat, p.lng"
        f" FROM observations o LEFT JOIN diagnoses d ON d.observation_id = o.id"
        f" JOIN plots p ON p.id = o.plot_id"
        f" WHERE o.taluka IN ({ph}) AND o.status = 'open' AND o.kind IN ('leaf','followup')"
        f" AND substr(o.observed_at,1,10) >= :since ORDER BY o.observed_at DESC",
        {**params, "since": since})
    for c in cases:
        c["abstained"] = bool(c.get("abstained"))
        worse = db.one(
            "SELECT id FROM followups WHERE done_observation = :o AND outcome = 'worse'",
            {"o": c["id"]})
        c["rescan_worse"] = bool(worse)
        if c.get("top_problem"):
            c["top_problem_name"] = reference.problem_name(c["top_problem"])
    counts: dict[str, int] = {}
    for c in cases:
        counts[c["taluka"]] = counts.get(c["taluka"], 0) + 1
    # Computed over the full district for the same reason as in outbreak.py: a
    # local statistic scored against two neighbours is not a statistic.
    hs = spatial.getis_ord(reference.TALUKAS, counts)
    firsts = {}
    for c in cases:
        off = (dt.date.fromisoformat(str(c["observed_at"])[:10]) - _today()).days
        firsts[c["taluka"]] = min(firsts.get(c["taluka"], 0), off)
    front = spatial.spread_front(reference.TALUKAS, firsts) if len(firsts) >= 3 else None
    out = spatial.priority_queue(cases, hs, front["velocity_km_per_day"] if front else None,
                                 capacity)
    out["scope"] = scopes
    return out


@router.get("/route", summary="A suggested inspection sequence",
            description="A planning suggestion, not an optimal route — straight-line distances, "
                        "no knowledge of Nashik district roads.")
def route(capacity: int = Query(5, ge=1, le=20),
          lat: float | None = Query(None), lng: float | None = Query(None),
          user: dict[str, Any] = Depends(require_roles("officer")),
          db: Database = Depends(db_dep)):
    from .. import routeplan
    q = queue(capacity=capacity, days=14, user=user, db=db)
    stops = q.get("visit_this_week") or q.get("queue", [])[:capacity]
    base = None
    if lat is not None and lng is not None:
        base = {"lat": lat, "lng": lng}
    else:
        officer = officer_of(db, user) if user["role"] == "officer" else None
        t = reference.TALUKA_BY_ID.get((officer or {}).get("taluka") or "")
        if t:
            base = {"lat": t["lat"], "lng": t["lng"]}
    return routeplan.plan(stops, base, capacity)


@router.post("/assignments", status_code=201, summary="Assign a case for a field visit")
def assign(data: AssignIn, user: dict[str, Any] = Depends(require_roles("officer")),
           db: Database = Depends(db_dep)):
    scopes = _scope(db, user)
    officer = officer_of(db, user) if user["role"] == "officer" else None
    if not data.observation_id and not data.case_id:
        raise bad_request("nothing_to_assign", "Give an observation_id or a case_id.")
    taluka = None
    if data.observation_id:
        obs = db.one("SELECT * FROM observations WHERE id = :id", {"id": data.observation_id})
        if not obs:
            raise not_found("observation", data.observation_id)
        taluka = obs["taluka"]
    else:
        case = db.one("SELECT * FROM expert_cases WHERE id = :id", {"id": data.case_id})
        if not case:
            raise not_found("case", data.case_id)
        taluka = case["taluka"]
    if scopes and taluka not in scopes:
        raise forbidden("cases outside your assigned talukas")
    due = (_today() + dt.timedelta(days=data.due_in_days)).isoformat()
    aid = db.insert_returning_id(
        "INSERT INTO assignments (observation_id, case_id, officer_id, taluka, priority, due_on,"
        " status, assigned_at) VALUES (:o,:c,:off,:tk,:pri,:due,'assigned',:now)",
        {"o": data.observation_id, "c": data.case_id,
         "off": data.officer_id or (officer or {}).get("id"), "tk": taluka,
         "pri": data.priority, "due": due, "now": now_iso()})
    if data.observation_id:
        obs = db.one("SELECT plot_id FROM observations WHERE id = :id", {"id": data.observation_id})
        db.execute(
            "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
            " VALUES (:p,:at,'officer','watch',:t,:d,:ref,:now)",
            {"p": obs["plot_id"], "at": _today().isoformat(),
             "t": "An extension officer will visit this field",
             "d": f"Priority {data.priority}, due {due}.", "ref": str(aid), "now": now_iso()})
    audit("officer.assign", entity="assignment", entity_id=str(aid), user_id=user["id"])
    return db.one("SELECT * FROM assignments WHERE id = :id", {"id": aid})


@router.get("/assignments", summary="Your assigned visits")
def assignments(status: str | None = Query(None),
                user: dict[str, Any] = Depends(require_roles("officer")),
                db: Database = Depends(db_dep)):
    officer = officer_of(db, user) if user["role"] == "officer" else None
    sql = ("SELECT a.*, o.plot_id, o.crop, p.name AS plot_name, p.lat, p.lng,"
           " f.name AS farmer_name, f.phone AS farmer_phone"
           " FROM assignments a LEFT JOIN observations o ON o.id = a.observation_id"
           " LEFT JOIN plots p ON p.id = o.plot_id"
           " LEFT JOIN farmers f ON f.id = p.farmer_id WHERE 1=1")
    params: dict[str, Any] = {}
    if officer:
        sql += " AND a.officer_id = :off"
        params["off"] = officer["id"]
    if status:
        sql += " AND a.status = :st"
        params["st"] = status
    return {"assignments": db.rows(sql + " ORDER BY a.due_on", params),
            "note": ("Farmer contact details appear here because you have been assigned this "
                     "visit. They do not appear in the queue or on any map.")}


@router.post("/assignments/{assignment_id}/close", summary="Close a visit with a finding")
def close(assignment_id: int, data: AssignmentCloseIn,
          user: dict[str, Any] = Depends(require_roles("officer")),
          db: Database = Depends(db_dep)):
    row = db.one("SELECT * FROM assignments WHERE id = :id", {"id": assignment_id})
    if not row:
        raise not_found("assignment", str(assignment_id))
    rt = get_runtime()
    db.execute(
        "UPDATE assignments SET status = :s, finding = :f, closed_at = :now WHERE id = :id",
        {"s": data.status, "f": data.finding, "now": now_iso(), "id": assignment_id})
    prior_shift = None
    if data.status == "confirmed" and data.confirmed_problem and row["observation_id"]:
        obs = db.one("SELECT * FROM observations WHERE id = :id", {"id": row["observation_id"]})
        dx = db.one("SELECT * FROM diagnoses WHERE observation_id = :o", {"o": obs["id"]})
        if dx:
            db.execute("UPDATE diagnoses SET confirmed = :v, confirmed_by = :by, confirmed_at = :at"
                       " WHERE id = :id",
                       {"v": data.confirmed_problem, "by": user["full_name"],
                        "at": now_iso(), "id": dx["id"]})
        db.execute("UPDATE observations SET status = 'confirmed' WHERE id = :id", {"id": obs["id"]})
        prior_shift = rt.diagnosis.bump_prior(obs["taluka"], obs["crop"], data.confirmed_problem)
        db.execute(
            "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
            " VALUES (:p,:at,'officer','info',:t,:d,:ref,:now)",
            {"p": obs["plot_id"], "at": _today().isoformat(),
             "t": f"Officer confirmed on the ground: {reference.problem_name(data.confirmed_problem)}",
             "d": data.finding or "", "ref": str(assignment_id), "now": now_iso()})
    audit("officer.close", entity="assignment", entity_id=str(assignment_id), user_id=user["id"],
          detail={"status": data.status})
    return {"assignment_id": assignment_id, "status": data.status, "prior_shift": prior_shift}


@router.get("/audit", summary="The views that let an officer check PRAHARI's claims",
            description="Computed from stored rows only. Anyone with the database can reproduce "
                        "every number the app displays.")
def audit_views(user: dict[str, Any] = Depends(require_roles("officer")),
                db: Database = Depends(db_dep)):
    scopes = _scope(db, user)
    ph, params = _in(scopes) if scopes else ("''", {})
    spray_ledger = db.rows(
        f"SELECT tc.crop, tc.pest, COUNT(*) AS checks,"
        f" SUM(CASE WHEN tc.acted = 0 THEN 1 ELSE 0 END) AS not_sprayed,"
        f" SUM(CASE WHEN tc.acted = 1 THEN 1 ELSE 0 END) AS sprayed,"
        f" ROUND(SUM(CASE WHEN tc.acted = 0 THEN COALESCE(tc.saving,0) ELSE 0 END)) AS rupees_saved"
        f" FROM threshold_checks tc JOIN plots p ON p.id = tc.plot_id"
        f" WHERE p.taluka IN ({ph}) GROUP BY tc.crop, tc.pest", params)
    harvest_gate = db.rows(
        f"SELECT p.id AS plot_id, p.name, p.crop, MAX(a.clears_on) AS earliest_harvest"
        f" FROM plots p JOIN applications a ON a.plot_id = p.id"
        f" WHERE p.taluka IN ({ph}) AND a.kind = 'chemical' GROUP BY p.id, p.name, p.crop", params)
    abstentions = db.rows(
        f"SELECT d.abstain_reason, COUNT(*) AS n,"
        f" SUM(CASE WHEN d.confirmed IS NOT NULL THEN 1 ELSE 0 END) AS resolved_by_expert"
        f" FROM diagnoses d JOIN observations o ON o.id = d.observation_id"
        f" WHERE o.taluka IN ({ph}) AND d.abstained = 1 GROUP BY d.abstain_reason", params)
    model_vs_expert = db.rows(
        f"SELECT d.top_problem AS suspected, d.confirmed, COUNT(*) AS n"
        f" FROM diagnoses d JOIN observations o ON o.id = d.observation_id"
        f" WHERE o.taluka IN ({ph}) AND d.confirmed IS NOT NULL AND d.abstained = 0"
        f" GROUP BY d.top_problem, d.confirmed", params)
    claims = db.rows(
        "SELECT status, COUNT(*) AS n FROM label_claims GROUP BY status")
    deliveries = db.rows(
        "SELECT channel, state, COUNT(*) AS n FROM notification_deliveries GROUP BY channel, state")
    return {
        "spray_ledger": spray_ledger,
        "harvest_gate": harvest_gate,
        "abstentions": abstentions,
        "model_vs_expert": model_vs_expert,
        "label_claims_by_status": claims,
        "notification_deliveries": deliveries,
        "note": ("Every figure above is a GROUP BY over stored rows. A delivery counted as 'sent' "
                 "means a gateway accepted the message — only a provider callback can make it "
                 "'delivered', and nothing in PRAHARI sets that by itself."),
    }
