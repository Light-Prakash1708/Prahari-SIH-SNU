"""
PRAHARI · the field-visit planner
════════════════════════════════════════════════════════════════════════════
An officer has five visits this week. This turns a ranked queue into an order
to drive them in.

Nearest-neighbour from the officer's base, then a 2-opt pass. That is a
HEURISTIC and the response says so: the point is a sensible day, not a proven
optimum, and claiming optimality for a greedy tour is exactly the kind of small
lie that makes everything else suspect.
"""
from __future__ import annotations

from typing import Any

from . import reference, spatial


def _pt(item: dict[str, Any]) -> dict[str, float] | None:
    if item.get("lat") is not None and item.get("lng") is not None:
        return {"lat": float(item["lat"]), "lng": float(item["lng"])}
    t = reference.TALUKA_BY_ID.get(item.get("taluka") or "")
    return {"lat": t["lat"], "lng": t["lng"]} if t else None


def _dist(a: dict[str, float], b: dict[str, float]) -> float:
    return spatial.haversine(a, b)


def plan(stops: list[dict[str, Any]], base: dict[str, float] | None = None,
         capacity: int = 5) -> dict[str, Any]:
    usable = [s for s in stops if _pt(s)][:max(1, capacity)]
    if not usable:
        return {"sequence": [], "total_km": 0,
                "note": "No cases in your scope have a location recorded."}
    if base is None:
        first = _pt(usable[0])
        base = first

    remaining = list(usable)
    order: list[dict[str, Any]] = []
    cur = base
    while remaining:
        # Priority pulls a case forward even when it is not the nearest: a P1
        # case 12 km away beats a P3 case 2 km away, and the officer can see why.
        def cost(s, here=cur):
            weight = {"P0": 0.45, "P1": 0.6, "P2": 1.0, "P3": 1.6}.get(s.get("priority", "P2"), 1.0)
            return _dist(here, _pt(s)) * weight
        nxt = min(remaining, key=cost)
        remaining.remove(nxt)
        order.append(nxt)
        cur = _pt(nxt)

    order = _two_opt(order, base)
    total = 0.0
    cur = base
    seq = []
    for i, s in enumerate(order):
        p = _pt(s)
        leg = _dist(cur, p)
        total += leg
        seq.append({
            "position": i + 1,
            "observation_id": s.get("id") or s.get("observation_id"),
            "plot_id": s.get("plot_id"),
            "plot_name": s.get("plot_name"),
            "taluka": s.get("taluka"),
            "taluka_name": reference.taluka_name(s.get("taluka") or ""),
            "crop": s.get("crop"),
            "priority": s.get("priority", "P2"),
            "why": s.get("why"),
            "leg_km": round(leg, 1),
            "lat": p["lat"], "lng": p["lng"],
        })
        cur = p
    return {
        "sequence": seq,
        "total_km": round(total, 1),
        "stops": len(seq),
        "method": ("Nearest-neighbour from your starting point, weighted by case priority, then a "
                   "2-opt improvement pass."),
        "caveat": ("A planning suggestion, not an optimal route. Distances are straight-line "
                   "between field coordinates — real driving distance on Nashik district roads "
                   "will be longer, and PRAHARI does not pretend to know the roads."),
    }


def _two_opt(order: list[dict[str, Any]], base: dict[str, float],
             rounds: int = 40) -> list[dict[str, Any]]:
    if len(order) < 4:
        return order

    def tour_len(seq):
        cur, total = base, 0.0
        for s in seq:
            p = _pt(s)
            total += _dist(cur, p)
            cur = p
        return total

    best, best_len = order, tour_len(order)
    for _ in range(rounds):
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 2, len(best)):
                cand = best[:i + 1] + best[i + 1:j + 1][::-1] + best[j + 1:]
                length = tour_len(cand)
                if length < best_len - 1e-6:
                    best, best_len, improved = cand, length, True
        if not improved:
            break
    return best
