"""Authentication, sessions and the boundary between two farmers."""
from __future__ import annotations

import pytest

from conftest import scan


def test_register_returns_a_working_token(client):
    r = client.post("/api/auth/register", json={
        "full_name": "Rajesh Pawar", "password": "strong-pass-2026",
        "phone": "9812345678", "taluka": "niphad"})
    assert r.status_code == 201
    token = r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["full_name"] == "Rajesh Pawar"
    assert me.json()["profile"]["taluka"] == "niphad"
    assert "password_hash" not in me.json()["user"]


def test_weak_password_is_refused(client):
    r = client.post("/api/auth/register", json={
        "full_name": "X Y", "password": "12345678", "phone": "9812345670", "taluka": "niphad"})
    assert r.status_code == 400
    assert r.json()["error"] == "weak_password"


def test_duplicate_phone_is_refused(client, farmer):
    r = client.post("/api/auth/register", json={
        "full_name": "Someone Else", "password": "strong-pass-2026",
        "phone": "9812345678", "taluka": "niphad"})
    assert r.status_code == 409
    assert r.json()["error"] == "phone_taken"


def test_officer_role_cannot_be_self_registered(client):
    r = client.post("/api/auth/register", json={
        "full_name": "Fake Officer", "password": "strong-pass-2026",
        "email": "fake@x.com", "role": "officer", "taluka": "niphad"})
    assert r.status_code == 400
    assert r.json()["error"] == "role_not_self_serviceable"


def test_wrong_password_and_unknown_account_give_the_same_answer(client, farmer):
    a = client.post("/api/auth/login", json={"identifier": "9812345678", "password": "wrong"})
    b = client.post("/api/auth/login", json={"identifier": "9800000000", "password": "wrong"})
    assert a.status_code == b.status_code == 401
    assert a.json()["message"] == b.json()["message"]


def test_logout_revokes_the_session(client, farmer):
    assert client.get("/api/auth/me", headers=farmer["headers"]).status_code == 200
    assert client.post("/api/auth/logout", headers=farmer["headers"]).status_code == 200
    after = client.get("/api/auth/me", headers=farmer["headers"])
    assert after.status_code == 401
    assert after.json()["error"] == "unauthenticated"


def test_password_reset_ends_every_session(client, farmer):
    req = client.post("/api/auth/password/reset-request", json={"identifier": "9812345678"})
    assert req.status_code == 200
    token = req.json()["dev_token"]
    done = client.post("/api/auth/password/reset",
                       json={"token": token, "new_password": "another-strong-2026"})
    assert done.status_code == 200
    assert client.get("/api/auth/me", headers=farmer["headers"]).status_code == 401
    again = client.post("/api/auth/login",
                        json={"identifier": "9812345678", "password": "another-strong-2026"})
    assert again.status_code == 200


def test_reset_request_does_not_reveal_whether_an_account_exists(client, farmer):
    known = client.post("/api/auth/password/reset-request", json={"identifier": "9812345678"})
    unknown = client.post("/api/auth/password/reset-request", json={"identifier": "9800000000"})
    assert known.json()["message"] == unknown.json()["message"]


def test_no_token_is_rejected(client, plot):
    assert client.get("/api/plots").status_code == 401
    assert client.get(f"/api/risk/{plot['id']}").status_code == 401


def test_a_tampered_token_is_rejected(client, farmer):
    bad = {"Authorization": farmer["headers"]["Authorization"][:-4] + "aaaa"}
    assert client.get("/api/auth/me", headers=bad).status_code == 401
