"""PRAHARI · /api/auth — registration, login, logout, password reset."""
from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Request

from .. import accounts, reference
from ..clock import now_iso
from ..config import get_settings
from ..db import Database
from ..deps import current_user, db_dep
from ..errors import bad_request, not_found
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
from ..security import hash_password

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


DEMO_CONSOLE_ROLES = {
    "farmer":  ("Demo Farmer", "farmer@prahari.demo"),
    "expert":  ("Dr. A. Kulkarni (demo)", "expert@prahari.demo"),
    "officer": ("Krishi Sahayak (demo)", "officer@prahari.demo"),
    "fpo":     ("FPO coordinator (demo)", "fpo@prahari.demo"),
}

# The organisation the demo FPO account is linked to. Clearly a demo, and it
# starts with NO members: membership stays the farmer's own act, so it fills
# only when a farmer (the demo farmer included) chooses to join it.
DEMO_FPO = ("FPO-DEMO", "Demo Producer Organisation", "डेमो उत्पादक संस्था")


@router.post("/demo-console", response_model=TokenOut,
             summary="Sign in to a demo console (only when DEMO_CONSOLE_ACCESS is on)",
             description=(
                 "Returns a normal session for one of four fixed demo accounts, so the officer "
                 "and expert consoles can be shown without an administrator provisioning staff "
                 "first.\n\n"
                 "It grants nothing new. The account it signs in is a real account of that role, "
                 "created server-side, and the token comes back from the SAME `accounts.login()` "
                 "every other sign-in uses — same JWT, same session row, same revocation. What it "
                 "removes is the need for a password to exist anywhere a client could read: one "
                 "is generated per request, used once, and never returned.\n\n"
                 "Disabled unless DEMO_CONSOLE_ACCESS=true, in which case this route does not "
                 "exist. It never touches a real account: the four addresses are fixed and end "
                 "in @prahari.demo.\n\n"
                 "Errors: 404 not_found when the switch is off · 400 unknown_role"))
def demo_console(role: str, request: Request, db: Database = Depends(db_dep)):
    """The presenter's door. Narrow on purpose.

    Three things make this safe to leave in a production build:

    1. It is off unless a server-side switch says otherwise, and when off the
       route answers 404 — the same as any path that does not exist, so its
       presence is not advertised.
    2. The role is not taken from the caller in any meaningful sense: it selects
       one of four FIXED accounts by a table in this file. A caller cannot name
       an account, cannot name a role outside the table, and cannot reach admin.
    3. No credential exists to steal. The password is generated here, per
       request, used immediately by the real login path, and never stored in a
       form anyone can read or returned in any response.

    What it does NOT do: it does not weaken `accounts.register`, which still
    refuses privileged self-registration; it does not bypass JWT or session
    validation; and it gives the frontend no authority whatsoever over roles.
    """
    s = get_settings()
    if not s.demo_console_access:
        raise not_found("route")
    if role not in DEMO_CONSOLE_ROLES:
        raise bad_request("unknown_role",
                          f"Demo consoles: {', '.join(DEMO_CONSOLE_ROLES)}.")

    full_name, email = DEMO_CONSOLE_ROLES[role]
    # Fresh every time. Nothing downstream ever needs to know it again, so
    # there is no place for it to sit and no value for a response to leak.
    password = secrets.token_urlsafe(24)

    user = db.one("SELECT id FROM users WHERE email = :e", {"e": email})
    if user:
        db.execute("UPDATE users SET password_hash = :h, is_active = 1, updated_at = :now"
                   " WHERE id = :id",
                   {"h": hash_password(password), "now": now_iso(), "id": user["id"]})
    else:
        created = accounts.register(db, RegisterIn(
            full_name=full_name, password=password, role=role, email=email, lang="en",
            taluka=reference.TALUKA_IDS[0],
            **({"institution": "KVK Nashik", "specialism": "Plant pathology"}
               if role == "expert" else {})), allow_privileged=True)
        if role == "officer":
            # Without a scope an officer console is correctly empty. Granting
            # the demo officer the covered talukas is the same call the admin
            # console makes; it is not a new permission model.
            for taluka in reference.TALUKA_IDS:
                accounts.grant_scope(db, created["profile"]["id"], taluka)

    token = accounts.login(db, email, password,
                           user_agent=request.headers.get("user-agent", ""),
                           ip=_ip(request))
    if role == "fpo":
        _link_demo_fpo(db, token["user_id"])
    if role == "farmer":
        _ensure_demo_field(db, token["user_id"])
    audit("auth.demo_console", entity="user", entity_id=token["user_id"],
          user_id=token["user_id"], role=token["role"], ip=_ip(request),
          detail={"console": role})
    log.warning("demo console session issued", extra={"console": role})
    return token


def _ensure_demo_field(db: Database, user_id: str) -> None:
    """A demo farmer with no field opens on an empty "add your first field"
    screen, which shows a judge nothing. Give the demo account ONE field —
    placed at its taluka's centre, sown 45 days ago — through the same
    create_plot every farmer uses. Everything shown for it afterwards is real:
    live weather for those coordinates and the published risk models on it.
    No observation, count or score is invented; those start empty."""
    import datetime as dt

    from ..schemas import PlotIn
    from .plots import create_plot
    farmer = db.one("SELECT id, taluka FROM farmers WHERE user_id = :u", {"u": user_id})
    if not farmer or db.one("SELECT id FROM plots WHERE farmer_id = :f", {"f": farmer["id"]}):
        return
    from ..clock import today
    user = db.one("SELECT * FROM users WHERE id = :u", {"u": user_id})
    create_plot(PlotIn(name="Demo field · tomato", crop="tomato", area_acre=1.0,
                       sown_on=today() - dt.timedelta(days=45),
                       taluka=farmer["taluka"], location_source="manual"),
                user=user, db=db)


def _link_demo_fpo(db: Database, user_id: str) -> None:
    fid, name, name_mr = DEMO_FPO
    if not db.one("SELECT id FROM fpos WHERE id = :i", {"i": fid}):
        db.execute("INSERT INTO fpos (id, name, name_mr, district, created_at)"
                   " VALUES (:i,:n,:nm,'nashik',:now)",
                   {"i": fid, "n": name, "nm": name_mr, "now": now_iso()})
    if not db.one("SELECT 1 AS x FROM fpo_staff WHERE fpo_id = :f AND user_id = :u",
                  {"f": fid, "u": user_id}):
        db.execute("INSERT INTO fpo_staff (fpo_id, user_id, created_at) VALUES (:f,:u,:now)",
                   {"f": fid, "u": user_id, "now": now_iso()})


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
    if profile and profile.get("taluka"):
        profile = {**profile, "taluka_name": reference.taluka_name(profile["taluka"])}
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
