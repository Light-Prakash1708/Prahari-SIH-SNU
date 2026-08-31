"""
PRAHARI · the crop health score, and what changed
════════════════════════════════════════════════════════════════════════════
A single 0-100 number is the most dangerous thing in an agriculture app,
because it is the easiest thing to invent. So this one is built from four
terms that each come from an engine that already exists, and every term is
shown to the farmer with its own arithmetic.

    score = 100 − disease − pest − weather − nearby

  disease   one published infection model that has FIRED costs 18; one that
            the forecast says will fire costs 9. Capped at 40, because a field
            with three diseases is not three times worse than a field with one —
            it is one field you have to walk.
  pest      a trap count over the economic threshold costs 20 when the pest is
            at its damaging life stage and 12 when it is not — adults flying at
            twice the threshold is a warning worth having a few days early.
            Over half the threshold at the damaging stage, 10. At the damaging
            stage with no count taken at all, 6, because not knowing is itself
            a risk.
  weather   4 per forecast day on which any model crosses, capped at 16.
  nearby    12 if this taluka is a statistically significant Gi* hotspot, 6 if
            elevated. Capped at 14.

Nothing here is tuned to make a demo look good. The weights are ordinal — they
encode "a confirmed threshold crossing matters more than a forecast" — and that
ordering is the only claim being made. The UI says so.
"""
from __future__ import annotations

import json
from typing import Any

CAPS = {"disease": 40.0, "pest": 30.0, "weather": 16.0, "nearby": 14.0}

BANDS = [
    (85, "safe", "Safe", "सुरक्षित"),
    (70, "watch", "Watch", "लक्ष ठेवा"),
    (50, "rising", "Rising", "धोका वाढतोय"),
    (0, "high", "High risk", "जास्त धोका"),
]


def band_for(score: float) -> dict[str, str]:
    for floor, key, label, mr in BANDS:
        if score >= floor:
            return {"key": key, "label": label, "label_mr": mr}
    return {"key": "high", "label": "High risk", "label_mr": "जास्त धोका"}


def compute(board: list[dict], forecast: list[dict], trap_state: list[dict],
            nearby_z: float | None) -> dict[str, Any]:
    """board  — the risk board from /api/risk
       forecast — per-day levels from risk_forecast()
       trap_state — latest count per pest with its effective threshold
       nearby_z — this taluka's Getis-Ord Gi* z-score, or None"""
    terms: list[dict[str, Any]] = []

    # ── disease ────────────────────────────────────────────────────────────
    disease = 0.0
    for b in board:
        if b.get("kind") != "disease":
            continue
        if b.get("fired"):
            disease += 18
            terms.append({"group": "disease", "cost": 18,
                          "why": f"{b['name']} — {b.get('model')} has fired"})
        elif b.get("level") == "rising":
            disease += 9
            terms.append({"group": "disease", "cost": 9,
                          "why": f"{b['name']} — forecast crosses on {b.get('lead_day')}"})
    disease = min(disease, CAPS["disease"])

    # ── pest ───────────────────────────────────────────────────────────────
    pest = 0.0
    for t in trap_state:
        dmg, n, etl_v = t.get("damaging"), t.get("count"), t["etl"]
        if n is None:
            if dmg:
                pest += 6
                terms.append({"group": "pest", "cost": 6,
                              "why": f"{t['name']} is at its damaging stage and no trap count has been taken"})
            continue
        if n >= etl_v:
            # A count over threshold matters whether or not the pest is at its
            # damaging stage today. An earlier version skipped it entirely when
            # the GDD model said "adults flying" — but adults flying at twice the
            # threshold is precisely the warning worth having, a few days early.
            cost = 20 if dmg else 12
            pest += cost
            terms.append({"group": "pest", "cost": cost,
                          "why": (f"{t['name']} at {n:g} {t['unit']} — over the threshold of {etl_v:g}"
                                  + ("" if dmg else f", and although it is currently "
                                     f"'{t.get('stage','')}', that count is what the damaging stage "
                                     f"is built from"))})
        elif dmg and n >= etl_v * 0.5:
            pest += 10
            terms.append({"group": "pest", "cost": 10,
                          "why": f"{t['name']} at {n:g} {t['unit']} — over half the threshold of {etl_v:g}"})
    pest = min(pest, CAPS["pest"])

    # ── weather ────────────────────────────────────────────────────────────
    crossing = [f for f in forecast if f["level"] in ("high", "rising") and f["offset"] > 0]
    weather = min(len(crossing) * 4.0, CAPS["weather"])
    if crossing:
        terms.append({"group": "weather", "cost": weather,
                      "why": f"{len(crossing)} of the next {len([f for f in forecast if f['offset']>0])} "
                             f"days cross an infection threshold"})

    # ── nearby ─────────────────────────────────────────────────────────────
    nearby = 0.0
    if nearby_z is not None:
        if nearby_z > 1.96:
            nearby = 12.0
            terms.append({"group": "nearby", "cost": 12,
                          "why": f"this taluka is a statistically significant hotspot (Gi* z = {nearby_z})"})
        elif nearby_z > 1.0:
            nearby = 6.0
            terms.append({"group": "nearby", "cost": 6,
                          "why": f"nearby reports are elevated (Gi* z = {nearby_z})"})
    nearby = min(nearby, CAPS["nearby"])

    score = max(0.0, 100.0 - disease - pest - weather - nearby)
    b = band_for(score)
    return {
        "score": round(score),
        "band": b["key"], "band_label": b["label"], "band_label_mr": b["label_mr"],
        "components": {
            "disease": {"penalty": round(disease), "cap": CAPS["disease"],
                        "band": _sub_band(disease, CAPS["disease"])},
            "pest": {"penalty": round(pest), "cap": CAPS["pest"],
                     "band": _sub_band(pest, CAPS["pest"])},
            "weather": {"penalty": round(weather), "cap": CAPS["weather"],
                        "band": _sub_band(weather, CAPS["weather"])},
            "nearby": {"penalty": round(nearby), "cap": CAPS["nearby"],
                       "band": _sub_band(nearby, CAPS["nearby"])},
        },
        "terms": terms,
        "method": ("score = 100 − disease − pest − weather − nearby. Every term comes from an engine "
                   "you can open: the published infection models, the economic threshold table, the "
                   "weather forecast and the Getis-Ord hotspot statistic. The weights are ordinal — "
                   "they encode that a confirmed threshold crossing matters more than a forecast — "
                   "and that ordering is the only claim being made."),
    }


def _sub_band(penalty: float, cap: float) -> str:
    if cap <= 0:
        return "safe"
    r = penalty / cap
    return "safe" if r < 0.2 else "watch" if r < 0.5 else "rising" if r < 0.8 else "high"


# ── what changed since last time ────────────────────────────────────────────
def diff(now: dict[str, Any], before: dict[str, Any] | None,
         days_since: int | None) -> dict[str, Any]:
    """The screen a returning farmer sees first. If there is no previous
    snapshot we say so rather than inventing a delta of zero — "no change"
    and "we have never looked before" are different sentences."""
    if not before:
        return {"first_visit": True,
                "message": "This is the first health check on this field. Come back tomorrow and "
                           "PRAHARI will show you what moved.",
                "message_mr": "या शेताची ही पहिली तपासणी आहे. उद्या परत या — काय बदलले ते दिसेल.",
                "rows": [], "headline": None}

    def d(k):
        return round(before["components"][k]["penalty"] - now["components"][k]["penalty"])

    rows = [
        {"key": "disease", "label": "Disease risk", "label_mr": "रोगाचा धोका", "delta": -d("disease")},
        {"key": "pest", "label": "Pest risk", "label_mr": "किडीचा धोका", "delta": -d("pest")},
        {"key": "weather", "label": "Weather risk", "label_mr": "हवामान धोका", "delta": -d("weather")},
        {"key": "nearby", "label": "Nearby outbreak", "label_mr": "जवळचा प्रादुर्भाव", "delta": -d("nearby")},
    ]
    score_delta = round(now["score"] - before["score"])
    moved = [r for r in rows if r["delta"] != 0]
    moved.sort(key=lambda r: -abs(r["delta"]))

    if not moved:
        head = "Nothing has moved since your last check."
        head_mr = "मागच्या तपासणीनंतर काहीही बदललेले नाही."
        reason = None
    else:
        top = moved[0]
        direction = "up" if top["delta"] > 0 else "down"
        head = (f"Crop health {'fell' if score_delta < 0 else 'rose'} {abs(score_delta)} points."
                if score_delta else "Crop health is unchanged, but the reasons behind it have moved.")
        head_mr = (f"पीक आरोग्य {abs(score_delta)} अंकांनी {'घटले' if score_delta < 0 else 'वाढले'}."
                   if score_delta else "पीक आरोग्य तेवढेच, पण कारणे बदलली आहेत.")
        # The reason is the largest-moving term, quoted from its own why-string.
        term = next((t for t in (now["terms"] if top["delta"] > 0 else before["terms"])
                     if t["group"] == top["key"]), None)
        reason = (f"Mainly {top['label'].lower()}: {term['why']}." if term
                  else f"Mainly {top['label'].lower()}, {direction} {abs(top['delta'])} points.")

    return {
        "first_visit": False, "days_since": days_since,
        "score_delta": score_delta, "rows": rows,
        "headline": head, "headline_mr": head_mr, "reason": reason,
        "message": None,
    }


# ── persistence helpers ─────────────────────────────────────────────────────
def load_snapshot(con, plot_id: str, day: str) -> dict[str, Any] | None:
    r = con.execute("SELECT * FROM health_snapshots WHERE plot_id=? AND day=?",
                    (plot_id, day)).fetchone()
    if not r:
        return None
    return _unpack(r)


def previous_snapshot(con, plot_id: str, before_day: str) -> dict[str, Any] | None:
    r = con.execute("""SELECT * FROM health_snapshots WHERE plot_id=? AND day < ?
                       ORDER BY day DESC LIMIT 1""", (plot_id, before_day)).fetchone()
    if not r:
        return None
    return _unpack(r)


def _unpack(r) -> dict[str, Any]:
    d = dict(r)
    drivers = json.loads(d.get("drivers") or "{}")
    return {"day": d["day"], "score": d["score"], "terms": drivers.get("terms", []),
            "components": drivers.get("components", {
                "disease": {"penalty": d["disease"]}, "pest": {"penalty": d["pest"]},
                "weather": {"penalty": d["weather"]}, "nearby": {"penalty": d["nearby"]}})}


def save_snapshot(con, plot_id: str, day: str, h: dict[str, Any]) -> None:
    c = h["components"]
    con.execute("""INSERT INTO health_snapshots (plot_id, day, score, disease, pest, weather, nearby, drivers)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(plot_id, day) DO UPDATE SET
                     score=excluded.score, disease=excluded.disease, pest=excluded.pest,
                     weather=excluded.weather, nearby=excluded.nearby, drivers=excluded.drivers""",
                (plot_id, day, h["score"], c["disease"]["penalty"], c["pest"]["penalty"],
                 c["weather"]["penalty"], c["nearby"]["penalty"],
                 json.dumps({"terms": h["terms"], "components": c})))
    con.commit()
