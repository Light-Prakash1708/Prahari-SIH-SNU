"""
PRAHARI · summit readiness — the things that would embarrass us in Bengal
════════════════════════════════════════════════════════════════════════════
Each test pins one finding from docs/PRAHARI_SUMMIT_READINESS.md:

· production never serves generated weather, even with the flag left on;
· a Bengal field is never snapped to a Nashik taluka;
· adding Bengal blocks (no farm counts) does not move Nashik's hotspot maths;
· the count preview on the decision screen writes nothing and names nothing;
· the threshold is known BEFORE the first count (it used to read "undefined");
· Bengali is an accepted account language and the assistant is not told to
  answer a Bengali farmer in Marathi.
"""
from __future__ import annotations

import pytest


# ── weather ─────────────────────────────────────────────────────────────────
def test_production_ignores_the_generated_weather_fallback(env, monkeypatch):
    from app.config import Settings
    from app.db import Database
    from app.weather import WeatherService, WeatherUnavailable

    s = Settings(**{**env.model_dump(), "weather_demo_fallback": True})
    monkeypatch.setattr(Settings, "is_production", property(lambda self: True))
    db = Database(s)
    db.migrate()
    svc = WeatherService(db, s, demo_profile_fn=lambda: "monsoon")
    assert svc._demo_fallback is None, "generated weather must never be armed in production"

    def dead(*a, **k):
        raise WeatherUnavailable("open-meteo", "simulated total outage")
    monkeypatch.setattr(svc.provider, "series", dead)
    import datetime as dt
    with pytest.raises(WeatherUnavailable):
        svc.series(19.99, 73.79, dt.date(2026, 8, 27))


# ── geography ───────────────────────────────────────────────────────────────
def test_bengal_coordinates_land_in_a_bengal_block_and_nowhere_else(env):
    from app import reference
    assert reference.nearest_taluka(22.89, 88.02) == "wb_tarakeswar"
    assert reference.nearest_taluka(23.07, 87.98) == "wb_jamalpur"
    assert reference.nearest_taluka(20.08, 74.11) == "niphad"
    # Delhi is in no covered unit — it must not be snapped to the closest one.
    assert reference.nearest_taluka(28.61, 77.21) is None
    # A Kolkata-adjacent point must never resolve to a Maharashtra taluka.
    got = reference.nearest_taluka(22.80, 88.20)
    assert got is not None and got.startswith("wb_")


def test_a_field_outside_coverage_is_refused_not_snapped(client, farmer):
    r = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Delhi plot", "crop": "tomato", "area_acre": 1.0, "sown_on": "2026-08-01",
        "lat": 28.61, "lng": 77.21, "location_source": "gps"})
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "outside_coverage"


def test_a_bengal_field_is_placed_in_its_block(client, farmer):
    r = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Arambagh plot", "crop": "tomato", "area_acre": 1.0, "sown_on": "2026-08-01",
        "lat": 22.88, "lng": 87.79, "location_source": "gps"})
    assert r.status_code == 201, r.text
    assert r.json()["taluka"] == "wb_arambagh"


def test_bengal_blocks_do_not_change_nashik_hotspot_statistics(env):
    from app import reference, spatial
    nashik = [t for t in reference.TALUKAS if t.get("region") == "nashik"]
    counts = {"niphad": 9, "pimpalgaon": 6, "dindori": 4, "nashik": 1}
    alone = {r["taluka"]: r["z"] for r in spatial.getis_ord(nashik, counts)}
    pooled = {r["taluka"]: r["z"] for r in spatial.getis_ord(reference.TALUKAS, counts)}
    assert alone == {k: v for k, v in pooled.items() if k in alone}
    # A block with no sourced farm count has no incidence, so it is not scored.
    assert not any(k.startswith("wb_") for k in pooled)


def test_bengal_block_names_are_served_in_bengali(env):
    from app import reference
    assert reference.taluka_name("wb_singur", "bn") == "সিঙ্গুর"
    assert reference.taluka_name("wb_singur", "en") == "Singur"
    assert reference.taluka_name("niphad", "bn") == "Niphad"   # no Bengali written: English, never Marathi


# ── decision screen ─────────────────────────────────────────────────────────
def test_threshold_is_known_before_the_first_count(client, farmer, plot):
    r = client.get(f"/api/management/{plot['id']}?target=helicoverpa&lang=en",
                   headers=farmer["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["threshold"] is None                  # nothing counted yet
    ref = body["etl_reference"]
    assert ref and ref["etl_effective"] > 0 and ref["unit"]
    assert ref["etl_effective"] == round(ref["etl_base"] * ref["stage_factor"], 2)
    assert "chemical_authorised" not in ref           # a reference authorises nothing


def test_count_preview_writes_nothing_and_names_no_chemical(client, farmer, plot):
    from app.db import get_db
    before = get_db().one("SELECT COUNT(*) AS n FROM threshold_checks")["n"]
    r = client.get(f"/api/management/{plot['id']}/threshold-preview?target=helicoverpa&count=50",
                   headers=farmer["headers"])
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["preview"] is True and p["recorded"] is False
    assert p["percent_of_threshold"] > 100
    for forbidden in ("chemical_authorised", "options", "product", "dose", "recommended"):
        assert forbidden not in p
    after = get_db().one("SELECT COUNT(*) AS n FROM threshold_checks")["n"]
    assert after == before, "a preview must never be recorded as a count"


def test_count_preview_matches_the_saved_decision(client, farmer, plot):
    pv = client.get(f"/api/management/{plot['id']}/threshold-preview?target=helicoverpa&count=6",
                    headers=farmer["headers"]).json()
    saved = client.post("/api/threshold", headers=farmer["headers"],
                        json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 6})
    assert saved.status_code in (200, 201), saved.text
    m = client.get(f"/api/management/{plot['id']}?target=helicoverpa&lang=en",
                   headers=farmer["headers"]).json()
    assert m["threshold"]["percent_of_threshold"] == pv["percent_of_threshold"]
    assert m["threshold"]["band"] == pv["band"]


def test_count_preview_refuses_a_target_with_no_published_threshold(client, farmer, plot):
    r = client.get(f"/api/management/{plot['id']}/threshold-preview?target=late_blight&count=3",
                   headers=farmer["headers"])
    assert r.status_code == 404


def test_count_preview_is_only_for_your_own_field(client, farmer, farmer_b, plot):
    r = client.get(f"/api/management/{plot['id']}/threshold-preview?target=helicoverpa&count=3",
                   headers=farmer_b["headers"])
    assert r.status_code in (403, 404)


# ── language ────────────────────────────────────────────────────────────────
def test_bengali_is_an_accepted_account_language(client):
    r = client.post("/api/auth/register", json={
        "full_name": "Ratan Mondal", "password": "strong-pass-2026",
        "phone": "9812300001", "lang": "bn", "taluka": "wb_arambagh"})
    assert r.status_code == 201, r.text


def test_the_assistant_is_not_told_to_answer_bengali_in_marathi():
    """Unknown languages used to default to Marathi in llm.py."""
    import app.llm as llm
    src = open(llm.__file__, encoding="utf-8").read()
    assert src.count('"bn": "Bengali') == 2      # both prompt builders


# ── judge mode ──────────────────────────────────────────────────────────────
@pytest.fixture
def staging(tmp_path, monkeypatch, env):
    """A demo/staging service: DEMO_MODE on (from `env`) plus demo consoles."""
    monkeypatch.setenv("DEMO_CONSOLE_ACCESS", "true")
    from fastapi.testclient import TestClient

    from app.config import reload_settings
    from app.main import create_app
    s = reload_settings()
    with TestClient(create_app(s)) as c:
        yield c


def _console(c, role):
    r = c.post(f"/api/auth/demo-console?role={role}", json={})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_judge_guide_lists_eight_cases_with_an_honesty_line(staging):
    h = _console(staging, "farmer")
    g = staging.get("/api/demo/judge", headers=h).json()
    assert [c["n"] for c in g["cases"]] == list(range(1, 9))
    assert all(c["honesty"] for c in g["cases"])
    assert any("never" in r.lower() and "production" in r.lower() for r in g["rules"])


def test_judge_reset_archives_never_deletes_and_is_repeatable(staging, farmer):
    from app.db import get_db
    h = _console(staging, "farmer")
    db = get_db()
    real_before = db.one("SELECT COUNT(*) AS n FROM plots p JOIN farmers f ON f.id = p.farmer_id"
                         " JOIN users u ON u.id = f.user_id WHERE u.email IS NULL OR u.email NOT LIKE '%@prahari.demo'")["n"]
    total_before = db.one("SELECT COUNT(*) AS n FROM plots")["n"]
    a = staging.post("/api/demo/judge/reset", headers=h, json={}).json()
    b = staging.post("/api/demo/judge/reset", headers=h, json={}).json()
    assert a["scenario"] == b["scenario"] == "emerging"
    total_after = db.one("SELECT COUNT(*) AS n FROM plots")["n"]
    assert total_after >= total_before, "reset must never delete a field"
    real_after = db.one("SELECT COUNT(*) AS n, SUM(archived) AS arch FROM plots p JOIN farmers f ON f.id = p.farmer_id"
                        " JOIN users u ON u.id = f.user_id WHERE u.email IS NULL OR u.email NOT LIKE '%@prahari.demo'")
    assert real_after["n"] == real_before and not real_after["arch"], "a real farmer's field was touched"
    live = db.one("SELECT COUNT(*) AS n FROM plots p JOIN farmers f ON f.id = p.farmer_id JOIN users u"
                  " ON u.id = f.user_id WHERE u.email = 'farmer@prahari.demo' AND p.archived = 0")["n"]
    assert live == 1


def test_judge_routes_do_not_exist_without_demo_mode(tmp_path, monkeypatch, env):
    monkeypatch.setenv("DEMO_MODE", "false")
    from fastapi.testclient import TestClient

    from app.config import reload_settings
    from app.main import create_app
    with TestClient(create_app(reload_settings())) as c:
        assert c.get("/api/demo/judge").status_code == 404
        # POST hits no route at all (405 from the SPA catch-all GET), never the reset.
        assert c.post("/api/demo/judge/reset", json={}).status_code in (404, 405)
