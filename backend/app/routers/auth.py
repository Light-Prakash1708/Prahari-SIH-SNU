"""PRAHARI · /api/auth — registration, login, logout, password reset."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from .. import accounts
from ..config import get_settings
from ..db import Database
from ..deps import current_user, db_dep
from ..errors import bad_request
from ..obs import audit
from ..schemas import (
    LoginIn,
    MeOut,
    PasswordChangeIn,
    PasswordResetIn,
    PasswordResetRequestIn,
    RegisterIn,
    TokenOut,
)

log = logging.getLogger("prahari.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201,
             summary="Register a farmer account and sign in",
             description=("Creates a user and the matching farmer profile, then returns a bearer "
                          "token. Officer, expert and administrator accounts are created by an "
                          "administrator through /api/admin/users — an officer account can see a "
                          "whole taluka's farmers, so it is not self-serviceable.\n\n"
                          "Errors: 400 weak_password · 400 unknown_taluka · "
                          "400 role_not_self_serviceable · 409 email_taken · 409 phone_taken"))
def register(data: RegisterIn, request: Request, db: Database = Depends(db_dep)):
    result = accounts.register(db, data)
    token = accounts.login(db, data.email or data.phone, data.password,
                           user_agent=request.headers.get("user-agent", ""),
                           ip=_ip(request))
    audit("auth.register", entity="user", entity_id=result["user_id"],
          user_id=result["user_id"], role=data.role, ip=_ip(request))
    return token


@router.post("/login", response_model=TokenOut,
             summary="Sign in with email or mobile number",
             description="Errors: 401 unauthenticated (identical for unknown account and wrong password)")
def login(data: LoginIn, request: Request, db: Database = Depends(db_dep)):
    token = accounts.login(db, data.identifier, data.password,
                           user_agent=request.headers.get("user-agent", ""),
                           ip=_ip(request))
    audit("auth.login", entity="user", entity_id=token["user_id"],
          user_id=token["user_id"], role=token["role"], ip=_ip(request))
    return token


@router.post("/logout", summary="End this session",
             description="Revokes the session behind the presented token. The JWT signature stays "
                         "valid until it expires; the session does not, and every request checks it.")
def logout(user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    accounts.logout(db, user["jti"])
    audit("auth.logout", entity="user", entity_id=user["id"], user_id=user["id"])
    return {"ok": True, "message": "Signed out on this device."}


@router.post("/logout-all", summary="End every session for this account")
def logout_all(user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    n = accounts.logout_all(db, user["id"])
    return {"ok": True, "sessions_ended": n}


@router.post("/password/reset-request",
             summary="Request a password reset link",
             description=("Always responds identically, whether or not the account exists — a "
                          "reset form that says 'no such number' is a way to discover which "
                          "numbers are registered. In development the token is returned in the "
                          "response so the flow can be tested without a mail or SMS gateway; in "
                          "production it is only ever delivered through the notification service."))
def reset_request(data: PasswordResetRequestIn, request: Request,
                  db: Database = Depends(db_dep)):
    s = get_settings()
    out = accounts.begin_reset(db, data.identifier)
    body: dict[str, Any] = {
        "ok": True,
        "message": ("If that account exists, a reset link has been sent to it. The link is valid "
                    f"for {s.password_reset_ttl_minutes} minutes."),
    }
    if out:
        raw, user = out
        from ..runtime import get_runtime
        rt = get_runtime()
        rt.notify.push(user_id=user["id"], plot_id=None, kind="account",
                       title="Password reset requested",
                       body=f"Use this code to set a new password: {raw}",
                       title_mr="पासवर्ड बदलण्याची विनंती",
                       body_mr=f"नवीन पासवर्डसाठी हा कोड वापरा: {raw}",
                       channels=["sms"] if user.get("phone") else ["email"],
                       address=user.get("phone") or user.get("email"),
                       lang=user.get("lang", "mr"))
        if not s.is_production:
            body["dev_token"] = raw
            body["dev_note"] = "Returned only because APP_ENV is not production."
        audit("auth.reset_request", entity="user", entity_id=user["id"], ip=_ip(request))
    return body


@router.post("/password/reset", summary="Set a new password with a reset token",
             description="Errors: 400 invalid_reset_token · 400 weak_password. A successful reset "
                         "ends every existing session for that account.")
def reset(data: PasswordResetIn, db: Database = Depends(db_dep)):
    if not accounts.complete_reset(db, data.token, data.new_password):
        raise bad_request("invalid_reset_token",
                          "That reset code is not valid, has already been used, or has expired.",
                          message_mr="हा कोड चुकीचा आहे किंवा त्याची मुदत संपली आहे.")
    return {"ok": True, "message": "Password changed. Sign in with your new password."}


@router.post("/password/change", summary="Change your password while signed in")
def change(data: PasswordChangeIn, user: dict[str, Any] = Depends(current_user),
           db: Database = Depends(db_dep)):
    accounts.change_password(db, user, data.current_password, data.new_password)
    audit("auth.password_change", entity="user", entity_id=user["id"], user_id=user["id"])
    return {"ok": True}


@router.get("/me", response_model=MeOut, summary="The signed-in account and its profile",
            description="Returns the authenticated user, their role profile, and — for an officer "
                        "— the exact list of talukas they are authorised to query.")
def me(user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    profile = accounts.profile_for(db, user)
    scopes = []
    if user["role"] in ("officer", "admin"):
        from ..deps import officer_talukas
        try:
            scopes = officer_talukas(db, user)
        except Exception:
            scopes = []
    safe = {k: v for k, v in user.items() if k not in ("password_hash", "jti")}
    return {"user": safe, "profile": profile, "scopes": scopes}


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""
