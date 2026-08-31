"""
PRAHARI · outbreak intelligence
════════════════════════════════════════════════════════════════════════════
Individual reports become geographic intelligence — and the LABEL on that
intelligence is graded by the evidence that actually exists.

    emerging cluster    ≥ 3 reports, ≥ 2 fields, growth over the window,
                        but no expert confirmation yet
    suspected hotspot   the above AND a Getis-Ord Gi* z > 1.96 (95%)
    confirmed hotspot   the above AND ≥ 3 expert-confirmed cases

Nothing is called a confirmed outbreak until an expert has confirmed cases in
it. "Outbreak" is a word that moves budgets and triggers state advisories; a
dashboard that spends it on three photographs is a dashboard nobody trusts the
second time.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from . import reference, spatial
from .clock import now_iso
from .clock import today as _today
from .db import Database, dumps

GRADES = {
    "none": {"label": "No cluster", "label_mr": "समूह नाही", "rank": 0},
    "emerging_cluster": {"label": "Emerging cluster", "label_mr": "उदयोन्मुख समूह", "rank": 1},
    "suspected_hotspot": {"label": "Suspected hotspot", "label_mr": "संशयित हॉटस्पॉट", "rank": 2},
    "confirmed_hotspot": {"label": "Confirmed hotspot", "label_mr": "पुष्ट हॉटस्पॉट", "rank": 3},
}

MIN_REPORTS = 3
MIN_FIELDS = 2
MIN_CONFIRMED = 3
GI_SIGNIFICANT = 1.96


class OutbreakService:
    def __init__(self, db: Database):
        self.db = db

    def _reports(self, problem: str, crop: str | None, days: int,
                 talukas: list[str] | None) -> list[dict[str, Any]]:
        since = (_today() - dt.timedelta(days=days)).isoformat()
        sql = ("SELECT o.id, o.plot_id, o.taluka, o.crop, o.observed_at, o.status,"
               " d.top_problem, d.confirmed, d.abstained"
               " FROM observations o JOIN diagnoses d ON d.observation_id = o.id"
               " WHERE substr(o.observed_at,1,10) >= :since AND o.status <> 'rejected'"
               " AND (d.top_problem = :prob OR d.confirmed = :prob)")
        params: dict[str, Any] = {"since": since, "prob": problem}
        if crop:
            sql += " AND o.crop = :crop"
            params["crop"] = crop
        rows = self.db.rows(sql + " ORDER BY o.observed_at", params)
        if talukas is not None:
            rows = [r for r in rows if r["taluka"] in talukas]
        return rows

    def hotspots(self, problem: str = "late_blight", *, crop: str | None = None,
                 days: int = 21, band_km: float = 22.0,
                 talukas: list[str] | None = None) -> dict[str, Any]:
        reports = self._reports(problem, crop, days, talukas)
        counts: dict[str, int] = {}
        for r in reports:
            counts[r["taluka"]] = counts.get(r["taluka"], 0) + 1
        # Gi* is a LOCAL statistic: it scores a unit against its neighbours, so it
        # must be computed over the whole district even when the officer may only
        # see part of it. Computing it over a two-taluka scope returned nothing at
        # all — silently, which is the worst way for a statistic to fail. Compute
        # over everything, then filter the ROWS to what this officer may see.
        hs = spatial.getis_ord(reference.TALUKAS, counts, band_km)
        if talukas is not None:
            hs = [h for h in hs if h["taluka"] in talukas]

        firsts: dict[str, int] = {}
        for r in reports:
            day = str(r["observed_at"])[:10]
            offset = (dt.date.fromisoformat(day) - _today()).days
            firsts[r["taluka"]] = min(firsts.get(r["taluka"], 0), offset)
        front = (spatial.spread_front(reference.TALUKAS, firsts)
                 if len(firsts) >= 3 else None)
        return {
            "problem": problem, "problem_name": reference.problem_name(problem),
            "crop": crop, "window_days": days, "band_km": band_km,
            "hotspots": hs, "front": front, "total_reports": len(reports),
            "statistic": ("Getis-Ord Gi* on incidence per 1,000 farm households, binary "
                          "distance-band weights with the focal unit included. |z| > 1.96 is a "
                          "95% hotspot. The statistic is computed across the whole district — a "
                          "local statistic needs its neighbours — and then filtered to the "
                          "talukas you are authorised to see."),
            "caveat": ("Gi* measures whether reports cluster more than chance would produce. "
                       "It does not measure disease — reports also cluster where the app is "
                       "used most, and that bias is real until coverage is even."),
        }

    def assess(self, taluka: str, problem: str, *, crop: str | None = None,
               days: int = 21, gi_z: float | None = None) -> dict[str, Any]:
        """The graded verdict for one taluka. This is the only function allowed
        to attach the words 'cluster' or 'hotspot' to anything."""
        reports = [r for r in self._reports(problem, crop, days, None)
                   if r["taluka"] == taluka]
        fields = {r["plot_id"] for r in reports}
        confirmed = [r for r in reports if r["confirmed"] == problem]
        day = _today()
        last72 = [r for r in reports
                  if (day - dt.date.fromisoformat(str(r["observed_at"])[:10])).days <= 3]
        prior72 = [r for r in reports
                   if 3 < (day - dt.date.fromisoformat(str(r["observed_at"])[:10])).days <= 6]
        growth = None
        if prior72:
            growth = round((len(last72) - len(prior72)) / len(prior72) * 100, 1)
        elif last72 and not prior72:
            growth = None       # a first appearance has no growth rate, and saying "+∞" is silly

        if gi_z is None:
            hs = self.hotspots(problem, crop=crop, days=days)["hotspots"]
            me = next((h for h in hs if h["taluka"] == taluka), None)
            gi_z = me["z"] if me else 0.0

        grade = "none"
        evidence: list[dict[str, Any]] = []
        if len(reports) >= MIN_REPORTS and len(fields) >= MIN_FIELDS:
            grade = "emerging_cluster"
            evidence.append({"test": "volume",
                             "detail": f"{len(reports)} reports from {len(fields)} distinct fields "
                                       f"in {days} days (threshold: {MIN_REPORTS} reports, "
                                       f"{MIN_FIELDS} fields)"})
            if gi_z is not None and gi_z > GI_SIGNIFICANT:
                grade = "suspected_hotspot"
                evidence.append({"test": "spatial",
                                 "detail": f"Getis-Ord Gi* z = {gi_z} (> {GI_SIGNIFICANT} is a "
                                           f"95% significant cluster)"})
            else:
                evidence.append({"test": "spatial",
                                 "detail": f"Gi* z = {gi_z} — not a statistically significant "
                                           f"cluster, so this stays an emerging cluster"})
            if len(confirmed) >= MIN_CONFIRMED and grade == "suspected_hotspot":
                grade = "confirmed_hotspot"
                evidence.append({"test": "expert",
                                 "detail": f"{len(confirmed)} expert-confirmed cases "
                                           f"(threshold: {MIN_CONFIRMED})"})
            else:
                evidence.append({"test": "expert",
                                 "detail": f"{len(confirmed)} expert-confirmed case(s) — "
                                           f"{MIN_CONFIRMED} are needed before PRAHARI will call "
                                           f"this confirmed"})
        else:
            evidence.append({"test": "volume",
                             "detail": f"{len(reports)} report(s) from {len(fields)} field(s) — "
                                       f"below the {MIN_REPORTS}-report, {MIN_FIELDS}-field floor "
                                       f"for calling anything a cluster"})

        radius = self._radius(reports)
        out = {
            "taluka": taluka, "taluka_name": reference.taluka_name(taluka),
            "problem": problem, "problem_name": reference.problem_name(problem),
            "crop": crop, "grade": grade, **GRADES[grade],
            "reports": len(reports), "fields": len(fields), "confirmed": len(confirmed),
            "gi_z": gi_z, "growth_pct_72h": growth, "radius_km": radius,
            "window_days": days,
            "evidence": evidence,
            "recommended_action": self._action(grade, len(reports), len(confirmed)),
            "wording_rule": ("PRAHARI grades a cluster by the evidence that exists: reports and "
                             "distinct fields make it 'emerging', a significant Gi* makes it "
                             "'suspected', and only expert confirmations make it 'confirmed'."),
        }
        if grade != "none":
            self._persist(out)
        return out

    def _radius(self, reports: list[dict[str, Any]]) -> float | None:
        talukas = {r["taluka"] for r in reports}
        pts = [reference.TALUKA_BY_ID[t] for t in talukas if t in reference.TALUKA_BY_ID]
        if len(pts) < 2:
            return None
        worst = 0.0
        for i, a in enumerate(pts):
            for b in pts[i + 1:]:
                worst = max(worst, spatial.haversine(a, b))
        return round(worst / 2, 1)

    def _action(self, grade: str, reports: int, confirmed: int) -> str:
        return {
            "none": "No action beyond routine surveillance.",
            "emerging_cluster": ("Send an officer to confirm two or three of these reports on the "
                                 "ground. Until a human confirms one, this is a cluster of "
                                 "photographs, not of disease."),
            "suspected_hotspot": ("Prioritise field inspection in this taluka and warn adjacent "
                                  "talukas to increase scouting. Do not issue a blanket spray "
                                  "advisory on this evidence."),
            "confirmed_hotspot": ("Issue a taluka-level advisory, brief the Krishi Sahayaks, and "
                                  "increase inspection frequency in adjacent talukas along the "
                                  "spread front."),
        }[grade]

    def _persist(self, assessment: dict[str, Any]) -> None:
        day = _today().isoformat()
        existing = self.db.one(
            "SELECT * FROM outbreak_events WHERE taluka=:t AND problem=:p AND closed_on IS NULL"
            " ORDER BY opened_on DESC", {"t": assessment["taluka"], "p": assessment["problem"]})
        params = {
            "reports": assessment["reports"], "confirmed": assessment["confirmed"],
            "gi": assessment["gi_z"], "growth": assessment["growth_pct_72h"],
            "radius": assessment["radius_km"], "grade": assessment["grade"],
            "ev": dumps(assessment["evidence"]),
        }
        if existing:
            self.db.execute(
                "UPDATE outbreak_events SET grade=:grade, reports=:reports, confirmed=:confirmed,"
                " gi_z=:gi, growth_pct_72h=:growth, radius_km=:radius, evidence=:ev WHERE id=:id",
                {**params, "id": existing["id"]})
        else:
            self.db.execute(
                "INSERT INTO outbreak_events (id, taluka, crop, problem, grade, reports, confirmed,"
                " gi_z, growth_pct_72h, radius_km, evidence, opened_on, created_at)"
                " VALUES (:id,:t,:crop,:p,:grade,:reports,:confirmed,:gi,:growth,:radius,:ev,:on,:now)",
                {**params, "id": "OB-" + uuid.uuid4().hex[:10].upper(),
                 "t": assessment["taluka"], "crop": assessment.get("crop") or "",
                 "p": assessment["problem"], "on": day, "now": now_iso()})

    def open_events(self, talukas: list[str] | None = None) -> list[dict[str, Any]]:
        rows = self.db.rows(
            "SELECT * FROM outbreak_events WHERE closed_on IS NULL ORDER BY grade DESC, reports DESC")
        if talukas is not None:
            rows = [r for r in rows if r["taluka"] in talukas]
        for r in rows:
            r["taluka_name"] = reference.taluka_name(r["taluka"])
            r["problem_name"] = reference.problem_name(r["problem"])
            r.update({k: v for k, v in GRADES.get(r["grade"], GRADES["none"]).items()
                      if k != "rank"})
        return rows
