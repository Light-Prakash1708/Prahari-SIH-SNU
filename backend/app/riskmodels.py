"""
PRAHARI · published infection models
════════════════════════════════════════════════════════════════════════════
These are the reason this is an EARLY-warning system rather than a detection
app. Every model here fires from weather alone, days before a symptom exists.
A photograph can only confirm what the farmer can already see.

Each model is implemented exactly as published, and each returns the sentence
that explains WHY — an alert with no reason gets ignored the second time.

References
  Hutton Criteria      AHDB Fight Against Blight, adopted 2017, replacing the
                       Smith Period. Two consecutive days, each with a minimum
                       temperature >= 10 C and >= 6 hours at RH >= 90%.
  TOMCAST              Disease Severity Values from leaf-wetness hours and the
                       mean temperature during wetness; cumulative 15-20 DSV
                       since the last application justifies a fungicide.
  Gubler-Thomas        UC IPM grape powdery mildew risk index, 0-100.
  The 3-10 rule        Grape downy mildew primary infection: shoots >= 10 cm,
                       temperature >= 10 C, >= 10 mm rain within 24-48 h.
  Growing degree days  GDD = sum of max(0, mean temp - T_base). Per-pest T_base
                       and thermal requirement per generation decide which life
                       stage is in the field right now.
"""
from __future__ import annotations

import builtins
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ModelResult:
    model: str
    fired: bool
    level: str                          # low | watch | rising | high
    detail: str
    detail_mr: str = ""
    value: float | None = None
    threshold: float | None = None
    lead_day: str | None = None      # the forecast day it fires, if future
    series: list[builtins.dict[str, Any]] = field(default_factory=list)

    def dict(self):
        return asdict(self)


# ── Hutton Criteria ─────────────────────────────────────────────────────────
def hutton(days: list[dict]) -> ModelResult:
    """days: [{label,tmin,rh90_hours,future}], oldest first."""
    qual = [(d["tmin"] >= 10 and d["rh90_hours"] >= 6) for d in days]
    hits, run, best = [], 0, 0
    for i, ok in enumerate(qual):
        run = run + 1 if ok else 0
        best = max(best, run)
        if run >= 2:
            hits.append(days[i])
    past = [h for h in hits if not h.get("future")]
    fwd = [h for h in hits if h.get("future")]
    fired = len(past) > 0
    last = past[-1] if past else None
    lead = fwd[0]["label"] if fwd and not fired else None

    if fired:
        detail = (f"Two consecutive Hutton days ending {last['label']} — night minimum "
                  f"{last['tmin']} °C (needs ≥10) and {last['rh90_hours']} h at RH ≥90% (needs ≥6). "
                  f"Infection is under way; first lesions appear in three to five days.")
        detail_mr = (f"{last['label']} रोजी सलग दोन हटन दिवस — किमान तापमान {last['tmin']} °से, "
                     f"{last['rh90_hours']} तास आर्द्रता ९०%+. संसर्ग सुरू; ३-५ दिवसांत डाग दिसतील.")
    elif lead:
        detail = (f"Not yet — but the forecast crosses the Hutton criterion on {lead}. "
                  f"This is the window to act preventively, before any symptom exists.")
        detail_mr = f"अजून नाही — पण {lead} रोजी हटन निकष ओलांडला जाईल. प्रतिबंधात्मक उपाय आताच करा."
    else:
        detail = (f"No Hutton period. Longest qualifying run is {best} of the 2 consecutive days "
                  f"required. There is nothing to spray for.")
        detail_mr = f"हटन कालावधी नाही ({best}/२ दिवस). फवारणीची गरज नाही."

    return ModelResult(
        model="Hutton Criteria", fired=fired,
        level="high" if fired else ("rising" if lead else "low"),
        detail=detail, detail_mr=detail_mr, value=float(best), threshold=2.0, lead_day=lead,
        series=[{"label": d["label"], "tmin": d["tmin"], "rh90": d["rh90_hours"],
                 "ok": q, "future": d.get("future", False)} for d, q in zip(days, qual, strict=True)])


# ── TOMCAST ─────────────────────────────────────────────────────────────────
# The published lookup, verbatim. Rows are temperature bands during leaf
# wetness; breakpoints are wetness hours; the index of the first breakpoint not
# exceeded is the day's DSV.
_TOMCAST = [(13, 17, [6, 15, 20, 25]),
            (18, 20, [3, 8, 15, 22]),
            (21, 25, [2, 5, 12, 20]),
            (26, 29, [3, 8, 15, 22])]


def dsv(temp_c: float, wet_h: float) -> int:
    if temp_c < 13 or temp_c > 29 or wet_h <= 0:
        return 0
    for lo, hi, breaks in _TOMCAST:
        if lo <= temp_c <= hi:
            for i, b in enumerate(breaks):
                if wet_h <= b:
                    return i
            return 4
    return 0


def tomcast(days: list[dict], since_spray_index: int = 0, threshold: int = 15) -> ModelResult:
    cum, series, cross = 0, [], None
    for i, d in enumerate(days):
        v = dsv(d["tmean"], d["leaf_wet_hours"]) if i >= since_spray_index else 0
        cum += v
        series.append({"label": d["label"], "dsv": v, "cum": cum,
                       "future": d.get("future", False)})
        if cum >= threshold and cross is None:
            cross = d["label"]
    fired = any(s["cum"] >= threshold and not s["future"] for s in series)
    lead = None if fired else cross
    detail = (f"Cumulative DSV since the last application is {cum} against the {threshold} that "
              f"justifies a fungicide. " +
              ("Threshold crossed — a spray is economically warranted." if fired else
               (f"The forecast crosses it on {lead}." if lead else
                "Below threshold — a spray now buys nothing.")))
    detail_mr = (f"शेवटच्या फवारणीनंतर एकूण DSV {cum}/{threshold}. " +
                 ("मर्यादा ओलांडली — फवारणी आवश्यक." if fired else "मर्यादेखाली — फवारणीची गरज नाही."))
    return ModelResult(model="TOMCAST", fired=fired,
                       level="high" if fired else ("rising" if lead else "low"),
                       detail=detail, detail_mr=detail_mr,
                       value=float(cum), threshold=float(threshold), lead_day=lead, series=series)


# ── Gubler-Thomas ───────────────────────────────────────────────────────────
def gubler_thomas(days: list[dict]) -> ModelResult:
    idx, run, started, series = 0.0, 0, False, []
    for d in days:
        q = d["hours_21_30"] >= 6
        if not started:
            run = run + 1 if q else 0
            if run >= 3:
                started, idx = True, 60.0
        else:
            idx += 20 if q else -10
            if d["tmax"] >= 35:
                idx -= 10
            idx = max(0.0, min(100.0, idx))
        series.append({"label": d["label"], "index": round(idx), "qualifying": q,
                       "future": d.get("future", False)})
    interval = "7-10 days" if idx >= 60 else ("14-17 days" if idx >= 40 else "21 days, or none")
    return ModelResult(
        model="Gubler-Thomas index", fired=idx >= 60,
        level="high" if idx >= 60 else ("rising" if idx >= 40 else "low"),
        detail=f"Risk index {round(idx)}/100. At this index the validated spray interval is {interval}.",
        detail_mr=f"जोखीम निर्देशांक {round(idx)}/१००. फवारणी अंतर: {interval}.",
        value=round(idx), threshold=60.0, series=series)


# ── The 3-10 rule ───────────────────────────────────────────────────────────
def three_ten(days: list[dict], shoot_cm: float = 45.0) -> ModelResult:
    primary, secondary = [], []
    for i in range(1, len(days)):
        d, p = days[i], days[i - 1]
        if shoot_cm >= 10 and d["tmin"] >= 10 and (d["rain_mm"] + p["rain_mm"]) >= 10:
            primary.append(d)
        if d["rh90_hours"] >= 4 and d["tmin"] >= 18 and d["tmax"] <= 32:
            secondary.append(d)
    past = [x for x in primary if not x.get("future")]
    fired = len(past) > 0
    last = past[-1] if past else None
    if fired:
        detail = (f"Primary infection window on {last['label']} — shoots {shoot_cm:.0f} cm, minimum "
                  f"{last['tmin']} °C, {last['rain_mm']:.0f} mm rain. {len(secondary)} secondary-cycle "
                  f"nights since; each cycle completes in about four days.")
        detail_mr = (f"{last['label']} रोजी प्राथमिक संसर्ग — फूट {shoot_cm:.0f} सेमी, किमान "
                     f"{last['tmin']} °से, पाऊस {last['rain_mm']:.0f} मिमी.")
    else:
        detail = ("No primary infection window: the rule needs 10 mm of rain, 10 °C and 10 cm shoots "
                  "together, and they have not coincided.")
        detail_mr = "प्राथमिक संसर्ग नाही — १० मिमी पाऊस, १० °से आणि १० सेमी फूट एकत्र लागतात."
    return ModelResult(model="3-10 rule", fired=fired, level="high" if fired else "low",
                       detail=detail, detail_mr=detail_mr,
                       value=float(len(primary)), threshold=1.0,
                       series=[{"label": d["label"], "primary": d in primary,
                                "secondary": d in secondary, "future": d.get("future", False)}
                               for d in days])


# ── Growing degree days ─────────────────────────────────────────────────────
def gdd_phenology(days: list[dict], tbase: float, dd_per_generation: float,
                  stages: list[list]) -> dict:
    """Accumulated heat, generation number, and — the part that matters — which
    life stage is in the field, because spraying a pupa that is in the soil
    achieves nothing and the app should say so rather than sell a product."""
    total = sum(max(0.0, d["tmean"] - tbase) for d in days if not d.get("future"))
    within = total % dd_per_generation
    generation = int(total // dd_per_generation) + 1
    stage = next((s for s in stages if s[0] <= within < s[1]), stages[-1])
    damaging = "DAMAGE" in stage[2].upper() or "TRANSMISSION" in stage[2].upper()
    return {
        "model": f"Growing degree days (T₀ = {tbase} °C)",
        "gdd": round(total), "within_generation": round(within),
        "generation": generation, "stage": stage[2], "damaging": damaging,
        "level": "high" if damaging else "watch",
        "detail": (f"{round(total)} degree-days accumulated — generation {generation}, currently: "
                   f"{stage[2]}. " +
                   ("This is the stage that causes damage and the stage a spray can still reach."
                    if damaging else
                    "Spraying now would hit a stage that is not susceptible; wait for the larval window.")),
        "detail_mr": (f"{round(total)} डिग्री-दिवस — पिढी {generation}, सध्या: {stage[2]}. " +
                      ("हीच नुकसानकारक अवस्था — फवारणी परिणामकारक." if damaging else
                       "सध्याची अवस्था फवारणीला प्रतिसाद देत नाही; अळी अवस्थेची वाट पहा.")),
    }


MODELS = {"hutton": hutton, "tomcast": tomcast, "gubler": gubler_thomas, "three_ten": three_ten}
