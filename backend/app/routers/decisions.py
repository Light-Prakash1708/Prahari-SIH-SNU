"""PRAHARI · /api/threshold, /api/decisions, /api/recommendations, /api/applications."""
from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import chemicals, reference
from ..clock import now_iso
from ..clock import today as _today
from ..db import Database
from ..deps import current_user, db_dep, farmer_of, owned_plot, visible_plot
from ..errors import bad_request
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import ApplyIn, ThresholdIn

router = APIRouter(prefix="/api", tags=["decisions"])


@router.post("/threshold", summary="Check a count against the economic threshold",
             description=("The only path by which a chemical recommendation can be reached. "
                          "Below the threshold, 'do not spray' is returned as a decision with a "
                          "rupee value and a re-check date, not as an absence of advice.\n\n"
                          "Errors: 400 no_threshold — PRAHARI has no published ETL for that "
                          "combination and says so rather than guessing one."))
def check_threshold(data: ThresholdIn, user: dict[str, Any] = Depends(current_user),
                    db: Database = Depends(db_dep)):
    plot = owned_plot(db, user, data.plot_id)
    rt = get_runtime()
    stage = rt.risk.crop_stage(plot)
    damaging = rt.risk.damaging_stage(plot, data.pest)

    d = rt.decisions.check_threshold(plot, data.pest, data.count, stage,
                                     trap_obs_id=data.trap_obs_id, damaging_stage=damaging)
    if d.get("error"):
        raise bad_request("no_threshold", d["message"])

    decision = rt.decisions.spray_decision(plot, data.pest, threshold=d,
                                           damaging_stage=damaging)
    from ..services.decisions import chemical_rung_open
    prescription = rt.decisions.prescription(
        plot, data.pest, stage, chemical_authorised=chemical_rung_open(decision))

    pest_name = reference.problem_name(data.pest)
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
        " VALUES (:p,:at,'count',:sev,:t,:d,:ref,:now)",
        {"p": plot["id"], "at": _today().isoformat(),
         "sev": "high" if d["chemical_authorised"] else "watch",
         "t": f"{pest_name} counted — {data.count:g} {d['unit']}",
         "d": f"{d['percent_of_threshold']}% of the threshold ({d['etl_effective']:g}). {d['title']}",
         "ref": str(d["check_id"]), "now": now_iso()})

    if decision["decision"] in ("do_not_spray", "non_chemical") and d.get("saving_if_not_sprayed"):
        farmer = db.one("SELECT * FROM farmers WHERE id = :f", {"f": plot["farmer_id"]})
        rt.notify.push(
            user_id=(farmer or {}).get("user_id"), plot_id=plot["id"], kind="threshold",
            severity="low", title=f"No spray needed for {pest_name}",
            body=(f"At {d['percent_of_threshold']}% of the economic threshold. Not spraying keeps "
                  f"₹{d['saving_if_not_sprayed']:,} in your pocket. Count again in five days."),
            title_mr=f"{reference.problem_name(data.pest,'mr')} साठी फवारणीची गरज नाही",
            body_mr=(f"आर्थिक नुकसान मर्यादेच्या {d['percent_of_threshold']}% वर आहे. फवारणी न "
                     f"केल्याने ₹{d['saving_if_not_sprayed']:,} वाचतात. पाच दिवसांनी पुन्हा मोजा."),
            channels=["sms"] if (farmer or {}).get("phone") else [],
            address=(farmer or {}).get("phone"), lang=(farmer or {}).get("lang", "mr"))

    audit("threshold.check", entity="threshold_check", entity_id=str(d["check_id"]),
          user_id=user["id"], detail={"pest": data.pest, "band": d["band"],
                                      "authorised": d["chemical_authorised"]})
    return {"threshold": d, "decision": decision, **prescription}


@router.get("/decisions/{plot_id}/should-i-spray",
            summary="Should I spray? — the decision card",
            description=("Answers from the most recent count and diagnosis on record for this "
                          "target. Returns a decision object with evidence and a re-check date "
                          "whether the answer is yes or no."))
def should_i_spray(plot_id: str, target: str = Query(...),
                   user: dict[str, Any] = Depends(current_user),
                   db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rt = get_runtime()
    stage = rt.risk.crop_stage(plot)
    check = db.one(
        "SELECT * FROM threshold_checks WHERE plot_id = :p AND pest = :t"
        " ORDER BY checked_at DESC, id DESC LIMIT 1", {"p": plot_id, "t": target})
    threshold = None
    if check:
        row = reference.threshold_for(target, plot["crop"])
        from .. import etl
        threshold = etl.decide(row, check["count"], check["crop_stage"],
                               reference.CROPS[plot["crop"]], plot["area_acre"]) if row else None
        if threshold:
            threshold["check_id"] = check["id"]
            threshold["counted_on"] = str(check["checked_on"])
            threshold["etl_provenance"] = {"source": (row or {}).get("source"),
                                           "status": (row or {}).get("status", "draft")}
    dx = db.one(
        "SELECT * FROM diagnoses WHERE plot_id = :p AND (top_problem = :t OR confirmed = :t)"
        " ORDER BY created_at DESC LIMIT 1", {"p": plot_id, "t": target})
    damaging = rt.risk.damaging_stage(plot, target)
    decision = rt.decisions.spray_decision(
        plot, target, threshold=threshold,
        diagnosis={"abstained": bool(dx["abstained"]), "abstain_reason": dx["abstain_reason"],
                   "explain": dx["explain"], "id": dx["id"]} if dx else None,
        damaging_stage=damaging)
    from ..services.decisions import chemical_rung_open
    prescription = rt.decisions.prescription(
        plot, target, stage, chemical_authorised=chemical_rung_open(decision))
    return {"decision": decision, "threshold": threshold, **prescription}


@router.get("/recommendations/{plot_id}", summary="The IPM ladder for a target",
            description=("Monitoring → cultural → mechanical → biological → chemical. The chemical "
                          "rung opens only when the threshold gate authorised it AND a VERIFIED "
                          "label claim exists. Draft claims are never shown, and their product "
                          "names are never printed."))
def recommendations(plot_id: str, target: str = Query(...),
                    user: dict[str, Any] = Depends(current_user),
                    db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rt = get_runtime()
    stage = rt.risk.crop_stage(plot)
    check = db.one(
        "SELECT * FROM threshold_checks WHERE plot_id = :p AND pest = :t"
        " ORDER BY checked_at DESC, id DESC LIMIT 1", {"p": plot_id, "t": target})
    # The ladder must agree with the decision card. Computing the decision here
    # (without writing a decision row — this is a read) is how they stay in step.
    from ..services.decisions import chemical_rung_open
    threshold = None
    if check:
        from .. import etl
        row = reference.threshold_for(target, plot["crop"])
        if row:
            threshold = etl.decide(row, check["count"], check["crop_stage"],
                                   reference.CROPS[plot["crop"]], plot["area_acre"])
            threshold["check_id"] = check["id"]
    dx = db.one(
        "SELECT * FROM diagnoses WHERE plot_id = :p AND (top_problem = :t OR confirmed = :t)"
        " ORDER BY created_at DESC LIMIT 1", {"p": plot_id, "t": target})
    decision = rt.decisions.spray_decision(
        plot, target, threshold=threshold,
        diagnosis={"abstained": bool(dx["abstained"]), "abstain_reason": dx["abstain_reason"],
                   "explain": dx["explain"], "id": dx["id"]} if dx else None,
        damaging_stage=rt.risk.damaging_stage(plot, target),
        persist=False)
    out = rt.decisions.prescription(plot, target, stage,
                                    chemical_authorised=chemical_rung_open(decision))
    out["decision"] = decision
    out["threshold_authorised"] = bool(check and check["chemical_authorised"])
    out["last_check"] = check
    return out


@router.post("/applications", status_code=201,
             summary="Record an action taken, and schedule its follow-up",
             description=("Logging an application does two things: it sets the pre-harvest gate, "
                          "and it schedules the re-scan that closes the loop.\n\n"
                          "A CHEMICAL application is refused unless a verified label claim exists "
                          "for the crop and target AND a threshold check authorised it. Errors: "
                          "409 chemical_not_authorised · 409 no_verified_claim"))
def record_application(data: ApplyIn, user: dict[str, Any] = Depends(current_user),
                       db: Database = Depends(db_dep)):
    plot = owned_plot(db, user, data.plot_id)
    rt = get_runtime()
    day = data.applied_on or _today()

    claim = None
    if data.kind == "chemical":
        check = db.one("SELECT * FROM threshold_checks WHERE id = :id AND plot_id = :p",
                       {"id": data.check_id, "p": plot["id"]}) if data.check_id else None
        if not check or not check["chemical_authorised"]:
            from ..errors import conflict
            raise conflict(
                "chemical_not_authorised",
                "A chemical application can only be logged against a threshold check that "
                "authorised it. Count the pest first — that is the whole point of the gate.",
                message_mr=("रासायनिक फवारणीची नोंद फक्त मर्यादा ओलांडल्याच्या तपासणीसोबतच करता येते. "
                            "आधी कीड मोजा."))
        verified = chemicals.verified_claims(db, plot["crop"], data.target)
        claim = next((c for c in verified
                      if c["id"] == data.claim_id or c["product"] == data.product), None)
        if not claim:
            from ..errors import conflict
            raise conflict("no_verified_claim", chemicals.UNAVAILABLE_MESSAGE,
                           chemicals.UNAVAILABLE_MESSAGE_MR)

    phi = int(claim["phi_days"]) if claim else int(data.phi_days)
    clears = day + dt.timedelta(days=phi)
    app_id = db.insert_returning_id(
        "INSERT INTO applications (plot_id, crop, target, kind, product, moa_group, dose_text,"
        " phi_days, applied_on, clears_on, claim_id, authorised_by_check, decision_id, created_at)"
        " VALUES (:p,:c,:t,:k,:prod,:moa,:dose,:phi,:on,:clears,:claim,:check,:dec,:now)",
        {"p": plot["id"], "c": plot["crop"], "t": data.target, "k": data.kind,
         "prod": data.product, "moa": (claim or {}).get("moa_group") or data.moa_group,
         "dose": data.dose_text, "phi": phi, "on": day.isoformat(),
         "clears": clears.isoformat(), "claim": (claim or {}).get("id"),
         "check": data.check_id, "dec": data.decision_id, "now": now_iso()})
    if data.check_id:
        db.execute("UPDATE threshold_checks SET acted = 1 WHERE id = :id", {"id": data.check_id})

    due = day + dt.timedelta(days=5)
    fu_id = db.insert_returning_id(
        "INSERT INTO followups (plot_id, application_id, due_on, created_at)"
        " VALUES (:p,:a,:d,:now)",
        {"p": plot["id"], "a": app_id, "d": due.isoformat(), "now": now_iso()})
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
        " VALUES (:p,:at,'apply','rising',:t,:d,:ref,:now)",
        {"p": plot["id"], "at": day.isoformat(),
         "t": f"Applied {data.product}",
         "d": (f"{data.dose_text or ''} "
               + (f"Harvest gated until {clears.isoformat()}." if phi else
                  "Non-chemical action — no harvest gate.")).strip(),
         "ref": str(app_id), "now": now_iso()})
    farmer = db.one("SELECT * FROM farmers WHERE id = :f", {"f": plot["farmer_id"]})
    rt.notify.push(
        user_id=(farmer or {}).get("user_id"), plot_id=plot["id"], kind="followup",
        severity="watch", at=due.isoformat(),
        title="Scan this field again in 5 days",
        body=("PRAHARI will compare the two scans and tell you whether the action worked. If it is "
              "worse, the case goes to an officer rather than to a second spray."),
        title_mr="पाच दिवसांनी हे शेत पुन्हा तपासा",
        body_mr=("प्रहरी दोन्ही फोटोंची तुलना करून उपाय लागू पडला का ते सांगेल. स्थिती बिघडली असेल तर "
                 "प्रकरण दुसऱ्या फवारणीकडे नाही, अधिकाऱ्याकडे जाईल."),
        channels=["sms"] if (farmer or {}).get("phone") else [],
        address=(farmer or {}).get("phone"), lang=(farmer or {}).get("lang", "mr"))
    audit("application.record", entity="application", entity_id=str(app_id),
          user_id=user["id"], detail={"kind": data.kind, "product": data.product})

    from .. import prescribe
    log = db.rows("SELECT * FROM applications WHERE plot_id = :p AND kind='chemical'"
                  " ORDER BY applied_on", {"p": plot["id"]})
    return {
        "application_id": app_id, "followup_id": fu_id,
        "followup_due": due.isoformat(),
        "phi": prescribe.phi_status(log, plot["crop"], _today()),
        "harvest_gate": clears.isoformat() if phi else None,
        "note": ("A re-scan is scheduled for five days from now. If the problem is worse after "
                 "treatment, that is the strongest available signal the diagnosis was wrong, and "
                 "the case escalates to an extension officer automatically."),
    }


@router.get("/ledger", summary="Sprays avoided, against a stated counterfactual",
            description=("Counts threshold checks that came back below threshold against the "
                          "7-day prophylactic calendar most growers actually run. This is "
                          "deliberately the WEAKEST available claim — a stronger one needs a "
                          "season of paired untreated plots, which has not been run."))
def ledger(plot_id: str | None = Query(None),
           user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    rt = get_runtime()
    if plot_id:
        visible_plot(db, user, plot_id)
        return rt.decisions.ledger(plot_id)
    if user["role"] == "farmer":
        farmer = farmer_of(db, user)
        plots = db.rows("SELECT id FROM plots WHERE farmer_id = :f", {"f": farmer["id"]})
        merged = {"checks": [], "summary": None}
        for p in plots:
            part = rt.decisions.ledger(p["id"])
            merged["checks"].extend(part["checks"])
        from .. import etl
        merged["summary"] = etl.ledger(merged["checks"])
        return merged
    raise bad_request("plot_required", "Specify a plot_id.")
