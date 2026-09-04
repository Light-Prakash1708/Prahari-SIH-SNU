"""PRAHARI · notifications, offline sync, reference data, admin, health, demo."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from .. import advisory, chemicals, reference
from ..clock import now_iso
from ..clock import today as _today
from ..config import get_settings
from ..db import Database, loads
from ..deps import (
    current_user,
    db_dep,
    owned_plot,
    require_roles,
    visible_plot,
)
from ..errors import bad_request, forbidden, not_found
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import ClaimStatusIn, RegisterIn, SyncIn, VerifyClaimIn

# ── notifications ───────────────────────────────────────────────────────────
notifications = APIRouter(prefix="/api/notifications", tags=["notifications"])


@notifications.get("", summary="Your notifications")
def list_notifications(plot_id: str | None = Query(None), limit: int = Query(40, le=200),
                       user: dict[str, Any] = Depends(current_user),
                       db: Database = Depends(db_dep)):
    sql = "SELECT * FROM notifications WHERE user_id = :u"
    params: dict[str, Any] = {"u": user["id"]}
    if plot_id:
        visible_plot(db, user, plot_id)
        sql += " AND plot_id = :p"
        params["p"] = plot_id
    rows = db.rows(sql + " ORDER BY at DESC, created_at DESC LIMIT :n", {**params, "n": limit})
    for r in rows:
        r["read"] = bool(r.get("read_at"))
        r["deliveries"] = db.rows(
            "SELECT channel, state, provider, error, updated_at FROM notification_deliveries"
            " WHERE notification_id = :n", {"n": r["id"]})
    unread = db.scalar("SELECT COUNT(*) FROM notifications WHERE user_id = :u AND read_at IS NULL",
                       {"u": user["id"]}) or 0
    return {"notifications": rows, "unread": unread,
            "delivery_note": ("'sent' means a gateway accepted the message. Only a provider "
                              "callback moves it to 'delivered' — PRAHARI never claims delivery "
                              "it has not been told about.")}


@notifications.post("/read", summary="Mark notifications read")
def mark_read(plot_id: str | None = Query(None),
              user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    sql = "UPDATE notifications SET read_at = :now WHERE user_id = :u AND read_at IS NULL"
    params: dict[str, Any] = {"now": now_iso(), "u": user["id"]}
    if plot_id:
        sql += " AND plot_id = :p"
        params["p"] = plot_id
    return {"marked": db.execute(sql, params)}


@notifications.post("/webhook/delivery", summary="Provider delivery callback",
                    description=("The only way a delivery becomes 'delivered'. Requires the "
                                  "provider's shared secret in X-Prahari-Signature."))
def delivery_webhook(request: Request, notification_id: str = Query(...),
                     channel: str = Query(...), provider_ref: str = Query(""),
                     db: Database = Depends(db_dep)):
    s = get_settings()
    secret = s.sms_api_key or s.jwt_secret
    if request.headers.get("x-prahari-signature") != secret:
        raise forbidden("this webhook")
    rt = get_runtime()
    n = rt.notify.mark_delivered(notification_id, channel, provider_ref)
    return {"updated": n}


# ── offline sync ────────────────────────────────────────────────────────────
sync = APIRouter(prefix="/api/sync", tags=["offline"])


@sync.post("", summary="Flush the offline queue",
           description=("Every item carries a client_ref. Re-sending an item that has already "
                          "been accepted returns its original result rather than creating a "
                          "second row, so a flaky connection cannot double-count a trap."))
def flush(data: SyncIn, user: dict[str, Any] = Depends(current_user),
          db: Database = Depends(db_dep)):
    rt = get_runtime()
    results = []
    for item in data.items:
        try:
            plot = owned_plot(db, user, item.plot_id)
        except Exception:
            results.append({"client_ref": item.client_ref, "state": "rejected",
                            "error": "forbidden",
                            "message": "That field does not belong to this account."})
            continue
        existing = db.one(
            "SELECT id FROM observations WHERE farmer_id = :f AND client_ref = :c",
            {"f": plot["farmer_id"], "c": item.client_ref})
        if existing:
            results.append({"client_ref": item.client_ref, "state": "duplicate",
                            "observation_id": existing["id"]})
            continue
        if item.kind == "threshold":
            stage = rt.risk.crop_stage(plot)
            pest = item.payload.get("pest")
            count = item.payload.get("count")
            if pest is None or count is None:
                results.append({"client_ref": item.client_ref, "state": "rejected",
                                "error": "bad_payload"})
                continue
            out = rt.decisions.check_threshold(plot, pest, float(count), stage)
            if out.get("error"):
                results.append({"client_ref": item.client_ref, "state": "rejected",
                                "error": out["error"], "message": out["message"]})
                continue
            _receipt(db, plot, item.client_ref, "count", item.captured_at)
            results.append({"client_ref": item.client_ref, "state": "accepted",
                            "kind": "threshold", "check_id": out["check_id"],
                            "band": out["band"]})
        elif item.kind == "note":
            oid = _receipt(db, plot, item.client_ref, "symptom", item.captured_at,
                           notes=item.payload.get("text"))
            results.append({"client_ref": item.client_ref, "state": "accepted",
                            "observation_id": oid})
        else:
            results.append({"client_ref": item.client_ref, "state": "rejected",
                            "error": "unsupported_kind",
                            "message": (f"'{item.kind}' cannot be synced without its image. "
                                        f"Upload it through /api/observations with the same "
                                        f"client_ref when the connection allows.")})
    audit("sync.flush", entity="sync", user_id=user["id"],
          detail={"items": len(data.items),
                  "accepted": sum(1 for r in results if r["state"] == "accepted")})
    return {"results": results, "server_time": now_iso()}


def _receipt(db: Database, plot: dict[str, Any], client_ref: str, kind: str,
             captured_at: dt.datetime, notes: str | None = None) -> str:
    oid = "O-" + uuid.uuid4().hex[:10].upper()
    db.execute(
        "INSERT INTO observations (id, plot_id, farmer_id, kind, taluka, crop, observed_at,"
        " notes, source, client_ref, status, created_at)"
        " VALUES (:id,:p,:f,:k,:tk,:crop,:at,:notes,'offline_sync',:ref,'open',:now)",
        {"id": oid, "p": plot["id"], "f": plot["farmer_id"], "k": kind,
         "tk": plot["taluka"], "crop": plot["crop"],
         "at": captured_at.replace(microsecond=0).isoformat(),
         "notes": notes, "ref": client_ref, "now": now_iso()})
    return oid


# ── reference and advisory ──────────────────────────────────────────────────
meta = APIRouter(prefix="/api", tags=["reference"])


@meta.get("/reference", summary="Everything the client needs to render",
          description="Crops, problems, thresholds, talukas — with the verification status of "
                      "every chemical reference row, so the UI can never present a draft as a "
                      "recommendation.")
def get_reference(db: Database = Depends(db_dep)):
    by_status = {r["status"]: r["n"] for r in db.rows(
        "SELECT status, COUNT(*) AS n FROM label_claims GROUP BY status")}
    return {
        "crops": reference.CROPS, "diseases": reference.DISEASES, "pests": reference.PESTS,
        "talukas": reference.TALUKAS, "thresholds": reference.THRESHOLDS,
        "stage_names_mr": reference.STAGE_MR,
        "model_provenance": reference.MODEL_PROVENANCE,
        "label_claims": {
            "by_status": by_status,
            "verified": by_status.get("verified", 0),
            "actionable_rule": (
                "Only a claim with status 'verified' — verified by a named person, on a recorded "
                "date, against a cited source — is ever returned as an actionable chemical "
                "recommendation. Draft rows are not shown and their product names are not printed."),
        },
        "restricted_count": db.scalar("SELECT COUNT(*) FROM restricted_products") or 0,
    }


@meta.get("/advisory", summary="An SMS and IVR advisory for a decision",
          description="Generated from stored decision rows and reviewed Marathi strings — never "
                      "machine-translated at request time, because a mistranslated dose is a "
                      "poisoning.")
def get_advisory(plot_id: str = Query(...), target: str = Query(...),
                 lang: str = Query("mr"),
                 user: dict[str, Any] = Depends(current_user),
                 db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rt = get_runtime()
    problem = reference.problem(target)
    if not problem:
        raise bad_request("unknown_target", f"'{target}' is not a problem PRAHARI knows.")
    check = db.one(
        "SELECT * FROM threshold_checks WHERE plot_id = :p AND pest = :t"
        " ORDER BY checked_at DESC, id DESC LIMIT 1", {"p": plot_id, "t": target})
    decision = None
    if check:
        from .. import etl
        row = reference.threshold_for(target, plot["crop"])
        if row:
            decision = etl.decide(row, check["count"], check["crop_stage"],
                                  reference.CROPS[plot["crop"]], plot["area_acre"])
    rec = None
    if decision and decision["chemical_authorised"]:
        stage = rt.risk.crop_stage(plot)
        pres = rt.decisions.prescription(plot, target, stage, chemical_authorised=True)
        rec = pres["chemical"].get("recommended")
    reason = decision["why"] if decision else problem.get("scout", "")
    out = advisory.build(lang, problem, decision, rec, reason)
    out["translation_policy"] = (
        "Marathi strings are reviewed translations stored alongside the English, not machine "
        "translation performed at request time. Safety terminology — dose, pre-harvest interval, "
        "protective equipment — is never machine-translated.")
    out["delivery"] = ("This is the message body. Sending it creates a delivery row whose state "
                       "reflects what the gateway said.")
    return out


@meta.get("/health", summary="Liveness", description="Is the process up? No dependency checks.")
def health():
    s = get_settings()
    return {"ok": True, "service": "prahari", "version": s.app_version,
            "app_env": s.app_env, "demo_mode": s.demo_mode, "today": _today().isoformat()}


@meta.get("/ready", summary="Readiness",
          description="Checks the database, weather provider, vision model, storage and "
                      "notification channels. Returns 503 if a hard dependency is down.")
def ready():
    from fastapi.responses import JSONResponse
    rt = get_runtime()
    s = get_settings()
    checks = rt.health()
    hard_ok = bool(checks["database"].get("ok")) and bool(checks["storage"].get("ok"))
    body = {
        "ready": hard_ok,
        "checks": checks,
        "config": s.redacted(),
        "migrations": rt.db.migration_state(),
        "degraded": [] if hard_ok else ["database" if not checks["database"].get("ok") else "storage"],
        "soft_warnings": _soft(checks, s),
    }
    return JSONResponse(body, status_code=200 if hard_ok else 503)


def _soft(checks: dict[str, Any], s) -> list[str]:
    out = []
    if not checks["vision"].get("ready"):
        out.append("No trained vision model is configured — image diagnosis falls back to the "
                   "symptom-feature classifier, which is labelled as such everywhere it appears.")
    if checks["weather"].get("provider") == "none":
        out.append("No weather provider is configured — risk forecasting will return "
                   "weather_unavailable.")
    if checks["weather"].get("kind") == "generated":
        out.append("WEATHER IS GENERATED (demo mode). Not real observations.")
    a = checks.get("assistant") or {}
    if not a.get("configured"):
        out.append("No language-model key is configured — AgriDoc, scan explanations and disease "
                   "cards fall back to the retrieved reference text, which is always available.")
    elif a.get("cooling_down"):
        out.append(f"The assistant key is cooling down for {a['cooling_down']}s after a provider "
                   "429 or 5xx. Answers are served from reference text until it clears.")
    if a.get("vision_provider") == "gemini" and not checks["vision"].get("ready"):
        out.append("VISION_PROVIDER=gemini but no key resolved, so image diagnosis is NOT using "
                   "the vision model.")
    if not checks["notifications"]["sms"]["configured"]:
        out.append("No SMS gateway is configured — SMS deliveries will be recorded as 'skipped'.")
    return out


# ── admin ───────────────────────────────────────────────────────────────────
admin = APIRouter(prefix="/api/admin", tags=["admin"])


@admin.post("/users", status_code=201, summary="Create an officer, expert or admin account")
def create_user(data: RegisterIn, user: dict[str, Any] = Depends(require_roles("admin")),
                db: Database = Depends(db_dep)):
    from .. import accounts
    out = accounts.register(db, data, allow_privileged=True)
    audit("admin.create_user", entity="user", entity_id=out["user_id"], user_id=user["id"], role=user.get("role"),
          detail={"role": data.role})
    return out


@admin.post("/officers/{officer_id}/scopes", summary="Grant an officer a taluka")
def grant_scope(officer_id: str, taluka: str = Query(...),
                user: dict[str, Any] = Depends(require_roles("admin")),
                db: Database = Depends(db_dep)):
    from .. import accounts
    if taluka not in reference.TALUKA_IDS:
        raise bad_request("unknown_taluka", f"'{taluka}' is not a taluka PRAHARI covers.")
    accounts.grant_scope(db, officer_id, taluka)
    audit("admin.grant_scope", entity="officer", entity_id=officer_id, user_id=user["id"], role=user.get("role"),
          detail={"taluka": taluka})
    return {"officer_id": officer_id, "scopes": accounts.officer_scopes(db, officer_id)}


@admin.get("/claims", summary="The chemical reference table with its verification status")
def list_claims(status: str | None = Query(None), crop: str | None = Query(None),
                user: dict[str, Any] = Depends(require_roles("admin")),
                db: Database = Depends(db_dep)):
    sql = "SELECT * FROM label_claims WHERE 1=1"
    params: dict[str, Any] = {}
    if status:
        sql += " AND status = :st"
        params["st"] = status
    if crop:
        sql += " AND crop = :crop"
        params["crop"] = crop
    rows = db.rows(sql + " ORDER BY crop, target, product", params)
    return {"claims": rows, "count": len(rows),
            "rule": ("A claim becomes actionable only through POST /api/admin/claims/{id}/verify, "
                     "which records who verified it, when, and against which CIB&RC citation.")}


@admin.post("/claims/{claim_id}/verify", summary="Verify a label claim against a cited source",
            description=("The ONLY way a chemical recommendation becomes actionable. Records the "
                          "verifier's name, the timestamp and the citation. Verify nothing you "
                          "have not personally checked against the CIB&RC 'Major Uses of "
                          "Pesticides' list."))
def verify_claim(claim_id: str, data: VerifyClaimIn,
                 user: dict[str, Any] = Depends(require_roles("admin")),
                 db: Database = Depends(db_dep)):
    row = chemicals.verify_claim(
        db, claim_id, verified_by=user["full_name"], source=data.source,
        source_url=data.source_url,
        expires_on=data.expires_on.isoformat() if data.expires_on else None)
    if not row:
        raise not_found("label claim", claim_id)
    audit("admin.verify_claim", entity="label_claim", entity_id=claim_id, user_id=user["id"], role=user.get("role"),
          detail={"source": data.source})
    return {"claim": row,
            "effect": ("This product may now be returned as an actionable chemical recommendation "
                       "for its crop and target — still subject to the state restriction list, the "
                       "resistance rotation and the pre-harvest interval.")}


@admin.post("/claims/{claim_id}/status", summary="Change a claim's status")
def set_claim_status(claim_id: str, data: ClaimStatusIn,
                     user: dict[str, Any] = Depends(require_roles("admin")),
                     db: Database = Depends(db_dep)):
    row = chemicals.set_status(db, claim_id, data.status, data.note or "")
    if not row:
        raise not_found("label claim", claim_id)
    audit("admin.claim_status", entity="label_claim", entity_id=claim_id, user_id=user["id"], role=user.get("role"),
          detail={"status": data.status, "note": data.note})
    return {"claim": row}


@admin.get("/staff", summary="Officer, expert and admin accounts, with their scope")
def list_staff(user: dict[str, Any] = Depends(require_roles("admin")),
               db: Database = Depends(db_dep)):
    """Staff only, deliberately.

    An administrator needs to see who can act on other people's records and
    where — that is the point of the screen. They do not need a directory of
    farmers, so this query cannot return one: the role filter is in the SQL,
    not in a parameter a caller could widen.
    """
    rows = db.rows(
        "SELECT u.id, u.full_name, u.role, u.email, u.is_active, u.created_at,"
        "       u.last_login_at, o.id AS officer_id, o.taluka AS officer_taluka,"
        "       e.id AS expert_id, e.institution"
        "  FROM users u"
        "  LEFT JOIN officers o ON o.user_id = u.id"
        "  LEFT JOIN experts  e ON e.user_id = u.id"
        " WHERE u.role IN ('officer', 'expert', 'admin')"
        " ORDER BY u.role, u.full_name")
    for r in rows:
        r["scopes"] = ([s["taluka"] for s in db.rows(
            "SELECT taluka FROM officer_scopes WHERE officer_id = :o ORDER BY taluka",
            {"o": r["officer_id"]})] if r.get("officer_id") else [])
    return {"staff": rows, "count": len(rows),
            "talukas": [{"id": t, "label": reference.taluka_name(t)}
                        for t in sorted(reference.TALUKA_IDS)]}


@admin.get("/overview", summary="What an administrator needs to see first")
def admin_overview(user: dict[str, Any] = Depends(require_roles("admin")),
                   db: Database = Depends(db_dep)):
    """Counts, and the state of the two things that gate advice.

    The unverified-claims count is the one number on this screen that changes
    what farmers are told: `chemicals.py` will not return a claim that has not
    been verified against a CIB&RC citation, so an unverified row is a
    recommendation the app is refusing to make.
    """
    one = db.scalar
    claims = {st: int(one("SELECT COUNT(*) FROM label_claims WHERE status = :s",
                          {"s": st}) or 0)
              for st in ("verified", "draft", "rejected", "expired")}
    rt = get_runtime()
    return {
        "counts": {
            "farmers": int(one("SELECT COUNT(*) FROM farmers") or 0),
            "fields": int(one("SELECT COUNT(*) FROM plots") or 0),
            "observations": int(one("SELECT COUNT(*) FROM observations") or 0),
            "diagnoses": int(one("SELECT COUNT(*) FROM diagnoses") or 0),
            "community_posts": int(one("SELECT COUNT(*) FROM community_posts") or 0),
            "staff": int(one("SELECT COUNT(*) FROM users WHERE role <> 'farmer'") or 0),
        },
        "claims": claims,
        "claims_note": ("Only a VERIFIED claim can be returned as a chemical recommendation. "
                        "A draft row is advice the app is currently refusing to give."),
        "vision": rt.vision.health(),
        "migrations": db.migration_state(),
        "config": get_settings().redacted(),
    }


@admin.get("/audit-log", summary="The audit trail")
def audit_log(limit: int = Query(100, le=1000), action: str | None = Query(None),
              user: dict[str, Any] = Depends(require_roles("admin")),
              db: Database = Depends(db_dep)):
    sql = "SELECT * FROM audit_logs WHERE 1=1"
    params: dict[str, Any] = {}
    if action:
        sql += " AND action = :a"
        params["a"] = action
    rows = db.rows(sql + " ORDER BY id DESC LIMIT :n", {**params, "n": limit})
    for r in rows:
        r["detail"] = loads(r["detail"], {})
    return {"entries": rows}


@admin.delete("/me/data", summary="Delete this account and everything it owns",
              description="Farmer data is the farmer's. Deletion cascades through fields, "
                          "observations, diagnoses and images.")
def delete_own_data(user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep),
                    confirm: str = Query(..., description="Type DELETE to confirm")):
    if confirm != "DELETE":
        raise bad_request("confirmation_required", "Send confirm=DELETE to proceed.")
    rt = get_runtime()
    if user["role"] == "farmer":
        farmer = db.one("SELECT * FROM farmers WHERE user_id = :u", {"u": user["id"]})
        if farmer:
            for img in db.rows(
                    "SELECT i.storage_key, i.thumb_key FROM observation_images i"
                    " JOIN observations o ON o.id = i.observation_id WHERE o.farmer_id = :f",
                    {"f": farmer["id"]}):
                for key in (img["storage_key"], img["thumb_key"]):
                    if not key:
                        continue
                    try:
                        import pathlib
                        if rt.settings.storage_provider == "local":
                            pathlib.Path(rt.storage.root / key).unlink(missing_ok=True)
                    except Exception:
                        pass
    audit("account.delete", entity="user", entity_id=user["id"], user_id=user["id"])
    db.execute("DELETE FROM users WHERE id = :u", {"u": user["id"]})
    return {"deleted": True,
            "note": ("Your account, fields, observations and images have been removed. Aggregated "
                     "taluka-level surveillance counts that no longer identify you are retained, "
                     "as they carry no personal data.")}

