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

There is ONE cache, and it is the `weather_cache` table. An earlier version
also kept a dict in process memory with a different key and a different TTL;
two caches that cannot see each other are two chances to miss, and the dict was
lost on every restart and duplicated per worker. What the process does hold is
much smaller and is not data: a cooldown deadline per provider, and one lock
per cache key.

Three things keep this module off the provider's rate limiter:

  · a COOLDOWN. A 429 or a 5xx parks the provider for a while, honouring
    `Retry-After` when it is sent. Without it a rate-limited deployment retries
    on every request and holds itself under the limit — the failure feeds
    itself, which is exactly what was observed.
  · SINGLE FLIGHT. Concurrent requests for the same cache key wait on one
    lock, so a cold cache costs one HTTP call rather than one per request.
  · a NARROW REQUEST. Only the three hourly variables the infection models
    actually read are asked for. Open-Meteo weighs a call by variables times
    days, and wind and cloud cover were being fetched, rolled up and read by
    nothing.

None of the three can invent a number. When they run out, the caller gets
WeatherUnavailable and the screen says so.
"""
from __future__ import annotations

import datetime as dt
import logging
import random
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from .clock import iso, now, now_iso, parse_ts
from .config import Settings, get_settings
from .db import Database, dumps, loads
from .errors import unavailable

log = logging.getLogger("prahari.weather")

# ── what this process holds ────────────────────────────────────────────────
# Not weather. A cooldown deadline per provider, and one lock per cache key.
# Both are per-process, which is the honest scope: with several workers each
# keeps its own, so the cooldown reduces the call rate by a factor of the
# worker count rather than to zero. Correctness never depends on either — they
# only decide whether an outbound call is attempted.
_COOLDOWN: dict[str, float] = {}
_COOLDOWN_REASON: dict[str, str] = {}
_COOLDOWN_LOCK = threading.Lock()

_INFLIGHT: dict[str, threading.Lock] = {}
_INFLIGHT_GUARD = threading.Lock()


def _cooldown_remaining(provider: str) -> float:
    """Seconds left before this provider may be called again. 0.0 when open."""
    with _COOLDOWN_LOCK:
        until = _COOLDOWN.get(provider)
    if until is None:
        return 0.0
    left = until - time.monotonic()
    return left if left > 0 else 0.0


def _cooldown_reason(provider: str) -> str:
    with _COOLDOWN_LOCK:
        return _COOLDOWN_REASON.get(provider, "")


def _open_cooldown(provider: str, seconds: float, reason: str) -> None:
    with _COOLDOWN_LOCK:
        until = time.monotonic() + max(0.0, seconds)
        # Never shorten a cooldown that is already longer — a second 429
        # arriving mid-cooldown must not reset the clock downwards.
        if until > _COOLDOWN.get(provider, 0.0):
            _COOLDOWN[provider] = until
            _COOLDOWN_REASON[provider] = reason


def clear_cooldowns() -> None:
    """Test seam. Nothing in the application calls this."""
    with _COOLDOWN_LOCK:
        _COOLDOWN.clear()
        _COOLDOWN_REASON.clear()


def _key_lock(key: str) -> threading.Lock:
    with _INFLIGHT_GUARD:
        lock = _INFLIGHT.get(key)
        if lock is None:
            lock = _INFLIGHT[key] = threading.Lock()
        if len(_INFLIGHT) > 5000:                  # bound the dict, not the locks in use
            _INFLIGHT.clear()
            _INFLIGHT[key] = lock
        return lock


def parse_retry_after(value: str | None) -> float | None:
    """`Retry-After` as seconds. Accepts the delta-seconds form and the HTTP-date
    form; returns None for anything else, so a malformed header falls back to
    the configured default rather than parking the provider forever."""
    if not value:
        return None
    v = value.strip()
    try:
        return max(0.0, float(int(v)))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        when = parsedate_to_datetime(v)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    return max(0.0, (when - dt.datetime.now(dt.UTC)).total_seconds())


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


# The only hourly variables anything downstream reads. wind_speed_10m and
# cloud_cover were fetched, rolled up into wind_kmh_mean / wind_kmh_max /
# cloud_pct_mean, and read by no screen, no model and no service — while
# Open-Meteo weighs a request by variables times days. Adding a variable here
# costs quota on every field, every refresh, so add one only when something
# actually reads it.
HOURLY = "temperature_2m,relative_humidity_2m,precipitation"


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
            "hourly": HOURLY,
            "past_days": max(1, min(int(back), 92)),
            "forecast_days": max(1, min(int(forward) + 1, 16)),
            "timezone": "Asia/Kolkata",
        }
        if self.s.weather_api_key:
            params["apikey"] = self.s.weather_api_key

        # A cooldown is in force: do not spend a request finding out that the
        # limit is still there. The caller falls back to labelled-stale cache or
        # is told weather is unavailable — never to a substitute series.
        left = _cooldown_remaining(self.name)
        if left > 0:
            raise WeatherUnavailable(
                self.name,
                f"{_cooldown_reason(self.name) or 'provider unavailable'}; "
                f"not retried for another {int(left) + 1}s")

        # ONE retry, and only for a transport failure — a dropped connection or
        # a timeout on a village network, which is the failure that actually
        # clears by asking again. A 429 or a 5xx is handled below and is never
        # retried: asking a provider that just said "stop" to try again is how
        # a rate limit was being held open in the first place. The pause is
        # jittered so several fields failing together do not come back in step.
        last: Exception | None = None
        r = None
        for attempt in range(2):
            try:
                r = httpx.get(self.s.weather_api_url, params=params,
                              timeout=self.s.weather_timeout_seconds)
                break
            except Exception as exc:
                last = exc
                if attempt == 0:
                    time.sleep(0.25 + random.random() * 0.35)
        if r is None:
            raise WeatherUnavailable(
                self.name, f"{type(last).__name__}: {str(last)[:160]}") from last

        if r.status_code == 429 or r.status_code >= 500:
            # The two shapes of "stop asking". Honour Retry-After when it is
            # sent; otherwise use the configured default. Clamped either way so
            # a hostile or mistaken header cannot park weather for a day.
            hinted = parse_retry_after(r.headers.get("Retry-After")
                                       if hasattr(r, "headers") else None)
            seconds = hinted if hinted is not None else float(self.s.weather_cooldown_seconds)
            seconds = max(1.0, min(seconds, float(self.s.weather_cooldown_max_seconds)))
            why = ("Open-Meteo rate limited the request"
                   if r.status_code == 429 else
                   f"Open-Meteo returned HTTP {r.status_code}")
            _open_cooldown(self.name, seconds, why)
            log.warning("weather provider cooling down",
                        extra={"provider": self.name, "status": r.status_code,
                               "seconds": round(seconds)})
            raise WeatherUnavailable(
                self.name, f"{why}. Not retried for {int(seconds)}s.")

        try:
            r.raise_for_status()
            payload = r.json()
        except Exception as exc:
            raise WeatherUnavailable(
                self.name, f"{type(exc).__name__}: {str(exc)[:160]}") from exc

        h = payload.get("hourly") or {}
        if not h.get("time"):
            raise WeatherUnavailable(self.name, "provider returned no hourly series")

        by_day: dict[dt.date, list[dict[str, float]]] = {}
        times = h["time"]
        temps = h.get("temperature_2m") or []
        rhs = h.get("relative_humidity_2m") or []
        rains = h.get("precipitation") or []
        for i, stamp_iso in enumerate(times):
            if i >= len(temps) or temps[i] is None or i >= len(rhs) or rhs[i] is None:
                continue
            stamp = dt.datetime.fromisoformat(stamp_iso)
            day = stamp.date()
            by_day.setdefault(day, []).append(
                {"t": float(temps[i]), "rh": float(rhs[i]),
                 "rain": float(rains[i] or 0.0) if i < len(rains) else 0.0})
        if not by_day:
            raise WeatherUnavailable(self.name, "provider returned an unusable hourly series")

        days = [_rollup(hours, day, future=day > today)
                for day, hours in sorted(by_day.items())]
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
        out = {"provider": self.name, "configured": True, "url": self.s.weather_api_url}
        left = _cooldown_remaining(self.name)
        if left > 0:
            out["cooling_down_seconds"] = int(left) + 1
            out["cooling_down_reason"] = _cooldown_reason(self.name)
        return out


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

    def _stale(self, key: str) -> dict[str, Any] | None:
        """A cached series past its TTL but still recent enough to be useful.

        Real weather twelve hours old, labelled stale with the reason it could
        not be refreshed, is honest and is what a farmer standing in a field
        would rather have than nothing. Beyond the window it is withheld: an
        infection model run on three-day-old humidity is not a cautious answer,
        it is a wrong one wearing a timestamp.
        """
        row = self.db.one("SELECT * FROM weather_cache WHERE cache_key = :k", {"k": key})
        if not row:
            return None
        fetched = parse_ts(row["fetched_at"])
        if fetched is None:
            return None
        age_h = (now() - fetched).total_seconds() / 3600.0
        if age_h > self.s.weather_stale_max_hours:
            return None
        payload = loads(row["payload"], {})
        if not payload:
            return None
        payload["cached"] = True
        payload["stale"] = True
        payload["fetched_at"] = row["fetched_at"]
        return payload

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

        # Single flight. Ten screens opening on one field at once used to make
        # ten identical provider calls, all of them missing the same cold
        # cache; now nine of them wait here and then read what the first one
        # stored. The lock is per cache key, so different fields never block
        # each other.
        lock = _key_lock(key)
        with lock:
            hit = self._from_cache(key)
            if hit:
                return self._decorate(hit, fresh=True)
            try:
                payload = self.provider.series(lat, lng, today, back, forward)
            except WeatherUnavailable as exc:
                stale = self._stale(key) if allow_stale else None
                if stale is not None:
                    # Stale real data, clearly labelled as stale, beats
                    # generated data — and beats a blank screen.
                    stale["stale_reason"] = exc.reason
                    log.warning("weather provider failed; serving stale cache",
                                extra={"provider": exc.provider, "reason": exc.reason})
                    return self._decorate(stale, fresh=False)
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
