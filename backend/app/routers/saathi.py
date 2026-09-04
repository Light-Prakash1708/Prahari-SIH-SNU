"""PRAHARI · /api/saathi — the grounded agricultural assistant."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from .. import explain as explain_mod
from .. import llm as llm_mod
from .. import saathi as saathi_mod
from ..clock import now_iso
from ..config import get_settings
from ..db import Database
from ..deps import current_user, db_dep, visible_plot
from ..errors import bad_request
from ..obs import audit
from ..runtime import get_runtime

log = logging.getLogger("prahari.saathi")

router = APIRouter(prefix="/api/saathi", tags=["assistant"])


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    plot_id: str | None = None
    lang: str = "mr"
    # A farmer with a key can turn the rewriting off for one question — useful
    # when they want to see the retrieved wording exactly as PRAHARI holds it.
    enhance: bool = True
    # Ask for the answer broken into named sections as well as prose. Off by
    # default because it costs a second call to the provider, and because the
    # prose answer is the one every existing client renders.
    sections: bool = False


class KeyIn(BaseModel):
    provider: str = Field(pattern="^(gemini|openai)$")
    api_key: str = Field(min_length=8, max_length=400)
    model: str | None = Field(default=None, max_length=80)


@router.post("/ask", summary="Ask PRAHARI Saathi",
             description=(
                 "Answers ONLY from published agronomic references, VERIFIED chemical label "
                 "claims, and the asker's own field records. There is no language model on "
                 "this path: the answer is assembled from retrieved rows, so it cannot invent "
                 "a dose, a legal restriction, a treatment or a yield figure.\n\n"
                 "When nothing grounds the answer it returns `grounded: false` and says so, "
                 "rather than producing a plausible sentence.\n\n"
                 "Errors: 403 forbidden — you may only ask about your own field."))
def ask(data: AskIn, user: dict[str, Any] = Depends(current_user),
        db: Database = Depends(db_dep)):
    plot = None
    if data.plot_id:
        plot = visible_plot(db, user, data.plot_id)
    rt = get_runtime()
    engine = saathi_mod.Saathi(db, rt)
    answer = engine.ask(data.question, plot=plot, lang=data.lang)
    out = answer.dict(data.lang)

    # ── the optional language-model pass ────────────────────────────────────
    # Retrieval has already happened and `out` is already a correct answer.
    # Everything below can only replace its WORDING, and only if the guards in
    # llm.py pass. If anything at all goes wrong the retrieved answer stands.
    cfg = _llm_for(db, user)
    out["llm"] = {"available": bool(cfg), "used": False}
    if cfg and data.enhance:
        # Everything from here down can only change the WORDING of an answer
        # that is already correct and already in `out`. So it gets a net: an
        # unexpected failure while assembling the facts or calling the provider
        # costs the rewrite, never the answer. Without this a TypeError in the
        # bundle would 500 a request that had a good reply sitting in hand.
        try:
            verdict = _rephrased(db, rt, plot, answer, data, cfg)
        except Exception as exc:                     # pragma: no cover - net
            log.exception("saathi enhancement failed; serving the retrieved answer")
            verdict = {"used": False, "reason": f"enhancement error: {type(exc).__name__}"}
        if verdict.get("used"):
            out["answer"] = verdict["text"]
            out["answer_template"] = answer.text_mr if data.lang == "mr" else answer.text
            out["grounded"] = True
            out["llm"] = {"available": True, "used": True,
                          "provider": verdict["provider"], "model": verdict["model"],
                          "note": ("Worded by a language model from the facts above. Every "
                                   "number in it was checked against those facts before it "
                                   "was shown.")}
        else:
            out["llm"] = {"available": True, "used": False,
                          "reason": verdict.get("reason", "")}
            if verdict.get("quota"):
                # Named separately because it is the one reason that is about
                # the account rather than about the answer.
                out["llm"]["quota"] = True
            if verdict.get("rejected"):
                # Kept so a reviewer can see WHAT was thrown away. It is never
                # rendered as an answer.
                out["llm"]["discarded_draft"] = verdict["rejected"]

    # ── the optional sectioned pass ────────────────────────────────────────
    # Same facts, same guards, a different shape. It is additive: `answer` is
    # untouched, so a client that does not ask for sections sees exactly what
    # it saw before, and a client that does can render the reasoning without
    # PRAHARI having to guess at headings inside a prose blob.
    if cfg and data.sections and answer.grounded:
        try:
            out["sections"] = _sectioned(db, rt, plot, answer, data, cfg)
        except Exception:                            # pragma: no cover - net
            log.exception("saathi sections failed; serving the prose answer")

    audit("saathi.ask", entity="plot", entity_id=data.plot_id or "", user_id=user["id"],
          detail={"intent": answer.intent, "grounded": answer.grounded,
                  "llm_used": out["llm"].get("used")})
    return out


SECTION_KEYS = ("answer", "why", "what_to_check", "what_to_do_now",
                "when_to_escalate", "sources")

SECTION_TASK = (
    "Answer the farmer's question in six short named parts. Each part is one or two plain "
    "sentences a farmer can read on a phone in a field.\n"
    "  answer            — what the farmer asked, answered directly\n"
    "  why               — the reasoning, naming the field records, weather or scans in the "
    "FACTS that lead to it\n"
    "  what_to_check     — what to walk out and look at, and where on the plant\n"
    "  what_to_do_now    — practical steps. Only a step the FACTS support. Never a chemical "
    "unless the FACTS record a count against a threshold\n"
    "  when_to_escalate  — the condition under which this should go to an expert\n"
    "  sources           — which records or references in the FACTS this rests on\n"
    "A part the FACTS cannot support must be left empty. An empty part is shown as absent, "
    "which is honest; a filled-in one that the FACTS do not support is not.\n\n"
    "FARMER'S QUESTION: ")


def _sectioned(db: Database, rt, plot, answer, data: AskIn,
               cfg: dict[str, Any]) -> dict[str, Any]:
    """The same answer, in named parts. Never raises past the caller's net."""
    facts = {
        "prahari_answer": answer.text,
        "sources": [s_.dict() if hasattr(s_, "dict") else s_ for s_ in (answer.sources or [])],
        "field": saathi_mod.field_facts(db, rt, plot),
    }
    verdict = llm_mod.structured(
        provider=cfg["provider"], key=cfg["key"], model=cfg.get("model"),
        task=SECTION_TASK + data.question, facts=facts,
        keys=SECTION_KEYS, lang=data.lang)
    if not verdict.get("used"):
        return {"available": False, "reason": verdict.get("reason", "")}
    fields = {k: v for k, v in (verdict.get("data") or {}).items() if v}
    if not fields:
        return {"available": False, "reason": "the model returned every part empty"}
    return {"available": True, "fields": fields,
            "model": verdict.get("model"),
            "note": ("Written by a language model from the records above. Every number in it "
                     "was checked against those records before it was shown.")}


def _rephrased(db: Database, rt, plot, answer, data: AskIn,
               cfg: dict[str, Any]) -> dict[str, Any]:
    """Hand the retrieved facts to the model and return its verdict.

    Split out so the caller can put one net around the whole of it — assembling
    the bundle and calling the provider are equally capable of failing, and
    neither may cost the farmer the answer PRAHARI already has.
    """
    facts = {
        "prahari_answer": answer.text,
        "sources": answer.sources,
        "supporting_data": answer.data,
        "field": saathi_mod.field_facts(db, rt, plot),
    }
    # An ungrounded answer is handed the field facts and nothing else. If those
    # do not answer the question the model must return INSUFFICIENT_CONTEXT,
    # and the refusal stands — which is the whole rule the farmer asked for:
    # PRAHARI's data, or no answer.
    if not answer.grounded:
        facts.pop("prahari_answer", None)
    return llm_mod.rephrase(
        provider=cfg["provider"], key=cfg["key"], model=cfg.get("model"),
        question=data.question, facts=facts, lang=data.lang)


# ── explaining what the vision model found ──────────────────────────────────
# These live in the saathi router because saathi IS the assistant: the key
# lookup, the cooldown, the guards and the fallback are all here already, and a
# second AI surface with its own copy of them is the duplicate system this
# project keeps warning about.


class ExplainIn(BaseModel):
    observation_id: str = Field(min_length=1, max_length=64)
    lang: str = "mr"


def _wx_for(rt, plot):
    """Today's weather if it is available, and nothing at all if it is not.

    The assistant is allowed to say what conditions MEAN. It is never handed a
    weather value PRAHARI does not have, which is the only reason it cannot
    report one.
    """
    from ..weather import WeatherUnavailable
    if not plot:
        return None, None
    try:
        return rt.risk.weather_series(plot), rt.risk.crop_stage(plot)
    except WeatherUnavailable as exc:
        return (exc.payload if exc.code == "insufficient_history" else None), None
    except Exception:
        log.exception("weather lookup failed while building assistant facts")
        return None, None


@router.post("/explain", summary="Explain a scan result in a farmer's words",
             description=(
                 "Words the diagnosis PRAHARI already produced. It does not diagnose: the "
                 "vision engine decides what was found and how sure it is, and this only "
                 "puts that, the published reference text for the problem and today's "
                 "conditions into plain sentences.\n\n"
                 "When the engine ABSTAINED the facts say so in those words, so the reply "
                 "reports that nothing was identified rather than describing a disease.\n\n"
                 "Always 200. `ai.used` is false when no key is configured or the provider "
                 "failed, and the retrieved text stands on its own."))
def explain(data: ExplainIn, user: dict[str, Any] = Depends(current_user),
            db: Database = Depends(db_dep)):
    from .observations import _observation_view
    obs = db.one("SELECT plot_id FROM observations WHERE id = :i",
                 {"i": data.observation_id})
    if not obs:
        from ..errors import not_found
        raise not_found("observation", data.observation_id)
    plot = visible_plot(db, user, obs["plot_id"])
    rt = get_runtime()
    view = _observation_view(db, data.observation_id)
    dx = view.get("diagnosis") or {}
    top = (dx.get("top") or {})
    problem_id = top.get("id") if not dx.get("abstain") else None

    wx, stage = _wx_for(rt, plot)
    facts = explain_mod.explain_facts(db, problem_id, dx, plot, wx, stage)
    out: dict[str, Any] = {
        "observation_id": data.observation_id,
        "problem": problem_id,
        "abstained": bool(dx.get("abstain")),
        "grounding": ("DETECTED" if problem_id else "NOT IDENTIFIED"),
        "facts_note": ("Assembled from this scan's own diagnosis, the published reference "
                       "text for the problem, and this field's conditions."),
        "ai": {"available": False, "used": False},
        "sections": {},
    }
    cfg = _llm_for(db, user)
    out["ai"]["available"] = bool(cfg)
    if cfg:
        try:
            verdict = llm_mod.structured(
                provider=cfg["provider"], key=cfg["key"], model=cfg.get("model"),
                task=("Explain this scan result to the farmer who took the photograph. "
                      "If nothing was identified, say that first and plainly."),
                facts=facts, keys=explain_mod.EXPLAIN_KEYS, lang=data.lang)
        except Exception as exc:                     # pragma: no cover - net
            log.exception("assistant explanation failed; serving the retrieved text")
            verdict = {"used": False, "reason": f"error: {type(exc).__name__}"}
        if verdict.get("used"):
            out["sections"] = {k: v for k, v in verdict["data"].items() if v}
            out["ai"] = {"available": True, "used": True, "provider": verdict["provider"],
                         "model": verdict["model"],
                         "note": ("Worded by a language model from PRAHARI's own records and "
                                  "references. Every number in it was checked against them "
                                  "first.")}
        else:
            out["ai"] = {"available": True, "used": False,
                         "reason": verdict.get("reason", "")}
    audit("saathi.explain", entity="observation", entity_id=data.observation_id,
          user_id=user["id"], detail={"problem": problem_id, "ai": out["ai"].get("used")})
    return out


@router.get("/flashcards", summary="Farmer-friendly cards about one problem",
            description=(
                "Eight short cards built from the reference text PRAHARI already holds for "
                "this problem, worded by the assistant when a key is configured and served "
                "as the retrieved text when it is not — so the cards never depend on a "
                "provider being up.\n\n"
                "A section the reference tables do not support comes back absent rather "
                "than filled in. No chemical product or dose appears: those reach a farmer "
                "through the recommendation screen, behind the threshold gate."))
def flashcards(problem: str = Query(..., min_length=1, max_length=64),
               plot_id: str | None = Query(None), lang: str = Query("mr"),
               user: dict[str, Any] = Depends(current_user),
               db: Database = Depends(db_dep)):
    from .. import reference
    if not reference.problem(problem):
        from ..errors import bad_request
        raise bad_request("unknown_problem",
                          f"'{problem}' is not a problem PRAHARI knows.")
    plot = visible_plot(db, user, plot_id) if plot_id else None
    rt = get_runtime()
    wx, stage = _wx_for(rt, plot)
    facts = explain_mod.flashcard_facts(problem, plot, wx, stage)

    cards = explain_mod.fallback_cards(problem, lang)
    source = "reference"
    ai: dict[str, Any] = {"available": False, "used": False}
    cfg = _llm_for(db, user)
    ai["available"] = bool(cfg)
    if cfg:
        try:
            verdict = llm_mod.structured(
                provider=cfg["provider"], key=cfg["key"], model=cfg.get("model"),
                task=("Write eight short flashcards for a farmer about this problem in "
                      "this field. Leave a card empty if the facts do not support it."),
                facts=facts, keys=explain_mod.FLASHCARD_KEYS, lang=lang)
        except Exception as exc:                     # pragma: no cover - net
            log.exception("assistant flashcards failed; serving the reference text")
            verdict = {"used": False, "reason": f"error: {type(exc).__name__}"}
        if verdict.get("used"):
            cards, source = verdict["data"], "assistant"
            ai = {"available": True, "used": True, "provider": verdict["provider"],
                  "model": verdict["model"]}
        else:
            ai = {"available": True, "used": False, "reason": verdict.get("reason", "")}

    ordered = [{"key": k,
                "label": explain_mod.FLASHCARD_LABELS[k][0],
                "label_mr": explain_mod.FLASHCARD_LABELS[k][1],
                "body": (cards.get(k) or "").strip()}
               for k in explain_mod.FLASHCARD_KEYS]
    return {
        "problem": problem,
        "problem_name": reference.problem_name(problem),
        "problem_name_mr": reference.problem_name(problem, "mr"),
        "crop": (plot or {}).get("crop"),
        "source": source,
        "ai": ai,
        # Empty cards are dropped here rather than in the browser, so "we have
        # nothing on this" is a decision the backend made and can be audited.
        "cards": [c for c in ordered if c["body"]],
        "policy": ("Built from published references and this field's own records. No "
                   "chemical product or dose appears on a card — those come from the "
                   "recommendation screen, which cites a verified label."),
    }


# ── the farmer's own key ────────────────────────────────────────────────────
def _llm_for(db: Database, user: dict[str, Any]) -> dict[str, Any] | None:
    """This account's key, else the deployment's, else nothing.

    The account's own key wins so that a farmer who has supplied one is never
    silently spending someone else's quota, and so that removing it actually
    removes it.
    """
    row = db.one("SELECT * FROM llm_keys WHERE user_id = :u", {"u": user["id"]})
    if row:
        key = llm_mod.decrypt_key(row["key_cipher"])
        if key:
            return {"provider": row["provider"], "key": key, "model": row.get("model"),
                    "source": "account"}
    s = get_settings()
    if s.llm_provider in llm_mod.PROVIDERS and s.llm_api_key:
        return {"provider": s.llm_provider, "key": s.llm_api_key,
                "model": s.llm_model, "source": "deployment"}
    return None


@router.get("/key", summary="Whether this account has a language-model key")
def key_status(user: dict[str, Any] = Depends(current_user),
               db: Database = Depends(db_dep)):
    """Never returns the key. The hint is the last four characters, which is
    enough for the owner to recognise which key is stored and no use to anyone
    else."""
    row = db.one("SELECT provider, model, hint, verified_at, updated_at"
                 "  FROM llm_keys WHERE user_id = :u", {"u": user["id"]})
    s = get_settings()
    return {
        "configured": bool(row),
        "key": row or None,
        "deployment_fallback": bool(s.llm_provider in llm_mod.PROVIDERS and s.llm_api_key),
        "providers": [
            {"id": "gemini", "label": "Google Gemini",
             "where": "aistudio.google.com/apikey", "default_model": "gemini-2.5-flash"},
            {"id": "openai", "label": "OpenAI",
             "where": "platform.openai.com/api-keys", "default_model": "gpt-4o-mini"},
        ],
        "policy": ("A key changes only how the answer is WORDED. AgriDoc still answers "
                   "from your field records, published references and verified label "
                   "claims — and still refuses when it has none. Every number in a "
                   "reworded answer is checked against those records before you see it, "
                   "and the reworded version is discarded if any number is not there."),
        "policy_mr": ("किल्लीमुळे उत्तराची फक्त भाषा सुधारते. AgriDoc अजूनही तुमच्या शेताच्या "
                      "नोंदी व प्रमाणित संदर्भांवरूनच उत्तर देतो — नसेल तर नकार देतो."),
    }


@router.put("/key", summary="Store a Gemini or OpenAI key for this account")
def key_set(body: KeyIn, user: dict[str, Any] = Depends(current_user),
            db: Database = Depends(db_dep)):
    """Verified against the provider before it is stored, so a mistyped key
    fails here rather than in the middle of a farmer's question."""
    ok, why = llm_mod.verify_key(body.provider, body.api_key, body.model)
    if not ok:
        raise bad_request("key_rejected", why or "The provider rejected this key.",
                          "पुरवठादाराने ही किल्ली नाकारली.")
    now = now_iso()
    db.execute("DELETE FROM llm_keys WHERE user_id = :u", {"u": user["id"]})
    db.execute(
        "INSERT INTO llm_keys (user_id, provider, model, key_cipher, hint, verified_at,"
        " created_at, updated_at) VALUES (:u,:p,:m,:c,:h,:v,:now,:now)",
        {"u": user["id"], "p": body.provider, "m": body.model,
         "c": llm_mod.encrypt_key(body.api_key), "h": llm_mod.hint(body.api_key),
         "v": now, "now": now})
    audit("saathi.key_set", entity="user", entity_id=user["id"], user_id=user["id"],
          detail={"provider": body.provider})
    return key_status(user, db)


@router.delete("/key", summary="Remove this account's language-model key")
def key_clear(user: dict[str, Any] = Depends(current_user),
              db: Database = Depends(db_dep)):
    db.execute("DELETE FROM llm_keys WHERE user_id = :u", {"u": user["id"]})
    audit("saathi.key_cleared", entity="user", entity_id=user["id"], user_id=user["id"])
    return key_status(user, db)


@router.get("/suggestions", summary="Questions Saathi can actually answer",
            description="Shown as chips, so a farmer is not left guessing what is in scope.")
def suggestions(lang: str = Query("mr")):
    return {
        "suggestions": saathi_mod.SUGGESTIONS.get(lang, saathi_mod.SUGGESTIONS["en"]),
        "scope": saathi_mod.SCOPE.get(lang, saathi_mod.SCOPE["en"]),
        # Bilingual, because this list is a promise and a promise nobody can
        # read is not one. It stayed English-only while the rest of the screen
        # was Marathi, which is exactly backwards for the audience it protects.
        "will_not_do": [
            {"en": "Invent a pesticide name, dose or spray interval",
             "mr": "औषधाचे नाव, मात्रा किंवा फवारणीचे अंतर स्वतःहून सांगणे"},
            {"en": "Give a legal restriction it cannot cite",
             "mr": "संदर्भाशिवाय कायदेशीर बंधन सांगणे"},
            {"en": "Estimate yield, loss or income",
             "mr": "उत्पादन, नुकसान किंवा उत्पन्नाचा अंदाज देणे"},
            {"en": "Diagnose from a description instead of a photograph and a count",
             "mr": "फोटो व मोजणीशिवाय फक्त वर्णनावरून निदान करणे"},
        ],
    }
