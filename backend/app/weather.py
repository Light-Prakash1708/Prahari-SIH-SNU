"""
PRAHARI · weather
════════════════════════════════════════════════════════════════════════════
The infection models need four things per day: night minimum temperature, the
number of HOURS at RH ≥ 90%, rainfall, and hours inside 21–30 °C. Nothing else.
Hour counts cannot be recovered from a daily mean, so this module always rolls
up an hourly series itself.

    WeatherProvider
        ├── OpenMeteoProvider     real, free, no key, hourly, 16-day forecast
        ├── DemoWeatherProvider   generated — constructed ONLY when DEMO_MODE
        └── NullProvider          configured off; every call fails honestly

The rule this module exists to enforce: when the provider fails, the caller
gets an error, not a substitute series. A fabricated humidity number becomes a
fabricated infection risk becomes a spray a farmer did not need.
"""
from __future__ import annotations

import datetime as dt
import logging
from abc import ABC, abstractmethod
from typing import Any

from .clock import iso, now, now_iso, parse_ts
from .config import Settings, get_settings
from .db import Database, dumps, loads
from .errors import unavailable

log = logging.getLogger("prahari.weather")

# Reused unchanged from the prototype: it is the correct rollup and the models
# are calibrated against exactly this shape.
from .weather_demo import PROFILES, _rollup, demo_series  # noqa: E402


class WeatherUnavailable(RuntimeError):
    def __init__(self, provider: str, reason: str):
        self.provider, self.reason = provider, reason
        super().__init__(f"{provider}: {reason}")


class WeatherProvider(ABC):
    name = "abstract"
    kind = "none"

    @abstractmethod
    def series(self, lat: float, lng: float, today: dt.date,
               back: int, forward: int) -> dict[str, Any]:
        """Returns {'source','days',...}. Raises WeatherUnavailable on failure —
        never returns a partial or invented series."""

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "configured": True}


class NullProvider(WeatherProvider):
    name = "none"
    kind = "none"

    def series(self, lat, lng, today, back, forward):
        raise WeatherUnavailable("none",
                                 "No weather provider is configured (WEATHER_PROVIDER=none).")

    def health(self):
        return {"provider": "none", "configured": False,
                "note": "WEATHER_PROVIDER is not set. Risk forecasting is disabled."}


class OpenMeteoProvider(WeatherProvider):
    """Open-Meteo: free, no API key, hourly temperature / RH / precipitation and
    a 16-day forecast. Mahavedh — Maharashtra's ~2,060-station automatic weather
    network — would be the right source at plot level, but its data sits behind
    the WINDS portal and is not openly available. If a deployment is granted
    access, only this class changes."""
    name = "open-meteo"
    kind = "live"

    def __init__(self, settings: Settings):
        self.s = settings

    def series(self, lat, lng, today, back, forward):
        try:
            import httpx
        except ImportError as exc:                      # pragma: no cover
            raise WeatherUnavailable(self.name, f"httpx is not installed: {exc}") from exc
        params = {
            "latitude": round(float(lat), 4), "longitude": round(float(lng), 4),
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,"
                      "wind_speed_10m,cloud_cover",
            "past_days": max(1, min(int(back), 92)),
            "forecast_days": max(1, min(int(forward) + 1, 16)),
            "timezone": "Asia/Kolkata",
        }
        if self.s.weather_api_key:
            params["apikey"] = self.s.weather_api_key
        try:
            r = httpx.get(self.s.weather_api_url, params=params,
                          timeout=self.s.weather_timeout_seconds)
            r.raise_for_status()
            payload = r.json()
        except Exception as exc:
            raise WeatherUnavailable(self.name, f"{type(exc).__name__}: {str(exc)[:160]}") from exc

        h = payload.get("hourly") or {}
        if not h.get("time"):
            raise WeatherUnavailable(self.name, "provider returned no hourly series")

        by_day: dict[dt.date, list[dict[str, float]]] = {}
        wind: dict[dt.date, list[float]] = {}
        cloud: dict[dt.date, list[float]] = {}
        times = h["time"]
        temps = h.get("temperature_2m") or []
        rhs = h.get("relative_humidity_2m") or []
        rains = h.get("precipitation") or []
        winds = h.get("wind_speed_10m") or [None] * len(times)
        clouds = h.get("cloud_cover") or [None] * len(times)
        for i, stamp_iso in enumerate(times):
            if i >= len(temps) or temps[i] is None or i >= len(rhs) or rhs[i] is None:
                continue
            stamp = dt.datetime.fromisoformat(stamp_iso)
            day = stamp.date()
            by_day.setdefault(day, []).append(
                {"t": float(temps[i]), "rh": float(rhs[i]),
                 "rain": float(rains[i] or 0.0) if i < len(rains) else 0.0})
            if i < len(winds) and winds[i] is not None:
                wind.setdefault(day, []).append(float(winds[i]))
            if i < len(clouds) and clouds[i] is not None:
                cloud.setdefault(day, []).append(float(clouds[i]))
        if not by_day:
            raise WeatherUnavailable(self.name, "provider returned an unusable hourly series")

        days = []
        for day, hours in sorted(by_day.items()):
            row = _rollup(hours, day, future=day > today)
            if wind.get(day):
                row["wind_kmh_mean"] = round(sum(wind[day]) / len(wind[day]), 1)
                row["wind_kmh_max"] = round(max(wind[day]), 1)
            if cloud.get(day):
                row["cloud_pct_mean"] = round(sum(cloud[day]) / len(cloud[day]), 0)
            days.append(row)
        return {
            "source": "open-meteo",
            "source_kind": "live",
            "source_url": "https://open-meteo.com/",
            "profile": None,
            "days": days,
            "note": ("Hourly Open-Meteo readings for this field's coordinates, rolled up here. "
                     "Hours at RH ≥ 90% are counted from the hourly series, never estimated "
                     "from a daily mean."),
        }

    def health(self):
        return {"provider": self.name, "configured": True, "url": self.s.weather_api_url}


class DemoWeatherProvider(WeatherProvider):
    """A deterministic generated series, so a demo produces identical numbers on
    every laptop and cannot fail because a venue firewall blocked an API call.

    Constructed only when DEMO_MODE=true. config.py refuses WEATHER_PROVIDER=demo
    in production, so this class cannot be reached by a deployed instance.
    """
    name = "deterministic-demo"
    kind = "generated"

    def __init__(self, profile_fn=None):
        self._profile_fn = profile_fn or (lambda: "monsoon")

    def series(self, lat, lng, today, back, forward):
        profile = self._profile_fn() or "monsoon"
        p = PROFILES.get(profile, PROFILES["monsoon"])
        return {
            "source": "deterministic-demo",
            "source_kind": "generated",
            "profile": profile,
            "profile_label": p["label"],
            "days": demo_series(lat, lng, today, back, forward, profile),
            "note": ("GENERATED WEATHER — demo mode. Identical on every machine. The infection "
                     "models are untouched; only the weather they are fed changes, which is "
                     "exactly what changes in a real field."),
            "warning": "This is not real weather. DEMO_MODE is on.",
        }


# ── the service: provider + cache + freshness metadata ──────────────────────
class WeatherService:
    def __init__(self, db: Database, settings: Settings | None = None,
                 demo_profile_fn=None):
        self.db = db
        self.s = settings or get_settings()
        self.provider = self._build(demo_profile_fn)

    def _build(self, demo_profile_fn) -> WeatherProvider:
        p = self.s.weather_provider
        if p == "openmeteo":
            return OpenMeteoProvider(self.s)
        if p == "demo":
            if not self.s.demo_mode:
                log.warning("WEATHER_PROVIDER=demo requires DEMO_MODE=true; disabling weather")
                return NullProvider()
            return DemoWeatherProvider(demo_profile_fn)
        return NullProvider()

    # ── cache ──────────────────────────────────────────────────────────────
    def _key(self, lat: float, lng: float, back: int, forward: int) -> str:
        # ~1 km resolution. Fields inside the same kilometre share a forecast,
        # which is well inside the resolution of any public weather model.
        #
        # The demo profile is part of the key. Without it, switching scenarios
        # served the previous scenario's weather from cache and the whole demo
        # silently stopped responding to the control it was built around.
        profile = ""
        if isinstance(self.provider, DemoWeatherProvider):
            profile = ":" + (self.provider._profile_fn() or "monsoon")
        return (f"{self.provider.name}{profile}:{round(float(lat), 2)}:{round(float(lng), 2)}"
                f":{back}:{forward}")

    def _from_cache(self, key: str) -> dict[str, Any] | None:
        row = self.db.one("SELECT * FROM weather_cache WHERE cache_key = :k", {"k": key})
        if not row:
            return None
        if str(row["expires_at"]) < now_iso():
            return None
        payload = loads(row["payload"], {})
        if not payload:
            return None
        payload["cached"] = True
        payload["fetched_at"] = row["fetched_at"]
        return payload

    def _store(self, key: str, lat: float, lng: float, payload: dict[str, Any]) -> None:
        expires = iso(now() + dt.timedelta(minutes=self.s.weather_cache_minutes))
        stamp = now_iso()
        self.db.execute(
            "INSERT INTO weather_cache (cache_key, lat, lng, provider, fetched_at, expires_at, payload)"
            " VALUES (:k,:lat,:lng,:p,:f,:e,:pl)"
            " ON CONFLICT (cache_key) DO UPDATE SET fetched_at=:f, expires_at=:e, payload=:pl",
            {"k": key, "lat": float(lat), "lng": float(lng), "p": self.provider.name,
             "f": stamp, "e": expires, "pl": dumps(payload)})

    # ── the call every risk path makes ─────────────────────────────────────
    def series(self, lat: float | None, lng: float | None, today: dt.date,
               back: int = 21, forward: int = 6,
               allow_stale: bool = True) -> dict[str, Any]:
        if lat is None or lng is None:
            raise WeatherUnavailable("none", "This field has no coordinates recorded.")
        key = self._key(lat, lng, back, forward)
        hit = self._from_cache(key)
        if hit:
            return self._decorate(hit, fresh=True)
        try:
            payload = self.provider.series(lat, lng, today, back, forward)
        except WeatherUnavailable as exc:
            stale = self.db.one("SELECT * FROM weather_cache WHERE cache_key=:k", {"k": key})
            if allow_stale and stale:
                # Stale real data, clearly labelled as stale, beats generated data.
                payload = loads(stale["payload"], {})
                payload["cached"] = True
                payload["stale"] = True
                payload["fetched_at"] = stale["fetched_at"]
                payload["stale_reason"] = exc.reason
                log.warning("weather provider failed; serving stale cache",
                            extra={"provider": exc.provider, "reason": exc.reason})
                return self._decorate(payload, fresh=False)
            raise
        self._store(key, lat, lng, payload)
        payload["cached"] = False
        payload["fetched_at"] = now_iso()
        return self._decorate(payload, fresh=True)

    def _decorate(self, payload: dict[str, Any], fresh: bool) -> dict[str, Any]:
        fetched = parse_ts(payload.get("fetched_at"))
        age_min = int((now() - fetched).total_seconds() // 60) if fetched else None
        payload["freshness"] = {
            "fetched_at": payload.get("fetched_at"),
            "age_minutes": age_min,
            "fresh": bool(fresh and (age_min is None or age_min <= self.s.weather_cache_minutes)),
            "cache_ttl_minutes": self.s.weather_cache_minutes,
        }
        days = payload.get("days") or []
        payload["forecast_from"] = next((d["date"] for d in days if d.get("future")), None)
        payload["observed_through"] = next(
            (d["date"] for d in reversed(days) if not d.get("future")), None)
        return payload

    def health(self) -> dict[str, Any]:
        h = self.provider.health()
        h["kind"] = self.provider.kind
        return h


def to_http_error(exc: WeatherUnavailable):
    return unavailable(
        "weather_unavailable",
        "Weather data could not be retrieved for this field, so risk cannot be forecast. "
        "PRAHARI does not substitute invented weather.",
        message_mr="या शेतासाठी हवामान माहिती मिळाली नाही. प्रहरी खोटी माहिती दाखवत नाही.",
        detail={"provider": exc.provider, "reason": exc.reason})
