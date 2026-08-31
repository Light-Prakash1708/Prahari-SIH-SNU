"""
Production refuses to start when it is configured unsafely.

Each of these would be a silent way for a deployed instance to serve generated
weather, seeded accounts, or an API signed with a guessable key. The guard is in
config.py; this is the proof that it holds.
"""
from __future__ import annotations

import pytest

from app.config import Settings

SAFE = dict(app_env="production", jwt_secret="x" * 40,
            database_url="postgresql+psycopg://u:p@h/prahari",
            cors_origins="https://prahari.maharashtra.gov.in",
            weather_provider="openmeteo")


@pytest.mark.parametrize("label,override", [
    ("a short JWT secret", dict(jwt_secret="short")),
    ("no JWT secret at all", dict(jwt_secret=None)),
    ("DEMO_MODE on", dict(demo_mode=True)),
    ("AUTO_SEED_DEMO on", dict(auto_seed_demo=True)),
    ("generated weather", dict(weather_provider="demo")),
    ("a pinned clock", dict(prahari_today="2026-08-27")),
    ("a CORS wildcard", dict(cors_origins="*")),
    ("SQLite as the production database", dict(database_url="sqlite:///x.db")),
])
def test_production_refuses(label, override):
    with pytest.raises(Exception) as exc:
        Settings(_env_file=None, **{**SAFE, **override})
    assert "validation error" in str(exc.value).lower() or "value error" in str(exc.value).lower(), label


def test_a_correct_production_config_is_accepted():
    s = Settings(_env_file=None, **SAFE)
    assert s.is_production
    assert s.demo_mode is False
    assert s.redacted()["database"] == "postgresql"
    assert "*" not in s.cors_origin_list


def test_development_gets_an_ephemeral_secret_rather_than_a_shared_default():
    """Two development instances must not sign each other's tokens."""
    a = Settings(_env_file=None, app_env="development", jwt_secret=None)
    b = Settings(_env_file=None, app_env="development", jwt_secret=None)
    assert a.jwt_secret and len(a.jwt_secret) >= 32
    assert a.jwt_secret != b.jwt_secret
