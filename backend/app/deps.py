"""
PRAHARI · authorisation
════════════════════════════════════════════════════════════════════════════
Every scope decision in the system passes through this file.

  current_user      a valid, unrevoked session
  require_roles     role gate
  owned_plot        a farmer may touch their own plot and no other
  visible_plot      farmer (own) · officer (in scope) · expert (assigned case)
  officer_talukas   the exact list of talukas this officer may query

Nothing above this layer filters by ownership in the client, and nothing below
it trusts a plot_id that arrived in a request body.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, Header, Request

from . import accounts
from .db import Database, get_db
from .errors import forbidden, not_found, unauthorized
from .obs import user_id_var
from .security import decode_token


def db_dep() -> Database:
    return get_db()


async def current_user(request: Request,
                       authorization: str | None = Header(default=None),
                       db: Database = Depends(db_dep)) -> dict[str, Any]:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        token = request.cookies.get("prahari_token")
    if not token:
        raise unauthorized()
    claims = decode_token(token)
    if not claims:
        raise unauthorized("Your session has expired. Sign in again.")
    jti = claims.get("jti", "")
    if not accounts.session_valid(db, jti):
        raise unauthorized("This session has been signed out. Sign in again.")
    user = db.one("SELECT * FROM users WHERE id = :id", {"id": claims["sub"]})
    if not user or not user["is_active"]:
        raise unauthorized("This account is no longer active.")
    user = dict(user)
    user["jti"] = jti
    user_id_var.set(user["id"])
    request.state.user = user
    return user


async def optional_user(request: Request,
                        authorization: str | None = Header(default=None),
                        db: Database = Depends(db_dep)) -> dict[str, Any] | None:
    try:
        return await current_user(request, authorization, db)
    except Exception:
        return None


def require_roles(*roles: str) -> Callable:
    async def _guard(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["role"] not in roles and user["role"] != "admin":
            raise forbidden("this area of PRAHARI")
        return user
    return _guard


# ── profile resolvers ───────────────────────────────────────────────────────
def farmer_of(db: Database, user: dict[str, Any]) -> dict[str, Any]:
    row = db.one("SELECT * FROM farmers WHERE user_id = :u", {"u": user["id"]})
    if not row:
        raise forbidden("farmer records — this account has no farmer profile")
    return row


def officer_of(db: Database, user: dict[str, Any]) -> dict[str, Any]:
    row = db.one("SELECT * FROM officers WHERE user_id = :u", {"u": user["id"]})
    if not row:
        raise forbidden("the officer console — this account has no officer profile")
    return row


def expert_of(db: Database, user: dict[str, Any]) -> dict[str, Any]:
    row = db.one("SELECT * FROM experts WHERE user_id = :u", {"u": user["id"]})
    if not row:
        raise forbidden("the expert portal — this account has no expert profile")
    return row


def officer_talukas(db: Database, user: dict[str, Any]) -> list[str]:
    """An admin sees the district. An officer sees exactly their granted scope
    — an empty scope means no data, never all data."""
    if user["role"] == "admin":
        from . import reference
        return list(reference.TALUKA_IDS)
    officer = officer_of(db, user)
    return accounts.officer_scopes(db, officer["id"])


# ── plot access ─────────────────────────────────────────────────────────────
def load_plot(db: Database, plot_id: str) -> dict[str, Any]:
    row = db.one(
        "SELECT p.*, f.user_id AS farmer_user_id, f.name AS farmer_name, f.phone AS farmer_phone,"
        " f.lang AS farmer_lang, f.village AS farmer_village"
        " FROM plots p JOIN farmers f ON f.id = p.farmer_id WHERE p.id = :id",
        {"id": plot_id})
    if not row:
        raise not_found("field", plot_id)
    return dict(row)


def owned_plot(db: Database, user: dict[str, Any], plot_id: str) -> dict[str, Any]:
    """Write access. Only the farmer who owns the field, or an admin."""
    plot = load_plot(db, plot_id)
    if user["role"] == "admin":
        return plot
    if user["role"] != "farmer" or plot["farmer_user_id"] != user["id"]:
        raise forbidden("this field")
    return plot


def visible_plot(db: Database, user: dict[str, Any], plot_id: str) -> dict[str, Any]:
    """Read access, widened only as far as each role's legitimate need goes."""
    plot = load_plot(db, plot_id)
    role = user["role"]
    if role == "admin":
        return plot
    if role == "farmer":
        if plot["farmer_user_id"] != user["id"]:
            raise forbidden("this field")
        return plot
    if role == "officer":
        if plot["taluka"] not in officer_talukas(db, user):
            raise forbidden("fields outside your assigned talukas")
        return plot
    if role == "expert":
        expert = expert_of(db, user)
        assigned = db.one(
            "SELECT id FROM expert_cases WHERE plot_id = :p AND (assigned_to = :e OR assigned_to IS NULL)",
            {"p": plot_id, "e": expert["id"]})
        if not assigned:
            raise forbidden("fields with no verification case assigned to you")
        return plot
    raise forbidden("this field")


def redact_for(role: str, plot: dict[str, Any]) -> dict[str, Any]:
    """An officer needs to find the field. They do not need the farmer's phone
    number until they have a case assigned, and a public map never gets either."""
    out = dict(plot)
    if role in ("expert",):
        out.pop("farmer_phone", None)
        out.pop("farmer_user_id", None)
    if role == "officer":
        out.pop("farmer_user_id", None)
    return out
