"""
PRAHARI · the four-day risk forecast
════════════════════════════════════════════════════════════════════════════
"What is coming?" — the question no photo-diagnosis app can answer, and the
one a farmer most wants answered.

The implementation is deliberately unclever: for each day in the window, run
the SAME published infection models on the weather record ending on that day.
Today's answer uses observed weather; day +3's answer uses forecast weather.
Nothing is extrapolated, smoothed or learned — the model is the model, and the
only thing that changes is how much of the future it is allowed to see.

That is why the reason string is trustworthy. When PRAHARI says risk rises on
Thursday, it is because the Hutton Criteria crosses on Thursday's forecast
minimum temperature and humidity hours, and it will name both numbers.
"""
from __future__ import annotations

from typing import Any

from . import riskmodels

LEVEL_RANK = {"low": 0, "watch": 1, "rising": 2, "high": 3}
RANK_LEVEL = {v: k for k, v in LEVEL_RANK.items()}

LEVEL_LABEL = {
    "low": {"en": "Low", "mr": "कमी"},
    "watch": {"en": "Watch", "mr": "लक्ष ठेवा"},
    "rising": {"en": "Rising", "mr": "वाढतोय"},
    "high": {"en": "High", "mr": "जास्त"},
}


def _run(model: str, window: list[dict], since_idx: int = 0):
    if model == "hutton":
        return riskmodels.hutton(window)
    if model == "tomcast":
        return riskmodels.tomcast(window, since_spray_index=since_idx)
    if model == "gubler":
        return riskmodels.gubler_thomas(window)
    if model == "three_ten":
        return riskmodels.three_ten(window)
    return None


def by_day(days: list[dict], problems: dict[str, dict], horizon: int = 4,
           since_idx: int = 0) -> list[dict[str, Any]]:
    """days must be the full series, oldest first, with `future` set."""
    past = [d for d in days if not d.get("future")]
    future = [d for d in days if d.get("future")]
    out: list[dict[str, Any]] = []

    for offset in range(0, horizon):
        # The window is everything observed, plus `offset` days of forecast.
        window = past + future[:offset]
        if not window:
            continue
        day = window[-1]
        worst_rank, drivers = 0, []
        for pid, p in problems.items():
            model = p.get("model")
            if not model:
                continue
            r = _run(model, window, since_idx)
            if r is None:
                continue
            rank = LEVEL_RANK.get(r.level, 0)
            if rank >= 2:
                driver = {"id": pid, "name": p["name"], "name_mr": p["mr"],
                          "em": p["em"], "model": r.model, "level": r.level,
                          "detail": r.detail}
                if p.get("model_caveat"):
                    driver["model_caveat"] = p["model_caveat"]
                drivers.append(driver)
            worst_rank = max(worst_rank, rank)
        level = RANK_LEVEL[worst_rank]
        out.append({
            "offset": offset,
            "date": day["date"], "label": "Today" if offset == 0 else day["label"],
            "label_mr": "आज" if offset == 0 else day["label"],
            "level": level,
            "level_label": LEVEL_LABEL[level]["en"], "level_label_mr": LEVEL_LABEL[level]["mr"],
            "observed": offset == 0,
            "tmin": day["tmin"], "tmax": day["tmax"],
            "rh90_hours": day["rh90_hours"], "rain_mm": day["rain_mm"],
            "drivers": drivers,
        })
    return out


def headline(series: list[dict[str, Any]], crop_stage: dict[str, Any]) -> dict[str, Any]:
    """The one sentence at the top of the farmer's home screen, plus the
    bulleted reasons underneath it. Both are assembled from model output, never
    written by a language model."""
    if not series:
        return {"level": "low", "title": "No forecast available", "reasons": []}

    today = series[0]
    worst = max(series, key=lambda s: LEVEL_RANK[s["level"]])
    rising = next((s for s in series if s["offset"] > 0
                   and LEVEL_RANK[s["level"]] > LEVEL_RANK[today["level"]]), None)

    reasons: list[str] = []
    reasons_mr: list[str] = []
    wet_days = [s for s in series if s["rh90_hours"] >= 6]
    if wet_days:
        reasons.append(f"{len(wet_days)} of the next {len(series)} days have six or more hours "
                       f"above 90% humidity")
        reasons_mr.append(f"पुढील {len(series)} पैकी {len(wet_days)} दिवस आर्द्रता ९०%+ सहा तासांहून जास्त")
    warm_nights = [s for s in series if s["tmin"] >= 10]
    if len(warm_nights) == len(series) and wet_days:
        reasons.append("night minimums stay above 10 °C throughout — the temperature half of the "
                       "Hutton criterion is met every night")
        reasons_mr.append("रात्रीचे किमान तापमान सतत १० °से वर — हटन निकषाचा तापमान भाग पूर्ण")
    rain = sum(s["rain_mm"] for s in series)
    if rain >= 10:
        reasons.append(f"{round(rain)} mm of rain forecast across the window")
        reasons_mr.append(f"या कालावधीत {round(rain)} मिमी पाऊस अपेक्षित")
    if crop_stage.get("label"):
        reasons.append(f"the crop is at {crop_stage['label'].lower()}, when it is most susceptible")
        reasons_mr.append(f"पीक सध्या {crop_stage.get('label_mr') or crop_stage['label']} "
                          f"अवस्थेत — सर्वाधिक संवेदनशील")

    if rising:
        title = (f"{_names(rising['drivers']) or 'Disease'} risk rises on {rising['label']}.")
        title_mr = f"{rising['label']} रोजी धोका वाढणार आहे."
        kind = "rising"
    elif LEVEL_RANK[today["level"]] >= 3:
        title = f"{_names(today['drivers']) or 'Disease'} risk is high right now."
        title_mr = "सध्या धोका जास्त आहे."
        kind = "high"
    elif LEVEL_RANK[worst["level"]] >= 2:
        title = f"{_names(worst['drivers']) or 'Disease'} risk is elevated this week."
        title_mr = "या आठवड्यात धोका वाढलेला आहे."
        kind = "watch"
    else:
        title = "No infection threshold is crossed in the next four days."
        title_mr = "पुढील चार दिवसांत कोणताही संसर्ग निकष ओलांडला जात नाही."
        kind = "low"
        reasons = [r for r in reasons if "humidity" not in r and "आर्द्रता" not in r] or \
                  ["humidity stays below the level any of these diseases need"]
        reasons_mr = ["कोणत्याही रोगाला लागणारी आर्द्रता नाही"]

    return {"level": kind, "title": title, "title_mr": title_mr,
            "reasons": reasons, "reasons_mr": reasons_mr,
            "lead_days": rising["offset"] if rising else 0,
            "method": ("Each day is scored by running the same published infection models on the "
                       "weather record ending that day — observed weather for today, forecast "
                       "weather beyond. Nothing is extrapolated or learned."),
            "method_mr": ("प्रत्येक दिवसाचा गुण त्या दिवसापर्यंतच्या हवामान नोंदीवर तीच "
                          "प्रकाशित संसर्ग मॉडेल चालवून काढला जातो — आजसाठी प्रत्यक्ष हवामान, "
                          "पुढे अंदाज. काहीही ताणून किंवा शिकून काढलेले नाही.")}


def _names(drivers: list[dict]) -> str:
    if not drivers:
        return ""
    names = [d["name"] for d in drivers[:2]]
    return " and ".join(names) if len(names) > 1 else names[0]
