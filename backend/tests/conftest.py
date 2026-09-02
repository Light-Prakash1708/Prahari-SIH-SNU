"""
PRAHARI · test fixtures
════════════════════════════════════════════════════════════════════════════
Every test runs against a real application, a real (temporary) database and the
real engines. Nothing below stubs a service the tests are meant to be checking:
the weather provider is the deterministic demo generator so runs are
reproducible, and that is stated in every assertion that depends on it.
"""
from __future__ import annotations

import io
import os
import random
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="function")
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/prahari.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("AUTO_SEED_DEMO", "false")
    monkeypatch.setenv("WEATHER_PROVIDER", "demo")
    monkeypatch.setenv("VISION_PROVIDER", "none")
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("JWT_SECRET", "test-secret-long-enough-to-be-accepted-1234567890")
    monkeypatch.setenv("PRAHARI_TODAY", "2026-08-27")
    monkeypatch.setenv("LOG_LEVEL", "CRITICAL")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "100000")
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "100000")
    from app.config import reload_settings
    from app.db import reset_db
    reset_db()
    return reload_settings()


@pytest.fixture(scope="function", autouse=True)
def _no_inherited_weather_cooldown():
    """The provider cooldown lives in module state, which is what makes it work
    across requests. It must not leak across TESTS: one test that simulates a
    429 would otherwise silently disable weather for everything that ran after
    it, and the failures would land far from the cause."""
    from app.weather import clear_cooldowns
    clear_cooldowns()
    yield
    clear_cooldowns()


@pytest.fixture(scope="function")
def client(env):
    from fastapi.testclient import TestClient
    from app.main import create_app
    app = create_app(env)
    with TestClient(app) as c:
        c.settings = env          # type: ignore[attr-defined]
        yield c


# ── people ──────────────────────────────────────────────────────────────────
def _auth(resp) -> Dict[str, str]:
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def farmer(client):
    r = client.post("/api/auth/register", json={
        "full_name": "Rajesh Pawar", "password": "strong-pass-2026",
        "phone": "9812345678", "lang": "mr", "taluka": "niphad", "village": "Niphad"})
    assert r.status_code == 201, r.text
    return {"headers": _auth(r), "user_id": r.json()["user_id"]}


@pytest.fixture
def farmer_b(client):
    r = client.post("/api/auth/register", json={
        "full_name": "Sunita Deshmukh", "password": "strong-pass-2026",
        "phone": "9812345679", "taluka": "niphad"})
    assert r.status_code == 201, r.text
    return {"headers": _auth(r), "user_id": r.json()["user_id"]}


@pytest.fixture
def admin(client):
    from app import accounts
    from app.db import get_db
    from app.schemas import RegisterIn
    accounts.register(get_db(), RegisterIn(
        full_name="District Administrator", password="strong-pass-2026",
        role="admin", email="admin@prahari-test.example.com", taluka="niphad"), allow_privileged=True)
    r = client.post("/api/auth/login",
                    json={"identifier": "admin@prahari-test.example.com", "password": "strong-pass-2026"})
    return {"headers": _auth(r)}


@pytest.fixture
def officer(client, admin):
    r = client.post("/api/admin/users", headers=admin["headers"], json={
        "full_name": "Krishi Sahayak", "password": "strong-pass-2026", "role": "officer",
        "email": "officer@prahari-test.example.com", "taluka": "niphad"})
    assert r.status_code == 201, r.text
    oid = r.json()["profile"]["id"]
    for t in ("niphad", "pimpalgaon", "dindori"):
        client.post(f"/api/admin/officers/{oid}/scopes?taluka={t}", headers=admin["headers"])
    login = client.post("/api/auth/login",
                        json={"identifier": "officer@prahari-test.example.com", "password": "strong-pass-2026"})
    return {"headers": _auth(login), "officer_id": oid}


@pytest.fixture
def expert(client, admin):
    r = client.post("/api/admin/users", headers=admin["headers"], json={
        "full_name": "Dr A Kulkarni", "password": "strong-pass-2026", "role": "expert",
        "email": "expert@prahari-test.example.com", "taluka": "niphad", "institution": "KVK Nashik"})
    assert r.status_code == 201, r.text
    login = client.post("/api/auth/login",
                        json={"identifier": "expert@prahari-test.example.com", "password": "strong-pass-2026"})
    return {"headers": _auth(login), "expert_id": r.json()["profile"]["id"]}


@pytest.fixture
def plot(client, farmer):
    r = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Tomato block 1", "crop": "tomato", "area_acre": 2.0,
        "sown_on": "2026-06-25", "lat": 20.0810, "lng": 74.1100,
        "location_source": "gps", "soil": "medium black", "irrigation": "drip"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def monsoon(client, farmer):
    """Put the demo weather generator into the monsoon story, so the growing
    degree-day model puts Helicoverpa at its damaging stage. Reproducible by
    construction — it is a generator seeded on the date."""
    client.post("/api/demo/scenario?key=threshold", headers=farmer["headers"])
    return "monsoon"


# ── synthetic leaves ────────────────────────────────────────────────────────
def leaf_image(kind: str = "blight", size=(700, 700)) -> bytes:
    """Synthetic reference leaves. Labelled synthetic everywhere they appear —
    they exercise the measurement and the gate, and no accuracy claim is made
    from them."""
    import numpy as np
    from PIL import Image, ImageFilter
    rng = np.random.default_rng(4)
    a = np.zeros((size[1], size[0], 3), np.uint8)
    a[:, :] = (150, 120, 85)                       # dry Nashik soil
    yy, xx = np.mgrid[0:size[1], 0:size[0]]
    cx, cy = size[0] / 2, size[1] / 2
    leaf = (((xx - cx) / (size[0] * 0.40)) ** 2 + ((yy - cy) / (size[1] * 0.46)) ** 2) < 1
    a[leaf] = (60, 135, 55)
    a = a + rng.normal(0, 7, a.shape)
    r = random.Random(3)
    if kind == "blight":
        for _ in range(9):
            lx, ly = r.randint(200, 500), r.randint(200, 500)
            m = ((xx - lx) ** 2 + (yy - ly) ** 2) < r.randint(700, 2200)
            a[m & leaf] = (95, 62, 32)
    elif kind == "improved":
        for _ in range(3):
            lx, ly = r.randint(200, 500), r.randint(200, 500)
            m = ((xx - lx) ** 2 + (yy - ly) ** 2) < 700
            a[m & leaf] = (95, 62, 32)
    elif kind == "worse":
        for _ in range(22):
            lx, ly = r.randint(180, 520), r.randint(180, 520)
            m = ((xx - lx) ** 2 + (yy - ly) ** 2) < r.randint(1400, 3600)
            a[m & leaf] = (95, 62, 32)
    elif kind == "powdery":
        for _ in range(14):
            lx, ly = r.randint(200, 500), r.randint(200, 500)
            m = ((xx - lx) ** 2 + (yy - ly) ** 2) < 900
            a[m & leaf] = (228, 228, 224)
    img = Image.fromarray(np.clip(a, 0, 255).astype("uint8"))
    if kind == "blurry":
        img = img.filter(ImageFilter.GaussianBlur(14))
    if kind == "dark":
        img = Image.fromarray((np.asarray(img) * 0.10).astype("uint8"))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


@pytest.fixture
def leaf():
    return leaf_image


def scan(client, headers, plot_id, kind="blight", **extra):
    return client.post("/api/observations", headers=headers,
                       files={"image": ("leaf.jpg", leaf_image(kind), "image/jpeg")},
                       data={"plot_id": plot_id, **extra})
