"""
PRAHARI · weather
════════════════════════════════════════════════════════════════════════════
The infection models in riskmodels.py need four things per day: the night
minimum temperature, the number of hours at RH >= 90%, rainfall, and the hours
spent inside 21-30 C. Nothing else.

Two sources, one shape:

  live  — Open-Meteo. Free, no API key, hourly temperature / relative humidity
          / precipitation. We roll the hourly series up ourselves rather than
          trusting a daily summary, because "hours at RH >= 90" is a COUNT and
          a daily mean cannot produce it.

  demo  — a deterministic generator seeded on the date, so the demo produces
          identical numbers on every laptop and cannot fail because a venue
          firewall blocked an API call at the wrong moment.

Mahavedh, Maharashtra's ~2,060-station automatic weather network, would be the
right source at plot level. Its data sits behind the WINDS portal and is not
openly available to third parties, so it is not used here. If a deployment gets
authorised access, only fetch_live() changes.
"""
from __future__ import annotations

import datetime as dt
import math

try:
    import httpx
except Exception:                                  # keep the app importable offline
    httpx = None

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"


# ── deterministic pseudo-random, so the demo is reproducible ────────────────
class _Seeded:
    def __init__(self, seed: int):
        self.s = seed & 0xFFFFFFFF

    def next(self) -> float:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return self.s / 0xFFFFFFFF

    def gauss(self) -> float:
        return (sum(self.next() for _ in range(6)) - 3) / 1.732


def _rollup(hours: list[dict], day: dt.date, future: bool) -> dict:
    """The only function that turns hourly readings into the four model inputs.
    RH hours are counted, one per sample, never estimated from a daily mean."""
    temps = [h["t"] for h in hours]
    rhs = [h["rh"] for h in hours]
    rain = sum(h["rain"] for h in hours)
    step = 24.0 / max(1, len(hours))               # hours represented by one sample
    rh90 = sum(step for h in hours if h["rh"] >= 90)
    band = sum(step for h in hours if 21 <= h["t"] <= 30)
    # Leaf wetness is not measured by any public feed and dedicated sensors report
    # ~100% false positives above 90% RH, so we use the RH>=90 proxy and say so.
    wet = rh90 + (2.5 if rain > 1 else 0.0)
    return {
        "date": day.isoformat(),
        "label": day.strftime("%-d %b") if hasattr(day, "strftime") else str(day),
        "tmin": round(min(temps), 1), "tmax": round(max(temps), 1),
        "tmean": round(sum(temps) / len(temps), 1),
        "rh_mean": round(sum(rhs) / len(rhs), 1),
        "rh90_hours": round(rh90, 1),
        "leaf_wet_hours": round(wet, 1),
        "rain_mm": round(rain, 1),
        "hours_21_30": round(band, 1),
        "samples": len(hours),
        "future": future,
        "leaf_wetness_note": "RH ≥ 90% proxy — no public feed measures leaf wetness directly",
    }


# Three weather stories, so a presenter can put the infection models into a
# known state without faking their output. The models are untouched — only the
# weather they are fed changes, which is exactly what changes in a real field.
PROFILES = {
    "monsoon": {"label": "Warm and humid — monsoon tail",
                "night_rh": 92, "day_rh": 68, "rain": 1.0, "cool": 3.2},
    "dry": {"label": "Warm and dry",
            "night_rh": 58, "day_rh": 33, "rain": 0.0, "cool": 0.0},
    "rising": {"label": "Dry now, turning humid in two days",
               "night_rh": 62, "day_rh": 38, "rain": 0.0, "cool": 0.5,
               "turns_on_offset": 2, "then": "monsoon"},
}


def demo_series(lat: float, lng: float, today: dt.date,
                back: int = 21, forward: int = 6, profile: str = "monsoon") -> list[dict]:
    """Late-August Nashik: the tail of the south-west monsoon, which is exactly
    when late blight and downy mildew fire. Generated, but generated to the
    right shape — the models below are unchanged when real data replaces it."""
    # Seeded on the DATE and the PLACE, so one field on one day always
    # produces the same forecast however many times a screen is refreshed, and
    # two different fields produce different but equally stable ones. Longitude
    # is in the seed as well as latitude: without it every field on the same
    # parallel shared a forecast.
    rng = _Seeded(int(today.strftime("%Y%m%d")) + int(lat * 100) + int(lng * 10_000))
    base = PROFILES.get(profile, PROFILES["monsoon"])
    out = []
    for offset in range(-back, forward + 1):
        day = today + dt.timedelta(days=offset)
        doy = day.timetuple().tm_yday
        seasonal = math.cos((doy - 130) / 365 * 2 * math.pi)
        # A profile may switch part-way through the window. That is what makes
        # the "rising" story honest: the model does not fire today and does fire
        # on the forecast, because the forecast weather genuinely changes.
        p = base
        if base.get("turns_on_offset") is not None and offset >= base["turns_on_offset"]:
            p = PROFILES[base["then"]]
        wet = p["rain"]
        spell = max(0.0, min(1.0, 0.45 + 0.5 * math.sin(offset / 3.1) + 0.35 * rng.gauss()))
        rain_day = max(0.0, (spell - 0.35) * 46 + rng.gauss() * 7) * wet
        if rain_day < 0.4:
            rain_day = 0.0
        tmax = 31.5 + 4.5 * seasonal - p["cool"] - rain_day * 0.11 + rng.gauss() * 1.5
        tmin = 20.0 + 4.0 * seasonal - 0.4 * wet + rain_day * 0.02 + rng.gauss() * 1.0
        tmin = min(tmin, tmax - 3)
        rh_night = min(99.0, p["night_rh"] + rain_day * 0.18 + rng.gauss() * 3)
        rh_day = max(24.0, p["day_rh"] + rain_day * 0.22 + rng.gauss() * 4)

        hours = []
        for h in range(24):
            night = h < 7 or h > 21
            t = (tmin if night else tmax) + 2.6 * math.sin((h - 9) / 24 * 2 * math.pi) + rng.gauss() * 0.5
            rh = (rh_night if night else rh_day) - 1.8 * math.sin((h - 9) / 24 * 2 * math.pi) + rng.gauss() * 2
            hours.append({"t": round(t, 1), "rh": max(12.0, min(99.5, round(rh, 1))),
                          "rain": round(rain_day / 24, 2)})
        out.append(_rollup(hours, day, future=offset > 0))
    return out


def fetch_live(lat: float, lng: float, back: int = 21, forward: int = 6,
               timeout: float = 6.0) -> list[dict] | None:
    """Open-Meteo. Returns None on any failure — the caller falls back to the
    deterministic series rather than showing a farmer an error page."""
    if httpx is None:
        return None
    try:
        r = httpx.get(OPEN_METEO, timeout=timeout, params={
            "latitude": lat, "longitude": lng,
            "hourly": "temperature_2m,relative_humidity_2m,precipitation",
            "past_days": min(back, 92), "forecast_days": min(forward + 1, 16),
            "timezone": "Asia/Kolkata",
        })
        r.raise_for_status()
        h = r.json()["hourly"]
        by_day: dict[dt.date, list[dict]] = {}
        for iso, t, rh, rain in zip(h["time"], h["temperature_2m"],
                                    h["relative_humidity_2m"], h["precipitation"],
                                    strict=False):
            stamp = dt.datetime.fromisoformat(iso)
            by_day.setdefault(stamp.date(), []).append(
                {"t": t, "rh": rh, "rain": rain or 0.0})
        today = dt.date.today()
        return [_rollup(v, k, future=k > today) for k, v in sorted(by_day.items()) if v]
    except Exception:
        return None


def get_series(lat: float, lng: float, today: dt.date, mode: str = "auto",
               back: int = 21, forward: int = 6, profile: str = "monsoon") -> dict:
    """mode: 'auto' tries live then falls back; 'demo' never touches the network."""
    if mode == "auto":
        live = fetch_live(lat, lng, back, forward)
        if live:
            return {"source": "open-meteo", "profile": None, "days": live,
                    "note": "Hourly Open-Meteo readings, rolled up here. RH-hours are counted, not averaged."}
    p = PROFILES.get(profile, PROFILES["monsoon"])
    return {"source": "deterministic-demo", "profile": profile, "profile_label": p["label"],
            "days": demo_series(lat, lng, today, back, forward, profile),
            "note": ("Generated series, identical on every machine — " + p["label"].lower() +
                     ". The infection models are untouched; only the weather they are fed changes, "
                     "which is exactly what changes in a real field. Swap in Open-Meteo or Mahavedh "
                     "and no model code changes.")}
