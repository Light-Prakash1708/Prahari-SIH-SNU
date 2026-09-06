"""
PRAHARI · the presenter's door

A demonstration needs the officer and expert consoles open in front of judges,
and the rule that guards them — officer and expert accounts are created BY an
administrator — is one nobody should relax for a demo.

So this route does not relax it. It signs in three FIXED accounts the server
owns, through the same accounts.login() every other sign-in uses, with a
password generated per request that never leaves the process. There is no
credential to leak, no role a caller can name, and no path to admin.

These tests are mostly about what it must NOT become.
"""
from __future__ import annotations

import json

import pytest

from app.config import reload_settings


def _app(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    return TestClient(create_app(settings))


@pytest.fixture
def demo_on(env, monkeypatch):
    monkeypatch.setenv("DEMO_CONSOLE_ACCESS", "true")
    return reload_settings()


# ── off by default, and invisible when off ──────────────────────────────────
def test_the_route_does_not_exist_unless_the_switch_is_on(client):
    for role in ("farmer", "expert", "officer", "admin"):
        r = client.post(f"/api/auth/demo-console?role={role}")
        assert r.status_code == 404, f"{role} -> {r.status_code}"


def test_the_switch_is_off_by_default(env):
    assert env.demo_console_access is False


def test_ready_reports_the_switch_so_the_ui_can_hide_the_card(env, monkeypatch):
    """The card is hidden by the SERVER's answer, not by a build flag."""
    with _app(env) as c:
        assert c.get("/api/ready").json()["config"]["demo_console_access"] is False
    monkeypatch.setenv("DEMO_CONSOLE_ACCESS", "true")
    with _app(reload_settings()) as c:
        assert c.get("/api/ready").json()["config"]["demo_console_access"] is True


# ── it opens the real consoles ──────────────────────────────────────────────
@pytest.mark.parametrize("role", ["farmer", "expert", "officer"])
def test_each_button_returns_a_real_session_for_that_role(demo_on, role):
    with _app(demo_on) as c:
        r = c.post(f"/api/auth/demo-console?role={role}")
        assert r.status_code == 200, r.text
        assert r.json()["role"] == role
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        me = c.get("/api/auth/me", headers=h)
        assert me.status_code == 200
        assert me.json()["user"]["role"] == role


def test_the_expert_session_opens_the_existing_expert_console(demo_on):
    with _app(demo_on) as c:
        h = {"Authorization": "Bearer " + c.post(
            "/api/auth/demo-console?role=expert").json()["access_token"]}
        assert c.get("/api/expert/cases", headers=h).status_code == 200
        assert c.get("/api/expert/model-agreement", headers=h).status_code == 200
        # and only the expert console
        assert c.get("/api/officer/summary", headers=h).status_code == 403


def test_the_officer_session_opens_the_existing_officer_console_with_scope(demo_on):
    with _app(demo_on) as c:
        h = {"Authorization": "Bearer " + c.post(
            "/api/auth/demo-console?role=officer").json()["access_token"]}
        for path in ("/api/officer/summary", "/api/officer/queue", "/api/officer/outbreaks",
                     "/api/officer/hotspots?problem=late_blight"):
            assert c.get(path, headers=h).status_code == 200, path
        assert c.get("/api/expert/cases", headers=h).status_code == 403


def test_the_session_is_a_normal_revocable_session_not_a_bypass(demo_on):
    with _app(demo_on) as c:
        h = {"Authorization": "Bearer " + c.post(
            "/api/auth/demo-console?role=officer").json()["access_token"]}
        assert c.get("/api/officer/summary", headers=h).status_code == 200
        assert c.post("/api/auth/logout", headers=h).status_code == 200
        # the JWT is still signed and still unexpired; the SESSION is gone
        assert c.get("/api/officer/summary", headers=h).status_code == 401


# ── the things it must never become ─────────────────────────────────────────
def test_it_cannot_be_asked_for_admin(demo_on):
    with _app(demo_on) as c:
        r = c.post("/api/auth/demo-console?role=admin")
        assert r.status_code == 400
        assert r.json()["error"] == "unknown_role"


def test_it_cannot_be_asked_for_an_arbitrary_account(demo_on):
    with _app(demo_on) as c:
        for role in ("../admin", "root", "officer@real-person.example.com", ""):
            assert c.post(f"/api/auth/demo-console?role={role}").status_code in (400, 422)


def test_no_password_is_ever_returned(demo_on):
    with _app(demo_on) as c:
        body = json.dumps(c.post("/api/auth/demo-console?role=officer").json())
        assert "password" not in body.lower()
        for k in ("access_token", "role", "user_id", "expires_at"):
            assert k in body


def test_the_password_changes_every_time_so_none_is_guessable(demo_on):
    """Nothing keeps a demo password, so nothing can be found out and reused
    against the deployment later."""
    with _app(demo_on) as c:
        c.post("/api/auth/demo-console?role=officer")
        for guess in ("prahari-demo-2026", "password", "demo", "officer"):
            r = c.post("/api/auth/login",
                       json={"identifier": "officer@prahari.demo", "password": guess})
            assert r.status_code == 401, f"{guess!r} signed in"


def test_it_never_touches_a_real_account(demo_on, client):
    """The three addresses are fixed in a table. A farmer's own account is
    untouched by any of this."""
    with _app(demo_on) as c:
        r = c.post("/api/auth/register", json={
            "full_name": "Rajesh Pawar", "password": "strong-pass-2026",
            "phone": "9812345678", "lang": "mr", "taluka": "niphad", "village": "Niphad"})
        assert r.status_code == 201
        c.post("/api/auth/demo-console?role=officer")
        again = c.post("/api/auth/login",
                       json={"identifier": "9812345678", "password": "strong-pass-2026"})
        assert again.status_code == 200
        assert again.json()["role"] == "farmer"


# ── the rules underneath, still exactly as they were ────────────────────────
@pytest.mark.parametrize("role", ["officer", "expert", "admin"])
def test_public_registration_still_refuses_privileged_roles_with_demo_on(demo_on, role):
    with _app(demo_on) as c:
        r = c.post("/api/auth/register", json={
            "full_name": "Chancer", "password": "strong-pass-2026", "role": role,
            "email": f"{role}@chancer.example.com", "taluka": "niphad"})
        assert r.status_code == 400
        assert r.json()["error"] == "role_not_self_serviceable"


def test_a_farmer_is_still_blocked_from_both_consoles_with_demo_on(demo_on):
    with _app(demo_on) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={
            "full_name": "Rajesh Pawar", "password": "strong-pass-2026",
            "phone": "9812345678", "lang": "mr", "taluka": "niphad",
            "village": "Niphad"}).json()["access_token"]}
        assert c.get("/api/officer/summary", headers=h).status_code == 403
        assert c.get("/api/expert/cases", headers=h).status_code == 403
        assert c.post("/api/admin/users", headers=h, json={
            "full_name": "X", "password": "strong-pass-2026", "role": "officer",
            "email": "x@y.example.com", "taluka": "niphad"}).status_code == 403
