"""
PRAHARI · /api/observations — the camera, and its right to refuse.

The order is quality gate → classifier → Bayes → abstention, and a photograph
that fails the gate never reaches the classifier. See services/diagnosis.py.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from .. import reference
from .. import storage as storage_mod
from ..clock import now_iso
from ..clock import today as _today
from ..config import get_settings
from ..db import Database, dumps, loads
from ..deps import current_user, db_dep, farmer_of, owned_plot, visible_plot
from ..errors import bad_request, conflict, not_found
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import AnswersIn, ExpertRequestIn
from ..weather import WeatherUnavailable

router = APIRouter(prefix="/api/observations", tags=["observations"])


@router.post("", status_code=201,
             summary="Record an observation and diagnose its photograph",
             description=(
                 "Multipart upload. The image is validated (real image bytes, size and dimension "
                 "caps), re-encoded to strip EXIF — which carries the GPS location of wherever the "
                 "photograph was taken — stored in object storage, and measured.\n\n"
                 "Then, in this order: the QUALITY GATE, and only if it passes, the configured "
                 "classifier. A photograph that fails the gate is returned with guidance and NO "
                 "diagnosis. `client_ref` makes the call idempotent for the offline queue.\n\n"
                 "Errors: 400 not_an_image · 400 unsupported_image_format · 413 file_too_large · "
                 "403 forbidden · 503 weather_unavailable"))
async def create_observation(
        request: Request,
        plot_id: str = Form(...),
        image: UploadFile = File(...),
        kind: str = Form("leaf"),
        image_role: str = Form("affected"),
        notes: str | None = Form(None),
        lat: float | None = Form(None),
        lng: float | None = Form(None),
        client_ref: str | None = Form(None),
        user: dict[str, Any] = Depends(current_user),
        db: Database = Depends(db_dep)):
    rt = get_runtime()
    s = get_settings()
    plot = owned_plot(db, user, plot_id)
    farmer = farmer_of(db, user) if user["role"] == "farmer" else \
        db.one("SELECT * FROM farmers WHERE id = :f", {"f": plot["farmer_id"]})

    if client_ref:
        existing = db.one(
            "SELECT id FROM observations WHERE farmer_id = :f AND client_ref = :c",
            {"f": farmer["id"], "c": client_ref})
        if existing:
            return _observation_view(db, existing["id"], deduped=True)

    raw = await image.read()
    content_type, width, height, _fmt = storage_mod.validate_image(raw, s.max_upload_bytes)
    clean = storage_mod.sanitize(raw)
    thumb = storage_mod.thumbnail(clean)
    key = storage_mod.make_key(f"observations/{plot_id}")
    thumb_key = key.replace(".jpg", "_thumb.jpg")
    rt.storage.put(key, clean, "image/jpeg")
    rt.storage.put(thumb_key, thumb, "image/jpeg")

    stage = rt.risk.crop_stage(plot)
    cycle = rt.risk.active_cycle(plot_id)
    oid = "O-" + uuid.uuid4().hex[:10].upper()
    stamp = now_iso()
    db.execute(
        "INSERT INTO observations (id, plot_id, farmer_id, cycle_id, kind, taluka, crop,"
        " crop_stage, observed_at, lat, lng, notes, source, client_ref, status, created_at)"
        " VALUES (:id,:p,:f,:cy,:k,:tk,:crop,:cs,:at,:lat,:lng,:notes,:src,:ref,'open',:now)",
        {"id": oid, "p": plot_id, "f": farmer["id"], "cy": (cycle or {}).get("id"),
         "k": kind, "tk": plot["taluka"], "crop": plot["crop"], "cs": stage.get("stage"),
         "at": stamp, "lat": lat, "lng": lng, "notes": notes,
         "src": "offline_sync" if client_ref else "app", "ref": client_ref, "now": stamp})

    features = rt.vision.analyse(clean)
    img_id = "I-" + uuid.uuid4().hex[:10].upper()
    db.execute(
        "INSERT INTO observation_images (id, observation_id, role, storage_key, thumb_key,"
        " content_type, bytes, width, height, sha256, quality, features, created_at)"
        " VALUES (:id,:o,:r,:k,:tk,:ct,:b,:w,:h,:sha,:q,:f,:now)",
        {"id": img_id, "o": oid, "r": image_role, "k": key, "tk": thumb_key,
         "ct": "image/jpeg", "b": len(clean), "w": width, "h": height,
         "sha": storage_mod.sha256(clean),
         "q": dumps(features["quality"]),
         "f": dumps({k: v for k, v in features.items() if k != "quality"}),
         "now": stamp})

    # Weather feeds the model-fired term of the posterior. If it is unavailable
    # the diagnosis still runs — with every weather factor neutral, and the
    # response says so — because refusing to look at a leaf because an API is
    # down would be worse than a slightly weaker prior.
    fired: dict[str, bool] = {}
    weather_meta: dict[str, Any] = {"available": False}
    try:
        wx = rt.risk.weather_series(plot)
        _board, fired = rt.risk.board(plot, wx, stage)
        weather_meta = {"available": True, "source": wx.get("source"),
                        "kind": wx.get("source_kind"),
                        "fetched_at": wx.get("fetched_at"),
                        "fired": fired}
    except WeatherUnavailable as exc:
        weather_meta = {"available": False, "reason": exc.reason, "provider": exc.provider,
                        "effect": ("Every weather factor was held neutral, so this diagnosis rests "
                                   "on the image and the taluka prior alone.")}

    dx = rt.diagnosis.run(observation={"id": oid}, plot=plot, image_bytes=clean,
                          features=features, fired=fired, weather_meta=weather_meta)

    _log_event(db, plot_id, dx, oid)
    if dx["abstain"] and dx["reason"] not in ("photo-quality",):
        _auto_case(db, rt, plot, farmer, oid, dx)

    audit("observation.create", entity="observation", entity_id=oid, user_id=user["id"],
          role=user["role"], detail={"abstained": dx["abstain"], "reason": dx["reason"],
                                     "engine": dx["engine"]["engine"]})
    return _observation_view(db, oid)


IMAGE_ROLES = {
    "whole_plant": "The whole plant, so the pattern of damage across it is visible",
    "affected": "The affected leaf, filling the frame",
    "closeup": "A close-up of one lesion",
    "underside": "The underside of the affected leaf",
    "stem": "The stem, fruit or growing point",
}


@router.post("/{observation_id}/images", status_code=201,
             summary="Add another photograph to an existing observation",
             description=(
                 "A second photograph of the same problem — the whole plant, the underside of "
                 "the leaf, a close-up of one lesion. Each is graded by the SAME quality gate "
                 "as the first, and the diagnosis is then re-run over the best-quality image "
                 "available, with the others recorded as corroborating evidence.\n\n"
                 "Adding an image can only ever change the answer by giving the engine a "
                 "better photograph to look at. It cannot be used to talk the engine into a "
                 "diagnosis it declined to make on the evidence.\n\n"
                 "Errors: 400 not_an_image · 400 unknown_role · 409 observation_closed · "
                 "413 file_too_large"))
async def add_image(
        observation_id: str,
        image: UploadFile = File(...),
        image_role: str = Form("closeup"),
        user: dict[str, Any] = Depends(current_user),
        db: Database = Depends(db_dep)):
    rt = get_runtime()
    s = get_settings()

    obs = db.one("SELECT * FROM observations WHERE id = :o", {"o": observation_id})
    if not obs:
        raise not_found("observation", observation_id)
    plot = owned_plot(db, user, obs["plot_id"])

    if image_role not in IMAGE_ROLES:
        raise bad_request("unknown_role",
                          f"'{image_role}' is not a photograph role. Use one of: "
                          + ", ".join(IMAGE_ROLES),
                          "हा फोटो प्रकार उपलब्ध नाही.")

    # An observation an expert has already ruled on is a closed record.
    if (obs.get("status") or "open") not in ("open", "answered"):
        raise conflict("observation_closed",
                       "This observation has been reviewed and can no longer be added to.",
                       "या नोंदीचे परीक्षण झाले आहे; आता फोटो जोडता येणार नाही.")

    raw = await image.read()
    content_type, width, height, _fmt = storage_mod.validate_image(raw, s.max_upload_bytes)
    clean = storage_mod.sanitize(raw)
    thumb = storage_mod.thumbnail(clean)
    key = storage_mod.make_key(f"observations/{obs['plot_id']}")
    thumb_key = key.replace(".jpg", "_thumb.jpg")
    rt.storage.put(key, clean, "image/jpeg")
    rt.storage.put(thumb_key, thumb, "image/jpeg")

    features = rt.vision.analyse(clean)
    stamp = now_iso()
    img_id = "I-" + uuid.uuid4().hex[:10].upper()
    db.execute(
        "INSERT INTO observation_images (id, observation_id, role, storage_key, thumb_key,"
        " content_type, bytes, width, height, sha256, quality, features, created_at)"
        " VALUES (:id,:o,:r,:k,:tk,:ct,:b,:w,:h,:sha,:q,:f,:now)",
        {"id": img_id, "o": observation_id, "r": image_role, "k": key, "tk": thumb_key,
         "ct": "image/jpeg", "b": len(clean), "w": width, "h": height,
         "sha": storage_mod.sha256(clean),
         "q": dumps(features["quality"]),
         "f": dumps({k: v for k, v in features.items() if k != "quality"}),
         "now": stamp})

    # A photograph that fails the gate is KEPT — it is the farmer's record of
    # what they saw — but it is never promoted to the one the engine reads.
    if not features["quality"]["ok"]:
        return {**_observation_view(db, observation_id),
                "added_image": {"id": img_id, "role": image_role,
                                "quality": features["quality"], "used_for_diagnosis": False},
                "note": ("This photograph was saved but not used for the diagnosis, because it "
                         "did not pass the quality gate. The reasons are in `quality.failures`.")}

    stage = rt.risk.crop_stage(plot)
    fired: dict[str, Any] = {}
    weather_meta: dict[str, Any] = {"available": False}
    try:
        wx = rt.risk.weather_series(plot)
        _board, fired = rt.risk.board(plot, wx, stage)
        weather_meta = {"available": True, "source": wx.get("source"),
                        "kind": wx.get("source_kind"), "fetched_at": wx.get("fetched_at"),
                        "fired": fired}
    except WeatherUnavailable as exc:
        weather_meta = {"available": False, "reason": exc.reason, "provider": exc.provider,
                        "effect": ("Every weather factor was held neutral, so this diagnosis "
                                   "rests on the image and the taluka prior alone.")}

    dx = rt.diagnosis.run(observation={"id": observation_id}, plot=plot, image_bytes=clean,
                          features=features, fired=fired, weather_meta=weather_meta)
    _log_event(db, obs["plot_id"], dx, observation_id)

    audit("observation.add_image", entity="observation", entity_id=observation_id,
          user_id=user["id"], role=user["role"],
          detail={"role": image_role, "abstained": dx["abstain"], "reason": dx["reason"]})

    return {**_observation_view(db, observation_id),
            "added_image": {"id": img_id, "role": image_role,
                            "quality": features["quality"], "used_for_diagnosis": True},
            "note": ("The diagnosis was re-run on this photograph. Every image on this "
                     "observation is kept and shown to an expert who reviews it.")}


@router.get("/{observation_id}", summary="One observation with its diagnosis")
def get_observation(observation_id: str, user: dict[str, Any] = Depends(current_user),
                    db: Database = Depends(db_dep)):
    obs = db.one("SELECT * FROM observations WHERE id = :id", {"id": observation_id})
    if not obs:
        raise not_found("observation", observation_id)
    visible_plot(db, user, obs["plot_id"])
    return _observation_view(db, observation_id)


@router.get("", summary="Observations for a field")
def list_observations(plot_id: str = Query(...), limit: int = Query(30, le=200),
                      user: dict[str, Any] = Depends(current_user),
                      db: Database = Depends(db_dep)):
    visible_plot(db, user, plot_id)
    rows = db.rows(
        "SELECT o.*, d.id AS diagnosis_id, d.top_problem, d.top_posterior, d.abstained,"
        " d.abstain_reason, d.engine, d.confirmed"
        " FROM observations o LEFT JOIN diagnoses d ON d.observation_id = o.id"
        " WHERE o.plot_id = :p ORDER BY o.observed_at DESC LIMIT :n",
        {"p": plot_id, "n": limit})
    for r in rows:
        r["abstained"] = bool(r.get("abstained"))
        if r.get("top_problem"):
            r["top_problem_name"] = reference.problem_name(r["top_problem"])
    return {"observations": rows}


@router.get("/{observation_id}/questions",
            summary="Contextual questions for an uncertain diagnosis",
            description=("Returned only when the uncertainty is something a question can settle. "
                          "When the photograph itself is the blocker, this returns an empty list "
                          "and says why — questions cannot un-blur an image."))
def questions(observation_id: str, user: dict[str, Any] = Depends(current_user),
              db: Database = Depends(db_dep)):
    dx = _diagnosis_of(db, observation_id, user)
    if dx["abstain_reason"] in ("photo-quality", "crop-not-covered", "model-unavailable"):
        return {"questions": [], "blocked": True, "reason": dx["abstain_reason"],
                "message": ("The photograph is the blocker here, not ambiguity about the symptom. "
                            "No question can change that.")}
    from .. import loop
    ranked = [{"id": r["problem"], "posterior": r["posterior"]} for r in db.rows(
        "SELECT problem, posterior FROM diagnosis_candidates WHERE diagnosis_id = :d ORDER BY rank",
        {"d": dx["id"]})]
    return {"questions": loop.pick_questions(ranked, dx["abstain_reason"]), "blocked": False}


@router.post("/{observation_id}/answers",
             summary="Answer the contextual questions",
             description=("Re-weights candidates the image already ranked. An answer can never "
                          "introduce a candidate the photograph did not see, and never lifts "
                          "confidence past the 99% cap.\n\nErrors: 409 quality_block"))
def answer(observation_id: str, data: AnswersIn,
           user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    dx = _diagnosis_of(db, observation_id, user)
    rt = get_runtime()
    out = rt.diagnosis.answer(dx["id"], data.answers)
    if out.get("blocked"):
        raise conflict("quality_block", out["message"], out.get("message_mr"))
    audit("diagnosis.answers", entity="diagnosis", entity_id=dx["id"], user_id=user["id"])
    return out


@router.post("/{observation_id}/expert-review", status_code=201,
             summary="Send this observation to an expert",
             description="Creates a case an expert can review and the farmer can watch a status on.")
def request_expert(observation_id: str, data: ExpertRequestIn,
                   user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    obs = db.one("SELECT * FROM observations WHERE id = :id", {"id": observation_id})
    if not obs:
        raise not_found("observation", observation_id)
    plot = owned_plot(db, user, obs["plot_id"])
    rt = get_runtime()
    existing = db.one("SELECT * FROM expert_cases WHERE observation_id = :o", {"o": observation_id})
    if existing:
        return {"case": existing, "already_open": True}
    dx = db.one("SELECT * FROM diagnoses WHERE observation_id = :o", {"o": observation_id})
    case = _create_case(db, rt, plot, obs, dx, data.reason or "Requested by the farmer",
                        data.urgency)
    audit("expert.case_open", entity="expert_case", entity_id=case["id"], user_id=user["id"])
    return {"case": case, "already_open": False}


@router.get("/{observation_id}/image", summary="A signed URL for the observation's image")
def image_url(observation_id: str, thumb: bool = Query(False),
              user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    obs = db.one("SELECT * FROM observations WHERE id = :id", {"id": observation_id})
    if not obs:
        raise not_found("observation", observation_id)
    visible_plot(db, user, obs["plot_id"])
    img = db.one("SELECT * FROM observation_images WHERE observation_id = :o ORDER BY created_at",
                 {"o": observation_id})
    if not img:
        raise not_found("image", observation_id)
    rt = get_runtime()
    key = img["thumb_key"] if (thumb and img["thumb_key"]) else img["storage_key"]
    return {"url": rt.storage.url(key), "expires_in": get_settings().signed_url_ttl_seconds
            if get_settings().storage_provider == "s3" else None}


# ── helpers ─────────────────────────────────────────────────────────────────
def _diagnosis_of(db: Database, observation_id: str, user: dict[str, Any]) -> dict[str, Any]:
    obs = db.one("SELECT * FROM observations WHERE id = :id", {"id": observation_id})
    if not obs:
        raise not_found("observation", observation_id)
    visible_plot(db, user, obs["plot_id"])
    dx = db.one("SELECT * FROM diagnoses WHERE observation_id = :o", {"o": observation_id})
    if not dx:
        raise not_found("diagnosis", observation_id)
    return dx


def _observation_view(db: Database, observation_id: str,
                      deduped: bool = False) -> dict[str, Any]:
    rt = get_runtime()
    obs = db.one("SELECT * FROM observations WHERE id = :id", {"id": observation_id})
    dx = db.one("SELECT * FROM diagnoses WHERE observation_id = :o", {"o": observation_id})
    images = db.rows("SELECT * FROM observation_images WHERE observation_id = :o",
                     {"o": observation_id})
    candidates = db.rows(
        "SELECT * FROM diagnosis_candidates WHERE diagnosis_id = :d ORDER BY rank",
        {"d": (dx or {}).get("id")}) if dx else []
    case = db.one("SELECT id, status, urgency FROM expert_cases WHERE observation_id = :o",
                  {"o": observation_id})

    quality = loads(images[0]["quality"], {}) if images else {}
    differential = []
    if dx and dx["abstain_reason"] not in ("photo-quality", "crop-not-covered", "model-unavailable"):
        for c in candidates[:3]:
            p = reference.problem(c["problem"]) or {}
            differential.append({
                "id": c["problem"], "name": p.get("name", c["problem"]), "name_mr": p.get("mr"),
                "em": p.get("em"), "sci": p.get("sci"),
                "confidence": c["posterior"], "confidence_pct": round((c["posterior"] or 0) * 100),
                "prior": c["prior"], "image_fit": c["image_fit"],
                "weather_factor": c["weather_factor"],
                "supporting": loads(c["supporting"], []),
                "contradicting": loads(c["contradicting"], []),
            })
    from .. import loop
    questions = []
    if dx and dx["abstained"] and dx["abstain_reason"] not in (
            "photo-quality", "crop-not-covered", "model-unavailable", "unfamiliar-pattern"):
        questions = loop.pick_questions(
            [{"id": c["problem"], "posterior": c["posterior"]} for c in candidates],
            dx["abstain_reason"])

    engine_note = None
    if dx:
        neural = dx["engine"] in ("onnx", "api", "gemini")
        if dx["engine"] == "gemini":
            label = (f"Gemini vision ({dx['model_version']}) — general model, "
                     "not trained on this crop")
        elif neural:
            label = "Prahari Vision " + str(dx["model_version"])
        else:
            label = "Symptom-feature classifier v1 (not a neural network)"
        engine_note = {
            "engine": dx["engine"], "model_version": dx["model_version"],
            "is_neural_model": neural, "label": label,
        }

    return {
        "observation": {**obs, "crop_stage_label": reference.crop_stage(
            obs["crop"], None).get("label") if obs else None},
        "images": [{"id": i["id"], "role": i["role"],
                    "url": rt.storage.url(i["storage_key"]),
                    "thumb_url": rt.storage.url(i["thumb_key"]) if i["thumb_key"] else None,
                    "quality": loads(i["quality"], {}),
                    "features": loads(i["features"], {})} for i in images],
        "quality": quality,
        "diagnosis": ({
            "id": dx["id"], "abstain": bool(dx["abstained"]), "reason": dx["abstain_reason"],
            "explain": dx["explain"],
            "top": (differential[0] if differential and not dx["abstained"] else None),
            "differential": differential,
            "margin": dx["margin"],
            "evidence": loads(dx["evidence"], {}),
            "prior": loads(dx["prior_used"], {}),
            "weather": loads(dx["weather_used"], {}),
            "engine": engine_note,
            "confirmed": dx["confirmed"],
        } if dx else None),
        "questions": questions,
        "expert_case": case,
        "deduplicated": deduped,
        "next": _next_step(dx, case),
    }


def _next_step(dx, case) -> dict[str, str]:
    if not dx:
        return {"do": "record", "say": "Observation recorded."}
    if dx["abstain_reason"] == "photo-quality":
        return {"do": "retake",
                "say": "Take the photograph again following the guidance above. Nothing has been "
                       "diagnosed from this one.",
                "say_mr": "वरील सूचनांप्रमाणे पुन्हा फोटो काढा. या फोटोवरून कोणतेही निदान केलेले नाही."}
    if dx["abstained"]:
        return {"do": "expert" if not case else "wait",
                "say": ("This case is with an expert." if case else
                        "PRAHARI is not confident enough to name this. Answer the questions, or "
                        "send it to an expert."),
                "say_mr": ("हे प्रकरण तज्ज्ञांकडे आहे." if case else
                           "प्रहरी खात्रीने सांगू शकत नाही. प्रश्नांची उत्तरे द्या किंवा तज्ज्ञांकडे पाठवा.")}
    return {"do": "count",
            "say": "Now count the trap or the plants. A diagnosis alone cannot authorise a spray.",
            "say_mr": "आता सापळा किंवा झाडे मोजा. फक्त निदानावरून फवारणी ठरत नाही."}


def _log_event(db: Database, plot_id: str, dx: dict[str, Any], oid: str) -> None:
    top = dx.get("top")
    if dx["abstain"]:
        title = "Leaf scanned — no diagnosis"
        detail = dx.get("explain") or ""
        severity = "watch"
    else:
        title = f"Leaf scanned — {top['name']}"
        detail = f"{top['confidence_pct']}% posterior, {dx['engine']['label']}."
        severity = "rising"
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
        " VALUES (:p,:at,'scan',:sev,:t,:d,:ref,:now)",
        {"p": plot_id, "at": _today().isoformat(), "sev": severity, "t": title,
         "d": detail[:900], "ref": oid, "now": now_iso()})


def _auto_case(db: Database, rt, plot, farmer, oid: str, dx: dict[str, Any]) -> None:
    """An abstention that questions cannot settle goes to a human automatically.
    The farmer does not have to know that 'evidence-conflict' means 'ask someone'."""
    if dx["reason"] in ("evidence-conflict", "two-way-tie", "no-clear-candidate"):
        return                       # these have questions; the farmer escalates if unsatisfied
    obs = db.one("SELECT * FROM observations WHERE id = :id", {"id": oid})
    dxrow = db.one("SELECT * FROM diagnoses WHERE observation_id = :o", {"o": oid})
    _create_case(db, rt, plot, obs, dxrow,
                 f"Automatic: the model abstained ({dx['reason']}).", "normal")


def _create_case(db: Database, rt, plot, obs, dx, reason: str, urgency: str) -> dict[str, Any]:
    year = _today().year
    n = db.scalar("SELECT COUNT(*) FROM expert_cases") or 0
    cid = f"PRH-{year}-{n + 1:04d}"
    stamp = now_iso()
    db.execute(
        "INSERT INTO expert_cases (id, observation_id, diagnosis_id, plot_id, farmer_id, taluka,"
        " crop, reason, urgency, status, submitted_at, created_at)"
        " VALUES (:id,:o,:d,:p,:f,:tk,:crop,:r,:u,'submitted',:now,:now)",
        {"id": cid, "o": obs["id"], "d": (dx or {}).get("id"), "p": plot["id"],
         "f": obs["farmer_id"], "tk": plot["taluka"], "crop": plot["crop"],
         "r": reason, "u": urgency, "now": stamp})
    db.execute(
        "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
        " VALUES (:p,:at,'expert','watch',:t,:d,:ref,:now)",
        {"p": plot["id"], "at": _today().isoformat(),
         "t": f"Sent to an expert — case {cid}", "d": reason, "ref": cid, "now": stamp})
    farmer = db.one("SELECT * FROM farmers WHERE id = :f", {"f": obs["farmer_id"]})
    rt.notify.push(
        user_id=farmer["user_id"] if farmer else None, plot_id=plot["id"], kind="expert",
        severity="watch", title=f"Case {cid} is with an expert",
        body=("An agronomist will review your photograph, the weather at your field and its "
              "history, and confirm or correct the diagnosis. You will be told the verdict."),
        title_mr=f"प्रकरण {cid} तज्ज्ञांकडे पाठवले",
        body_mr=("तज्ज्ञ तुमचा फोटो, शेतावरील हवामान व इतिहास तपासून निदानाची खात्री करतील. "
                 "निकाल तुम्हाला कळवला जाईल."),
        channels=["sms"] if (farmer or {}).get("phone") else [],
        address=(farmer or {}).get("phone"), lang=(farmer or {}).get("lang", "mr"))
    return db.one("SELECT * FROM expert_cases WHERE id = :id", {"id": cid})
