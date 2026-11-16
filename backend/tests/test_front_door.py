"""
The front door: what a first-time visitor (or a judge) meets.

· HEAD on / and /api/health answers 200 — uptime monitors probe with HEAD,
  and a 405 made a healthy site look down to them.
· The demo farmer opens on a real field, not an empty onboarding screen —
  one field, created through the normal create_plot, with nothing invented
  on it: no observation, no count, no stored score.
"""
from __future__ import annotations

import pytest


def test_head_on_health_is_200(client):
    r = client.head("/api/health")
    assert r.status_code == 200


@pytest.fixture
def demo_on(client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "demo_console_access", True)
    return client


def _demo(client, role):
    r = client.post(f"/api/auth/demo-console?role={role}")
    if r.status_code == 404:
        pytest.skip("demo console switch is read at app build time here")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_demo_farmer_has_one_real_field_and_nothing_invented(demo_on):
    h = _demo(demo_on, "farmer")
    plots = demo_on.get("/api/plots", headers=h).json()
    plots = plots.get("plots", plots) if isinstance(plots, dict) else plots
    assert len(plots) == 1
    p = plots[0]
    assert p["crop"] == "tomato" and p["name"].startswith("Demo field")
    from app.db import get_db
    db = get_db()
    for table in ("observations", "threshold_checks", "applications", "health_snapshots"):
        n = db.scalar(f"SELECT COUNT(*) FROM {table} WHERE plot_id = :p", {"p": p["id"]})
        assert n == 0, table


def test_second_demo_sign_in_does_not_add_a_second_field(demo_on):
    _demo(demo_on, "farmer")
    h = _demo(demo_on, "farmer")
    plots = demo_on.get("/api/plots", headers=h).json()
    plots = plots.get("plots", plots) if isinstance(plots, dict) else plots
    assert len(plots) == 1


def test_a_real_farmer_gets_no_field_created(client, farmer):
    plots = client.get("/api/plots", headers=farmer["headers"]).json()
    plots = plots.get("plots", plots) if isinstance(plots, dict) else plots
    assert plots == []


def test_me_names_the_taluka_not_its_id(client, farmer):
    me = client.get("/api/auth/me", headers=farmer["headers"]).json()
    assert me["profile"]["taluka"] == "niphad"
    assert me["profile"]["taluka_name"] == "Niphad"


def test_officer_high_risk_lists_each_field_once_by_its_latest_score(client, farmer, plot, officer):
    from app.clock import now_iso
    from app.db import get_db
    db = get_db()
    # a bad day, then a worse day, for the same field
    for day, score in (("2026-08-25", 45.0), ("2026-08-26", 30.0)):
        db.execute("INSERT INTO health_snapshots (plot_id, day, score, disease, pest, weather,"
                   " nearby, created_at) VALUES (:p,:d,:s,0,0,0,0,:now)",
                   {"p": plot["id"], "d": day, "s": score, "now": now_iso()})
    rows = client.get("/api/officer/summary?days=14", headers=officer["headers"]).json()["high_risk_fields"]
    mine = [r for r in rows if r["plot_id"] == plot["id"]]
    assert len(mine) == 1 and mine[0]["score"] == 30.0
    assert mine[0]["taluka_name"]
    # it recovers: the latest snapshot is above 50, so it is no longer listed
    db.execute("INSERT INTO health_snapshots (plot_id, day, score, disease, pest, weather,"
               " nearby, created_at) VALUES (:p,'2026-08-27',80,0,0,0,0,:now)",
               {"p": plot["id"], "now": now_iso()})
    rows = client.get("/api/officer/summary?days=14", headers=officer["headers"]).json()["high_risk_fields"]
    assert not [r for r in rows if r["plot_id"] == plot["id"]]
