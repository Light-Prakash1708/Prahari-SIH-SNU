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
    """`code` separates two states that need different answers.

    `provider_unavailable` — nobody could be reached. Nothing is known.
    `insufficient_history` — a provider answered, and its plan covers less
    history than the infection models accumulate over. The current conditions
    ARE known; what cannot be produced is a model verdict. Collapsing the two
    into one message is what made a plan limit look like an outage.
    """

    def __init__(self, provider: str, reason: str, code: str = "provider_unavailable",
                 payload: dict[str, Any] | None = None):
        self.provider, self.reason, self.code = provider, reason, code
        # For `insufficient_history` there IS a real reading behind the
        # refusal. Carrying it lets a screen show today's conditions while
        # still refusing to run a model that needs three weeks of them.
        self.payload = payload
        super().__init__(f"{provider}: {reason}")


class WeatherProvider(ABC):
    name = "abstract"
    kind = "none"

    def can_serve(self, back: int, forward: int) -> tuple[bool, str]:
        """Whether this provider's PLAN covers the window being asked for.

        The chain asks before it calls. A provider that cannot cover the window
        is skipped rather than called and truncated, because a short series is
        not a smaller answer — TOMCAST accumulates disease-severity values
        since the last spray and the degree-day models accumulate from sowing,
        so handing them ten days where they asked for twenty-one silently
        changes what they compute. Refusing is the honest failure; the caller
        falls through to the next provider or to labelled-stale cache.
        """
        return True, ""

    def window_for(self, back: int, forward: int) -> tuple[int, int]:
        """The largest slice of the requested window this provider can cover.

        Used only after every provider that could cover the window IN FULL has
        already failed. Returning less is not a smaller answer for the
        accumulating models — the caller marks the result insufficient rather
        than feeding it to them.
        """
        return int(back), int(forward)

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
        if self.s.open_meteo_api_key:
            params["apikey"] = self.s.open_meteo_api_key

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


class WeatherApiProvider(WeatherProvider):
    """WeatherAPI.com — the primary provider when a key is configured.

    Two endpoints, because one call cannot cover both halves of the window:
    `forecast.json` returns hourly for today and the days ahead, `history.json`
    returns one past day per call. The models need hourly temperature, relative
    humidity and precipitation, which is exactly what both return, so the rows
    land in the same `_rollup` every other provider uses and the internal shape
    is unchanged.

    THE PLAN IS THE CONSTRAINT. The free tier is a 3-day forecast and one day
    of history; PRAHARI's risk window is 21 days back. `can_serve` therefore
    turns this provider DOWN for the risk window on a free key, and the chain
    goes to Open-Meteo — which is the correct outcome, not a bug. Configure
    WEATHERAPI_HISTORY_DAYS to whatever the plan actually allows and it becomes
    primary for that window too.

    One past day is one HTTP call, so a large history window is also a large
    number of calls. `_history_call_budget` caps it, and a window that would
    exceed the cap is declined rather than part-filled.
    """
    name = "weatherapi"
    kind = "live"

    def __init__(self, settings: Settings):
        self.s = settings

    def can_serve(self, back: int, forward: int) -> tuple[bool, str]:
        if not self.s.weather_api_key:
            return False, "no WEATHER_API_KEY is configured"
        need_back = max(1, int(back))
        if need_back > int(self.s.weatherapi_history_days):
            return False, (f"the plan allows {self.s.weatherapi_history_days} day(s) of history "
                           f"and this window needs {need_back}")
        cap = int(self.s.weatherapi_max_history_calls)
        if need_back > cap:
            return False, (f"{need_back} days of history is {need_back} separate requests, "
                           f"above the {cap}-call cap (WEATHERAPI_MAX_HISTORY_CALLS)")
        if int(forward) + 1 > int(self.s.weatherapi_forecast_days):
            return False, (f"the plan allows a {self.s.weatherapi_forecast_days}-day forecast "
                           f"and this window needs {int(forward) + 1}")
        return True, ""

    # ── one hourly block, whatever endpoint produced it ────────────────────
    @staticmethod
    def _hours(day_block: dict[str, Any]) -> list[dict[str, float]]:
        out = []
        for h in day_block.get("hour") or []:
            t, rh = h.get("temp_c"), h.get("humidity")
            if t is None or rh is None:
                continue
            out.append({"t": float(t), "rh": float(rh),
                        "rain": float(h.get("precip_mm") or 0.0)})
        return out

    def _get(self, path: str, params: dict[str, Any]):
        import httpx
        left = _cooldown_remaining(self.name)
        if left > 0:
            raise WeatherUnavailable(
                self.name,
                f"{_cooldown_reason(self.name) or 'provider unavailable'}; "
                f"not retried for another {int(left) + 1}s")
        try:
            r = httpx.get(f"{self.s.weatherapi_url.rstrip('/')}/{path}",
                          params={**params, "key": self.s.weather_api_key},
                          timeout=self.s.weather_timeout_seconds)
        except Exception as exc:
            raise WeatherUnavailable(
                self.name, f"{type(exc).__name__}: {str(exc)[:160]}") from exc

        if r.status_code == 429 or r.status_code >= 500:
            hinted = parse_retry_after(r.headers.get("Retry-After")
                                       if hasattr(r, "headers") else None)
            seconds = hinted if hinted is not None else float(self.s.weather_cooldown_seconds)
            seconds = max(1.0, min(seconds, float(self.s.weather_cooldown_max_seconds)))
            why = ("WeatherAPI rate limited the request" if r.status_code == 429
                   else f"WeatherAPI returned HTTP {r.status_code}")
            _open_cooldown(self.name, seconds, why)
            log.warning("weather provider cooling down",
                        extra={"provider": self.name, "status": r.status_code,
                               "seconds": round(seconds)})
            raise WeatherUnavailable(self.name, f"{why}. Not retried for {int(seconds)}s.")

        if r.status_code in (401, 403):
            # A bad key is a configuration fault, not a transient one. Cool the
            # provider down hard so a wrong key does not spend a request per
            # farmer per screen until someone notices.
            _open_cooldown(self.name, float(self.s.weather_cooldown_max_seconds),
                           "WeatherAPI rejected the key")
            raise WeatherUnavailable(self.name, "WeatherAPI rejected the API key.")
        try:
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            raise WeatherUnavailable(
                self.name, f"{type(exc).__name__}: {str(exc)[:160]}") from exc

    def window_for(self, back: int, forward: int) -> tuple[int, int]:
        if not self.s.weather_api_key:
            return 0, 0
        got_back = min(int(back), int(self.s.weatherapi_history_days),
                       int(self.s.weatherapi_max_history_calls))
        got_fwd = min(int(forward), max(0, int(self.s.weatherapi_forecast_days) - 1))
        return max(0, got_back), max(0, got_fwd)

    def series(self, lat, lng, today, back, forward):
        if not self.s.weather_api_key:
            raise WeatherUnavailable(self.name, "no WEATHER_API_KEY is configured")

        # Ask for what the PLAN allows, not for what was requested. Asking for
        # 21 days on a 1-day plan used to refuse the whole call, which — with
        # no fallback behind it — left the farmer with nothing at all when the
        # current conditions were sitting one request away. The shortfall is
        # declared on the payload; deciding what may be computed from a short
        # window is the caller's job, not this class's.
        want_back, want_fwd = int(back), int(forward)
        got_back, got_fwd = self.window_for(want_back, want_fwd)
        short = got_back < want_back or got_fwd < want_fwd

        q = f"{round(float(lat), 4)},{round(float(lng), 4)}"
        by_day: dict[dt.date, list[dict[str, float]]] = {}

        # History: one call per past day, oldest first.
        for n in range(got_back, 0, -1):
            day = today - dt.timedelta(days=n)
            data = self._get("history.json", {"q": q, "dt": day.isoformat()})
            for block in (data.get("forecast") or {}).get("forecastday") or []:
                d = dt.date.fromisoformat(block["date"])
                hours = self._hours(block)
                if hours:
                    by_day.setdefault(d, []).extend(hours)

        # Forecast: today and the days ahead, in one call.
        data = self._get("forecast.json", {
            "q": q, "days": max(1, min(got_fwd + 1,
                                       int(self.s.weatherapi_forecast_days))),
            "aqi": "no", "alerts": "no",
        })
        for block in (data.get("forecast") or {}).get("forecastday") or []:
            d = dt.date.fromisoformat(block["date"])
            hours = self._hours(block)
            if hours:
                by_day.setdefault(d, []).extend(hours)

        if not by_day:
            raise WeatherUnavailable(self.name, "provider returned no hourly series")
        days = [_rollup(hours, day, future=day > today)
                for day, hours in sorted(by_day.items())]
        out = {
            "source": "weatherapi",
            "source_kind": "live",
            "source_url": "https://www.weatherapi.com/",
            "profile": None,
            "days": days,
            "history_days": got_back,
            "history_days_requested": want_back,
            "note": ("Hourly WeatherAPI.com readings for this field's coordinates, rolled up "
                     "here. Hours at RH \u2265 90% are counted from the hourly series, never "
                     "estimated from a daily mean."),
        }
        if short:
            # Real readings, and not enough of them. Said plainly on the
            # payload so nothing downstream has to infer it from a length.
            out["insufficient_history"] = True
            out["insufficient_reason"] = (
                f"this plan covers {got_back} day(s) of history; the infection models "
                f"accumulate over {want_back}")
        return out

    def health(self):
        out = {"provider": self.name, "configured": bool(self.s.weather_api_key),
               "history_days": self.s.weatherapi_history_days,
               "forecast_days": self.s.weatherapi_forecast_days}
        left = _cooldown_remaining(self.name)
        if left > 0:
            out["cooling_down_seconds"] = int(left) + 1
            out["cooling_down_reason"] = _cooldown_reason(self.name)
        return out


class ChainProvider(WeatherProvider):
    """Try each provider in turn; return the first real series.

    Order is configuration, not preference expressed in code: whatever
    `_build` puts in the list is what gets tried. A provider that declines the
    window is skipped without a request, and a provider in cooldown declines
    itself for the same reason — so a rate-limited primary costs nothing on the
    way to the fallback.

    If every provider fails this raises, carrying each one's reason. It never
    blends two providers into one series: a day from one source and a day from
    another have different biases, and the infection models accumulate across
    days.
    """
    kind = "live"

    def __init__(self, providers: list[WeatherProvider]):
        self.providers = providers
        self.name = "+".join(p.name for p in providers) or "none"

    def can_serve(self, back, forward):
        for p in self.providers:
            ok, _ = p.can_serve(back, forward)
            if ok:
                return True, ""
        return False, "no configured provider covers this window"

    def series(self, lat, lng, today, back, forward):
        """Two passes, and the order matters more than anything else here.

        FIRST every provider that can cover the window IN FULL. A complete
        series is the only kind the infection models may run on, so a provider
        offering a partial one must never shadow a provider offering the whole
        thing — that would silently downgrade the risk board on a day when
        Open-Meteo was working perfectly.

        ONLY THEN a partial series, from whoever can produce the most of it.
        That is a real answer to "what is the weather doing" even though it is
        not enough to run an accumulating model on, and it is strictly better
        than telling a farmer nothing. It arrives labelled, and the caller
        decides what may be computed from it.
        """
        reasons = []
        partial: list[WeatherProvider] = []
        for p in self.providers:
            ok, why = p.can_serve(back, forward)
            if not ok:
                reasons.append(f"{p.name}: {why}")
                if p.window_for(back, forward)[0] > 0:
                    partial.append(p)
                continue
            try:
                return p.series(lat, lng, today, back, forward)
            except WeatherUnavailable as exc:
                reasons.append(f"{p.name}: {exc.reason}")
                log.warning("weather provider failed; trying the next",
                            extra={"provider": p.name, "reason": exc.reason})

        for p in sorted(partial, key=lambda x: -x.window_for(back, forward)[0]):
            try:
                out = p.series(lat, lng, today, back, forward)
                log.warning("no provider could cover the full window; serving a short one",
                            extra={"provider": p.name,
                                   "history_days": out.get("history_days")})
                return out
            except WeatherUnavailable as exc:
                reasons.append(f"{p.name}: {exc.reason}")
        raise WeatherUnavailable(self.name, "; ".join(reasons) or "no provider configured")

    def health(self):
        return {"provider": self.name, "configured": bool(self.providers),
                "chain": [p.health() for p in self.providers]}


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
        if p in ("auto", "weatherapi"):
            # WeatherAPI first when a key is configured, Open-Meteo behind it.
            # With no key the chain is Open-Meteo alone, which is exactly what
            # this deployment ran before — so "auto" is safe to set everywhere
            # and the key is the only thing that changes behaviour.
            chain: list[WeatherProvider] = []
            if self.s.weather_api_key:
                chain.append(WeatherApiProvider(self.s))
            # Open-Meteo goes in for BOTH settings, not just "auto". Naming
            # WeatherAPI used to mean "WeatherAPI alone", and on the free plan
            # that provider declines the 21-day risk window — so the whole
            # service failed with "the plan allows 1 day(s) of history and this
            # window needs 21" and there was nothing behind it to ask. A
            # deployment asking for a primary is asking for a primary, not for
            # the removal of its fallback.
            chain.append(OpenMeteoProvider(self.s))
            if not chain:
                log.warning("WEATHER_PROVIDER=weatherapi needs WEATHER_API_KEY; "
                            "no weather provider is configured")
                return NullProvider()
            return chain[0] if len(chain) == 1 else ChainProvider(chain)
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
            # A short series is NOT stored. The cache key describes the window
            # that was asked for, so writing a one-day payload under it would
            # answer the next twenty requests with a series that cannot run a
            # model — for the full ninety minutes, and long after the provider
            # that could cover the window had recovered.
            if not payload.get("insufficient_history"):
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


def status_of(payload: dict[str, Any] | None) -> dict[str, Any]:
    """The one shape the frontend reads to decide what to show.

    Deliberately free of technical detail. "Open-Meteo rate limited the
    request" is a sentence for a log and a status page; a farmer standing in a
    field gets told the update is late and offered a retry. The provider and
    the reason stay in the server log, where someone can act on them.
    """
    if payload is None:
        return {
            "available": False,
            "provider": None,
            "stale": False,
            "code": "provider_unavailable",
            "models_available": False,
            "message": "Weather update temporarily unavailable",
            "message_mr": "हवामान माहिती सध्या मिळत नाही",
            "retryable": True,
        }
    if payload.get("insufficient_history"):
        # Real current weather, and not enough history to forecast on. Saying
        # "unavailable" here would be wrong — the farmer can see conditions.
        return {
            "available": True,
            "provider": payload.get("source"),
            "stale": bool(payload.get("stale")),
            "code": "insufficient_history",
            "models_available": False,
            "message": "Showing current conditions · risk forecast needs more history",
            "message_mr": "सध्याची परिस्थिती दाखवली आहे · अंदाजासाठी पुरेशी जुनी नोंद नाही",
            "retryable": False,
        }
    stale = bool(payload.get("stale"))
    age = (payload.get("freshness") or {}).get("age_minutes")
    if stale:
        when = (f"{age} min ago" if isinstance(age, int) and age < 90
                else "earlier today" if isinstance(age, int) else "recently")
        msg = f"Using recent weather data · updated {when}"
        msg_mr = "अलीकडील हवामान माहिती वापरली आहे"
    else:
        msg = "Weather is up to date"
        msg_mr = "हवामान माहिती अद्ययावत आहे"
    return {
        "available": True,
        "provider": "cache" if stale else payload.get("source"),
        "stale": stale,
        "code": "ok",
        "models_available": True,
        "message": msg,
        "message_mr": msg_mr,
        "retryable": False,
    }


def to_http_error(exc: WeatherUnavailable):
    # The technical reason goes to the log, not to the phone. It used to travel
    # in `detail.reason`, which the error card printed verbatim — so a farmer
    # opening the app during a rate limit read "Open-Meteo rate limited the
    # request. Not retried for 120s." That sentence cannot help them and does
    # not belong on the screen.
    log.warning("weather unavailable",
                extra={"provider": exc.provider, "reason": exc.reason, "code": exc.code})
    if exc.code == "insufficient_history":
        # A different thing from an outage, and the client is told so. The
        # weather is fine; the PLAN covers fewer days than the infection models
        # accumulate over, so there is a reading but no forecast.
        return unavailable(
            "weather_insufficient_history",
            "Current conditions are available, but the risk forecast needs more days of "
            "past weather than this weather plan provides. Nothing has been estimated in "
            "its place, and everything that does not depend on the forecast is unchanged.",
            message_mr=("सध्याची परिस्थिती उपलब्ध आहे, पण अंदाजासाठी लागणारी जुनी हवामान नोंद "
                        "पुरेशी नाही. अंदाजाने काहीही भरलेले नाही; बाकी माहिती जशीच्या तशी आहे."),
            detail={"code": "insufficient_history"})
    return unavailable(
        "weather_unavailable",
        "Weather update temporarily unavailable, so risk cannot be forecast right now. "
        "Nothing has been estimated to fill the gap, and everything that does not depend "
        "on weather is unchanged.",
        message_mr=("हवामान माहिती सध्या मिळत नाही, त्यामुळे धोक्याचा अंदाज देता येत नाही. "
                    "काहीही अंदाजाने भरलेले नाही; बाकी सर्व माहिती जशीच्या तशी आहे."),
        detail={"code": "provider_unavailable"})
