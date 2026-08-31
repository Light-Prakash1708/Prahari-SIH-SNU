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
        def raise_for_status(self): pass
        def json(self):
            t0 = dt.datetime(2026, 8, 20)
            times = [(t0 + dt.timedelta(hours=i)).isoformat() for i in range(24 * 8)]
            return {"hourly": {
                "time": times,
                "temperature_2m": [24.0 if i % 24 < 8 else 31.0 for i in range(len(times))],
                "relative_humidity_2m": [95.0 if i % 24 < 8 else 55.0 for i in range(len(times))],
                "precipitation": [0.5] * len(times),
                "wind_speed_10m": [9.0] * len(times),
                "cloud_cover": [40.0] * len(times)}}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Fake())
    out = OpenMeteoProvider(env).series(20.08, 74.11, dt.date(2026, 8, 25), 21, 6)
    assert out["source"] == "open-meteo"
    assert out["source_kind"] == "live"
    day = out["days"][0]
    assert day["rh90_hours"] == 8.0, "eight hours at 95% must be counted as eight"
    assert day["tmin"] == 24.0 and day["tmax"] == 31.0
    assert day["rain_mm"] == 12.0
    assert day["wind_kmh_mean"] == 9.0
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
