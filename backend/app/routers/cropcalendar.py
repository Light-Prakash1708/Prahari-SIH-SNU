"""PRAHARI · /api/crop-calendar — the crop journey for one field.

One aggregation endpoint. It holds no agronomy: `cropcalendar.build` composes
services that already exist and are already tested. It is here so a phone on a
field boundary makes one request instead of seven, which is the whole reason
for its existence.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from .. import cropcalendar
from ..db import Database
from ..deps import current_user, db_dep, visible_plot
from ..runtime import get_runtime
from ..weather import WeatherUnavailable, to_http_error

router = APIRouter(prefix="/api", tags=["crop-calendar"])


@router.get("/crop-calendar/{plot_id}",
            summary="The crop journey — stage, threat windows, prevention window, history",
            description=(
                "Everything the calendar screen needs, in one request: the crop's own stage "
                "table resolved against this field's sowing date, the pest vulnerability of "
                "each stage read from the ICAR threshold tables' stage factors, the diseases "
                "currently firing on this field's weather, the prevention window, today's "
                "mission, and the field's own history.\n\n"
                "Disease bands appear only on the CURRENT stage. A disease fires when weather "
                "satisfies a published infection model, so a stage six weeks out cannot be "
                "coloured in without inventing the weather — and PRAHARI does not.\n\n"
                "Errors: 503 weather_unavailable — the prevention window is the point of this "
                "screen and cannot be computed without weather, so the endpoint fails rather "
                "than returning a calendar with the useful half missing."))
def crop_calendar(plot_id: str, lang: str = Query("en"),
                  user: dict[str, Any] = Depends(current_user),
                  db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    try:
        return cropcalendar.build(db, get_runtime(), plot, lang=lang)
    except WeatherUnavailable as exc:
        raise to_http_error(exc) from exc
