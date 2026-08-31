"""
PRAHARI · /api/community — the farmer community and the signal it produces.

Read the privacy contract in app/community.py before changing anything here.
The short version: every response on this router is built by
`CommunityService.public_post()` / `public_comment()`, which project from an
ALLOWLIST. No handler in this file builds a post dict by hand, because the one
that does will be the one that leaks a plot_id.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile

from .. import community as community_mod
from .. import reference
from .. import storage as storage_mod
from ..clock import now_iso
from ..config import get_settings
from ..db import Database, dumps
from ..deps import current_user, db_dep, expert_of, officer_talukas, require_roles
from ..errors import bad_request, forbidden, not_found
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import (
    CommunityCommentIn,
    CommunityExpertResponseIn,
    CommunityModerateIn,
    CommunityPostIn,
    CommunityReactionIn,
    CommunityReportIn,
    SignalConfirmIn,
)
from ..signals import GRADES, NOT_AN_OUTBREAK

router = APIRouter(prefix="/api/community", tags=["community"])


def _svc(db: Database) -> community_mod.CommunityService:
    return community_mod.CommunityService(db)


# ── the vocabulary the client renders from ──────────────────────────────────
@router.get("/meta", summary="Categories, symptoms, report reasons and the privacy rule")
def meta(user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    svc = _svc(db)
    ctx = svc.viewer_context(user)
    return {
        "categories": community_mod.CATEGORIES,
        "symptoms": community_mod.SYMPTOMS,
        "report_reasons": community_mod.REPORT_REASONS,
        "verification": community_mod.VERIFICATION,
        "signal_grades": GRADES,
        "topics": svc.topics(user["id"]),
        "my_talukas": [{"id": t, "name": reference.taluka_name(t)} for t in ctx["talukas"]],
        "my_crops": [{"id": c,
                      "name": (reference.CROPS.get(c, {}) or {}).get("name", c)}
                     for c in ctx["crops"]],
        "limits": {"posts_per_hour": community_mod.POST_LIMIT_PER_HOUR,
                   "comments_per_hour": community_mod.COMMENT_LIMIT_PER_HOUR},
        "privacy": community_mod.PRIVACY_STATEMENT,
        "privacy_mr": community_mod.PRIVACY_STATEMENT_MR,
        "unverified_notice": community_mod.UNVERIFIED_NOTICE,
        "unverified_notice_mr": community_mod.UNVERIFIED_NOTICE_MR,
    }


# ── the feed ────────────────────────────────────────────────────────────────
@router.get("", summary="The community feed",
            description=(
                "Tabs: `for_you` (ranked for your fields), `nearby` (your taluka and the ones "
                "within 25 km), `mine`, `experts` (posts an expert has answered), `saved`.\n\n"
                "Ranking is by relevance — your taluka, your crops, the problems those crops "
                "get, expert verification and recency. Popularity contributes at most four "
                "points as a tie-break, and every post carries `shown_because` so a farmer can "
                "see why it is in front of them."))
def feed(tab: str = Query("for_you",
                          pattern="^(for_you|nearby|mine|experts|saved)$"),
         category: str | None = Query(None), crop: str | None = Query(None),
         taluka: str | None = Query(None), q: str | None = Query(None, max_length=120),
         limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0),
         user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    return _svc(db).feed(user, tab=tab, category=category, crop=crop, taluka=taluka,
                         q=q, limit=limit, offset=offset)


@router.get("/search", summary="Search by crop, disease, pest, symptom or place")
def search(q: str = Query("", max_length=120), crop: str | None = Query(None),
           problem: str | None = Query(None), taluka: str | None = Query(None),
           symptom: str | None = Query(None),
           user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    svc = _svc(db)
    out = svc.feed(user, tab="all", crop=crop, taluka=taluka, q=q or None, limit=50)
    posts = out["posts"]
    if problem:
        posts = [p for p in posts
                 if problem in (p.get("suspected_problem"), p.get("confirmed_problem"))]
    if symptom:
        posts = [p for p in posts if symptom in (p.get("symptoms") or [])]
    return {"query": {"q": q, "crop": crop, "problem": problem, "taluka": taluka,
                      "symptom": symptom},
            "posts": posts, "total": len(posts), "privacy": out["privacy"]}


# ── writing ─────────────────────────────────────────────────────────────────
@router.post("", status_code=201, summary="Post a problem, a question or a result",
             description=(
                 "`plot_id` is used only to derive the taluka and village and, when "
                 "`share_context` is true, to build a REDACTED summary of what PRAHARI knows "
                 "about that field. The plot id itself is never published, and the summary "
                 "contains no coordinates, no area and no other farmer's data.\n\n"
                 "`client_ref` makes the call idempotent for the offline queue."))
def create(data: CommunityPostIn, user: dict[str, Any] = Depends(current_user),
           db: Database = Depends(db_dep)):
    from ..deps import owned_plot
    plot = owned_plot(db, user, data.plot_id) if data.plot_id else None
    farmer = db.one("SELECT * FROM farmers WHERE user_id = :u", {"u": user["id"]})
    payload = data.model_dump()
    if data.observed_on:
        payload["observed_on"] = data.observed_on.isoformat()
    if not plot and data.taluka:
        farmer = dict(farmer or {})
        farmer["taluka"] = data.taluka
    # A diagnosis may only be attached by the farmer who owns it.
    for key, table in (("observation_id", "observations"), ("diagnosis_id", "diagnoses")):
        val = payload.get(key)
        if val:
            if not plot:
                raise bad_request(
                    "context_needs_field",
                    "Attaching a PRAHARI scan to a post needs the field it came from.")
            row = db.one(f"SELECT id FROM {table} WHERE id = :i AND plot_id = :p",
                         {"i": val, "p": plot["id"]})
            if not row:
                raise forbidden("that scan")
    out = _svc(db).create_post(user, farmer, payload, plot)
    audit("community.post", entity="community_post", entity_id=out["post"]["id"],
          user_id=user["id"])
    if not out.get("duplicate"):
        _refresh_signal(db, out["post"])
    return out


@router.post("/{post_id}/images", status_code=201,
             summary="Attach a photograph to your post",
             description=(
                 "The image is re-encoded, which strips EXIF — the GPS tag a phone writes into a "
                 "photograph is exactly the precise farm location this feature must not publish. "
                 "The same quality measurement the scan path uses is stored alongside it, so a "
                 "reply can say 'this photo is too blurred to judge'."))
async def add_image(post_id: str, image: UploadFile = File(...),
                    user: dict[str, Any] = Depends(current_user),
                    db: Database = Depends(db_dep)):
    post = db.one("SELECT * FROM community_posts WHERE id = :id", {"id": post_id})
    if not post:
        raise not_found("post", post_id)
    if post["author_user_id"] != user["id"] and user["role"] != "admin":
        raise forbidden("this post")
    n = db.scalar("SELECT COUNT(*) FROM community_post_images WHERE post_id = :p", {"p": post_id})
    if int(n or 0) >= 4:
        raise bad_request("too_many_images", "A post carries at most four photographs.")
    rt = get_runtime()
    s = get_settings()
    raw = await image.read()
    _ct, width, height, _fmt = storage_mod.validate_image(raw, s.max_upload_bytes)
    clean = storage_mod.sanitize(raw)
    key = storage_mod.make_key(f"community/{post_id}")
    rt.storage.put(key, clean, "image/jpeg")
    features = rt.vision.analyse(clean)
    iid = "CI-" + uuid.uuid4().hex[:10].upper()
    db.execute(
        "INSERT INTO community_post_images (id, post_id, storage_key, content_type, bytes,"
        " width, height, sha256, quality, created_at)"
        " VALUES (:id,:p,:k,'image/jpeg',:b,:w,:h,:sha,:q,:now)",
        {"id": iid, "p": post_id, "k": key, "b": len(clean), "w": width, "h": height,
         "sha": storage_mod.sha256(clean), "q": dumps(features["quality"]), "now": now_iso()})
    return {"id": iid, "url": f"/api/community/images/{iid}",
            "quality": features["quality"]}


@router.get("/images/{image_id}", summary="A community photograph",
            response_class=Response)
def image_bytes(image_id: str, user: dict[str, Any] = Depends(current_user),
                db: Database = Depends(db_dep)):
    img = db.one(
        "SELECT i.*, p.status FROM community_post_images i"
        " JOIN community_posts p ON p.id = i.post_id WHERE i.id = :id", {"id": image_id})
    if not img or img["status"] == "removed":
        raise not_found("image", image_id)
    data = get_runtime().storage.get(img["storage_key"])
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


# ── conversation ────────────────────────────────────────────────────────────
@router.post("/{post_id}/comments", status_code=201, summary="Reply to a post")
def comment(post_id: str, data: CommunityCommentIn,
            user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    return _svc(db).comment(user, post_id, data.body, data.parent_id)


@router.post("/{post_id}/reactions", summary="Helpful · I have this too · thanks · save")
def react(post_id: str, data: CommunityReactionIn,
          user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    svc = _svc(db)
    out = svc.react(user, data.target_type, post_id, data.kind, data.on)
    if data.kind == "same_problem":
        row = db.one("SELECT * FROM community_posts WHERE id = :id", {"id": post_id})
        if row:
            _refresh_signal(db, svc.public_post(row, user), taluka=row["taluka"],
                            problem=row["confirmed_problem"] or row["suspected_problem"],
                            crop=row["crop"])
    return out


@router.post("/comments/{comment_id}/reactions", summary="Mark a reply helpful")
def react_comment(comment_id: str, data: CommunityReactionIn,
                  user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    return _svc(db).react(user, "comment", comment_id, data.kind, data.on)


@router.get("/me/saved", summary="Posts you saved")
def saved(user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    return {"posts": _svc(db).saved(user)}


@router.post("/topics/{topic_id}/follow", summary="Follow or unfollow a topic")
def follow(topic_id: str, on: bool = Query(True),
           user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    return _svc(db).follow(user["id"], topic_id, on)


# ── moderation ──────────────────────────────────────────────────────────────
@router.post("/{target_id}/report", summary="Report a post or a reply",
             description=("PRAHARI does not remove content because one person disagrees. Three "
                          "independent reports flag it for review; six hide it pending a "
                          "moderator. An expert can correct it instead of it being deleted."))
def report(target_id: str, data: CommunityReportIn,
           user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    out = _svc(db).report(user, data.target_type, target_id, data.reason, data.note)
    audit("community.report", entity=data.target_type, entity_id=target_id, user_id=user["id"])
    return out


@router.post("/{post_id}/block", summary="Stop seeing posts from this author")
def block(post_id: str, on: bool = Query(True),
          user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    return _svc(db).block(user, post_id, on)


@router.get("/moderation/queue", summary="Open content reports (admin)")
def mod_queue(user: dict[str, Any] = Depends(require_roles("admin")),
              db: Database = Depends(db_dep)):
    return {"reports": _svc(db).moderation_queue()}


@router.post("/moderation/{report_id}", summary="Act on a content report (admin)")
def moderate(report_id: str, data: CommunityModerateIn,
             user: dict[str, Any] = Depends(require_roles("admin")),
             db: Database = Depends(db_dep)):
    out = _svc(db).moderate(user, report_id, data.action, data.note)
    audit("community.moderate", entity="community_report", entity_id=report_id,
          user_id=user["id"], detail={"action": data.action})
    return out


# ── the expert's verdict ────────────────────────────────────────────────────
@router.post("/{post_id}/expert-response", status_code=201,
             summary="An expert's formal response to a post",
             description=(
                 "The ONLY way a post's verification changes. Requires an expert (or admin) "
                 "account with an expert profile — a farmer cannot mark anything verified, and "
                 "neither can agreement from other farmers.\n\n"
                 "CONFIRMED and CORRECTED must name the problem. A CONFIRMED response also adds "
                 "one to that taluka's Dirichlet prior, which is the same learning step an "
                 "expert case makes."))
def expert_response(post_id: str, data: CommunityExpertResponseIn,
                    user: dict[str, Any] = Depends(require_roles("expert")),
                    db: Database = Depends(db_dep)):
    expert = expert_of(db, user)
    svc = _svc(db)
    out = svc.expert_respond(user, expert, post_id, data.model_dump())
    audit("community.expert_response", entity="community_post", entity_id=post_id,
          user_id=user["id"], detail={"status": data.status})
    row = db.one("SELECT * FROM community_posts WHERE id = :id", {"id": post_id})
    if row:
        _refresh_signal(db, out["post"], taluka=row["taluka"],
                        problem=row["confirmed_problem"] or row["suspected_problem"],
                        crop=row["crop"])
    return out


@router.get("/expert/inbox", summary="Posts waiting for an expert answer")
def expert_inbox(limit: int = Query(30, ge=1, le=100),
                 user: dict[str, Any] = Depends(require_roles("expert")),
                 db: Database = Depends(db_dep)):
    """Unanswered disease and pest posts first, oldest first — the opposite of a
    feed. An expert's scarce hour should go to the question nobody has answered,
    not to the one everybody is already reading."""
    svc = _svc(db)
    rows = db.rows(
        "SELECT * FROM community_posts WHERE status='published'"
        " AND category IN ('disease','pest','crop_problem','question')"
        " AND verification = 'UNVERIFIED' AND moderation_state <> 'blocked'"
        " ORDER BY expert_count, same_problem_count DESC, created_at LIMIT :n", {"n": limit})
    return {"posts": [svc.public_post(r, user) for r in rows],
            "rule": ("Oldest unanswered first, with posts several farmers say they share "
                     "lifted above the rest.")}


# ── the signal ──────────────────────────────────────────────────────────────
@router.get("/signals/mine", summary="What the community is seeing near YOUR fields",
            description=("Aggregated counts for the talukas your own fields are in. Never a list "
                         "of other farmers, never coordinates — how many, and where at taluka "
                         "level."))
def my_signals(user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    svc = _svc(db)
    ctx = svc.viewer_context(user)
    eng = get_runtime().signals
    out = eng.open_signals(ctx["near_talukas"] or None)
    return {"signals": out, "talukas": ctx["talukas"],
            "what_this_is_not": NOT_AN_OUTBREAK,
            "privacy": community_mod.PRIVACY_STATEMENT}


@router.get("/signals", summary="Cluster signals in your scope (officer)")
def signals(refresh: bool = Query(False),
            user: dict[str, Any] = Depends(require_roles("officer")),
            db: Database = Depends(db_dep)):
    scope = officer_talukas(db, user)
    eng = get_runtime().signals
    if refresh:
        eng.sweep(talukas=scope)
    return {"signals": eng.open_signals(scope), "talukas": scope,
            "what_this_is_not": NOT_AN_OUTBREAK,
            "grades": GRADES}


@router.get("/signals/{signal_id}", summary="One signal, with the posts behind it (officer)")
def signal_detail(signal_id: str, user: dict[str, Any] = Depends(require_roles("officer")),
                  db: Database = Depends(db_dep)):
    row = db.one("SELECT * FROM community_cluster_signals WHERE id = :id", {"id": signal_id})
    if not row:
        raise not_found("signal", signal_id)
    if row["taluka"] not in officer_talukas(db, user):
        raise forbidden("signals outside your assigned talukas")
    svc = _svc(db)
    fresh = get_runtime().signals.assess(row["taluka"], row["problem"],
                                         crop=row["crop"] or None,
                                         days=row["window_days"])
    posts = db.rows(
        "SELECT * FROM community_posts WHERE taluka = :t AND status='published'"
        " AND signal_eligible = 1 AND (suspected_problem = :p OR confirmed_problem = :p)"
        " ORDER BY created_at DESC LIMIT 50", {"t": row["taluka"], "p": row["problem"]})
    return {"signal": fresh, "id": signal_id,
            # An officer sees the posts because acting on a signal means reading
            # what was actually said. They still do not see coordinates: the
            # projection is the same one every other reader gets.
            "posts": [svc.public_post(p, user) for p in posts],
            "note": ("An officer reads the same public projection every farmer reads. Confirming "
                     "a signal is a statement about a taluka, not about a named field — open the "
                     "surveillance panel to work from diagnosed cases.")}


@router.post("/signals/{signal_id}/confirm", summary="Confirm or dismiss a signal (officer)")
def confirm_signal(signal_id: str, data: SignalConfirmIn,
                   user: dict[str, Any] = Depends(require_roles("officer")),
                   db: Database = Depends(db_dep)):
    row = db.one("SELECT * FROM community_cluster_signals WHERE id = :id", {"id": signal_id})
    if not row:
        raise not_found("signal", signal_id)
    if row["taluka"] not in officer_talukas(db, user):
        raise forbidden("signals outside your assigned talukas")
    eng = get_runtime().signals
    out = eng.officer_confirm(signal_id, user, confirmed=data.confirmed, note=data.note)
    audit("community.signal_confirm", entity="community_signal", entity_id=signal_id,
          user_id=user["id"], detail={"confirmed": data.confirmed})
    if data.confirmed:
        fresh = eng.assess(row["taluka"], row["problem"], crop=row["crop"] or None,
                           days=row["window_days"])
        fresh["id"] = signal_id
        out["alert"] = eng.alert(fresh)
    return out


# ── the catch-all path parameter, LAST ──────────────────────────────────────
# FastAPI matches in declaration order, so `/{post_id}` must come after every
# literal route or `GET /api/community/signals` resolves to "post 'signals' does
# not exist" — which is exactly the kind of bug that only shows up in the demo.
@router.get("/{post_id}", summary="One post, its replies, its expert verdicts and similar cases")
def detail(post_id: str, user: dict[str, Any] = Depends(current_user),
           db: Database = Depends(db_dep)):
    return _svc(db).post_detail(post_id, user)


@router.delete("/{post_id}", summary="Withdraw your own post")
def withdraw(post_id: str, user: dict[str, Any] = Depends(current_user),
             db: Database = Depends(db_dep)):
    out = _svc(db).delete_own(user, post_id)
    audit("community.withdraw", entity="community_post", entity_id=post_id, user_id=user["id"])
    return out


# ── internal ────────────────────────────────────────────────────────────────
def _refresh_signal(db: Database, post: dict[str, Any], *, taluka: str | None = None,
                    problem: str | None = None, crop: str | None = None) -> None:
    """Recompute the one (taluka, problem) pair this action could have moved.
    Sweeping the district on every post would be wasteful and, worse, would make
    the signal a function of when someone last looked."""
    taluka = taluka or post.get("taluka")
    problem = problem or post.get("confirmed_problem") or post.get("suspected_problem")
    if not taluka or not problem:
        return
    eng = get_runtime().signals
    a = eng.assess(taluka, problem, crop=crop or post.get("crop") or None)
    if a.get("grade") and GRADES.get(a["grade"], {}).get("rank", 0) >= 2:
        eng.alert(a)
