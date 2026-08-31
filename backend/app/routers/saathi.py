"""PRAHARI · /api/saathi — the grounded agricultural assistant."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from .. import llm as llm_mod
from .. import saathi as saathi_mod
from ..clock import now_iso
from ..config import get_settings
from ..db import Database
from ..deps import current_user, db_dep, visible_plot
from ..errors import bad_request
from ..obs import audit
from ..runtime import get_runtime

router = APIRouter(prefix="/api/saathi", tags=["assistant"])


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    plot_id: str | None = None
    lang: str = "mr"
    # A farmer with a key can turn the rewriting off for one question — useful
    # when they want to see the retrieved wording exactly as PRAHARI holds it.
    enhance: bool = True


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
        facts = {
            "prahari_answer": answer.text,
            "sources": answer.sources,
            "supporting_data": answer.data,
            "field": saathi_mod.field_facts(db, rt, plot),
        }
        # An ungrounded answer is handed the field facts and nothing else. If
        # those do not answer the question the model must return
        # INSUFFICIENT_CONTEXT, and the refusal stands — which is the whole
        # rule the farmer asked for: PRAHARI's data, or no answer.
        if not answer.grounded:
            facts.pop("prahari_answer", None)
        verdict = llm_mod.rephrase(
            provider=cfg["provider"], key=cfg["key"], model=cfg.get("model"),
            question=data.question, facts=facts, lang=data.lang)
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
            if verdict.get("rejected"):
                # Kept so a reviewer can see WHAT was thrown away. It is never
                # rendered as an answer.
                out["llm"]["discarded_draft"] = verdict["rejected"]

    audit("saathi.ask", entity="plot", entity_id=data.plot_id or "", user_id=user["id"],
          detail={"intent": answer.intent, "grounded": answer.grounded,
                  "llm_used": out["llm"].get("used")})
    return out


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
             "where": "aistudio.google.com/apikey", "default_model": "gemini-2.0-flash"},
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
