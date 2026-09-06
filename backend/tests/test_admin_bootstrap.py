"""
PRAHARI · the first administrator

Officer and expert accounts are created BY an administrator. That rule is the
point — an officer account can see a whole taluka's farmers — and every test
below that touches it is checking the rule still holds.

What was missing was narrower than it looked: nothing could create the FIRST
administrator on a deployed instance, because the only thing that ever had was
the demo seed, and the demo seed is refused in production. So a correct
provisioning system had no way in.

These pin the one step that closes that, and the four things it must not
become: a login path, a role a farmer can request, a way to overwrite an
administrator that already exists, or a reason the application will not start.
"""
from __future__ import annotations

import pytest

from app.config import reload_settings

BOOT = "bootstrap-pass-2026-strong"


def _app(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app
    return TestClient(create_app(settings))


@pytest.fixture
def armed(env, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "admin@prahari-boot.example.com")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", BOOT)
    return reload_settings()


# ── it does the one thing ───────────────────────────────────────────────────
def test_with_both_set_an_administrator_exists_and_can_sign_in(armed):
    with _app(armed) as c:
        r = c.post("/api/auth/login", json={"identifier": "admin@prahari-boot.example.com",
                                            "password": BOOT})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "admin"


def test_that_administrator_can_create_an_officer_and_an_expert(armed):
    """The whole point: the existing provisioning path now has a way in."""
    with _app(armed) as c:
        h = {"Authorization": "Bearer " + c.post(
            "/api/auth/login", json={"identifier": "admin@prahari-boot.example.com",
                                     "password": BOOT}).json()["access_token"]}
        o = c.post("/api/admin/users", headers=h, json={
            "full_name": "Krishi Sahayak", "password": "officer-pass-2026-strong",
            "role": "officer", "email": "officer@prahari-boot.example.com",
            "taluka": "niphad"})
        assert o.status_code == 201, o.text
        e = c.post("/api/admin/users", headers=h, json={
            "full_name": "Dr A Kulkarni", "password": "expert-pass-2026-strong",
            "role": "expert", "email": "expert@prahari-boot.example.com",
            "taluka": "niphad", "institution": "KVK Nashik"})
        assert e.status_code == 201, e.text

        for who, pw in (("officer@prahari-boot.example.com", "officer-pass-2026-strong"),
                        ("expert@prahari-boot.example.com", "expert-pass-2026-strong")):
            lr = c.post("/api/auth/login", json={"identifier": who, "password": pw})
            assert lr.status_code == 200, lr.text
            assert lr.json()["role"] in ("officer", "expert")


# ── and nothing else ────────────────────────────────────────────────────────
def test_unset_changes_nothing(env):
    with _app(env) as c:
        assert c.post("/api/auth/login",
                      json={"identifier": "admin@prahari-boot.example.com",
                            "password": BOOT}).status_code == 401


def test_it_never_overwrites_an_administrator_that_already_exists(armed):
    """Restarts are not a second chance at the password. Once an administrator
    exists the variables are inert, so leaving them set is harmless — and a
    changed value can never take over the existing account."""
    with _app(armed) as c:
        assert c.post("/api/auth/login", json={"identifier": "admin@prahari-boot.example.com",
                                               "password": BOOT}).status_code == 200
    import os
    os.environ["ADMIN_BOOTSTRAP_PASSWORD"] = "a-different-password-2026"
    s2 = reload_settings()
    with _app(s2) as c:
        assert c.post("/api/auth/login",
                      json={"identifier": "admin@prahari-boot.example.com",
                            "password": "a-different-password-2026"}).status_code == 401
        assert c.post("/api/auth/login",
                      json={"identifier": "admin@prahari-boot.example.com",
                            "password": BOOT}).status_code == 200


def test_a_weak_password_is_refused_and_the_app_still_starts(env, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "admin@prahari-boot.example.com")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "1234")
    s = reload_settings()
    with _app(s) as c:
        assert c.get("/api/health").status_code == 200, "the app must still boot"
        assert c.post("/api/auth/login",
                      json={"identifier": "admin@prahari-boot.example.com",
                            "password": "1234"}).status_code == 401


def test_the_password_is_never_returned_by_any_endpoint(armed):
    import json as _json
    with _app(armed) as c:
        blob = _json.dumps(c.get("/api/ready").json()) + _json.dumps(c.get("/api/health").json())
        assert BOOT not in blob
        assert "admin@prahari-boot.example.com" not in blob
        assert c.get("/api/ready").json()["config"]["admin_bootstrap"] == "armed"


# ── the rule it must not weaken ─────────────────────────────────────────────
@pytest.mark.parametrize("role", ["officer", "expert", "admin"])
def test_public_registration_still_refuses_every_privileged_role(client, role):
    """A farmer typing role=officer into the request body is still refused, and
    that is the assertion that matters most in this file."""
    r = client.post("/api/auth/register", json={
        "full_name": "Chancer", "password": "strong-pass-2026", "role": role,
        "email": f"{role}@chancer.example.com", "taluka": "niphad"})
    assert r.status_code == 400
    assert r.json()["error"] == "role_not_self_serviceable"


def test_a_farmer_cannot_reach_the_admin_provisioning_endpoint(client, farmer):
    r = client.post("/api/admin/users", headers=farmer["headers"], json={
        "full_name": "Me But Better", "password": "strong-pass-2026",
        "role": "officer", "email": "nope@chancer.example.com", "taluka": "niphad"})
    assert r.status_code == 403


def test_a_farmer_is_still_refused_the_officer_and_expert_consoles(client, farmer):
    assert client.get("/api/officer/summary", headers=farmer["headers"]).status_code == 403
    assert client.get("/api/expert/cases", headers=farmer["headers"]).status_code == 403
