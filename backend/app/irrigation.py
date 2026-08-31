"""
PRAHARI · irrigation advice from a water balance
════════════════════════════════════════════════════════════════════════════
"When should I irrigate, and how much?" answered from the same weather record
the disease models already run on, by the same published method the FAO uses.

    ET0   reference evapotranspiration     Hargreaves-Samani (FAO-56 eq. 52)
    ETc   crop water use                   ET0 x Kc(stage)
    Pe    effective rainfall               USDA-SCS monthly method, per-day form
    D     soil water depletion             sum(ETc - Pe) since the last wetting
    TAW   total available water            AWC(soil texture) x root depth
    RAW   readily available water          TAW x p(crop)

Irrigate when D >= RAW. The amount is D / irrigation efficiency.

WHY HARGREAVES AND NOT PENMAN-MONTEITH
--------------------------------------
Penman-Monteith is the FAO standard and it needs net radiation, wind at 2 m and
vapour pressure. A public hourly feed gives temperature, humidity, rain and
sometimes wind at 10 m. Deriving radiation from cloud cover and calling the
result Penman-Monteith would be a more impressive-sounding number computed from
data that does not exist. Hargreaves-Samani needs only Tmax, Tmin and the
extraterrestrial radiation Ra, which is pure astronomy — latitude and day of
year — and FAO-56 endorses it precisely for this situation. It is typically
within 10-15% of Penman-Monteith, and this module says so on every response.

WHAT THIS IS NOT
----------------
It is not a soil moisture sensor. The depletion is MODELLED from weather since
the last wetting event, so it drifts: runoff, a leaking pipe, a hardpan or a
water table the model knows nothing about will all break it. The output is a
prompt to go and check the soil with a hand auger, with a number attached — not
an instruction to open a valve. Every response carries that sentence.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

from . import reference

# ── available water capacity by texture, mm of water per metre of soil ──────
# Indian soil survey ranges; the midpoint is used and the range is reported.
SOILS: dict[str, dict[str, Any]] = {
    "sandy": {"awc": 90, "label": "Sandy / light", "label_mr": "हलकी वाळूमिश्रित",
              "range": [70, 110]},
    "sandy loam": {"awc": 120, "label": "Sandy loam", "label_mr": "वाळूमिश्रित पोयटा",
                   "range": [100, 140]},
    "loam": {"awc": 160, "label": "Loam", "label_mr": "पोयटा", "range": [140, 180]},
    "clay loam": {"awc": 180, "label": "Clay loam", "label_mr": "चिकणमाती-पोयटा",
                  "range": [160, 200]},
    "medium black": {"awc": 190, "label": "Medium black", "label_mr": "मध्यम काळी",
                     "range": [170, 210]},
    "deep black": {"awc": 210, "label": "Deep black / heavy", "label_mr": "खोल काळी",
                   "range": [190, 230]},
    "clay": {"awc": 200, "label": "Clay", "label_mr": "चिकणमाती", "range": [180, 220]},
}
DEFAULT_SOIL = "medium black"

# ── application efficiency by method ────────────────────────────────────────
METHODS: dict[str, dict[str, Any]] = {
    "drip": {"eff": 0.90, "label": "Drip", "label_mr": "ठिबक"},
    "sprinkler": {"eff": 0.75, "label": "Sprinkler", "label_mr": "तुषार"},
    "furrow": {"eff": 0.60, "label": "Furrow", "label_mr": "सरी"},
    "flood": {"eff": 0.50, "label": "Flood", "label_mr": "पाट"},
    "rainfed": {"eff": 0.0, "label": "Rainfed", "label_mr": "कोरडवाहू"},
}
DEFAULT_METHOD = "drip"

# ── crop coefficients and rooting, FAO-56 Table 12 / Table 22 ───────────────
# Kc by PRAHARI stage key, root depth in metres, and p (the fraction of TAW a
# crop can lose before it is stressed).
CROP_WATER: dict[str, dict[str, Any]] = {
    "tomato": {"p": 0.40, "root": {"sowing": 0.2, "vegetative": 0.5, "flowering": 0.9,
                                   "fruiting": 1.0, "harvest": 1.0},
               "kc": {"sowing": 0.6, "vegetative": 0.85, "flowering": 1.15,
                      "fruiting": 1.15, "harvest": 0.80}},
    "onion": {"p": 0.30, "root": {"nursery": 0.15, "vegetative": 0.3, "bulb": 0.4,
                                  "maturity": 0.4},
              "kc": {"nursery": 0.70, "vegetative": 0.95, "bulb": 1.05, "maturity": 0.75}},
    "grape": {"p": 0.45, "root": {"pruning": 1.0, "shoot": 1.0, "flowering": 1.2,
                                  "berry": 1.2, "harvest": 1.2},
              "kc": {"pruning": 0.30, "shoot": 0.60, "flowering": 0.75, "berry": 0.80,
                     "harvest": 0.55}},
    "maize": {"p": 0.55, "root": {"seedling": 0.3, "earlywhorl": 0.6, "latewhorl": 0.9,
                                  "tassel": 1.2, "grain": 1.4},
              "kc": {"seedling": 0.40, "earlywhorl": 0.80, "latewhorl": 1.10,
                     "tassel": 1.20, "grain": 0.90}},
    "cotton": {"p": 0.65, "root": {"seedling": 0.3, "vegetative": 0.7, "flowering": 1.1,
                                   "boll": 1.4, "harvest": 1.4},
               "kc": {"seedling": 0.40, "vegetative": 0.80, "flowering": 1.15,
                      "boll": 1.10, "harvest": 0.60}},
    "soybean": {"p": 0.50, "root": {"seedling": 0.25, "vegetative": 0.6, "flowering": 0.9,
                                    "pod": 1.1, "maturity": 1.1},
                "kc": {"seedling": 0.40, "vegetative": 0.85, "flowering": 1.15,
                       "pod": 1.10, "maturity": 0.55}},
    "pigeonpea": {"p": 0.55, "root": {"seedling": 0.3, "vegetative": 0.7, "flowering": 1.1,
                                      "pod": 1.4, "maturity": 1.4},
                  "kc": {"seedling": 0.40, "vegetative": 0.80, "flowering": 1.05,
                         "pod": 1.00, "maturity": 0.45}},
}

SOURCE = ("FAO Irrigation and Drainage Paper 56 — Kc values (Table 12), rooting depth and "
          "depletion fraction p (Table 22), Hargreaves-Samani ET0 (eq. 52) and the USDA-SCS "
          "effective-rainfall method. Implemented from the published equations; not an "
          "endorsement by the FAO.")

CAVEAT = ("This is a MODELLED water balance, not a soil moisture reading. It knows the weather "
          "and the crop; it does not know about runoff, a leaking line, a hardpan or a water "
          "table. Treat the number as a prompt to push an auger into the root zone and look — if "
          "the soil at 15 cm crumbles dry, irrigate; if it ribbons wet, wait, and tell PRAHARI "
          "you irrigated so the balance resets.")
CAVEAT_MR = ("हा हवामानावर आधारित अंदाज आहे — जमिनीतील ओलाव्याचे प्रत्यक्ष मापन नाही. १५ सेंमी "
             "खोलीवरची माती हातात घेऊन तपासा: भुसभुशीत कोरडी असल्यास पाणी द्या.")


def ra_mm_per_day(lat_deg: float, day_of_year: int) -> float:
    """Extraterrestrial radiation, FAO-56 eq. 21, expressed in mm/day equivalent.

    Pure astronomy — latitude and the day of the year. Nothing measured, nothing
    guessed, and identical on every machine."""
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    d = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    x = -math.tan(phi) * math.tan(d)
    ws = math.acos(max(-1.0, min(1.0, x)))
    ra_mj = (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(d) + math.cos(phi) * math.cos(d) * math.sin(ws))
    return ra_mj * 0.408                      # MJ m-2 d-1 → mm d-1


def et0_hargreaves(day: dict[str, Any], lat: float) -> float | None:
    """FAO-56 eq. 52: ET0 = 0.0023 x Ra x (Tmean + 17.8) x sqrt(Tmax - Tmin)."""
    tmax, tmin, tmean = day.get("tmax"), day.get("tmin"), day.get("tmean")
    if tmax is None or tmin is None or tmean is None or tmax < tmin:
        return None
    try:
        doy = dt.date.fromisoformat(str(day["date"])[:10]).timetuple().tm_yday
    except (ValueError, KeyError, TypeError):
        return None
    ra = ra_mm_per_day(lat, doy)
    return round(max(0.0, 0.0023 * ra * (tmean + 17.8) * math.sqrt(max(0.0, tmax - tmin))), 2)


def effective_rain(rain_mm: float) -> float:
    """USDA-SCS: not all rain enters the root zone. Below 5 mm effectively none
    of it does — it wets the surface and evaporates — and above that roughly
    75-80% is retained until the profile fills."""
    if rain_mm < 5:
        return 0.0
    return round(min(rain_mm * 0.8, rain_mm - 2.0), 1)


def advise(plot: dict[str, Any], wx: dict[str, Any], stage: dict[str, Any],
           last_irrigation: dt.date | None, today: dt.date) -> dict[str, Any]:
    lat = plot.get("lat")
    crop = plot.get("crop")
    cw = CROP_WATER.get(crop)
    if lat is None or cw is None:
        return {"available": False,
                "reason": ("PRAHARI has no FAO crop coefficients for this crop, or the field has "
                           "no coordinates, so it will not estimate water use for it."),
                "source": SOURCE}

    soil_key = (plot.get("soil") or DEFAULT_SOIL).strip().lower()
    soil = SOILS.get(soil_key, SOILS[DEFAULT_SOIL])
    method_key = (plot.get("irrigation") or DEFAULT_METHOD).strip().lower()
    method = METHODS.get(method_key, METHODS[DEFAULT_METHOD])

    stage_key = stage.get("stage")
    kc = cw["kc"].get(stage_key)
    root = cw["root"].get(stage_key)
    if kc is None or root is None:
        # The crop is between stages the tables cover — say so rather than
        # silently using the nearest value.
        return {"available": False,
                "reason": (f"No FAO crop coefficient is tabulated for {crop} at the "
                           f"'{stage_key or 'unknown'}' stage, so PRAHARI will not estimate "
                           f"water use today."),
                "source": SOURCE}

    taw = soil["awc"] * root                       # mm
    raw = taw * cw["p"]

    # The balance starts at the last wetting event PRAHARI knows about: the
    # recorded irrigation, or the last day with meaningful rain, whichever is
    # later. Starting from an arbitrary date would accumulate a fiction.
    days = [d for d in wx.get("days", []) if not d.get("future")]
    start_idx = 0
    reset_reason = "the start of the weather record PRAHARI holds"
    for i, d in enumerate(days):
        day_d = dt.date.fromisoformat(str(d["date"])[:10])
        if last_irrigation and day_d <= last_irrigation:
            start_idx, reset_reason = i, f"your recorded irrigation on {last_irrigation}"
        if effective_rain(d.get("rain_mm") or 0) >= raw * 0.8:
            start_idx, reset_reason = i, f"{d.get('rain_mm')} mm of rain on {d['date']}"

    ledger: list[dict[str, Any]] = []
    depletion = 0.0
    missing = 0
    for d in days[start_idx:]:
        et0 = et0_hargreaves(d, lat)
        if et0 is None:
            missing += 1
            continue
        etc = et0 * kc
        pe = effective_rain(d.get("rain_mm") or 0)
        depletion = max(0.0, depletion + etc - pe)
        ledger.append({"date": d["date"], "et0": et0, "etc": round(etc, 2),
                       "rain_mm": d.get("rain_mm"), "effective_rain": pe,
                       "depletion": round(depletion, 1)})

    if not ledger:
        return {"available": False,
                "reason": "The weather record has no usable days to compute a balance from.",
                "source": SOURCE}

    forecast_rain = round(sum(effective_rain(d.get("rain_mm") or 0)
                              for d in wx.get("days", []) if d.get("future")), 1)
    due = depletion >= raw
    net_mm = round(depletion, 1)
    gross_mm = round(depletion / method["eff"], 1) if method["eff"] > 0 else None
    litres = round(gross_mm * 4046.86 * float(plot.get("area_acre") or 1.0)) if gross_mm else None

    if method_key == "rainfed":
        verdict, tone = "rainfed", "grey"
        say = ("This field is recorded as rainfed, so PRAHARI reports the deficit but has no "
               "irrigation to recommend. The number still tells you how much water the crop has "
               "not had.")
    elif forecast_rain >= net_mm and due:
        verdict, tone = "wait_for_rain", "info"
        say = (f"The root zone is {net_mm} mm short, but {forecast_rain} mm of effective rain is "
               f"forecast in the next few days — more than the deficit. Irrigating now and then "
               f"getting that rain waterlogs the roots, and on this crop that costs more than the "
               f"stress does.")
    elif due:
        verdict, tone = "irrigate", "warn"
        say = (f"The modelled depletion is {net_mm} mm, past the {round(raw)} mm this soil and "
               f"crop can lose before the plant is stressed. Apply about {gross_mm} mm by "
               f"{method['label'].lower()}"
               + (f" — roughly {litres:,} litres over {plot.get('area_acre')} acre(s)."
                  if litres else "."))
    else:
        headroom = round(raw - depletion, 1)
        per_day = ledger[-1]["etc"] if ledger else 0
        days_left = round(headroom / per_day, 1) if per_day > 0 else None
        verdict, tone = "hold", "ok"
        say = (f"No irrigation needed. The root zone has lost about {net_mm} mm of the "
               f"{round(raw)} mm it can afford"
               + (f", roughly {days_left} more day(s) at today's water use."
                  if days_left else "."))

    return {
        "available": True,
        "verdict": verdict, "tone": tone, "say": say,
        "depletion_mm": net_mm, "raw_mm": round(raw, 1), "taw_mm": round(taw, 1),
        "apply_mm": gross_mm if verdict == "irrigate" else None,
        "apply_litres": litres if verdict == "irrigate" else None,
        "et0_today": ledger[-1]["et0"], "etc_today": ledger[-1]["etc"],
        "kc": kc, "root_depth_m": root, "depletion_fraction_p": cw["p"],
        "soil": {"key": soil_key, **{k: v for k, v in soil.items() if k != "range"},
                 "awc_range_mm_per_m": soil["range"]},
        "method": {"key": method_key, **method},
        "forecast_effective_rain_mm": forecast_rain,
        "balance_since": ledger[0]["date"],
        "balance_reset_by": reset_reason,
        "days_without_weather": missing,
        "ledger": ledger[-14:],
        "source": SOURCE,
        "caveat": CAVEAT, "caveat_mr": CAVEAT_MR,
        "method_note": ("ET0 by Hargreaves-Samani, which needs only Tmax, Tmin and astronomical "
                        "radiation. Penman-Monteith is the FAO standard but needs net radiation "
                        "and 2 m wind, which no public hourly feed for this district provides — "
                        "deriving them and calling the result Penman-Monteith would be a better "
                        "name on a worse number. Expect Hargreaves to sit within about 10-15% of "
                        "Penman-Monteith."),
        "weather_source": wx.get("source"),
        "weather_kind": wx.get("source_kind"),
    }


def soil_options() -> list[dict[str, Any]]:
    return [{"key": k, "label": v["label"], "label_mr": v["label_mr"],
             "awc_mm_per_m": v["awc"]} for k, v in SOILS.items()]


def method_options() -> list[dict[str, Any]]:
    return [{"key": k, "label": v["label"], "label_mr": v["label_mr"],
             "efficiency": v["eff"]} for k, v in METHODS.items()]


def crops_covered() -> list[str]:
    return [c for c in CROP_WATER if c in reference.CROPS]
