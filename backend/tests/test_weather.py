"""The weather provider abstraction, its cache and its honest failure."""
from __future__ import annotations

import datetime as dt

import pytest


def test_open_meteo_hourly_series_is_rolled_up_not_averaged(env, monkeypatch):
    """RH-hours must be COUNTED from the hourly series. A daily mean cannot
    produce 'hours at RH >= 90', which is the input three of the four infection
    models need."""
    import httpx
    from app.weather import OpenMeteoProvider

    class Fake:
        """Shaped like a real httpx.Response, because the provider now reads a
        status code and a header off it before it reads the body."""
        status_code = 200
        headers: dict = {}

        def raise_for_status(self): pass
        def json(self):
            t0 = dt.datetime(2026, 8, 20)
            times = [(t0 + dt.timedelta(hours=i)).isoformat() for i in range(24 * 8)]
            return {"hourly": {
                "time": times,
                "temperature_2m": [24.0 if i % 24 < 8 else 31.0 for i in range(len(times))],
                "relative_humidity_2m": [95.0 if i % 24 < 8 else 55.0 for i in range(len(times))],
                "precipitation": [0.5] * len(times)}}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Fake())
    out = OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert out["source"] == "open-meteo"
    assert out["source_kind"] == "live"
    day = out["days"][0]
    assert day["rh90_hours"] == 8.0, "eight hours at 95% must be counted as eight"
    assert day["tmin"] == 24.0 and day["tmax"] == 31.0
    assert day["rain_mm"] == 12.0
    assert "RH ≥ 90" in day["leaf_wetness_note"]


def test_provider_failure_raises_rather_than_substituting(env, monkeypatch):
    import httpx
    from app.weather import OpenMeteoProvider, WeatherUnavailable
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("refused")))
    with pytest.raises(WeatherUnavailable):
        OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)


def test_the_cache_is_used_and_is_labelled(env):
    from app.db import Database
    from app.weather import WeatherService
    db = Database(env)
    db.migrate()
    ws = WeatherService(db, env, demo_profile_fn=lambda: "monsoon")
    first = ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    assert first["cached"] is False
    second = ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    assert second["cached"] is True
    assert second["freshness"]["age_minutes"] is not None


def test_a_stale_cache_beats_generated_data_and_is_labelled_stale(env, monkeypatch):
    from app.db import Database
    from app.weather import WeatherService, WeatherUnavailable
    db = Database(env)
    db.migrate()
    ws = WeatherService(db, env, demo_profile_fn=lambda: "monsoon")
    ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    db.execute("UPDATE weather_cache SET expires_at = '2000-01-01T00:00:00.000Z'")
    monkeypatch.setattr(ws.provider, "series",
                        lambda *a, **k: (_ for _ in ()).throw(
                            WeatherUnavailable("demo", "simulated outage")))
    out = ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    assert out["stale"] is True
    assert out["stale_reason"] == "simulated outage"
    assert out["freshness"]["fresh"] is False


def test_no_provider_configured_fails_loudly(env, monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER", "none")
    from app.config import reload_settings
    from app.db import Database
    from app.weather import WeatherService, WeatherUnavailable
    s = reload_settings()
    db = Database(s)
    db.migrate()
    ws = WeatherService(db, s)
    assert ws.health()["configured"] is False
    with pytest.raises(WeatherUnavailable):
        ws.series(20.08, 74.11, dt.date(2026, 8, 27))


def test_the_demo_provider_refuses_to_run_outside_demo_mode(env, monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER", "demo")
    monkeypatch.setenv("DEMO_MODE", "false")
    from app.config import reload_settings
    from app.db import Database
    from app.weather import NullProvider, WeatherService
    s = reload_settings()
    db = Database(s)
    db.migrate()
    ws = WeatherService(db, s)
    assert isinstance(ws.provider, NullProvider), \
        "generated weather must not be reachable outside demo mode"


def test_a_field_with_no_coordinates_gets_an_error_not_a_guess(env):
    from app.db import Database
    from app.weather import WeatherService, WeatherUnavailable
    db = Database(env)
    db.migrate()
    ws = WeatherService(db, env, demo_profile_fn=lambda: "monsoon")
    with pytest.raises(WeatherUnavailable):
        ws.series(None, None, dt.date(2026, 8, 27))


# ── what keeps PRAHARI off the provider's rate limiter ──────────────────────
# None of the four below may ever produce a weather value. They decide only
# whether an outbound request is attempted, and what a failure is called.

class _Resp:
    """An httpx.Response as far as the provider is concerned."""

    def __init__(self, status_code=200, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _good_payload():
    t0 = dt.datetime(2026, 8, 20)
    times = [(t0 + dt.timedelta(hours=i)).isoformat() for i in range(24 * 8)]
    return {"hourly": {"time": times,
                       "temperature_2m": [26.0] * len(times),
                       "relative_humidity_2m": [80.0] * len(times),
                       "precipitation": [0.0] * len(times)}}


def test_the_request_asks_only_for_the_variables_the_models_read(env, monkeypatch):
    """Open-Meteo weighs a call by variables times days. wind_speed_10m and
    cloud_cover were fetched on every request and read by nothing, so asking
    for them spent quota to produce numbers no screen showed."""
    import httpx
    from app.weather import OpenMeteoProvider
    seen = {}

    def capture(url, params=None, **k):
        seen.update(params or {})
        return _Resp(payload=_good_payload())

    monkeypatch.setattr(httpx, "get", capture)
    OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert seen["hourly"] == "temperature_2m,relative_humidity_2m,precipitation"
    assert "wind_speed_10m" not in seen["hourly"]
    assert "cloud_cover" not in seen["hourly"]


def test_a_rate_limited_provider_is_not_called_again_immediately(env, monkeypatch):
    """The bug this exists to prevent: a 429 raised, nothing was recorded, and
    the next request went straight back out. Under load that holds the
    deployment under its own rate limit indefinitely."""
    import httpx
    from app.weather import OpenMeteoProvider, WeatherUnavailable
    calls = []

    def limited(*a, **k):
        calls.append(1)
        return _Resp(429)

    monkeypatch.setattr(httpx, "get", limited)
    p = OpenMeteoProvider(env)
    with pytest.raises(WeatherUnavailable):
        p.series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert len(calls) == 1

    with pytest.raises(WeatherUnavailable) as second:
        p.series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert len(calls) == 1, "the second request must not reach the provider"
    assert "not retried" in second.value.reason


def test_retry_after_is_honoured_over_the_configured_default(env, monkeypatch):
    import httpx
    from app import weather as wx
    monkeypatch.setattr(httpx, "get",
                        lambda *a, **k: _Resp(429, {"Retry-After": "30"}))
    with pytest.raises(wx.WeatherUnavailable):
        wx.OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    left = wx._cooldown_remaining("open-meteo")
    assert 25 < left <= 30, f"expected the header's 30s, got {left}"


def test_a_malformed_retry_after_falls_back_to_the_configured_default(env, monkeypatch):
    import httpx
    from app import weather as wx
    monkeypatch.setattr(httpx, "get",
                        lambda *a, **k: _Resp(429, {"Retry-After": "soon-ish"}))
    with pytest.raises(wx.WeatherUnavailable):
        wx.OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    left = wx._cooldown_remaining("open-meteo")
    assert 0 < left <= env.weather_cooldown_seconds


def test_an_absurd_retry_after_is_capped(env, monkeypatch):
    """A header is provider input. Weather must not be parked for a day because
    one arrived wrong."""
    import httpx
    from app import weather as wx
    monkeypatch.setattr(httpx, "get",
                        lambda *a, **k: _Resp(429, {"Retry-After": "999999"}))
    with pytest.raises(wx.WeatherUnavailable):
        wx.OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert wx._cooldown_remaining("open-meteo") <= env.weather_cooldown_max_seconds


def test_a_server_error_cools_the_provider_down_too(env, monkeypatch):
    import httpx
    from app import weather as wx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(503))
    with pytest.raises(wx.WeatherUnavailable):
        wx.OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert wx._cooldown_remaining("open-meteo") > 0


def test_a_one_off_timeout_does_not_cool_the_provider_down(env, monkeypatch):
    """A single field timing out is not evidence the provider is refusing
    traffic. Only a 429 or a 5xx is."""
    import httpx
    from app import weather as wx
    monkeypatch.setattr(httpx, "get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("timed out")))
    with pytest.raises(wx.WeatherUnavailable):
        wx.OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert wx._cooldown_remaining("open-meteo") == 0.0


def test_concurrent_requests_for_one_field_make_one_provider_call(env):
    """Ten screens opening on one field used to be ten identical calls, all of
    them missing the same cold cache."""
    import threading
    from app.db import Database
    from app.weather import WeatherService
    db = Database(env)
    db.migrate()
    ws = WeatherService(db, env, demo_profile_fn=lambda: "monsoon")

    calls = []
    real = ws.provider.series

    def counted(*a, **k):
        calls.append(1)
        return real(*a, **k)

    ws.provider.series = counted            # type: ignore[method-assign]
    errors = []

    def ask():
        try:
            ws.series(20.08, 74.11, dt.date(2026, 8, 27))
        except Exception as exc:            # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=ask) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert len(calls) == 1, f"expected one provider call, made {len(calls)}"


def test_a_cache_older_than_the_stale_window_is_withheld_not_served(env, monkeypatch):
    """Stale real weather is served, labelled. Weather old enough to be wrong is
    not — an infection model run on three-day-old humidity is a wrong answer
    wearing a timestamp, which is worse than no answer."""
    from app.db import Database
    from app.weather import WeatherService, WeatherUnavailable
    db = Database(env)
    db.migrate()
    ws = WeatherService(db, env, demo_profile_fn=lambda: "monsoon")
    ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    db.execute("UPDATE weather_cache SET expires_at = '2000-01-01T00:00:00.000Z',"
               " fetched_at = '2000-01-01T00:00:00.000Z'")
    monkeypatch.setattr(ws.provider, "series",
                        lambda *a, **k: (_ for _ in ()).throw(
                            WeatherUnavailable("demo", "simulated outage")))
    with pytest.raises(WeatherUnavailable):
        ws.series(20.08, 74.11, dt.date(2026, 8, 27))


def test_a_dropped_connection_is_retried_once_and_no_more(env, monkeypatch):
    """The failure that actually clears by asking again — and the one that does
    not. A transport error gets a second attempt; a 429 gets none, because
    asking a provider that just said stop is what held the limit open."""
    import httpx
    from app import weather as wx
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("connection reset")
        return _Resp(payload=_good_payload())

    monkeypatch.setattr(httpx, "get", flaky)
    out = wx.OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert out["source"] == "open-meteo"
    assert len(calls) == 2, "one retry, taken"

    calls.clear()

    def always_down(*a, **k):
        calls.append(1)
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", always_down)
    with pytest.raises(wx.WeatherUnavailable):
        wx.OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert len(calls) == 2, "two attempts total, never more"


def test_a_rate_limit_is_never_retried(env, monkeypatch):
    import httpx
    from app import weather as wx
    calls = []

    def limited(*a, **k):
        calls.append(1)
        return _Resp(429)

    monkeypatch.setattr(httpx, "get", limited)
    with pytest.raises(wx.WeatherUnavailable):
        wx.OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert len(calls) == 1


# ── WeatherAPI.com as the primary, Open-Meteo behind it ─────────────────────

def _wapi_day(date_str, temp=26.0, rh=80.0, rain=0.0):
    return {"date": date_str,
            "hour": [{"temp_c": temp, "humidity": rh, "precip_mm": rain} for _ in range(24)]}


def _wapi(env, monkeypatch, **over):
    from app.config import Settings
    return Settings(**{**env.model_dump(), "weather_api_key": "test-key", **over})


def test_weatherapi_declines_a_window_its_plan_cannot_cover(env):
    """The whole reason this provider is not simply first in every case.

    The free tier gives one day of history; the risk board asks for
    twenty-one. Returning ten days would not be a smaller answer — TOMCAST
    accumulates since the last spray and the degree-day models accumulate from
    sowing, so a short series silently changes what they compute. It declines,
    and the chain goes to Open-Meteo.
    """
    from app.config import Settings
    from app.weather import WeatherApiProvider
    s = Settings(**{**env.model_dump(), "weather_api_key": "k",
                    "weatherapi_history_days": 1, "weatherapi_forecast_days": 3})
    ok, why = WeatherApiProvider(s).can_serve(21, 6)
    assert ok is False and "history" in why
    # A paid plan raises the plan limit — and the window is STILL declined,
    # because WeatherAPI returns one past day per request and twenty-one
    # requests to replace Open-Meteo's one is the opposite of fixing a rate
    # limit. Both gates have to be opened deliberately.
    s2 = Settings(**{**env.model_dump(), "weather_api_key": "k",
                     "weatherapi_history_days": 30, "weatherapi_forecast_days": 14})
    ok2, why2 = WeatherApiProvider(s2).can_serve(21, 6)
    assert ok2 is False and "separate requests" in why2
    s3 = Settings(**{**env.model_dump(), "weather_api_key": "k",
                     "weatherapi_history_days": 30, "weatherapi_forecast_days": 14,
                     "weatherapi_max_history_calls": 25})
    assert WeatherApiProvider(s3).can_serve(21, 6)[0] is True
    # and a short window it CAN cover
    assert WeatherApiProvider(s).can_serve(1, 2)[0] is True


def test_weatherapi_without_a_key_never_claims_it_can_serve(env):
    from app.weather import WeatherApiProvider
    ok, why = WeatherApiProvider(env).can_serve(1, 1)
    assert ok is False and "WEATHER_API_KEY" in why


def test_weatherapi_rolls_its_hourly_readings_into_the_same_shape(env, monkeypatch):
    """A · WeatherAPI succeeds. The internal contract is unchanged: the same
    rollup, the same day keys, the same counted RH-hours."""
    import httpx
    from app.config import Settings
    from app.weather import WeatherApiProvider
    today = dt.date(2026, 8, 25)
    s = Settings(**{**env.model_dump(), "weather_api_key": "k",
                    "weatherapi_history_days": 2, "weatherapi_forecast_days": 3})
    seen = []

    def fake(url, params=None, **k):
        seen.append((url, dict(params or {})))
        if "history" in url:
            return _Resp(payload={"forecast": {"forecastday": [_wapi_day(params["dt"], rh=95.0)]}})
        return _Resp(payload={"forecast": {"forecastday": [
            _wapi_day(today.isoformat()), _wapi_day((today + dt.timedelta(days=1)).isoformat())]}})

    monkeypatch.setattr(httpx, "get", fake)
    out = WeatherApiProvider(s).series(20.08, 74.11, today, 2, 1)
    assert out["source"] == "weatherapi" and out["source_kind"] == "live"
    day = out["days"][0]
    assert day["rh90_hours"] == 24.0, "RH-hours are counted from the hourly series"
    assert {"date", "tmin", "tmax", "rain_mm", "hours_21_30", "future"} <= set(day)
    # the key travels as a parameter and never in the path
    assert all(p.get("key") == "k" for _, p in seen)
    assert all("k" not in u for u, _ in seen)


def test_the_chain_falls_through_to_open_meteo(env, monkeypatch):
    """B · WeatherAPI fails, Open-Meteo is tried."""
    import httpx
    from app.config import Settings
    from app.weather import ChainProvider, OpenMeteoProvider, WeatherApiProvider
    s = Settings(**{**env.model_dump(), "weather_api_key": "k",
                    "weatherapi_history_days": 30, "weatherapi_forecast_days": 14,
                    "weatherapi_max_history_calls": 25})
    hits = []

    def fake(url, params=None, **k):
        hits.append(url)
        if "weatherapi" in url:
            return _Resp(500)
        return _Resp(payload=_good_payload())

    monkeypatch.setattr(httpx, "get", fake)
    chain = ChainProvider([WeatherApiProvider(s), OpenMeteoProvider(s)])
    out = chain.series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert out["source"] == "open-meteo", "the fallback served it"
    assert any("weatherapi" in h for h in hits), "the primary was tried first"


def test_a_declining_primary_costs_no_request_at_all(env, monkeypatch):
    """A provider that cannot cover the window is skipped, not called. On the
    free tier that is every risk-board request, so it must be free."""
    import httpx
    from app.config import Settings
    from app.weather import ChainProvider, OpenMeteoProvider, WeatherApiProvider
    s = Settings(**{**env.model_dump(), "weather_api_key": "k",
                    "weatherapi_history_days": 1, "weatherapi_forecast_days": 3})
    hits = []

    def fake(url, params=None, **k):
        hits.append(url)
        return _Resp(payload=_good_payload())

    monkeypatch.setattr(httpx, "get", fake)
    ChainProvider([WeatherApiProvider(s), OpenMeteoProvider(s)]).series(
        20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert not any("weatherapi" in h for h in hits)


def test_both_providers_failing_raises_and_names_both(env, monkeypatch):
    """C/D · with no cache behind it, the chain fails honestly rather than
    inventing a series."""
    import httpx
    from app.config import Settings
    from app.weather import ChainProvider, OpenMeteoProvider, WeatherApiProvider, WeatherUnavailable
    s = Settings(**{**env.model_dump(), "weather_api_key": "k",
                    "weatherapi_history_days": 30, "weatherapi_forecast_days": 14,
                    "weatherapi_max_history_calls": 25})
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(503))
    with pytest.raises(WeatherUnavailable) as exc:
        ChainProvider([WeatherApiProvider(s), OpenMeteoProvider(s)]).series(
            20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert "weatherapi" in exc.value.reason and "open-meteo" in exc.value.reason


def test_a_rejected_key_is_not_retried_on_every_screen(env, monkeypatch):
    """A wrong key is a configuration fault, not a transient one. Retrying it
    per farmer per screen spends the quota and fixes nothing."""
    import httpx
    from app import weather as wx
    from app.config import Settings
    s = Settings(**{**env.model_dump(), "weather_api_key": "bad",
                    "weatherapi_history_days": 30, "weatherapi_forecast_days": 14,
                    "weatherapi_max_history_calls": 25})
    calls = []

    def fake(*a, **k):
        calls.append(1)
        return _Resp(401)

    monkeypatch.setattr(httpx, "get", fake)
    p = wx.WeatherApiProvider(s)
    with pytest.raises(wx.WeatherUnavailable):
        p.series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    with pytest.raises(wx.WeatherUnavailable):
        p.series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert len(calls) == 1, "the second attempt must not reach the provider"


def test_auto_with_no_key_is_exactly_open_meteo(env, monkeypatch):
    """H · the app must start and behave normally with no WEATHER_API_KEY."""
    monkeypatch.setenv("WEATHER_PROVIDER", "auto")
    from app.config import reload_settings
    from app.db import Database
    from app.weather import OpenMeteoProvider, WeatherService
    s = reload_settings()
    db = Database(s)
    db.migrate()
    ws = WeatherService(db, s)
    assert isinstance(ws.provider, OpenMeteoProvider)
    assert ws.health()["configured"] is True


def test_the_status_object_never_carries_the_providers_own_words(env):
    """What the phone is allowed to be told. 'Open-Meteo rate limited the
    request' is a sentence for a log."""
    from app.weather import WeatherUnavailable, status_of, to_http_error
    down = status_of(None)
    assert down["available"] is False and down["stale"] is False
    assert down["provider"] is None and down["retryable"] is True
    blob = str(down).lower()
    for word in ("429", "rate limit", "open-meteo", "http", "weatherapi"):
        assert word not in blob

    err = to_http_error(WeatherUnavailable("open-meteo", "Open-Meteo rate limited the request"))
    body = str(err.detail).lower()
    for word in ("429", "rate limit", "open-meteo"):
        assert word not in body, f"{word!r} reached the client payload"


def test_the_status_object_labels_cached_weather_as_recent_not_broken(env):
    from app.weather import status_of
    fresh = status_of({"source": "weatherapi", "freshness": {"age_minutes": 4}})
    assert fresh["available"] is True and fresh["stale"] is False
    assert fresh["provider"] == "weatherapi"

    old = status_of({"source": "open-meteo", "stale": True,
                     "freshness": {"age_minutes": 40}})
    assert old["available"] is True and old["stale"] is True
    assert old["provider"] == "cache"
    assert "recent weather" in old["message"].lower()


# ── a plan that covers one day of history ──────────────────────────────────
# The production failure this exists to prevent: WEATHER_PROVIDER=weatherapi
# with a free plan logged "the plan allows 1 day(s) of history and this window
# needs 21" and served nothing, because naming a primary had quietly removed
# the fallback behind it.

def _free_plan(env, **over):
    from app.config import Settings
    return Settings(**{**env.model_dump(), "weather_api_key": "k",
                       "weatherapi_history_days": 1, "weatherapi_forecast_days": 3,
                       **over})


def test_naming_weatherapi_still_keeps_open_meteo_behind_it(env, monkeypatch):
    """The bug itself. `weatherapi` used to mean "weatherapi alone"."""
    monkeypatch.setenv("WEATHER_PROVIDER", "weatherapi")
    monkeypatch.setenv("WEATHER_API_KEY", "k")
    from app.config import reload_settings
    from app.db import Database
    from app.weather import (CompositeProvider, OpenMeteoProvider,
                             WeatherApiProvider, WeatherService)
    s = reload_settings()
    db = Database(s)
    db.migrate()
    ws = WeatherService(db, s)
    assert isinstance(ws.provider, CompositeProvider)
    assert isinstance(ws.provider.primary, WeatherApiProvider), \
        "WeatherAPI stays the configured primary"
    assert isinstance(ws.provider.historical, OpenMeteoProvider), \
        "a primary must not remove the history provider behind it"


def test_a_free_plan_falls_through_to_open_meteo_for_the_risk_window(env, monkeypatch):
    """The 21-day window is served, by the provider that can serve it, and the
    one-day plan costs no request on the way past."""
    import httpx
    from app.weather import ChainProvider, OpenMeteoProvider, WeatherApiProvider
    s = _free_plan(env)
    hits = []

    def fake(url, params=None, **k):
        hits.append(url)
        return _Resp(payload=_good_payload())

    monkeypatch.setattr(httpx, "get", fake)
    out = ChainProvider([WeatherApiProvider(s), OpenMeteoProvider(s)]).series(
        20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert out["source"] == "open-meteo"
    assert not out.get("insufficient_history")
    assert not any("weatherapi" in h for h in hits), "the declining plan cost nothing"


def test_a_short_window_is_served_only_when_nothing_else_can(env, monkeypatch):
    """C · Open-Meteo down as well. Rather than nothing, the farmer gets the
    real current conditions — labelled as too short to forecast on."""
    import httpx
    from app.weather import ChainProvider, OpenMeteoProvider, WeatherApiProvider
    s = _free_plan(env)
    today = dt.date(2026, 8, 27)

    def fake(url, params=None, **k):
        if "open-meteo" in url or "openmeteo" in url:
            return _Resp(503)
        if "history" in url:
            return _Resp(payload={"forecast": {"forecastday": [_wapi_day(params["dt"])]}})
        return _Resp(payload={"forecast": {"forecastday": [_wapi_day(today.isoformat())]}})

    monkeypatch.setattr(httpx, "get", fake)
    out = ChainProvider([WeatherApiProvider(s), OpenMeteoProvider(s)]).series(
        20.08, 74.11, today, 21, 6)
    assert out["source"] == "weatherapi"
    assert out["insufficient_history"] is True
    assert out["history_days"] == 1 and out["history_days_requested"] == 21
    assert out["days"], "and it is a real reading, not an empty shell"


def test_a_complete_series_always_beats_a_partial_one(env, monkeypatch):
    """The regression that would matter most: a partial provider must never
    shadow one that can cover the whole window."""
    import httpx
    from app.weather import ChainProvider, OpenMeteoProvider, WeatherApiProvider
    s = _free_plan(env)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(payload=_good_payload()))
    out = ChainProvider([WeatherApiProvider(s), OpenMeteoProvider(s)]).series(
        20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert out["source"] == "open-meteo" and not out.get("insufficient_history")


def test_a_short_series_is_never_cached_under_the_full_windows_key(env, monkeypatch):
    """Caching it would answer the next ninety minutes of requests with a
    series no model can run on, long after the full provider had recovered."""
    from app.db import Database
    from app.weather import WeatherService
    db = Database(env)
    db.migrate()
    ws = WeatherService(db, env, demo_profile_fn=lambda: "monsoon")
    monkeypatch.setattr(ws.provider, "series", lambda *a, **k: {
        "source": "weatherapi", "source_kind": "live", "days": [{"date": "2026-08-27"}],
        "insufficient_history": True, "history_days": 1, "history_days_requested": 21})
    out = ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    assert out["insufficient_history"] is True
    assert db.scalar("SELECT COUNT(*) FROM weather_cache") == 0


def test_the_status_object_separates_a_plan_limit_from_an_outage(env):
    """8 · insufficient_history is its own state. Weather IS available; what is
    not available is a model verdict."""
    from app.weather import status_of
    st = status_of({"source": "weatherapi", "insufficient_history": True,
                    "freshness": {"age_minutes": 2}})
    assert st["available"] is True, "the farmer can see conditions"
    assert st["models_available"] is False
    assert st["code"] == "insufficient_history"
    assert status_of(None)["code"] == "provider_unavailable"
    for word in ("429", "rate limit", "http", "weatherapi.com"):
        assert word not in str(st).lower()


def test_a_plan_limit_and_an_outage_are_different_http_bodies(env):
    """8 · so a deployment reading logs, and a screen reading `code`, can tell
    "we could not reach anyone" from "we reached them and the plan is short"."""
    from app.weather import WeatherUnavailable, to_http_error
    short = to_http_error(WeatherUnavailable(
        "weatherapi", "this plan covers 1 day(s) of history",
        code="insufficient_history"))
    assert short.detail["error"] == "weather_insufficient_history"
    assert short.detail["detail"]["code"] == "insufficient_history"
    assert "estimated" in short.detail["message"]

    down = to_http_error(WeatherUnavailable("open-meteo", "Open-Meteo rate limited"))
    assert down.detail["error"] == "weather_unavailable"
    for body in (str(short.detail).lower(), str(down.detail).lower()):
        for leak in ("rate limited", "429", "open-meteo", "weatherapi\","):
            assert leak not in body


# ── the two-source window ───────────────────────────────────────────────────
# The free WeatherAPI plan holds one day of history; the infection models
# accumulate over twenty-one. Choosing between the providers throws away
# whichever half you did not choose, so the window is split at the primary's
# own coverage boundary and each side supplies its part.

def _composite(env, **over):
    from app.config import Settings
    from app.weather import CompositeProvider, OpenMeteoProvider, WeatherApiProvider
    s = Settings(**{**env.model_dump(), "weather_api_key": "k",
                    "weatherapi_history_days": 1, "weatherapi_forecast_days": 3, **over})
    return CompositeProvider(WeatherApiProvider(s), OpenMeteoProvider(s)), s


def _om_window(today, back=21, forward=6):
    """An Open-Meteo hourly payload that really does cover the asked-for window,
    so a coverage assertion is testing the code and not the fixture."""
    start = dt.datetime.combine(today - dt.timedelta(days=back), dt.time())
    n = 24 * (back + forward + 1)
    times = [(start + dt.timedelta(hours=i)).isoformat() for i in range(n)]
    return {"hourly": {"time": times,
                       "temperature_2m": [26.0] * n,
                       "relative_humidity_2m": [85.0] * n,
                       "precipitation": [0.1] * n}}


def _routed(today, om_status=200, wapi_status=200):
    """One fake httpx.get that answers as whichever provider was called."""
    import httpx

    def fake(url, params=None, **k):
        if "open-meteo" in url or "openmeteo" in url:
            if om_status != 200:
                return _Resp(om_status)
            return _Resp(payload=_om_window(today))
        if wapi_status != 200:
            return _Resp(wapi_status)
        if "history" in url:
            return _Resp(payload={"forecast": {"forecastday": [_wapi_day(params["dt"])]}})
        n = int((params or {}).get("days", 1))
        return _Resp(payload={"forecast": {"forecastday": [
            _wapi_day((today + dt.timedelta(days=i)).isoformat()) for i in range(n)]}})
    return fake


def test_B_a_one_day_plan_still_gets_the_models_their_full_window(env, monkeypatch):
    """B · the scenario in production. WeatherAPI covers today and the
    forecast; Open-Meteo supplies the older days the models accumulate over,
    and the result is a complete twenty-one-day window."""
    import httpx
    today = dt.date(2026, 8, 25)
    cp, _ = _composite(env)
    monkeypatch.setattr(httpx, "get", _routed(today))
    out = cp.series(20.08, 74.11, today, 21, 6)

    assert not out.get("insufficient_history"), "the window is covered end to end"
    assert out["history_days"] >= 21
    assert out["sources"]["history"] == "open-meteo"
    assert out["sources"]["recent"] == "weatherapi"
    assert out["sources"]["forecast"] == "weatherapi"

    # every day says who reported it, and the seam is where it should be
    srcs = {d["src"] for d in out["days"]}
    assert srcs == {"open-meteo", "weatherapi"}
    boundary = today - dt.timedelta(days=1)
    for d in out["days"]:
        day = dt.date.fromisoformat(d["date"])
        assert d["src"] == ("weatherapi" if day >= boundary else "open-meteo")
    # dates are unique and ordered — no day counted twice across the seam
    dates = [d["date"] for d in out["days"]]
    assert dates == sorted(dates) and len(dates) == len(set(dates))


def test_A_current_and_forecast_come_from_the_primary(env, monkeypatch):
    """A · WeatherAPI is still the primary for what a farmer looks at."""
    import httpx
    today = dt.date(2026, 8, 25)
    cp, _ = _composite(env)
    monkeypatch.setattr(httpx, "get", _routed(today))
    out = cp.series(20.08, 74.11, today, 21, 6)
    future = [d for d in out["days"] if d.get("future")]
    assert future and all(d["src"] == "weatherapi" for d in future)
    today_row = next(d for d in out["days"] if d["date"] == today.isoformat())
    assert today_row["src"] == "weatherapi"


def test_C_the_primary_failing_leaves_a_complete_series(env, monkeypatch):
    """C · Open-Meteo covers the whole window by itself, so a WeatherAPI outage
    costs provenance, not the forecast."""
    import httpx
    today = dt.date(2026, 8, 25)
    cp, _ = _composite(env)
    monkeypatch.setattr(httpx, "get", _routed(today, wapi_status=503))
    out = cp.series(20.08, 74.11, today, 21, 6)
    assert out["source"] == "open-meteo"
    assert not out.get("insufficient_history")


def test_D_the_history_provider_failing_leaves_current_conditions(env, monkeypatch):
    """D · WeatherAPI still answers for today; the window is short and says so,
    and the models refuse it rather than accumulating over one day."""
    import httpx
    today = dt.date(2026, 8, 25)
    cp, _ = _composite(env)
    monkeypatch.setattr(httpx, "get", _routed(today, om_status=503))
    out = cp.series(20.08, 74.11, today, 21, 6)
    assert out["source"] == "weatherapi"
    assert out["insufficient_history"] is True
    assert out["days"], "current conditions are real and are kept"


def test_E_both_failing_raises_and_names_both(env, monkeypatch):
    """E · a graceful, typed failure — not a crash, and not a guess."""
    import httpx
    from app.weather import WeatherUnavailable
    today = dt.date(2026, 8, 25)
    cp, _ = _composite(env)
    monkeypatch.setattr(httpx, "get", _routed(today, om_status=503, wapi_status=503))
    with pytest.raises(WeatherUnavailable) as exc:
        cp.series(20.08, 74.11, today, 21, 6)
    assert "weatherapi" in exc.value.reason and "open-meteo" in exc.value.reason


def test_F_a_covered_window_is_cached_and_not_re_fetched(env, monkeypatch):
    """F · opening Home and Management repeatedly must not spend requests."""
    import httpx
    from app.db import Database
    from app.config import Settings
    from app.weather import (CompositeProvider, OpenMeteoProvider,
                             WeatherApiProvider, WeatherService)
    today = dt.date(2026, 8, 27)
    s = Settings(**{**env.model_dump(), "weather_api_key": "k",
                    "weatherapi_history_days": 1, "weatherapi_forecast_days": 3})
    db = Database(s)
    db.migrate()
    calls = []
    inner = _routed(today)

    def counting(url, params=None, **k):
        calls.append(url)
        return inner(url, params=params, **k)

    monkeypatch.setattr(httpx, "get", counting)
    ws = WeatherService(db, s)
    ws.provider = CompositeProvider(WeatherApiProvider(s), OpenMeteoProvider(s))
    ws.series(20.08, 74.11, today)
    first = len(calls)
    assert first > 0
    for _ in range(10):
        ws.series(20.08, 74.11, today)
    assert len(calls) == first, f"cache leaked {len(calls) - first} extra requests"
    assert db.scalar("SELECT COUNT(*) FROM weather_cache") == 1


def test_G_no_key_starts_and_uses_open_meteo(env, monkeypatch):
    """G · a missing WEATHER_API_KEY is a configuration state, not a crash."""
    monkeypatch.setenv("WEATHER_PROVIDER", "weatherapi")
    monkeypatch.delenv("WEATHER_API_KEY", raising=False)
    from app.config import reload_settings
    from app.db import Database
    from app.weather import OpenMeteoProvider, WeatherService
    s = reload_settings()
    db = Database(s)
    db.migrate()
    ws = WeatherService(db, s)
    assert isinstance(ws.provider, OpenMeteoProvider)
    assert ws.health()["configured"] is True


def test_H_no_provider_at_all_still_starts(env, monkeypatch):
    """H · WEATHER_PROVIDER=none is a supported deployment, not an error."""
    monkeypatch.setenv("WEATHER_PROVIDER", "none")
    from app.config import reload_settings
    from app.db import Database
    from app.weather import NullProvider, WeatherService, WeatherUnavailable
    s = reload_settings()
    db = Database(s)
    db.migrate()
    ws = WeatherService(db, s)
    assert isinstance(ws.provider, NullProvider)
    assert ws.health()["configured"] is False
    with pytest.raises(WeatherUnavailable):
        ws.series(20.08, 74.11, dt.date(2026, 8, 27))


def test_the_composite_never_invents_a_day_across_the_seam(env, monkeypatch):
    """Nothing is interpolated where the two sources meet. A day neither
    provider reported is simply absent."""
    import httpx
    today = dt.date(2026, 8, 25)
    cp, _ = _composite(env)

    def gappy(url, params=None, **k):
        if "open-meteo" in url or "openmeteo" in url:
            # a series with a hole in the middle of the historical range
            t0 = dt.datetime(2026, 8, 4)
            times, temps, rhs, rains = [], [], [], []
            for i in range(24 * 21):
                stamp = t0 + dt.timedelta(hours=i)
                if stamp.date() == dt.date(2026, 8, 10):
                    continue
                times.append(stamp.isoformat()); temps.append(26.0)
                rhs.append(85.0); rains.append(0.0)
            return _Resp(payload={"hourly": {"time": times, "temperature_2m": temps,
                                             "relative_humidity_2m": rhs,
                                             "precipitation": rains}})
        if "history" in url:
            return _Resp(payload={"forecast": {"forecastday": [_wapi_day(params["dt"])]}})
        return _Resp(payload={"forecast": {"forecastday": [_wapi_day(today.isoformat())]}})

    monkeypatch.setattr(httpx, "get", gappy)
    out = cp.series(20.08, 74.11, today, 21, 6)
    assert "2026-08-10" not in [d["date"] for d in out["days"]], \
        "a day nobody reported must not appear"


def test_the_response_says_which_provider_supplied_which_part(client, farmer, plot,
                                                              monkeypatch):
    """15 + 16 · live, forecast and historical are distinguishable in the
    payload, not just in the log."""
    import httpx
    from app.config import Settings
    from app.runtime import get_runtime
    from app.weather import CompositeProvider, OpenMeteoProvider, WeatherApiProvider
    today = dt.date(2026, 8, 27)
    s = Settings(**{**client.settings.model_dump(), "weather_api_key": "k",
                    "weatherapi_history_days": 1, "weatherapi_forecast_days": 3})
    rt = get_runtime()
    rt.weather.provider = CompositeProvider(WeatherApiProvider(s), OpenMeteoProvider(s))
    rt.db.execute("DELETE FROM weather_cache")
    monkeypatch.setattr(httpx, "get", _routed(today))

    body = client.get(f"/api/risk/{plot['id']}", headers=farmer["headers"]).json()
    w = body["weather"]
    assert w["sources"]["history"] == "open-meteo"
    assert w["sources"]["recent"] == "weatherapi"
    assert w["sources"]["forecast"] == "weatherapi"
    assert w["history_days"] >= 21 and w["history_days_requested"] == 21
    assert {d["src"] for d in w["days"]} == {"open-meteo", "weatherapi"}
    # and no credential rides along with the provenance
    assert "k" not in str(w.get("sources")) and "key" not in str(w).lower()[:2000]


def test_every_day_carries_its_source_in_every_branch(env, monkeypatch):
    """15 · `src` is never absent, so a missing tag can never be mistaken for
    'unknown provider'."""
    import httpx
    from app.weather import clear_cooldowns
    today = dt.date(2026, 8, 25)
    for om, wa in ((200, 200), (200, 503), (503, 200)):
        # Each case is its own outage. Without this the 503 in one iteration
        # leaves a cooldown that makes the next one fail for the wrong reason —
        # which is the cooldown working, not the composite failing.
        clear_cooldowns()
        cp, _ = _composite(env)
        monkeypatch.setattr(httpx, "get", _routed(today, om_status=om, wapi_status=wa))
        out = cp.series(20.08, 74.11, today, 21, 6)
        assert out["days"], f"om={om} wa={wa}"
        assert all(d.get("src") for d in out["days"]), f"untagged day with om={om} wa={wa}"
        assert out["sources"], f"no sources breakdown with om={om} wa={wa}"


def test_the_weather_api_key_is_never_written_to_a_log(env, monkeypatch, caplog):
    """WeatherAPI authenticates with `?key=` — its documented method — and
    httpx logs every outgoing URL at INFO. At LOG_LEVEL=INFO, which is the
    default and what the deployment runs, that wrote the live key into the
    application log on every weather fetch.

    A credential in a URL has to be silenced at the logger, not redacted after
    the fact: by the time it is a formatted string it has already been handed
    to every handler attached to the root.
    """
    import logging

    import httpx

    # 1 · nothing PRAHARI itself logs carries the credential, and the
    #     provenance line that replaced it names providers only.
    today = dt.date(2026, 8, 25)
    cp, _ = _composite(env)
    monkeypatch.setattr(httpx, "get", _routed(today))
    with caplog.at_level(logging.DEBUG):
        cp.series(20.08, 74.11, today, 21, 6)
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "key=" not in blob and "stub-key" not in blob
    assert any("weather assembled" in r.getMessage() for r in caplog.records)

    # 2 · and the client library that WOULD print it is held below INFO.
    #     Checked after the capture because configure_logging replaces the
    #     root handlers, which is what detaches caplog.
    from app.obs import configure_logging
    configure_logging()
    for noisy in ("httpx", "httpcore", "urllib3"):
        assert logging.getLogger(noisy).level >= logging.WARNING, noisy


# ── the fallback pipeline, tier by tier ─────────────────────────────────────
# live -> stale cache -> generated (opt-in) -> honest failure.
# The last two tiers are the ones worth pinning: one must never be mistaken for
# an observation, and the other must never appear unless someone asked for it.

def _svc(env, demo_fallback=False, **over):
    from app.config import Settings
    from app.db import Database
    from app.weather import WeatherService
    s = Settings(**{**env.model_dump(), "weather_demo_fallback": demo_fallback, **over})
    db = Database(s)
    db.migrate()
    return WeatherService(db, s, demo_profile_fn=lambda: "monsoon"), db, s


def _dead(*a, **k):
    from app.weather import WeatherUnavailable
    raise WeatherUnavailable("open-meteo", "simulated total outage")


def test_a_live_provider_is_used_and_labelled_live(env):
    """Tier 1 · nothing below it runs while a live provider answers."""
    ws, _db, _s = _svc(env, demo_fallback=True)
    out = ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    assert out["source_kind"] != "generated" or env.weather_provider == "demo"
    assert not out.get("demo_fallback")


def test_the_cache_is_preferred_over_generated_weather(env, monkeypatch):
    """Tier 2 · a real reading from an hour ago beats an invented one from now,
    even with the fallback armed. Stale real data is still data."""
    ws, db, _s = _svc(env, demo_fallback=True)
    ws.series(20.08, 74.11, dt.date(2026, 8, 27))          # warm the cache
    db.execute("UPDATE weather_cache SET expires_at = '2000-01-01T00:00:00.000Z'")
    monkeypatch.setattr(ws.provider, "series", _dead)
    out = ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    assert out["stale"] is True
    assert not out.get("demo_fallback"), "the cache must win over generated weather"


def test_with_no_cache_the_generated_series_stands_in(env, monkeypatch):
    """Tier 3 · and it says what it is, in every field that carries provenance."""
    from app.weather import status_of
    ws, db, _s = _svc(env, demo_fallback=True)
    monkeypatch.setattr(ws.provider, "series", _dead)
    db.execute("DELETE FROM weather_cache")
    out = ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    assert out["demo_fallback"] is True
    assert out["source_kind"] == "generated"
    assert out["warning"], "a generated series must carry its warning"
    assert "DEMO_MODE" not in out["warning"], \
        "the flag brought this on, not DEMO_MODE — say the true thing"
    assert "not real weather" in out["warning"]
    assert out["days"], "and it must be a usable series, not an empty shell"
    st = status_of(out)
    assert st["code"] == "demo" and st["generated"] is True
    assert "generated" in st["message"].lower()
    # it is never written into the cache — an hour later it would be
    # indistinguishable from a remembered observation
    assert db.scalar("SELECT COUNT(*) FROM weather_cache") == 0


def test_the_fallback_is_off_unless_a_deployment_asks_for_it(env, monkeypatch):
    """The default. Without the flag the failure is still a failure — which is
    what this system is supposed to do with weather it does not have."""
    from app.weather import WeatherUnavailable
    ws, db, _s = _svc(env, demo_fallback=False)
    monkeypatch.setattr(ws.provider, "series", _dead)
    db.execute("DELETE FROM weather_cache")
    with pytest.raises(WeatherUnavailable):
        ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    assert ws.health().get("demo_fallback") is None


def test_generated_weather_is_deterministic_for_one_field(env, monkeypatch):
    """8 · refreshing the page must not reroll the weather."""
    ws, db, _s = _svc(env, demo_fallback=True)
    monkeypatch.setattr(ws.provider, "series", _dead)
    db.execute("DELETE FROM weather_cache")
    a = ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    b = ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    assert [d["date"] for d in a["days"]] == [d["date"] for d in b["days"]]
    for x, y in zip(a["days"], b["days"], strict=True):
        assert (x["tmin"], x["tmax"], x["rain_mm"], x["rh90_hours"]) == \
               (y["tmin"], y["tmax"], y["rain_mm"], y["rh90_hours"])


def test_generated_weather_carries_the_fields_the_models_read(env, monkeypatch):
    """7 · the same structure, so the same pipeline runs on it unchanged."""
    ws, db, _s = _svc(env, demo_fallback=True)
    monkeypatch.setattr(ws.provider, "series", _dead)
    db.execute("DELETE FROM weather_cache")
    out = ws.series(20.08, 74.11, dt.date(2026, 8, 27))
    for day in out["days"]:
        assert {"date", "tmin", "tmax", "rh_mean", "rh90_hours", "rain_mm",
                "hours_21_30", "future"} <= set(day)
    assert any(d["future"] for d in out["days"]), "a forecast portion exists"


# ── the weather card is a different question from the risk board ────────────

def _wx_card(client, headers, plot_id, expect=200):
    r = client.get(f"/api/fields/{plot_id}/weather", headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def test_the_weather_card_renders_when_the_risk_board_cannot(client, farmer, plot,
                                                             monkeypatch):
    """6 + 7 · the whole point. The models need three weeks and say so; the
    forecast needs a week and is fine. Tying them together is what made a
    history limit look like a broken forecast."""
    from app import weather as wx_mod
    real = wx_mod.WeatherService.series

    def short_for_models(self, lat, lng, today, back=21, forward=6, **k):
        out = real(self, lat, lng, today, back=back, forward=forward, **k)
        if back > 7:                       # only the model window is starved
            out = dict(out)
            out["insufficient_history"] = True
            out["insufficient_reason"] = "this plan covers 1 day(s) of history"
        return out

    monkeypatch.setattr(wx_mod.WeatherService, "series", short_for_models)

    card = _wx_card(client, farmer["headers"], plot["id"])
    assert card["available"] is True
    assert card["current"] and card["forecast"], "the forecast still renders"
    # and the risk board is still honest about what it cannot do
    r = client.get(f"/api/risk/{plot['id']}", headers=farmer["headers"])
    assert r.status_code in (200, 503)
    if r.status_code == 503:
        assert r.json()["error"] == "weather_insufficient_history"


def test_the_weather_card_never_answers_503(client, farmer, plot, monkeypatch):
    """8 + 11 · a provider outage is not an application error. Even with every
    tier gone the card answers 200 and says it has nothing."""
    from app import weather as wx_mod
    from app.runtime import get_runtime
    get_runtime().weather._demo_fallback = None
    monkeypatch.setattr(
        wx_mod.WeatherService, "series",
        lambda *a, **k: (_ for _ in ()).throw(
            wx_mod.WeatherUnavailable("open-meteo", "simulated outage")))
    card = _wx_card(client, farmer["headers"], plot["id"])
    assert card["available"] is False
    assert card["status"]["code"] == "provider_unavailable"
    assert card["forecast"] == [] and card["current"] is None


def test_the_card_falls_back_to_generated_weather_and_labels_it(client, farmer, plot,
                                                                monkeypatch):
    """3 + 11 · never "weather unavailable" while a generated series can be
    produced — and never without saying it is generated."""
    from app import weather as wx_mod
    from app.runtime import get_runtime
    rt = get_runtime()
    rt.weather._demo_fallback = wx_mod.DemoWeatherProvider(lambda: "monsoon")
    rt.db.execute("DELETE FROM weather_cache")
    monkeypatch.setattr(
        rt.weather.provider, "series",
        lambda *a, **k: (_ for _ in ()).throw(
            wx_mod.WeatherUnavailable("open-meteo", "simulated outage")))

    card = _wx_card(client, farmer["headers"], plot["id"])
    assert card["available"] is True
    assert card["generated"] is True and card["status"]["code"] == "demo"
    assert card["warning"], "a generated card must carry its warning"
    assert len(card["forecast"]) == 7
    assert card["current"]["condition"] and card["current"]["icon"]


def test_the_generated_card_is_complete_and_internally_consistent(client, farmer, plot,
                                                                  monkeypatch):
    """3 · every field the card promises, and every value inside a sane range.
    A forecast that says 31°/34° or 140% rain is worse than none."""
    from app import weather as wx_mod
    from app.runtime import get_runtime
    rt = get_runtime()
    rt.weather._demo_fallback = wx_mod.DemoWeatherProvider(lambda: "monsoon")
    rt.db.execute("DELETE FROM weather_cache")
    monkeypatch.setattr(
        rt.weather.provider, "series",
        lambda *a, **k: (_ for _ in ()).throw(
            wx_mod.WeatherUnavailable("open-meteo", "simulated outage")))

    card = _wx_card(client, farmer["headers"], plot["id"])
    need = {"date", "day", "condition", "icon", "temp_min_c", "temp_max_c",
            "humidity_pct", "rain_mm", "rain_chance_pct", "wind_kmh",
            "wind_dir", "uv_index", "cloud_pct", "feels_like_c"}
    for d in card["forecast"]:
        assert need <= set(d), f"missing {need - set(d)} on {d['date']}"
        assert d["temp_min_c"] <= d["temp_max_c"], d["date"]
        assert 0 <= d["rain_chance_pct"] <= 100
        assert 0 <= d["humidity_pct"] <= 100
        assert 0 <= d["cloud_pct"] <= 100
        assert 0 <= d["uv_index"] <= 12
        assert d["wind_kmh"] >= 0
        assert d["rain_mm"] >= 0
    dates = [d["date"] for d in card["forecast"]]
    assert dates == sorted(dates) and len(dates) == len(set(dates))


def test_the_generated_card_is_identical_on_every_refresh(client, farmer, plot,
                                                          monkeypatch):
    """4 + 5 · refreshing must not reroll the weather."""
    from app import weather as wx_mod
    from app.runtime import get_runtime
    rt = get_runtime()
    rt.weather._demo_fallback = wx_mod.DemoWeatherProvider(lambda: "monsoon")
    monkeypatch.setattr(
        rt.weather.provider, "series",
        lambda *a, **k: (_ for _ in ()).throw(
            wx_mod.WeatherUnavailable("open-meteo", "simulated outage")))
    shots = []
    for _ in range(3):
        rt.db.execute("DELETE FROM weather_cache")
        shots.append(_wx_card(client, farmer["headers"], plot["id"])["forecast"])
    assert shots[0] == shots[1] == shots[2]


def test_two_fields_get_different_but_stable_generated_weather(env):
    """4 · same field, same forecast; different field, different forecast."""
    from app.weather import DemoWeatherProvider
    p = DemoWeatherProvider(lambda: "monsoon")
    today = dt.date(2026, 8, 27)
    a1 = p.series(20.0810, 74.1100, today, 1, 6)["days"]
    a2 = p.series(20.0810, 74.1100, today, 1, 6)["days"]
    b = p.series(20.1712, 73.9855, today, 1, 6)["days"]
    assert [d["tmax"] for d in a1] == [d["tmax"] for d in a2], "same field, same numbers"
    assert [d["tmax"] for d in a1] != [d["tmax"] for d in b], "different field, different"


def test_the_field_outlook_is_read_from_the_numbers_not_hardcoded(env):
    """5 · a dry week and a wet one must not produce the same advice."""
    from app.weather import DemoWeatherProvider, forecast_view
    today = dt.date(2026, 8, 27)
    wet = forecast_view(DemoWeatherProvider(lambda: "monsoon").series(
        20.08, 74.11, today, 1, 6), {"crop": "tomato"})
    dry = forecast_view(DemoWeatherProvider(lambda: "dry").series(
        20.08, 74.11, today, 1, 6), {"crop": "tomato"})
    wet_titles = [o["title"] for o in wet["field_outlook"]]
    dry_titles = [o["title"] for o in dry["field_outlook"]]
    assert wet_titles != dry_titles
    assert any("rain" in t.lower() for t in wet_titles)
    assert any("no rain" in t.lower() or "dry" in t.lower() for t in dry_titles)
    assert all(o["body"] for o in wet["field_outlook"] + dry["field_outlook"])


def test_live_weather_keeps_the_display_fields_weatherapi_already_sends(env, monkeypatch):
    """1 · wind, UV, cloud and the condition come back in the same response and
    were being discarded. They are observed, and they are never fed to a model."""
    import httpx
    from app.config import Settings
    from app.weather import WeatherApiProvider, forecast_view
    today = dt.date(2026, 8, 25)
    s = Settings(**{**env.model_dump(), "weather_api_key": "k",
                    "weatherapi_history_days": 1, "weatherapi_forecast_days": 3})

    def rich(url, params=None, **k):
        hours = [{"temp_c": 27.0, "humidity": 70, "precip_mm": 0.1, "wind_kph": 12.0,
                  "uv": 7.0, "cloud": 40, "feelslike_c": 29.0, "chance_of_rain": 30,
                  "condition": {"text": "Partly cloudy"}} for _ in range(24)]
        day = {"date": (params or {}).get("dt") or today.isoformat(), "hour": hours}
        return _Resp(payload={"forecast": {"forecastday": [day]}})

    monkeypatch.setattr(httpx, "get", rich)
    out = WeatherApiProvider(s).series(20.08, 74.11, today, 1, 2)
    d = out["days"][-1]
    assert d["wind_kmh_max"] == 12.0 and d["uv_max"] == 7.0
    assert d["condition"] == "Partly cloudy" and d["rain_chance_pct"] == 30.0
    view = forecast_view(out, {"crop": "tomato"})
    assert view["current"]["uv_index"] == 7.0
    assert view["generated"] is False
