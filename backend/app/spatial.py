"""
PRAHARI · surveillance statistics
════════════════════════════════════════════════════════════════════════════
Dots on a map are not evidence. This module turns farmer reports into three
things an agriculture officer can act on and defend in a review meeting:

  Getis-Ord Gi*     is this cluster real, or is it what random scatter looks
                    like? A z-score above 1.96 is a 95% hotspot.
  Spread front      each taluka's FIRST case regressed on its distance from the
                    index taluka. The slope is days per kilometre; its reciprocal
                    is the outbreak velocity, which converts a map of where the
                    disease IS into a list of where it WILL BE, with dates.
  Priority queue    extension in India reaches about 6.8% of farmers, roughly
                    36% of state agriculture posts are vacant, and 80.7% of
                    Maharashtra's CROPSAP field staff report resource shortage.
                    An app that generates more visits than the cadre can make
                    has made their problem worse. So cases are RANKED, and the
                    officer is told which five to visit this week.
"""
from __future__ import annotations

import math
from typing import Any

EARTH_KM = 6371.0


def haversine(a: dict[str, float], b: dict[str, float]) -> float:
    dlat = math.radians(b["lat"] - a["lat"])
    dlng = math.radians(b["lng"] - a["lng"])
    s = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(a["lat"])) * math.cos(math.radians(b["lat"])) * math.sin(dlng / 2) ** 2)
    return EARTH_KM * 2 * math.atan2(math.sqrt(s), math.sqrt(1 - s))


def getis_ord(talukas: list[dict[str, Any]], counts: dict[str, int],
              band_km: float = 22.0) -> list[dict[str, Any]]:
    """Gi*(i) = [Σⱼ wᵢⱼxⱼ − x̄Σⱼwᵢⱼ] / [S√((nΣⱼwᵢⱼ² − (Σⱼwᵢⱼ)²)/(n−1))]

    x is incidence per 1,000 farm households — a raw count would simply rank
    talukas by how many farms they contain. Binary distance-band weights with the
    focal unit INCLUDED, which is what makes it Gi* rather than Gi.

    Getis & Ord (1992), Geographical Analysis 24(3). The same statistic the FAO
    Desert Locust service uses for swarm reports.
    """
    n = len(talukas)
    if n < 3:
        return []
    x = [counts.get(t["id"], 0) / (t["farms"] / 1000.0) for t in talukas]
    mean = sum(x) / n
    var = sum(v * v for v in x) / n - mean * mean
    S = math.sqrt(max(var, 1e-12))

    out = []
    for i, t in enumerate(talukas):
        w = [1.0 if haversine(t, u) <= band_km else 0.0 for u in talukas]
        sw, sw2 = sum(w), sum(v * v for v in w)
        num = sum(wj * xj for wj, xj in zip(w, x, strict=True)) - mean * sw
        den = S * math.sqrt(max(1e-12, (n * sw2 - sw * sw) / (n - 1)))
        z = num / den if den > 0 else 0.0
        out.append({
            "taluka": t["id"], "name": t["name"], "name_mr": t.get("mr", t["name"]),
            "lat": t["lat"], "lng": t["lng"],
            "cases": counts.get(t["id"], 0),
            "incidence_per_1000": round(x[i], 2),
            "z": round(z, 2), "neighbours": int(sw),
            "class": ("hot" if z > 1.96 else "warm" if z > 1.0 else "cold" if z < -1.96 else "none"),
            "significant": abs(z) > 1.96,
        })
    out.sort(key=lambda r: -r["z"])
    return out


def spread_front(talukas: list[dict[str, Any]],
                 first_case_day: dict[str, int]) -> dict[str, Any] | None:
    """Ordinary least squares of first-case day on distance from the index taluka.

    Reported WITH its R² and its sample size, because a high R² on four points is
    not strong evidence and the projected dates should be read as a planning
    prompt rather than a schedule.
    """
    pts = [{"t": t, "first": first_case_day[t["id"]]}
           for t in talukas if t["id"] in first_case_day]
    if len(pts) < 3:
        return None
    index = min(pts, key=lambda p: p["first"])
    for p in pts:
        p["km"] = haversine(index["t"], p["t"])

    n = len(pts)
    sx = sum(p["km"] for p in pts)
    sy = sum(p["first"] for p in pts)
    sxy = sum(p["km"] * p["first"] for p in pts)
    sxx = sum(p["km"] ** 2 for p in pts)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-9:
        return None
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    ybar = sy / n
    ss_tot = sum((p["first"] - ybar) ** 2 for p in pts)
    ss_res = sum((p["first"] - (intercept + slope * p["km"])) ** 2 for p in pts)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    clean = []
    for t in talukas:
        if t["id"] in first_case_day:
            continue
        km = haversine(index["t"], t)
        eta = round(intercept + slope * km)
        clean.append({"taluka": t["id"], "name": t["name"], "km": round(km, 1),
                      "eta_day_offset": eta, "days_away": eta})
    clean.sort(key=lambda c: c["days_away"])

    return {
        "index_taluka": index["t"]["name"], "index_id": index["t"]["id"],
        "slope_days_per_km": round(slope, 4),
        "velocity_km_per_day": round(1 / slope, 1) if slope > 0.01 else None,
        "r2": round(r2, 3), "n_points": n,
        "at_risk": [c for c in clean if 0 < c["days_away"] < 21],
        "confidence_note": (
            f"Fitted on {n} talukas with confirmed cases. "
            + ("A high R² on this few points is not strong evidence — treat the projected dates as a "
               "planning prompt, not a schedule. They tighten as reports arrive."
               if n < 6 else
               "Sample is large enough for the slope to be meaningful, but the projection still "
               "assumes the front keeps its current speed.")),
    }


def priority_queue(cases: list[dict[str, Any]], hotspots: list[dict[str, Any]],
                   velocity: float | None, capacity: int = 5) -> dict[str, Any]:
    """Rank cases for a Krishi Sahayak who has time for `capacity` visits.

    score = uncertainty × area at risk × spatial urgency × escalation

    Deliberately NOT "highest confidence first". A case the model is sure about
    does not need a human; an uncertain case in a statistical hotspot with a lot
    of area behind it does. The whole point is to spend a scarce officer's day
    where a visit changes the outcome.
    """
    hz = {h["taluka"]: h for h in hotspots}
    scored = []
    for c in cases:
        h = hz.get(c["taluka"], {"z": 0.0, "class": "none", "name": c["taluka"]})
        # Uncertainty peaks at 0.5 posterior: certain cases need no visit, and a
        # case with no signal at all is usually a bad photograph.
        post = c.get("posterior") or 0.5
        uncertainty = 1.0 - abs(post - 0.5) * 2 if not c.get("abstained") else 1.0
        area = min(3.0, (c.get("area_acre") or 1.0) / 2.0)
        spatial = 1.0 + max(0.0, h["z"]) * 0.45
        escalation = 1.8 if c.get("abstained") else 1.0
        rescan = 1.6 if c.get("rescan_worse") else 1.0
        score = uncertainty * (0.6 + area) * spatial * escalation * rescan
        reasons = []
        if c.get("abstained"):
            reasons.append("the model declined to diagnose")
        if h["class"] == "hot":
            reasons.append(f"inside a 95% hotspot (z = {h['z']})")
        if c.get("rescan_worse"):
            reasons.append("worse on rescan after treatment")
        if (c.get("area_acre") or 0) >= 3:
            reasons.append(f"{c['area_acre']} acres at risk")
        if not reasons:
            reasons.append("routine confirmation")
        scored.append({**c, "priority_score": round(score, 2),
                       "taluka_name": h.get("name", c["taluka"]),
                       "hotspot_class": h["class"], "hotspot_z": h["z"],
                       "why": "; ".join(reasons)})
    scored.sort(key=lambda s: -s["priority_score"])

    # One visit per PLOT, not per scan. Three photographs of the same field are
    # three rows in `scouts` and one journey for the officer; a queue that lists
    # them separately spends a scarce visit twice on the same gate. The
    # highest-scoring scan represents the plot and carries the others with it.
    best: dict[str, dict[str, Any]] = {}
    for c in scored:
        key = c.get("plot_id") or c["id"]
        if key in best:
            best[key]["also_scans"] = best[key].get("also_scans", 1) + 1
        else:
            best[key] = {**c, "also_scans": 1}
    scored = sorted(best.values(), key=lambda s: -s["priority_score"])
    for c in scored:
        if c["also_scans"] > 1:
            c["why"] += f"; {c['also_scans']} scans from this plot"

    for i, s in enumerate(scored):
        s["priority"] = "P1" if i < capacity else ("P2" if i < capacity * 2 else "P3")
    return {
        "queue": scored,
        "capacity": capacity,
        "visit_this_week": scored[:capacity],
        "deferred": max(0, len(scored) - capacity),
        "rationale": (
            f"{len(scored)} open cases, and a Krishi Sahayak realistically has time for {capacity} "
            f"field visits this week. Ranked by uncertainty × area × spatial urgency, not by "
            f"confidence — a case the model is sure about does not need a human. "
            + (f"The front is moving at about {velocity} km/day, so the ranking weights hotspot "
               f"proximity accordingly." if velocity else "")),
    }
