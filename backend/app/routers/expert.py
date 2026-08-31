"""
PRAHARI · /api/expert — the verification portal.

VERIFY. An expert sees everything the model saw and everything it could not:
the images, the crop and its stage, the weather at that field, the AI's ranked
differential with its evidence, the taluka prior, the field's history and the
farmer's answers to the contextual questions.

Every decision is recorded. A confirmation moves the taluka prior by exactly
one integer — and that is the WHOLE learning step at request time. A production
image model is never retrained from a single confirmation; confirmations
accumulate into a reviewed dataset, and retraining is a separate, versioned,
evaluated act. See ml/README.md.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import reference
from ..clock import now_iso
from ..clock import today as _today
from ..db import Database, bit, loads
from ..deps import db_dep, expert_of, require_roles
from ..errors import bad_request, forbidden, not_found
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import ExpertReviewIn
from ..weather import WeatherUnavailable

router = APIRouter(prefix="/api/expert", tags=["expert"])


@router.get("/cases", summary="The verification queue",
            description="Cases assigned to you, plus unassigned cases you may claim.")
def cases(status: str | None = Query(None), limit: int = Query(50, le=200),
          user: dict[str, Any] = Depends(require_roles("expert")),
          db: Database = Depends(db_dep)):
    expert = expert_of(db, user) if user["role"] == "expert" else None
    sql = ("SELECT c.*, p.name AS plot_name, p.crop AS plot_crop, p.area_acre,"
           " d.top_problem, d.top_posterior, d.abstained, d.abstain_reason, d.engine"
           " FROM expert_cases c JOIN plots p ON p.id = c.plot_id"
           " LEFT JOIN diagnoses d ON d.id = c.diagnosis_id WHERE 1=1")
    params: dict[str, Any] = {}
    if status:
        sql += " AND c.status = :st"
        params["st"] = status
    if expert:
        sql += " AND (c.assigned_to = :e OR c.assigned_to IS NULL)"
        params["e"] = expert["id"]
    rows = db.rows(sql + " ORDER BY CASE c.urgency WHEN 'urgent' THEN 0 ELSE 1 END,"
                         " c.submitted_at LIMIT :n", {**params, "n": limit})
    for r in rows:
        r["abstained"] = bool(r.get("abstained"))
        r["taluka_name"] = reference.taluka_name(r["taluka"])
        if r.get("top_problem"):
            r["top_problem_name"] = reference.problem_name(r["top_problem"])
        r.pop("farmer_id", None)          # the queue does not need to name farmers
    return {"cases": rows,
            "note": ("Urgent cases first — a field that got worse after treatment, or a farmer who "
                     "asked for a person.")}


@router.get("/cases/{case_id}", summary="Everything the expert needs to decide",
            description=("Images, crop and stage, the weather at that field, the AI differential "
                          "with its evidence, the taluka prior, the field's history and the "
                          "farmer's answers. Farmer contact details are not included — an expert "
                          "verifies a photograph, they do not need to phone anyone."))
def case_detail(case_id: str, user: dict[str, Any] = Depends(require_roles("expert")),
                db: Database = Depends(db_dep)):
    case = db.one("SELECT * FROM expert_cases WHERE id = :id", {"id": case_id})
    if not case:
        raise not_found("case", case_id)
    _claimable(db, user, case)
    rt = get_runtime()
    plot = db.one("SELECT * FROM plots WHERE id = :id", {"id": case["plot_id"]})
    obs = db.one("SELECT * FROM observations WHERE id = :id", {"id": case["observation_id"]})
    dx = db.one("SELECT * FROM diagnoses WHERE observation_id = :o", {"o": case["observation_id"]})
    images = db.rows("SELECT * FROM observation_images WHERE observation_id = :o",
                     {"o": case["observation_id"]})
    candidates = db.rows(
        "SELECT * FROM diagnosis_candidates WHERE diagnosis_id = :d ORDER BY rank",
        {"d": (dx or {}).get("id")}) if dx else []
    context = db.rows(
        "SELECT question, answer_label, answered_at FROM diagnosis_context WHERE diagnosis_id = :d",
        {"d": (dx or {}).get("id")}) if dx else []
    events = db.rows(
        "SELECT at, kind, severity, title, detail FROM field_events WHERE plot_id = :p"
        " ORDER BY at DESC LIMIT 30", {"p": case["plot_id"]})
    reviews = db.rows("SELECT * FROM expert_reviews WHERE case_id = :c ORDER BY created_at",
                      {"c": case_id})

    weather = None
    try:
        wx = rt.risk.weather_series(plot)
        weather = {"source": wx.get("source"), "kind": wx.get("source_kind"),
                   "fetched_at": wx.get("fetched_at"),
                   "days": wx["days"][-10:]}
    except WeatherUnavailable as exc:
        weather = {"unavailable": True, "reason": exc.reason}

    return {
        "case": case,
        "plot": {k: v for k, v in (plot or {}).items() if k not in ("farmer_id",)},
        "crop_stage": rt.risk.crop_stage(plot) if plot else None,
        "observation": obs,
        "images": [{"role": i["role"], "url": rt.storage.url(i["storage_key"]),
                    "quality": loads(i["quality"], {}), "features": loads(i["features"], {})}
                   for i in images],
        "diagnosis": dx,
        "differential": [{**c, "supporting": loads(c["supporting"], []),
                          "contradicting": loads(c["contradicting"], []),
                          "problem_name": reference.problem_name(c["problem"])}
                         for c in candidates],
        "prior": loads((dx or {}).get("prior_used"), {}),
        "farmer_answers": context,
        "weather": weather,
        "field_history": events,
        "reviews": reviews,
        "candidate_problems": [
            {"id": k, "name": v["name"], "name_mr": v["mr"], "sci": v["sci"]}
            for k, v in reference.problems_for_crop(plot["crop"]).items()] if plot else [],
    }


@router.post("/cases/{case_id}/review", summary="Record an expert decision",
             description=("confirm · reject · change · request_info · field_visit · mark_urgent.\n\n"
                          "A confirm or change adds exactly 1 to α for that problem in that "
                          "taluka. No gradient, no retraining, and an officer can audit it by "
                          "counting confirmed cases."))
def review(case_id: str, data: ExpertReviewIn,
           user: dict[str, Any] = Depends(require_roles("expert")),
           db: Database = Depends(db_dep)):
    case = db.one("SELECT * FROM expert_cases WHERE id = :id", {"id": case_id})
    if not case:
        raise not_found("case", case_id)
    expert = _claimable(db, user, case)
    rt = get_runtime()
    stamp = now_iso()

    if data.verdict and data.verdict not in reference.DISEASES and data.verdict not in reference.PESTS:
        raise bad_request("unknown_problem",
                          f"'{data.verdict}' is not a problem PRAHARI knows for this crop.")

    db.execute(
        "INSERT INTO expert_reviews (case_id, expert_id, expert_name, action, verdict, confidence,"
        " note, created_at) VALUES (:c,:e,:n,:a,:v,:conf,:note,:now)",
        {"c": case_id, "e": (expert or {}).get("id"), "n": user["full_name"],
         "a": data.action, "v": data.verdict, "conf": data.confidence,
         "note": data.note, "now": stamp})

    status_map = {"confirm": "verified", "change": "verified", "reject": "rejected",
                  "request_info": "info_requested", "field_visit": "reviewing",
                  "mark_urgent": "reviewing"}
    new_status = status_map[data.action]
    db.execute(
        "UPDATE expert_cases SET status = :s, reviewed_at = :at, verdict = :v,"
        " assigned_to = COALESCE(assigned_to, :e),"
        " urgency = CASE WHEN :urgent = 1 THEN 'urgent' ELSE urgency END WHERE id = :id",
        {"s": new_status, "at": stamp, "v": data.verdict, "e": (expert or {}).get("id"),
         "urgent": bit(data.action in ("mark_urgent", "field_visit")), "id": case_id})

    prior_shift = None
    corrected = None
    if data.action in ("confirm", "change") and data.verdict:
        dx = db.one("SELECT * FROM diagnoses WHERE observation_id = :o",
                    {"o": case["observation_id"]})
        if dx:
            corrected = (dx["top_problem"] != data.verdict)
            db.execute(
                "UPDATE diagnoses SET confirmed = :v, confirmed_by = :by, confirmed_at = :at"
                " WHERE id = :id",
                {"v": data.verdict, "by": user["full_name"], "at": stamp, "id": dx["id"]})
        db.execute("UPDATE observations SET status = :s WHERE id = :o",
                   {"s": "corrected" if corrected else "confirmed", "o": case["observation_id"]})
        prior_shift = rt.diagnosis.bump_prior(case["taluka"], case["crop"], data.verdict)
    elif data.action == "reject":
        db.execute("UPDATE observations SET status = 'rejected' WHERE id = :o",
                   {"o": case["observation_id"]})

    verdict_name = reference.problem_name(data.verdict) if data.verdict else None
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
        " VALUES (:p,:at,'expert',:sev,:t,:d,:ref,:now)",
        {"p": case["plot_id"], "at": _today().isoformat(),
         "sev": "high" if data.action == "field_visit" else "info",
         "t": _event_title(data.action, verdict_name),
         "d": (data.note or "")[:800], "ref": case_id, "now": stamp})

    farmer = db.one("SELECT * FROM farmers WHERE id = :f", {"f": case["farmer_id"]})
    rt.notify.push(
        user_id=(farmer or {}).get("user_id"), plot_id=case["plot_id"], kind="expert",
        severity="rising" if data.action in ("confirm", "change") else "watch",
        title=_event_title(data.action, verdict_name),
        body=(data.note or "") or _default_body(data.action, verdict_name),
        title_mr=_event_title_mr(data.action,
                                 reference.problem_name(data.verdict, "mr") if data.verdict else None),
        body_mr=(data.note or "") or _default_body(data.action, verdict_name),
        channels=["sms"] if (farmer or {}).get("phone") else [],
        address=(farmer or {}).get("phone"), lang=(farmer or {}).get("lang", "mr"))
    audit("expert.review", entity="expert_case", entity_id=case_id, user_id=user["id"],
          role=user["role"], detail={"action": data.action, "verdict": data.verdict})

    return {
        "case_id": case_id, "status": new_status, "action": data.action,
        "verdict": data.verdict, "corrected_the_model": corrected,
        "prior_shift": prior_shift,
        "learning_note": (
            f"α for {data.verdict} in {case['taluka']} moved to {prior_shift['alpha']}. Every "
            f"future diagnosis in this taluka now weights this candidate higher. That is the "
            f"entire request-time learning mechanism — no gradient, no retraining."
            if prior_shift else
            "No prior was moved: only a confirm or a change is evidence about what the problem was."),
        "dataset_note": (
            "This confirmation is now a labelled observation. It enters the training corpus only "
            "through review and a versioned retraining run — a production model is never updated "
            "from one confirmation."),
    }


@router.get("/model-agreement", summary="AI/expert agreement, abstention and unknown rates",
            description=("More meaningful than a single accuracy number, and computed from stored "
                          "rows rather than asserted. Returns counts, not percentages, until the "
                          "sample is large enough for a rate to mean anything."))
def agreement(user: dict[str, Any] = Depends(require_roles("expert", "officer")),
              db: Database = Depends(db_dep)):
    rows = db.rows(
        "SELECT top_problem, confirmed, abstained, abstain_reason, engine, model_version"
        " FROM diagnoses WHERE confirmed IS NOT NULL")
    total = db.scalar("SELECT COUNT(*) FROM diagnoses") or 0
    abstained = db.scalar("SELECT COUNT(*) FROM diagnoses WHERE abstained = 1") or 0
    reviewed = len(rows)
    agreed = sum(1 for r in rows if not r["abstained"] and r["top_problem"] == r["confirmed"])
    scored = sum(1 for r in rows if not r["abstained"])
    by_reason = db.rows(
        "SELECT abstain_reason, COUNT(*) AS n FROM diagnoses WHERE abstained = 1"
        " GROUP BY abstain_reason ORDER BY n DESC")
    confusion = db.rows(
        "SELECT top_problem, confirmed, COUNT(*) AS n FROM diagnoses"
        " WHERE confirmed IS NOT NULL AND abstained = 0 GROUP BY top_problem, confirmed"
        " ORDER BY n DESC")
    return {
        "diagnoses_total": total,
        "abstentions": abstained,
        "abstention_rate": round(abstained / total, 3) if total else None,
        "expert_reviewed": reviewed,
        "scored_and_reviewed": scored,
        "agreed": agreed,
        "agreement_rate": round(agreed / scored, 3) if scored >= 20 else None,
        "agreement_rate_note": (None if scored >= 20 else
                                f"Only {scored} reviewed non-abstained diagnoses so far. PRAHARI "
                                f"will not print a rate from a sample this small."),
        "abstention_reasons": by_reason,
        "confusion": [{**c, "predicted_name": reference.problem_name(c["top_problem"] or ""),
                       "actual_name": reference.problem_name(c["confirmed"] or "")}
                      for c in confusion],
        "method": ("Every row here is a stored diagnosis with a stored expert verdict. Nothing is "
                   "modelled. Where the sample is too small for a rate to be meaningful, PRAHARI "
                   "returns the counts and says so."),
    }


def _claimable(db: Database, user: dict[str, Any], case: dict[str, Any]):
    if user["role"] == "admin":
        return None
    expert = expert_of(db, user)
    if case["assigned_to"] and case["assigned_to"] != expert["id"]:
        raise forbidden("a case assigned to another expert")
    return expert


def _event_title(action: str, verdict: str | None) -> str:
    return {
        "confirm": f"Expert confirmed: {verdict}",
        "change": f"Expert corrected the diagnosis to {verdict}",
        "reject": "Expert rejected this observation",
        "request_info": "Expert has asked for more information",
        "field_visit": "Expert has requested a field visit",
        "mark_urgent": "Expert marked this case urgent",
    }[action]


def _event_title_mr(action: str, verdict: str | None) -> str:
    return {
        "confirm": f"तज्ज्ञांनी निश्चित केले: {verdict}",
        "change": f"तज्ज्ञांनी निदान बदलले: {verdict}",
        "reject": "तज्ज्ञांनी ही नोंद नाकारली",
        "request_info": "तज्ज्ञांना अधिक माहिती हवी आहे",
        "field_visit": "तज्ज्ञांनी शेतभेटीची शिफारस केली",
        "mark_urgent": "तज्ज्ञांनी हे प्रकरण तातडीचे ठरवले",
    }[action]


def _default_body(action: str, verdict: str | None) -> str:
    return {
        "confirm": f"An agronomist has reviewed your photograph and confirmed {verdict}.",
        "change": f"An agronomist reviewed your photograph and identified {verdict} instead.",
        "reject": "An agronomist could not identify a problem from this observation.",
        "request_info": "Please send another photograph — the underside of an affected leaf helps most.",
        "field_visit": "An extension officer will visit your field.",
        "mark_urgent": "Your case has been prioritised.",
    }[action]
