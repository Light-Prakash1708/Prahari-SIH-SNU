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
