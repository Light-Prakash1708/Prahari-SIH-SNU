"""
PRAHARI · accounts
════════════════════════════════════════════════════════════════════════════
Registration, login, sessions, password reset — and the profile row that gives
a user a role in the agricultural world (farmer / officer / expert).

The prototype's `/api/me` returned the first row of the farmers table. That is
the single change that matters most here: identity is now a credential someone
holds, and every scope decision downstream is made from it, server-side.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import uuid
from typing import Any

from . import reference
from .clock import iso, now_iso, real_iso, real_now
from .config import get_settings
from .db import Database, bit, dumps
from .errors import bad_request, conflict, unauthorized
from .security import (
    hash_password,
    hash_token,
    issue_token,
    password_problems,
    reset_token,
    verify_password,
)

log = logging.getLogger("prahari.accounts")


def new_user_id() -> str:
    return "U-" + uuid.uuid4().hex[:12].upper()


def normalise_identifier(identifier: str) -> tuple[str | None, str | None]:
    """(email, phone) — exactly one is non-None."""
    v = (identifier or "").strip().lower()
    if "@" in v:
        # Only the phone branch may strip separators — an earlier version stripped
        # hyphens from the whole string and quietly turned a valid hyphenated
        # domain into an address that matched nothing.
        return v.replace(" ", ""), None
    digits = re.sub(r"\D", "", v)
    if len(digits) >= 10:
        return None, digits[-10:]
    return None, None


def find_user(db: Database, identifier: str) -> dict[str, Any] | None:
    email, phone = normalise_identifier(identifier)
    if email:
        return db.one("SELECT * FROM users WHERE email = :e", {"e": email})
    if phone:
        return db.one("SELECT * FROM users WHERE phone = :p", {"p": phone})
    return None


def register(db: Database, data, *, allow_privileged: bool = False) -> dict[str, Any]:
    """Creates the user AND the role profile in one transaction-shaped unit.

    Officer, expert and admin accounts cannot be self-registered on a public
    instance: an officer account grants sight of a whole taluka's farmers.
    """
    problems = password_problems(data.password)
    if problems:
        raise bad_request("weak_password",
                          "Choose a stronger password: " + ", ".join(problems) + ".",
                          message_mr="अधिक मजबूत पासवर्ड निवडा.")
    if data.role != "farmer" and not allow_privileged:
        raise bad_request(
            "role_not_self_serviceable",
            "Officer, expert and administrator accounts are created by an administrator, not by "
            "self-registration. Ask your district office to issue one.",
            message_mr="अधिकारी व तज्ज्ञ खाती प्रशासकाकडून तयार केली जातात.")
    email = (data.email or "").strip().lower() or None
    phone = data.phone or None
    if email and db.one("SELECT id FROM users WHERE email = :e", {"e": email}):
        raise conflict("email_taken", "An account already exists for that email address.",
                       message_mr="या ईमेलवर आधीच खाते आहे.")
    if phone and db.one("SELECT id FROM users WHERE phone = :p", {"p": phone}):
        raise conflict("phone_taken", "An account already exists for that mobile number.",
                       message_mr="या मोबाइल क्रमांकावर आधीच खाते आहे.")
    if data.role == "farmer" and data.taluka not in reference.TALUKA_IDS:
        raise bad_request("unknown_taluka",
                          f"'{data.taluka}' is not a taluka PRAHARI covers. "
                          f"Covered: {', '.join(reference.TALUKA_IDS)}.")

    uid = new_user_id()
    stamp = now_iso()
    db.execute(
        "INSERT INTO users (id, email, phone, password_hash, role, full_name, full_name_mr,"
        " lang, is_active, email_verified, created_at, updated_at)"
        " VALUES (:id,:e,:p,:h,:r,:n,:nmr,:l,1,0,:now,:now)",
        {"id": uid, "e": email, "p": phone, "h": hash_password(data.password),
         "r": data.role, "n": data.full_name, "nmr": data.full_name_mr,
         "l": data.lang, "now": stamp})

    profile = create_profile(db, uid, data)
    log.info("user registered", extra={"user_id": uid, "role": data.role})
    return {"user_id": uid, "role": data.role, "profile": profile}


def create_profile(db: Database, user_id: str, data) -> dict[str, Any]:
    stamp = now_iso()
    if data.role == "farmer":
        fid = "F-" + uuid.uuid4().hex[:10].upper()
        db.execute(
            "INSERT INTO farmers (id, user_id, name, name_mr, phone, farmer_id_agristack,"
            " taluka, village, lang, literacy, sms_opt_in, ivr_opt_in, created_at)"
            " VALUES (:id,:uid,:n,:nmr,:ph,:ag,:tk,:vil,:l,:lit,1,:ivr,:now)",
            {"id": fid, "uid": user_id, "n": data.full_name, "nmr": data.full_name_mr,
             "ph": data.phone, "ag": data.agristack_id, "tk": data.taluka,
             "vil": data.village, "l": data.lang, "lit": data.literacy,
             "ivr": bit(data.literacy == "voice_only"), "now": stamp})
        return db.one("SELECT * FROM farmers WHERE id = :id", {"id": fid})
    if data.role == "officer":
        oid = "O-" + uuid.uuid4().hex[:10].upper()
        db.execute(
            "INSERT INTO officers (id, user_id, name, role, taluka, district, visits_per_week,"
            " created_at) VALUES (:id,:uid,:n,'krishi_sahayak',:tk,'nashik',5,:now)",
            {"id": oid, "uid": user_id, "n": data.full_name, "tk": data.taluka, "now": stamp})
        # An officer with no explicit scope sees their own taluka, and only it.
        scopes = [data.taluka] if data.taluka else []
        for t in scopes:
            db.execute("INSERT INTO officer_scopes (officer_id, taluka) VALUES (:o,:t)",
                       {"o": oid, "t": t})
        return db.one("SELECT * FROM officers WHERE id = :id", {"id": oid})
    if data.role == "expert":
        eid = "E-" + uuid.uuid4().hex[:10].upper()
        db.execute(
            "INSERT INTO experts (id, user_id, name, institution, specialism, crops, created_at)"
            " VALUES (:id,:uid,:n,:inst,:spec,:crops,:now)",
            {"id": eid, "uid": user_id, "n": data.full_name, "inst": data.institution,
             "spec": data.specialism, "crops": dumps(list(reference.CROPS.keys())),
             "now": stamp})
        return db.one("SELECT * FROM experts WHERE id = :id", {"id": eid})
    return {}


def login(db: Database, identifier: str, password: str, *, user_agent: str = "",
          ip: str = "") -> dict[str, Any]:
    user = find_user(db, identifier)
    # Same message and comparable timing whether the account exists or the
    # password is wrong — an error that distinguishes them is a user enumerator.
    if not user or not verify_password(password, user["password_hash"]):
        if not user:
            hash_password("timing-equaliser")
        raise unauthorized("That email/mobile and password do not match an account.")
    if not user["is_active"]:
        raise unauthorized("This account has been deactivated. Contact your district office.")

    token, jti, expires = issue_token(user["id"], user["role"])
    db.execute(
        "INSERT INTO sessions (jti, user_id, issued_at, expires_at, user_agent, ip)"
        " VALUES (:j,:u,:i,:e,:ua,:ip)",
        {"j": jti, "u": user["id"], "i": real_iso(), "e": iso(expires),
         "ua": user_agent[:200], "ip": ip[:64]})
    db.execute("UPDATE users SET last_login_at = :now, updated_at = :now WHERE id = :id",
               {"now": now_iso(), "id": user["id"]})
    return {"access_token": token, "token_type": "bearer", "expires_at": iso(expires),
            "role": user["role"], "user_id": user["id"]}


def logout(db: Database, jti: str) -> None:
    db.execute("UPDATE sessions SET revoked_at = :now WHERE jti = :j AND revoked_at IS NULL",
               {"now": real_iso(), "j": jti})


def logout_all(db: Database, user_id: str) -> int:
    return db.execute(
        "UPDATE sessions SET revoked_at = :now WHERE user_id = :u AND revoked_at IS NULL",
        {"now": real_iso(), "u": user_id})


def session_valid(db: Database, jti: str) -> bool:
    row = db.one("SELECT revoked_at, expires_at FROM sessions WHERE jti = :j", {"j": jti})
    if not row or row["revoked_at"]:
        return False
    # Session expiry is protocol time, compared against the real clock — see
    # clock.real_now(). A pinned demo clock must not resurrect a dead session.
    return str(row["expires_at"]) > real_iso()


def profile_for(db: Database, user: dict[str, Any]) -> dict[str, Any] | None:
    role = user["role"]
    if role == "farmer":
        return db.one("SELECT * FROM farmers WHERE user_id = :u", {"u": user["id"]})
    if role == "officer":
        return db.one("SELECT * FROM officers WHERE user_id = :u", {"u": user["id"]})
    if role == "expert":
        return db.one("SELECT * FROM experts WHERE user_id = :u", {"u": user["id"]})
    return None


def officer_scopes(db: Database, officer_id: str) -> list[str]:
    return [r["taluka"] for r in db.rows(
        "SELECT taluka FROM officer_scopes WHERE officer_id = :o ORDER BY taluka",
        {"o": officer_id})]


def grant_scope(db: Database, officer_id: str, taluka: str) -> None:
    if db.one("SELECT taluka FROM officer_scopes WHERE officer_id=:o AND taluka=:t",
              {"o": officer_id, "t": taluka}):
        return
    db.execute("INSERT INTO officer_scopes (officer_id, taluka) VALUES (:o,:t)",
               {"o": officer_id, "t": taluka})


# ── password reset ──────────────────────────────────────────────────────────
def begin_reset(db: Database, identifier: str) -> tuple[str, dict[str, Any]] | None:
    """Returns (plaintext_token, user) or None. The CALLER decides how the token
    reaches the user; the endpoint always responds identically so the reset form
    cannot be used to discover which numbers are registered."""
    user = find_user(db, identifier)
    if not user:
        return None
    raw, digest = reset_token()
    ttl = get_settings().password_reset_ttl_minutes
    db.execute("DELETE FROM password_resets WHERE user_id = :u", {"u": user["id"]})
    db.execute(
        "INSERT INTO password_resets (token_hash, user_id, expires_at) VALUES (:h,:u,:e)",
        {"h": digest, "u": user["id"],
         "e": iso(real_now() + dt.timedelta(minutes=ttl))})
    return raw, user


def complete_reset(db: Database, token: str, new_password: str) -> bool:
    problems = password_problems(new_password)
    if problems:
        raise bad_request("weak_password",
                          "Choose a stronger password: " + ", ".join(problems) + ".")
    row = db.one("SELECT * FROM password_resets WHERE token_hash = :h",
                 {"h": hash_token(token)})
    if not row or row["used_at"] or str(row["expires_at"]) < real_iso():
        return False
    db.execute("UPDATE users SET password_hash = :h, updated_at = :now WHERE id = :u",
               {"h": hash_password(new_password), "now": now_iso(), "u": row["user_id"]})
    db.execute("UPDATE password_resets SET used_at = :now WHERE token_hash = :h",
               {"now": now_iso(), "h": row["token_hash"]})
    logout_all(db, row["user_id"])           # a reset ends every existing session
    return True


def change_password(db: Database, user: dict[str, Any], current: str, new: str) -> None:
    if not verify_password(current, user["password_hash"]):
        raise unauthorized("Your current password is not correct.")
    problems = password_problems(new)
    if problems:
        raise bad_request("weak_password",
                          "Choose a stronger password: " + ", ".join(problems) + ".")
    db.execute("UPDATE users SET password_hash = :h, updated_at = :now WHERE id = :id",
               {"h": hash_password(new), "now": now_iso(), "id": user["id"]})
