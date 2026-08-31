"""PRAHARI · /api/saathi — the grounded agricultural assistant."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from .. import saathi as saathi_mod
from ..db import Database
from ..deps import current_user, db_dep, visible_plot
from ..obs import audit
from ..runtime import get_runtime

router = APIRouter(prefix="/api/saathi", tags=["assistant"])


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    plot_id: str | None = None
    lang: str = "mr"


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
    audit("saathi.ask", entity="plot", entity_id=data.plot_id or "", user_id=user["id"],
          detail={"intent": answer.intent, "grounded": answer.grounded})
    return answer.dict(data.lang)


@router.get("/suggestions", summary="Questions Saathi can actually answer",
            description="Shown as chips, so a farmer is not left guessing what is in scope.")
def suggestions(lang: str = Query("mr")):
    return {
        "suggestions": saathi_mod.SUGGESTIONS.get(lang, saathi_mod.SUGGESTIONS["en"]),
        "scope": saathi_mod.SCOPE.get(lang, saathi_mod.SCOPE["en"]),
        "will_not_do": [
            "Invent a pesticide name, dose or spray interval",
            "Give a legal restriction it cannot cite",
            "Estimate yield, loss or income",
            "Diagnose from a description instead of a photograph and a count",
        ],
    }
