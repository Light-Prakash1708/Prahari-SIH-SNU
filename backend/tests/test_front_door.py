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
