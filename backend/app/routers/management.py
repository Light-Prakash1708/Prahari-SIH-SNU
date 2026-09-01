"""
PRAHARI · /api/management — the "Should I spray?" screen, in one call.

HTTP only. Everything is composed in `app/management.py`, which itself owns no
agronomy; this file authenticates, confirms the field belongs to the caller,
and shapes the answer.

The one write here is a disease assessment: the field walk that a disease needs
in place of a trap count. It is idempotent on `client_ref` for the same offline
queue every other write on this app uses.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import management as mgmt
from .. import reference
from ..clock import now_iso
from ..clock import today as _today
from ..db import Database
from ..deps import current_user, db_dep, owned_plot, visible_plot
from ..errors import bad_request
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import DiseaseAssessmentIn
from ..weather import WeatherUnavailable

router = APIRouter(prefix="/api/management", tags=["management"])


@router.get("/{plot_id}", summary="Everything the management screen needs")
def management(plot_id: str, target: str | None = Query(None),
               lang: str = Query("mr"),
               user: dict[str, Any] = Depends(current_user),
               db: Database = Depends(db_dep)):
    """The decision, its evidence, the ladder, the trend, the day's work and the
    open follow-up — assembled from services that already produce each of them.

    Errors: 403 — you may only ask about your own field.
            503 — weather is unavailable, and PRAHARI does not invent it.
    """
    plot = visible_plot(db, user, plot_id)
    try:
        return mgmt.build(db, get_runtime(), plot, target, lang)
    except WeatherUnavailable as exc:
        from ..errors import unavailable
        raise unavailable("weather_unavailable", str(exc),
                          "हवामान माहिती उपलब्ध नाही.") from exc


@router.post("/{plot_id}/assessment", status_code=201,
             summary="Record a field assessment for a disease")
def record_assessment(plot_id: str, data: DiseaseAssessmentIn,
                      user: dict[str, Any] = Depends(current_user),
                      db: Database = Depends(db_dep)):
    """A disease has no trap to count, so this is what a farmer records instead:
    how many plants they walked, and how many of those showed the symptom.

    Incidence is derived from those two numbers and nothing else. The API does
    not accept a percentage — a percentage that arrives ready-made cannot be
    checked, and the whole point of this record is that a farmer or an
    agronomist can redo the division.
    """
    plot = owned_plot(db, user, plot_id)
    if data.plants_affected > data.plants_inspected:
        raise bad_request(
            "affected_exceeds_inspected",
            "More plants are marked affected than were inspected.",
            "तपासलेल्या झाडांपेक्षा बाधित झाडांची संख्या जास्त आहे.")
    problem = reference.problem(data.problem)
    if not problem:
        raise bad_request("unknown_problem", f"'{data.problem}' is not a problem PRAHARI knows.")

    if data.client_ref:
        seen = db.one("SELECT id FROM disease_assessments WHERE plot_id = :p"
                      " AND client_ref = :c", {"p": plot_id, "c": data.client_ref})
        if seen:
            return {"assessment": mgmt.latest_assessment(db, plot_id, data.problem),
                    "duplicate": True}

    rt = get_runtime()
    stage = rt.risk.crop_stage(plot)
    cycle = rt.risk.active_cycle(plot_id)
    aid = "DA-" + uuid.uuid4().hex[:10].upper()
    db.execute(
        "INSERT INTO disease_assessments (id, plot_id, cycle_id, problem, crop, crop_stage,"
        " plants_inspected, plants_affected, spread_band, part, note, assessed_on,"
        " client_ref, created_at)"
        " VALUES (:id,:p,:cy,:q,:crop,:cs,:ins,:aff,:band,:part,:note,:on,:ref,:now)",
        {"id": aid, "p": plot_id, "cy": (cycle or {}).get("id"), "q": data.problem,
         "crop": plot["crop"], "cs": stage.get("stage"),
         "ins": data.plants_inspected, "aff": data.plants_affected,
         "band": data.spread_band, "part": data.part, "note": data.note,
         "on": (data.assessed_on or _today()).isoformat(),
         "ref": data.client_ref, "now": now_iso()})
    audit("management.assessment", entity="plot", entity_id=plot_id, user_id=user["id"],
          detail={"problem": data.problem, "inspected": data.plants_inspected,
                  "affected": data.plants_affected})
    return {"assessment": mgmt.latest_assessment(db, plot_id, data.problem),
            "duplicate": False}
