"""
PRAHARI · /api/followups — MONITOR, the loop nobody closes.

The problem statement asks for follow-up monitoring explicitly. It is also the
only free source of ground truth this system has: a re-scan that is worse after
treatment is the strongest available evidence that the diagnosis was wrong.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile

from .. import storage as storage_mod
from ..clock import now_iso
from ..clock import today as _today
from ..config import get_settings
from ..db import Database, bit, dumps, loads
from ..deps import current_user, db_dep, farmer_of, owned_plot, visible_plot
from ..errors import conflict, not_found
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import FollowupOutcomeIn

router = APIRouter(prefix="/api/followups", tags=["follow-up"])


@router.get("", summary="Follow-ups that are due")
def list_followups(plot_id: str | None = Query(None),
                   user: dict[str, Any] = Depends(current_user),
                   db: Database = Depends(db_dep)):
    if plot_id:
        visible_plot(db, user, plot_id)
        rows = db.rows(
            "SELECT f.*, p.crop, p.name AS plot_name FROM followups f JOIN plots p ON p.id=f.plot_id"
            " WHERE f.plot_id = :p AND f.done_observation IS NULL AND f.outcome IS NULL"
            " ORDER BY f.due_on",
            {"p": plot_id})
    elif user["role"] == "farmer":
        farmer = farmer_of(db, user)
        rows = db.rows(
            "SELECT f.*, p.crop, p.name AS plot_name FROM followups f JOIN plots p ON p.id=f.plot_id"
            " WHERE p.farmer_id = :f AND f.done_observation IS NULL AND f.outcome IS NULL"
            " ORDER BY f.due_on",
            {"f": farmer["id"]})
    else:
        from ..deps import officer_talukas
        scopes = officer_talukas(db, user)
        if not scopes:
            return {"followups": []}
        ph = ",".join(f":t{i}" for i in range(len(scopes)))
        rows = db.rows(
            f"SELECT f.*, p.crop, p.name AS plot_name FROM followups f JOIN plots p ON p.id=f.plot_id"
            f" WHERE p.taluka IN ({ph}) AND f.done_observation IS NULL AND f.outcome IS NULL"
            f" ORDER BY f.due_on",
            {f"t{i}": t for i, t in enumerate(scopes)})
    day = _today()
    import datetime as dt
    for r in rows:
        due = dt.date.fromisoformat(str(r["due_on"])[:10])
        r["days_until"] = (due - day).days
        r["overdue"] = r["days_until"] < 0
    return {
        "followups": rows,
        "note": ("Follow-up is the loop nobody closes. It is what turns a diagnosis into an "
                 "outcome, and it is the only source of ground truth PRAHARI gets for free."),
    }


@router.post("/{followup_id}/outcome",
             summary="Close a follow-up by reporting what happened",
             description=(
                 "The path for a farmer who cannot retake a comparable photograph — the leaf "
                 "has dropped, the crop is harvested, the light is gone.\n\n"
                 "This is recorded as SELF-REPORTED and is marked as such everywhere it is "
                 "read. A rescan produces a measured comparison of two photographs; this "
                 "produces a farmer's own account. Both close the loop, and PRAHARI never "
                 "presents the second as the first — an outcome nobody measured must not be "
                 "counted as evidence that a treatment worked.\n\n"
                 "Errors: 404 followup_not_found · 409 followup_already_closed"))
def report_outcome(followup_id: int, data: FollowupOutcomeIn,
                   user: dict[str, Any] = Depends(current_user),
                   db: Database = Depends(db_dep)):
    fu = db.one("SELECT * FROM followups WHERE id = :i", {"i": followup_id})
    if not fu:
        raise not_found("followup", str(followup_id))
    owned_plot(db, user, fu["plot_id"])
    if fu.get("done_observation") or fu.get("outcome"):
        raise conflict("followup_already_closed",
                       "This follow-up has already been closed.",
                       "ही पुनर्तपासणी आधीच पूर्ण झाली आहे.")

    day = _today().isoformat()
    db.execute(
        "UPDATE followups SET done_on = :d, outcome = :out, comparison = :cmp WHERE id = :i",
        {"d": day, "out": data.outcome, "i": followup_id,
         "cmp": dumps({"method": "self_reported", "measured": False,
                       "note": data.note, "reported_on": day})})

    # A worsening the farmer reports is still a reason to escalate, even though
    # nothing was measured — the person standing in the field saw something.
    escalated = False
    if data.outcome == "worse":
        db.execute("UPDATE followups SET escalated = :b WHERE id = :i",
                   {"b": bit(True), "i": followup_id})
        escalated = True

    audit("followup.outcome", entity="followup", entity_id=str(followup_id),
          user_id=user["id"], role=user["role"],
          detail={"outcome": data.outcome, "measured": False})

    return {
        "followup_id": followup_id,
        "outcome": data.outcome,
        "measured": False,
        "escalated": escalated,
        "note": ("Recorded as the farmer's own account. It closes the follow-up and is shown "
                 "in the field history, but it is not counted as a measured outcome — only a "
                 "rescan, which compares two photographs, produces one of those."),
        "note_mr": ("शेतकऱ्याने सांगितलेली नोंद. पुनर्तपासणी पूर्ण झाली, पण हे मोजलेले "
                    "निरीक्षण नाही — त्यासाठी नवीन फोटो लागतो."),
    }


@router.post("/{followup_id}/rescan", status_code=201,
             summary="Re-scan a field to close a follow-up",
             description=(
                 "Compares the new photograph with the original scan and reports the DIRECTION of "
                 "change only. These are two hand-held photographs of different leaves in "
                 "different light; direction survives that, a percentage does not.\n\n"
                 "A re-scan that comes back worse escalates the case to an extension officer "
                 "rather than offering a second spray."))
async def rescan(followup_id: int, image: UploadFile = File(...),
                 user: dict[str, Any] = Depends(current_user),
                 db: Database = Depends(db_dep)):
    fu = db.one("SELECT * FROM followups WHERE id = :id", {"id": followup_id})
    if not fu:
        raise not_found("follow-up", str(followup_id))
    plot = owned_plot(db, user, fu["plot_id"])
    rt = get_runtime()
    s = get_settings()

    raw = await image.read()
    _ct, width, height, _f = storage_mod.validate_image(raw, s.max_upload_bytes)
    clean = storage_mod.sanitize(raw)
    key = storage_mod.make_key(f"observations/{plot['id']}")
    rt.storage.put(key, clean, "image/jpeg")
    thumb_key = key.replace(".jpg", "_thumb.jpg")
    rt.storage.put(thumb_key, storage_mod.thumbnail(clean), "image/jpeg")

    stage = rt.risk.crop_stage(plot)
    oid = "O-" + uuid.uuid4().hex[:10].upper()
    stamp = now_iso()
    db.execute(
        "INSERT INTO observations (id, plot_id, farmer_id, kind, taluka, crop, crop_stage,"
        " observed_at, source, status, created_at)"
        " VALUES (:id,:p,:f,'followup',:tk,:crop,:cs,:at,'app','open',:now)",
        {"id": oid, "p": plot["id"], "f": plot["farmer_id"], "tk": plot["taluka"],
         "crop": plot["crop"], "cs": stage.get("stage"), "at": stamp, "now": stamp})
    features = rt.vision.analyse(clean)
    db.execute(
        "INSERT INTO observation_images (id, observation_id, role, storage_key, thumb_key,"
        " content_type, bytes, width, height, sha256, quality, features, created_at)"
        " VALUES (:id,:o,'affected',:k,:tk,'image/jpeg',:b,:w,:h,:sha,:q,:f,:now)",
        {"id": "I-" + uuid.uuid4().hex[:10].upper(), "o": oid, "k": key, "tk": thumb_key,
         "b": len(clean), "w": width, "h": height, "sha": storage_mod.sha256(clean),
         "q": dumps(features["quality"]),
         "f": dumps({k: v for k, v in features.items() if k != "quality"}), "now": stamp})

    if not features["quality"]["ok"]:
        return {
            "comparison": None,
            "outcome": "unmeasurable",
            "quality": features["quality"],
            "message": ("The re-scan photograph failed the quality gate, so it cannot be compared "
                        "with the first one. Take it again — same leaf position, same light if you "
                        "can. Nothing has been recorded as better or worse."),
            "message_mr": ("पुन्हा काढलेला फोटो तपासणीत नापास झाला, त्यामुळे तुलना करता येत नाही. "
                           "पुन्हा फोटो काढा."),
            "observation_id": oid,
        }

    origin = _origin_features(db, fu)
    if not origin:
        db.execute("UPDATE followups SET done_observation = :o, done_on = :d, outcome = 'unmeasurable'"
                   " WHERE id = :id", {"o": oid, "d": _today().isoformat(), "id": followup_id})
        return {"comparison": None, "outcome": "unmeasurable", "observation_id": oid,
                "message": ("There is no measurable first scan to compare this against — the "
                            "original observation was a count or a trap photograph, not a leaf "
                            "scan. PRAHARI will not invent a before-and-after.")}

    cmp = rt.diagnosis.compare(origin, {k: v for k, v in features.items() if k != "quality"})
    db.execute(
        "UPDATE followups SET done_observation = :o, done_on = :d, outcome = :out,"
        " comparison = :cmp, escalated = :esc WHERE id = :id",
        {"o": oid, "d": _today().isoformat(), "out": cmp["outcome"],
         "cmp": dumps(cmp), "esc": bit(cmp["escalate"]), "id": followup_id})
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
        " VALUES (:p,:at,'followup',:sev,:t,:d,:ref,:now)",
        {"p": plot["id"], "at": _today().isoformat(),
         "sev": {"better": "good", "same": "watch", "worse": "high"}[cmp["outcome"]],
         "t": f"Follow-up scan — {cmp['label']}", "d": cmp["say"], "ref": oid,
         "now": now_iso()})

    escalation = None
    if cmp["escalate"]:
        escalation = _escalate(db, rt, plot, oid, fu)
    farmer = db.one("SELECT * FROM farmers WHERE id = :f", {"f": plot["farmer_id"]})
    rt.notify.push(
        user_id=(farmer or {}).get("user_id"), plot_id=plot["id"], kind="followup",
        severity={"better": "low", "same": "watch", "worse": "high"}[cmp["outcome"]],
        title=f"Follow-up result — {cmp['label']}", body=cmp["say"],
        title_mr=f"पुन्हा तपासणीचा निकाल — {cmp['label_mr']}", body_mr=cmp["say"],
        channels=["sms"] if (farmer or {}).get("phone") else [],
        address=(farmer or {}).get("phone"), lang=(farmer or {}).get("lang", "mr"))
    audit("followup.rescan", entity="followup", entity_id=str(followup_id),
          user_id=user["id"], detail={"outcome": cmp["outcome"]})
    return {"comparison": cmp, "outcome": cmp["outcome"], "observation_id": oid,
            "escalation": escalation, "quality": features["quality"]}


def _origin_features(db: Database, fu: dict[str, Any]) -> dict[str, Any] | None:
    """The most recent leaf scan on this plot before the application, which is
    what 'before' actually means."""
    app = db.one("SELECT * FROM applications WHERE id = :id", {"id": fu["application_id"]}) \
        if fu.get("application_id") else None
    before = str(app["applied_on"]) if app else None
    sql = ("SELECT i.features FROM observation_images i JOIN observations o ON o.id = i.observation_id"
           " WHERE o.plot_id = :p AND o.kind = 'leaf'")
    params: dict[str, Any] = {"p": fu["plot_id"]}
    if before:
        sql += " AND substr(o.observed_at,1,10) <= :b"
        params["b"] = before
    row = db.one(sql + " ORDER BY o.observed_at DESC LIMIT 1", params)
    if not row:
        return None
    feats = loads(row["features"], {})
    return feats or None


def _escalate(db: Database, rt, plot: dict[str, Any], oid: str,
              fu: dict[str, Any]) -> dict[str, Any]:
    year = _today().year
    n = db.scalar("SELECT COUNT(*) FROM expert_cases") or 0
    cid = f"PRH-{year}-{n + 1:04d}"
    stamp = now_iso()
    db.execute(
        "INSERT INTO expert_cases (id, observation_id, plot_id, farmer_id, taluka, crop, reason,"
        " urgency, status, submitted_at, created_at)"
        " VALUES (:id,:o,:p,:f,:tk,:crop,:r,'urgent','submitted',:now,:now)",
        {"id": cid, "o": oid, "p": plot["id"], "f": plot["farmer_id"], "tk": plot["taluka"],
         "crop": plot["crop"],
         "r": ("The field is worse after treatment. Either the diagnosis was wrong or the "
               "treatment is not reaching the pathogen — escalated automatically rather than "
               "offering a second spray."),
         "now": stamp})
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
        " VALUES (:p,:at,'expert','high',:t,:d,:ref,:now)",
        {"p": plot["id"], "at": _today().isoformat(),
         "t": f"Escalated to an expert — case {cid}",
         "d": "Worse after treatment. A second spray is not offered.",
         "ref": cid, "now": stamp})
    return {"case_id": cid, "urgency": "urgent",
            "why": ("PRAHARI escalates rather than recommending a second application. A treatment "
                    "that made things worse is evidence about the diagnosis, not a dosing problem.")}
