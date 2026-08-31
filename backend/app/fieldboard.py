"""
PRAHARI · the multi-field board — which of my fields needs me first.

A farmer with one field opens the app and sees that field. A farmer with four
had to open each one in turn to find out which was in trouble, which is exactly
the moment an early-warning system stops warning early: the field that needed
attention was the third one they would have checked.

So this is one call that answers, for every field the caller owns:

    what is growing, and how far into the season
    what its crop-health score is, and which way it moved
    what it is asking for today, and how urgently
    when it was last actually looked at

and orders the fields by consequence rather than by name, so the top card is
the field to walk to.

It owns no agronomy. Every number here is produced by the same services that
produce the single-field screens — `risk.field_health` and `agenda` — so a
score on this board and the score on that field's home screen cannot disagree.
The ordering is the only judgement in the file, and it is a sort on values
those services already returned.

The cost is real: field health runs the infection models over a weather window
per field. That is why `attention` is computed here and cached by the frontend
like any other read, and why the per-field detail stays behind the card.
"""
from __future__ import annotations

import contextlib
import datetime as dt
from typing import Any

from . import reference
from .agenda import TONE_ACT, TONE_URGENT, agenda
from .clock import today as _today
from .db import Database
from .weather import WeatherUnavailable

# The order a farmer should walk their fields in. Urgency first, then the
# health score ascending, then the season — an early crop is cheaper to save
# than one three days from harvest, but only as a tie-break.
_TONE_RANK = {TONE_URGENT: 0, TONE_ACT: 1, "calm": 2, "none": 3}


def _last_seen(db: Database, plot_id: str) -> dict[str, Any] | None:
    """When this field was last actually looked at — a scan, a trap count or a
    soil test. Not when the app was opened: opening an app is not scouting."""
    rows = []
    for sql, kind in (
        ("SELECT MAX(observed_at) AS at FROM observations WHERE plot_id = :p", "scan"),
        ("SELECT MAX(o.counted_on) AS at FROM trap_observations o"
         " JOIN traps t ON t.id = o.trap_id WHERE t.plot_id = :p", "trap count"),
        ("SELECT MAX(tested_on) AS at FROM soil_tests WHERE plot_id = :p", "soil test"),
    ):
        at = db.scalar(sql, {"p": plot_id})
        if at:
            rows.append({"kind": kind, "at": str(at)[:10]})
    if not rows:
        return None
    best = max(rows, key=lambda r: r["at"])
    # A malformed date in an old row costs the "days ago" line, not the card.
    with contextlib.suppress(ValueError):
        best["days_ago"] = (_today() - dt.date.fromisoformat(best["at"])).days
    return best


def _cycle(db: Database, plot_id: str) -> dict[str, Any] | None:
    return db.one(
        "SELECT id, crop, sown_on, ended_on FROM crop_cycles WHERE plot_id = :p"
        " AND ended_on IS NULL ORDER BY sown_on DESC LIMIT 1", {"p": plot_id})


def _trend(db: Database, plot_id: str, score: float | None) -> dict[str, Any] | None:
    """Which way the score moved since the previous recorded snapshot.

    Returns None rather than 'steady' when there is only one snapshot: a field
    seen once has no trend, and drawing a flat arrow for it would be inventing
    a reading.
    """
    rows = db.rows(
        "SELECT day, score FROM health_snapshots WHERE plot_id = :p"
        " ORDER BY day DESC LIMIT 2", {"p": plot_id})
    if len(rows) < 2 or score is None:
        return None
    prev = rows[1]["score"]
    delta = round(score - prev)
    return {"delta": delta, "since": rows[1]["day"],
            "direction": "up" if delta > 1 else "down" if delta < -1 else "steady"}


def board(db: Database, rt, plots: list[dict[str, Any]], *,
          lang: str = "mr") -> dict[str, Any]:
    """One row per field, ordered by which needs attention first."""
    cards: list[dict[str, Any]] = []
    unavailable = 0

    for plot in plots:
        stage = reference.crop_stage(plot["crop"], plot.get("sown_on"), _today())
        card: dict[str, Any] = {
            "plot_id": plot["id"],
            "name": plot["name"],
            "crop": plot["crop"],
            "crop_label": reference.CROPS.get(plot["crop"], {}).get("name", plot["crop"]),
            "crop_label_mr": reference.CROPS.get(plot["crop"], {}).get("mr"),
            "crop_em": reference.CROPS.get(plot["crop"], {}).get("em", "🌱"),
            "area_acre": plot.get("area_acre"),
            "taluka_name": reference.taluka_name(plot.get("taluka") or ""),
            "village": plot.get("village"),
            "sown_on": plot.get("sown_on"),
            "crop_stage": stage,
            "cycle": _cycle(db, plot["id"]),
            "last_seen": _last_seen(db, plot["id"]),
        }

        # Weather can be unavailable for one field and fine for another — they
        # are different coordinates. A field without it is shown with its
        # records and no score, never with a score standing in for one.
        try:
            # `field_health` returns the whole picture — health, forecast,
            # headline, board — and the score lives one level in.
            full = rt.risk.field_health(plot)
            h = full["health"]
            day = agenda(db, rt, plot, health=full, lang=lang)
        except WeatherUnavailable as exc:
            unavailable += 1
            card.update({
                "score": None, "band": None, "trend": None,
                "attention": "none", "items": [], "item_count": 0,
                "unavailable": ("No weather is available for this field's coordinates right "
                                "now, so PRAHARI cannot score it. Nothing is estimated."),
                "unavailable_detail": str(exc)[:160],
            })
            cards.append(card)
            continue

        score = h.get("score")
        top = day["items"][0] if day["items"] else None
        card.update({
            "score": round(score) if score is not None else None,
            "band": h.get("band"),
            "band_label": h.get("band_label"),
            "band_label_mr": h.get("band_label_mr"),
            "headline": (full.get("headline") or {}).get("title"),
            "headline_mr": (full.get("headline") or {}).get("title_mr"),
            "trend": _trend(db, plot["id"], score),
            "attention": top["tone"] if top else "none",
            "item_count": day.get("count", 0),
            # Two items, not six. This is a board for choosing which field to
            # walk to; the full list is on that field's own screen.
            "items": [{k: v for k, v in i.items()
                       if k in ("key", "tone", "icon", "title", "title_mr")}
                      for i in day["items"][:2]],
            "all_clear": day.get("all_clear"),
        })
        cards.append(card)

    cards.sort(key=lambda c: (
        _TONE_RANK.get(c.get("attention") or "none", 3),
        c["score"] if c.get("score") is not None else 101,
        -(c.get("crop_stage") or {}).get("days", 0),
    ))

    needs = [c for c in cards if c.get("attention") in (TONE_URGENT, TONE_ACT)]
    return {
        "fields": cards,
        "count": len(cards),
        "needs_attention": len(needs),
        "weather_unavailable": unavailable,
        "order": ("Ordered by what each field is asking for today, then by crop-health score. "
                  "The field at the top is the one to walk to first."),
        "order_mr": ("आज प्रत्येक शेताला काय हवे आहे त्यानुसार, नंतर पीक आरोग्य गुणांनुसार "
                     "क्रम. सर्वात वरचे शेत आधी पाहावे."),
        "method": ("Each score and each item comes from the same services that produce that "
                   "field's own screen — the published infection models on that field's "
                   "weather, its own trap counts, its own follow-ups. Nothing on this board "
                   "is computed differently because there are several fields."),
        "method_mr": ("प्रत्येक गुण व सूचना त्याच सेवांमधून येतात ज्या त्या शेताच्या स्वतःच्या "
                      "पडद्यावर दिसतात. अनेक शेते असल्यामुळे इथे काहीही वेगळे मोजले जात नाही."),
    }
