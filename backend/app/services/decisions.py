"""
PRAHARI · the decision service
════════════════════════════════════════════════════════════════════════════
ACT — and the far more common answer, DON'T ACT YET.

"Should I spray?" is the question this whole platform exists to answer well, so
it is a first-class object with a row in the database:

    {"decision": "do_not_spray",
     "reason_code": "etl_not_crossed",
     "reason": "...",
     "evidence": [...],
     "recheck_after_hours": 48,
     "recheck_on": "2026-08-29"}

Six reasons a decision can come back as do_not_spray:

    etl_not_crossed          the count is below the economic threshold
    low_confidence           the diagnosis abstained or is below the floor
    non_chemical_sufficient  approaching threshold, cultural/biological holds it
    life_stage_unsuitable    the pest is not at a stage a spray can reach
    expert_review_required   a human needs to look first
    no_verified_chemical     no verified label claim exists for this combination

And the chemical rung of the IPM ladder can only open when the threshold gate
authorised it AND a VERIFIED label claim exists. Both, not either.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from .. import chemicals, etl, prescribe, reference
from ..clock import now_iso
from ..clock import today as _today
from ..db import Database, dumps


class DecisionService:
    def __init__(self, db: Database):
        self.db = db

    # ── the threshold gate ─────────────────────────────────────────────────
    def check_threshold(self, plot: dict[str, Any], pest: str, count: float,
                        stage: dict[str, Any], *, trap_obs_id: str | None = None,
                        damaging_stage: bool | None = None) -> dict[str, Any]:
        row = reference.threshold_for(pest, plot["crop"])
        if not row:
            return {"error": "no_threshold",
                    "message": (f"PRAHARI has no published economic threshold for "
                                f"{reference.problem_name(pest)} on {plot['crop']}, so it cannot "
                                f"judge whether an intervention is justified. Ask your Krishi "
                                f"Sahayak.")}
        d = etl.decide(row, count, stage.get("stage"), reference.CROPS[plot["crop"]],
                       plot["area_acre"])
        day = _today()
        check_id = self.db.insert_returning_id(
            "INSERT INTO threshold_checks (plot_id, crop, crop_stage, pest, count, etl_base,"
            " etl_effective, band, chemical_authorised, acted, saving, trap_obs_id, checked_on,"
            " checked_at, demo)"
            " VALUES (:p,:c,:cs,:pest,:n,:eb,:ee,:band,:auth,0,:sav,:trap,:on,:at,0)",
            {"p": plot["id"], "c": plot["crop"], "cs": stage.get("stage"), "pest": pest,
             "n": count, "eb": d["etl_base"], "ee": d["etl_effective"], "band": d["band"],
             "auth": 1 if d["chemical_authorised"] else 0,
             "sav": d.get("saving_if_not_sprayed"), "trap": trap_obs_id,
             "on": day.isoformat(), "at": now_iso()})
        d["check_id"] = check_id
        d["etl_provenance"] = {
            "source": row.get("source"), "status": row.get("status", "draft"),
            "alt": row.get("alt"),
            "note": ("The threshold value comes from the published advisory named above. "
                     "Stage scaling is applied because a count means different things at "
                     "different crop stages."),
        }
        hist = self.db.rows(
            "SELECT count, checked_on FROM threshold_checks WHERE plot_id = :p AND pest = :pest"
            " ORDER BY checked_at DESC, id DESC LIMIT 5", {"p": plot["id"], "pest": pest})
        d["trend"] = [{"count": h["count"], "on": str(h["checked_on"])} for h in reversed(hist)]
        if len(hist) >= 2:
            delta = hist[0]["count"] - hist[1]["count"]
            d["trend_direction"] = "up" if delta > 0 else "down" if delta < 0 else "flat"
            d["trend_say"] = (f"Up from {hist[1]['count']:g} at the last count."
                              if delta > 0 else
                              f"Down from {hist[1]['count']:g} at the last count."
                              if delta < 0 else "Unchanged since the last count.")
            if len(hist) >= 3 and hist[0]["count"] > hist[1]["count"] > hist[2]["count"]:
                d["trend_alert"] = ("Three consecutive rises. Count again tomorrow rather than in "
                                    "five days — this is how a population gets away from you.")
        d["damaging_stage"] = damaging_stage
        return d

    # ── the decision object ────────────────────────────────────────────────
    def spray_decision(self, plot: dict[str, Any], target: str, *,
                       threshold: dict[str, Any] | None = None,
                       diagnosis: dict[str, Any] | None = None,
                       damaging_stage: bool | None = None,
                       verified_available: bool | None = None,
                       persist: bool = True) -> dict[str, Any]:
        evidence: list[dict[str, Any]] = []
        day = _today()

        if verified_available is None:
            verified_available = bool(chemicals.verified_claims(self.db, plot["crop"], target))

        decision = reason_code = None
        reason = reason_mr = ""
        recheck_hours = 120

        # 1 · a diagnosis that abstained cannot authorise anything
        if diagnosis is not None and diagnosis.get("abstained"):
            decision, reason_code = "do_not_spray", "low_confidence"
            reason = ("PRAHARI is not confident enough about what this is to recommend a "
                      "treatment for it. Treating the wrong problem costs money and does not "
                      "stop the right one.")
            reason_mr = ("हे नेमके काय आहे याबद्दल प्रहरी पुरेसा खात्रीशीर नाही, त्यामुळे उपचार सुचवला जात नाही.")
            recheck_hours = 24
            evidence.append({"kind": "diagnosis", "detail": diagnosis.get("abstain_reason"),
                             "explain": diagnosis.get("explain")})

        # 2 · the threshold gate
        elif threshold is not None and not threshold.get("error"):
            evidence.append({
                "kind": "threshold",
                "detail": (f"{threshold['count']:g} {threshold['unit']} against an effective "
                           f"threshold of {threshold['etl_effective']:g} "
                           f"({threshold['percent_of_threshold']}%)"),
                "source": (threshold.get("etl_provenance") or {}).get("source"),
            })
            if not threshold["chemical_authorised"]:
                if threshold["band"] == "act-nonchemical":
                    decision, reason_code = "non_chemical", "non_chemical_sufficient"
                    reason = threshold["why"]
                    reason_mr = threshold["why_mr"]
                    recheck_hours = 72
                else:
                    decision, reason_code = "do_not_spray", "etl_not_crossed"
                    reason = threshold["why"]
                    reason_mr = threshold["why_mr"]
                    recheck_hours = 120
            elif damaging_stage is False:
                decision, reason_code = "do_not_spray", "life_stage_unsuitable"
                reason = ("The count is over the threshold, but this pest is not currently at a "
                          "life stage a spray can reach. Spraying now spends the product and the "
                          "money on insects it will not touch — and kills the natural enemies "
                          "that are still working.")
                reason_mr = ("संख्या मर्यादेपेक्षा जास्त आहे, पण कीड सध्या फवारणी पोहोचू शकेल अशा "
                             "अवस्थेत नाही. आत्ता फवारणी वाया जाईल.")
                recheck_hours = 48
                evidence.append({"kind": "phenology",
                                 "detail": "Growing-degree-day model says the reachable stage has not arrived."})
            elif not verified_available:
                decision, reason_code = "expert_review", "no_verified_chemical"
                reason = chemicals.UNAVAILABLE_MESSAGE
                reason_mr = chemicals.UNAVAILABLE_MESSAGE_MR
                recheck_hours = 24
                evidence.append({"kind": "label_claim",
                                 "detail": ("No label claim for this crop and target has been "
                                            "verified against the CIB&RC list on this instance.")})
            else:
                decision, reason_code = "intervene", "etl_crossed"
                reason = threshold["why"]
                reason_mr = threshold["why_mr"]
                recheck_hours = 120

        # 3 · no count at all
        else:
            decision, reason_code = "scout_again", "no_count"
            reason = ("Nothing has been counted in this field yet. A diagnosis says what is there; "
                      "only a count says whether it is worth acting on. Count the trap or the "
                      "plants first.")
            reason_mr = ("या शेतात अजून मोजणी झालेली नाही. निदान काय आहे ते सांगते; "
                         "कृती करावी का हे फक्त मोजणी सांगते.")
            recheck_hours = 24

        did = "DEC-" + uuid.uuid4().hex[:10].upper()
        recheck_on = (day + dt.timedelta(hours=recheck_hours)).isoformat() \
            if recheck_hours else None
        if persist:
            self.db.execute(
                "INSERT INTO decisions (id, plot_id, target, decision, reason_code, reason,"
                " reason_mr, evidence, recheck_after_hours, recheck_on, threshold_check_id,"
                " diagnosis_id, created_at)"
                " VALUES (:id,:p,:t,:d,:rc,:r,:rmr,:ev,:rh,:ro,:tc,:dx,:now)",
                {"id": did, "p": plot["id"], "t": target, "d": decision, "rc": reason_code,
                 "r": reason, "rmr": reason_mr, "ev": dumps(evidence), "rh": recheck_hours,
                 "ro": recheck_on, "tc": (threshold or {}).get("check_id"),
                 "dx": (diagnosis or {}).get("id"), "now": now_iso()})

        headline = _HEADLINE[decision]
        return {
            "id": did, "decision": decision, "reason_code": reason_code,
            "reason": reason, "reason_mr": reason_mr, "evidence": evidence,
            "recheck_after_hours": recheck_hours, "recheck_on": recheck_on,
            "target": target, "target_name": reference.problem_name(target),
            "target_name_mr": reference.problem_name(target, "mr"),
            **headline,
            "verified_chemical_available": verified_available,
        }

    # ── the disease path ───────────────────────────────────────────────────
    def disease_decision(self, plot: dict[str, Any], target: str, *,
                         assessment: dict[str, Any] | None = None,
                         board_row: dict[str, Any] | None = None,
                         diagnosis: dict[str, Any] | None = None,
                         verified_available: bool | None = None,
                         persist: bool = True) -> dict[str, Any]:
        """The same gate, for a problem that has no count and no economic threshold.

        A pest is decided by counting it against an ICAR threshold. A disease has
        neither a trap nor a threshold row, and the audit found what that meant in
        practice: asking this system about late blight returned "nothing counted
        yet, record a count" — a count that does not exist for a disease. A farmer
        arriving from a disease diagnosis could go no further.

        Two measured things decide it instead, and **no third one is invented**:

          · INCIDENCE — the farmer walks the field, inspects a fixed number of
            plants and records how many show the symptom. Affected ÷ inspected is
            arithmetic they can check.
          · THE PUBLISHED INFECTION MODEL — Hutton, TOMCAST, Gubler-Thomas, run
            on this field's own weather. It already produces `fired` for the risk
            board; nothing new is computed here.

        What is deliberately NOT done: no percentage of incidence is treated as an
        action threshold. There is no such published figure in this system's
        reference tables, and putting one in would be inventing the single number
        the whole decision turns on. So incidence is reported as measured, the
        model is reported as it fired, and the decision is stated in terms of
        both — never as "spray above N%".
        """
        evidence: list[dict[str, Any]] = []
        day = _today()
        if verified_available is None:
            verified_available = bool(chemicals.verified_claims(self.db, plot["crop"], target))

        fired = bool((board_row or {}).get("fired"))
        model_name = (board_row or {}).get("model") or (board_row or {}).get("provenance", {}).get("model")
        level = (board_row or {}).get("level")
        unforecast = level == "unforecast"

        decision = reason_code = None
        reason = reason_mr = ""
        recheck_hours = 72

        if diagnosis is not None and diagnosis.get("abstained"):
            decision, reason_code = "do_not_spray", "low_confidence"
            reason = ("PRAHARI is not confident enough about what this is to recommend a "
                      "treatment for it. Treating the wrong disease costs money and does not "
                      "stop the right one.")
            reason_mr = "हे नेमके काय आहे याबद्दल प्रहरी खात्रीशीर नाही, त्यामुळे उपचार सुचवला जात नाही."
            recheck_hours = 24
            evidence.append({"kind": "diagnosis", "detail": diagnosis.get("abstain_reason"),
                             "explain": diagnosis.get("explain")})

        elif assessment is None:
            decision, reason_code = "scout_again", "no_observation"
            reason = ("Nothing has been assessed in this field yet. A diagnosis says what may "
                      "be there; walking the field and recording how many plants actually show "
                      "it is what says whether to act. Inspect a set number of plants and "
                      "record how many are affected.")
            reason_mr = ("या शेतात अजून पाहणी झालेली नाही. निदान काय असू शकते ते सांगते; "
                         "किती झाडांवर प्रत्यक्ष लक्षणे आहेत हे पाहणीच सांगते.")
            recheck_hours = 24

        else:
            inc = assessment["incidence_pct"]
            evidence.append({
                "kind": "field_assessment",
                "detail": (f"{assessment['plants_affected']} of "
                           f"{assessment['plants_inspected']} plants showing symptoms "
                           f"({inc}%), assessed {assessment['assessed_on']}"),
            })
            if board_row and not unforecast:
                evidence.append({
                    "kind": "infection_model",
                    "detail": ((board_row.get("detail") or "")
                               or f"{model_name}: {'conditions met' if fired else 'conditions not met'}"),
                    "source": (board_row.get("provenance") or {}).get("source"),
                })
            elif unforecast:
                evidence.append({
                    "kind": "infection_model",
                    "detail": ("No implementable published infection model for this disease on "
                               "this crop, so weather is not part of this decision."),
                })

            if inc == 0 and not fired:
                decision, reason_code = "do_not_spray", "not_present_not_conducive"
                reason = ("No plant you inspected is showing it, and the weather has not met the "
                          "published infection criteria. Keep walking the field on the same "
                          "interval — this is the cheapest moment in the whole season.")
                reason_mr = ("तुम्ही पाहिलेल्या एकाही झाडावर लक्षणे नाहीत आणि हवामानही अनुकूल नाही. "
                             "तपासणी चालू ठेवा.")
                recheck_hours = 96
            elif inc == 0 and fired:
                decision, reason_code = "non_chemical", "conducive_not_yet_present"
                reason = ("Nothing is showing yet, but the weather has met the published "
                          "infection criteria — this is the prevention window. Sanitation and "
                          "airflow now are worth more than any spray later.")
                reason_mr = ("अजून लक्षणे दिसत नाहीत, पण हवामान संसर्गासाठी अनुकूल झाले आहे — "
                             "हीच प्रतिबंधाची वेळ आहे.")
                recheck_hours = 48
            elif not fired:
                decision, reason_code = "non_chemical", "present_not_conducive"
                reason = (f"{inc}% of the plants you inspected are showing it, but the weather "
                          "has not met the published infection criteria, so it is not being "
                          "driven right now. Remove affected material and re-assess.")
                reason_mr = (f"तपासलेल्या {inc}% झाडांवर लक्षणे आहेत, पण हवामान सध्या अनुकूल नाही. "
                             "बाधित भाग काढून टाका आणि पुन्हा पाहणी करा.")
                recheck_hours = 72
            elif not verified_available:
                decision, reason_code = "expert_review", "no_verified_chemical"
                reason = chemicals.UNAVAILABLE_MESSAGE
                reason_mr = chemicals.UNAVAILABLE_MESSAGE_MR
                recheck_hours = 24
                evidence.append({"kind": "label_claim",
                                 "detail": ("No label claim for this crop and disease has been "
                                            "verified against the CIB&RC list on this instance.")})
            else:
                decision, reason_code = "intervene", "present_and_conducive"
                reason = (f"{inc}% of the plants you inspected are showing it and the weather has "
                          "met the published infection criteria. Both are true at once, which is "
                          "when a foliar disease runs. Work the ladder from the top; the chemical "
                          "rung is open because a verified label claim exists.")
                reason_mr = ("तपासलेल्या झाडांवर लक्षणे आहेत आणि हवामानही अनुकूल आहे. "
                             "उपाययोजना वरपासून सुरू करा.")
                recheck_hours = 48

        did = "DEC-" + uuid.uuid4().hex[:10].upper()
        recheck_on = (day + dt.timedelta(hours=recheck_hours)).isoformat() if recheck_hours else None
        if persist:
            self.db.execute(
                "INSERT INTO decisions (id, plot_id, target, decision, reason_code, reason,"
                " reason_mr, evidence, recheck_after_hours, recheck_on, diagnosis_id, created_at)"
                " VALUES (:id,:p,:t,:d,:rc,:r,:rmr,:ev,:rh,:ro,:dx,:now)",
                {"id": did, "p": plot["id"], "t": target, "d": decision, "rc": reason_code,
                 "r": reason, "rmr": reason_mr, "ev": dumps(evidence), "rh": recheck_hours,
                 "ro": recheck_on, "dx": (diagnosis or {}).get("id"), "now": now_iso()})

        headline = _HEADLINE[decision]
        if decision == "scout_again":
            # The pest wording says COUNT FIRST. Nothing is counted for a disease.
            headline = {**headline, "answer": "ASSESS THE FIELD FIRST",
                        "answer_mr": "आधी शेताची पाहणी करा"}
        return {
            "id": did, "decision": decision, "reason_code": reason_code,
            "reason": reason, "reason_mr": reason_mr, "evidence": evidence,
            "recheck_after_hours": recheck_hours, "recheck_on": recheck_on,
            "target": target, "target_name": reference.problem_name(target),
            "target_name_mr": reference.problem_name(target, "mr"),
            "target_kind": "disease",
            **headline,
            "verified_chemical_available": verified_available,
        }

    # ── the IPM ladder + screened chemical options ─────────────────────────
    def prescription(self, plot: dict[str, Any], target: str, stage: dict[str, Any],
                     *, chemical_authorised: bool,
                     scout: dict[str, Any] | None = None) -> dict[str, Any]:
        """Chemical options come ONLY from verified label claims. A draft row is
        never rendered as an option, and its product name is never printed —
        naming it is half of recommending it."""
        availability = chemicals.availability(self.db, plot["crop"], target)
        verified = chemicals.verified_claims(self.db, plot["crop"], target)
        claims = [chemicals.to_prescribe_shape(r) for r in verified]
        restricted = [{"product": r["pattern"], "reason": r["reason"]}
                      for r in chemicals.restricted_products(self.db)]
        log = self.db.rows(
            "SELECT * FROM applications WHERE plot_id = :p AND kind = 'chemical'"
            " ORDER BY applied_on", {"p": plot["id"]})

        screened: dict[str, Any] = {"options": [], "allowed_count": 0, "blocked_count": 0,
                                    "recommended": None}
        if chemical_authorised and claims:
            screened = prescribe.screen(
                claims, restricted, log, plot["crop"], target,
                area_acre=plot["area_acre"], tank_litres=plot.get("tank_litres") or 15,
                days_to_harvest=stage.get("days_to_harvest"),
                flowering=(stage.get("stage") in ("flowering", "berry")),
                strict=False)          # every row reaching here is already verified
            screened.pop("verification_banner", None)
            for opt in screened["options"]:
                claim = next((c for c in claims if c["product"] == opt["product"]), {})
                opt["claim_id"] = claim.get("id")
                opt["verified"] = True
                opt["provenance"] = {"source": claim.get("source"),
                                     "source_url": claim.get("source_url"),
                                     "verified_by": claim.get("verified_by"),
                                     "verified_at": claim.get("verified_at")}
        ladder = prescribe.ladder(
            reference.IPM, target,
            bool(chemical_authorised and screened.get("recommended")),
            screened.get("recommended"), scout=scout)
        if chemical_authorised and not claims:
            for step in ladder:
                if step["key"] == "chemical":
                    step["title"] = "Chemical — no verified option available"
                    step["title_mr"] = "रासायनिक — तपासलेली शिफारस उपलब्ध नाही"
                    step["withheld"] = True
                    step["items"] = [{"text": chemicals.UNAVAILABLE_MESSAGE}]
        return {
            "ipm_ladder": ladder,
            "chemical": screened,
            "chemical_availability": availability,
            "phi": prescribe.phi_status(log, plot["crop"], _today()),
            "crop_stage": stage,
            "ladder_principle": (
                "Monitoring, then cultural, then mechanical, then biological, then chemical. "
                "A rung opens only when the one above it cannot hold the population — and the "
                "chemical rung additionally needs a verified label claim."),
        }

    # ── the ledger of sprays avoided ───────────────────────────────────────
    def ledger(self, plot_id: str | None = None) -> dict[str, Any]:
        sql = ("SELECT pest, count, band, acted, checked_on, checked_at FROM threshold_checks")
        params: dict[str, Any] = {}
        if plot_id:
            sql += " WHERE plot_id = :p"
            params["p"] = plot_id
        checks = self.db.rows(sql + " ORDER BY checked_at", params)
        day = _today()
        for c in checks:
            try:
                c["days_ago"] = (day - dt.date.fromisoformat(str(c["checked_on"])[:10])).days
            except Exception:
                c["days_ago"] = 0
        return {"checks": checks, "summary": etl.ledger(checks)}


# The five answers a decision can wear, shared by the pest and disease paths so
# the two cannot drift into saying the same thing in different words.
_HEADLINE = {
    "do_not_spray": {"answer": "NO — NOT YET", "answer_mr": "नाही — अजून नाही",
                     "tone": "green", "icon": "🟢"},
    "non_chemical": {"answer": "ACT, BUT NOT WITH CHEMISTRY",
                     "answer_mr": "उपाय करा — पण रासायनिक नको",
                     "tone": "amber", "icon": "🟡"},
    "intervene": {"answer": "ACTION REQUIRED", "answer_mr": "कृती आवश्यक",
                  "tone": "red", "icon": "🔴"},
    "expert_review": {"answer": "SEND TO AN EXPERT FIRST",
                      "answer_mr": "आधी तज्ज्ञांकडे पाठवा", "tone": "amber", "icon": "🟡"},
    "scout_again": {"answer": "COUNT FIRST", "answer_mr": "आधी मोजणी करा",
                    "tone": "grey", "icon": "⚪"},
}


def chemical_rung_open(decision: dict[str, Any]) -> bool:
    """The chemical rung of the IPM ladder opens when the DECISION says to
    intervene — or when it would, and the only thing stopping it is that no
    verified label claim exists. Any other reason (below threshold, wrong life
    stage, uncertain diagnosis) keeps it shut, and the ladder says which."""
    return decision["decision"] == "intervene" or decision["reason_code"] == "no_verified_chemical"
