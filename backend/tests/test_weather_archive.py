"""
Observed weather days are kept, and complete a short window later.

The incident: Open-Meteo rate-limited the deployment's shared IP, WeatherAPI's
free plan holds one day of history, and every risk request fell through to
generated weather — although PRAHARI had already been sent the real days.

Guarantees under test: past live days are stored, today and the forecast are
not, generated days never are; a short series is completed only when EVERY
missing day is in the store; stored days are labelled as such; nothing is
interpolated.
"""
from __future__ import annotations

import datetime as dt

import pytest

TODAY = dt.date(2026, 8, 27)


class FakeLive:
    name = "fake-live"
    kind = "live"

    def __init__(self):
        self.mode = "full"

    def can_serve(self, back, forward):
        return True, ""

    def window_for(self, back, forward):
        return back, forward

    def series(self, lat, lng, today, back, forward):
        start = today - dt.timedelta(days=back if self.mode == "full" else 1)
        n = (today - start).days + forward + 1
        days = [{"date": (start + dt.timedelta(days=i)).isoformat(), "src": self.name,
                 "tmin": 20.0, "tmax": 30.0, "rh90_hours": 4.0, "rain_mm": 1.0}
                for i in range(n)]
        out = {"source": self.name, "source_kind": "live", "days": days,
               "history_days": (today - start).days, "history_days_requested": back}
        if self.mode == "short":
            out["insufficient_history"] = True
            out["insufficient_reason"] = "1 day(s) of history available"
        return out

    def health(self):
        return {"provider": self.name}


@pytest.fixture
def ws(env):
    from app.db import Database
    from app.weather import WeatherService
    db = Database(env)
    db.migrate()
    w = WeatherService(db, env)
    w.provider = FakeLive()
    w._demo_fallback = None
    return w


def _stored(ws):
    return {r["day"] for r in ws.db.rows("SELECT day FROM weather_days")}


def test_past_days_are_kept_and_today_and_forecast_are_not(ws):
    ws.series(20.08, 74.11, TODAY, 21, 6)
    stored = _stored(ws)
    assert len(stored) == 21
    assert max(stored) == (TODAY - dt.timedelta(days=1)).isoformat()
    assert TODAY.isoformat() not in stored


def test_a_short_series_is_completed_from_kept_days_and_says_so(ws, monkeypatch):
    ws.series(20.08, 74.11, TODAY, 21, 6)              # Open-Meteo answered once
    ws.db.execute("DELETE FROM weather_cache")          # the cache entry expired
    ws.provider.mode = "short"                          # now history is rate-limited
    out = ws.series(20.08, 74.11, TODAY, 21, 6)
    assert not out.get("insufficient_history")
    assert out["archive_days"] == 20
    assert out["sources"]["history"] == "stored observations"
    kept = [d for d in out["days"] if d.get("archived")]
    assert kept and all(d["src"].endswith("(stored)") for d in kept)
    assert len({d["date"] for d in out["days"]}) == len(out["days"]), "no day twice"


def test_an_incomplete_store_leaves_the_series_short(ws):
    ws.series(20.08, 74.11, TODAY, 21, 6)
    ws.db.execute("DELETE FROM weather_days WHERE day = :d",
                  {"d": (TODAY - dt.timedelta(days=10)).isoformat()})
    ws.db.execute("DELETE FROM weather_cache")
    ws.provider.mode = "short"
    out = ws.series(20.08, 74.11, TODAY, 21, 6)
    assert out.get("insufficient_history") is True, "a gap is never filled by guessing"


def test_another_cell_never_borrows_these_days(ws):
    ws.series(20.08, 74.11, TODAY, 21, 6)
    ws.provider.mode = "short"
    out = ws.series(19.50, 73.80, TODAY, 21, 6)
    assert out.get("insufficient_history") is True


def test_generated_weather_is_never_kept(env):
    from app.db import Database
    from app.weather import WeatherService
    db = Database(env)
    db.migrate()
    w = WeatherService(db, env, demo_profile_fn=lambda: "monsoon")   # demo provider
    w.series(20.08, 74.11, TODAY, 21, 6)
    assert db.scalar("SELECT COUNT(*) FROM weather_days") == 0
