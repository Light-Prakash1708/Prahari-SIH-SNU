"""
An unreachable database degrades the service; it does not kill the process.

The incident this guards: the deployment's PostgreSQL instance was removed,
uvicorn exited at startup with "Application startup failed", and the whole site
— the static frontend included — vanished behind the host's error page for a
month. The process now stays up, says plainly that the database is unavailable,
refuses to pretend otherwise on any data route, and recovers by itself when the
database comes back.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def broken_env(tmp_path, monkeypatch):
    # A SQLite file inside a directory that does not exist yet: opening it
    # raises OperationalError, exactly the class a vanished host raises.
    missing = tmp_path / "not-yet"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{missing}/prahari.db")
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
    monkeypatch.setenv("DB_STARTUP_ATTEMPTS", "1")
    monkeypatch.setenv("DB_RETRY_SECONDS", "0")
    from app.config import reload_settings
    from app.db import reset_db
    reset_db()
    settings = reload_settings()
    settings._missing_dir = missing          # type: ignore[attr-defined]
    return settings


@pytest.fixture
def broken_client(broken_env):
    from fastapi.testclient import TestClient

    from app.main import create_app
    app = create_app(broken_env)
    with TestClient(app) as c:               # startup must not raise
        c.missing_dir = broken_env._missing_dir   # type: ignore[attr-defined]
        yield c


def test_the_process_starts_and_liveness_answers(broken_client):
    r = broken_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["database"] == "unavailable"


def test_readiness_reports_the_database_as_down(broken_client):
    r = broken_client.get("/api/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["ready"] is False
    assert "database" in body["degraded"]


def test_data_routes_refuse_honestly_instead_of_crashing(broken_client):
    for path in ("/api/auth/me", "/api/plots", "/api/reference"):
        r = broken_client.get(path)
        assert r.status_code == 503, path
        body = r.json()
        assert body["error"] == "database_unavailable"
        assert body["retryable"] is True
        assert body["message_mr"]
        assert "Retry-After" in r.headers


def test_nothing_about_the_connection_leaks_into_the_refusal(broken_client):
    text = broken_client.get("/api/plots").text
    assert "sqlite" not in text.lower()
    assert "not-yet" not in text


def test_it_recovers_by_itself_when_the_database_returns(broken_client):
    assert broken_client.get("/api/plots").status_code == 503
    broken_client.missing_dir.mkdir(parents=True)
    # The next data request retries the bring-up: migrations run, and the
    # route now answers on its merits (401 — no token), not with a 503.
    r = broken_client.get("/api/plots")
    assert r.status_code == 401
    assert broken_client.get("/api/health").json()["database"] == "ok"
    assert broken_client.get("/api/ready").json()["ready"] is True


def test_a_healthy_database_is_untouched(client):
    assert client.get("/api/health").json()["database"] == "ok"
    assert client.get("/api/ready").status_code in (200, 503)   # storage-dependent elsewhere
    assert client.get("/api/plots").status_code == 401
