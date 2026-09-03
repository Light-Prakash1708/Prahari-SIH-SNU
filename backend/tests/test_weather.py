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
    from app.weather import ChainProvider, OpenMeteoProvider, WeatherService
    s = reload_settings()
    db = Database(s)
    db.migrate()
    ws = WeatherService(db, s)
    assert isinstance(ws.provider, ChainProvider)
    assert any(isinstance(p, OpenMeteoProvider) for p in ws.provider.providers), \
        "a primary must not remove the fallback behind it"


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
