"""
PRAHARI · /api/privacy — what we hold, and how to end it.

HTTP only. Every rule about WHAT leaves and what survives lives in
`app/privacy.py`; this file authenticates, confirms intent, and shapes the
answer.

Two confirmations guard the destructive routes, and they guard different
mistakes. The password proves the person at the phone is the account holder —
a phone left unlocked on a bund should not be one tap from erasing a season.
The typed phrase proves they meant this specific thing; it is checked in the
farmer's own language, because a confirmation nobody can read is not consent.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from .. import privacy as pv
from ..db import Database
from ..deps import current_user, db_dep
from ..errors import bad_request, forbidden
from ..obs import audit
from ..runtime import get_runtime
from ..schemas import DeleteAccountIn, DeleteRecordsIn
from ..security import verify_password

router = APIRouter(prefix="/api/privacy", tags=["privacy"])

# Accepted in either language. Case and surrounding space are forgiven; the
# word itself is not, because that is the whole point of the check.
CONFIRM_DELETE = {"delete", "डिलीट", "हटवा"}


def _farmer(db: Database, user: dict[str, Any]) -> dict[str, Any] | None:
    """The farmer profile, or None.

    Unlike `deps.farmer_of` this does not raise: an officer or expert account
    has no farmer profile and is still entitled to see what is held about it
    and to close it.
    """
    return db.one("SELECT * FROM farmers WHERE user_id = :u", {"u": user["id"]})


def _check(user: dict[str, Any], password: str, confirm: str) -> None:
    if not verify_password(password or "", user["password_hash"]):
        raise forbidden("this deletion — the password did not match")
    if (confirm or "").strip().casefold() not in CONFIRM_DELETE:
        raise bad_request(
            "confirmation_required",
            "Type DELETE to confirm. Nothing has been removed.",
            "पुष्टीसाठी DELETE लिहा. काहीही हटवलेले नाही.")


@router.get("/summary", summary="What PRAHARI holds about this account")
def summary(user: dict[str, Any] = Depends(current_user),
            db: Database = Depends(db_dep)):
    return pv.summary(db, user, _farmer(db, user))


@router.get("/export", summary="Everything held about this account, as JSON")
def export(user: dict[str, Any] = Depends(current_user),
           db: Database = Depends(db_dep)):
    """Offered before deletion, not after. A farmer deciding whether to erase a
    season of records should be able to read them first."""
    return pv.export(db, user, _farmer(db, user))


@router.post("/records/delete", summary="Delete one or more categories of record")
def delete_records(body: DeleteRecordsIn,
                   user: dict[str, Any] = Depends(current_user),
                   db: Database = Depends(db_dep)):
    _check(user, body.password, body.confirm)
    if not body.categories:
        raise bad_request("no_categories", "Choose at least one thing to delete.",
                          "किमान एक प्रकार निवडा.")
    unknown = [c for c in body.categories if c not in pv.CATEGORY_IDS]
    if unknown:
        raise bad_request("unknown_category", f"Not a category: {', '.join(unknown)}")

    rt = get_runtime()
    out = pv.delete_records(db, rt.storage, user, _farmer(db, user),
                            body.categories, body.community_mode)
    audit("privacy.records_deleted", entity="user", entity_id=user["id"],
          user_id=user["id"], role=user.get("role"),
          detail={"categories": body.categories, "rows": out["rows"]})
    return out


@router.post("/account/delete", summary="Close this account and remove everything behind it")
def delete_account(body: DeleteAccountIn,
                   user: dict[str, Any] = Depends(current_user),
                   db: Database = Depends(db_dep)):
    """Irreversible, and described as such on the screen before it is called.

    An officer or expert account is refused here. Those accounts carry other
    people's case history — an expert's verdicts are the basis of other
    farmers' records — so closing one is an administrative act with a paper
    trail, not a self-service button.
    """
    if user.get("role") not in ("farmer",):
        raise forbidden(
            "self-service deletion of a staff account — an officer or expert "
            "account holds other people's case records; ask an administrator")
    _check(user, body.password, body.confirm)

    farmer = _farmer(db, user)
    farmer_id = (farmer or {}).get("id")
    rt = get_runtime()
    # Audited BEFORE the row goes: afterwards there is no user id to record.
    audit("privacy.account_delete_requested", entity="user",
          entity_id=user["id"], user_id=user["id"], role=user.get("role"), detail={"community_mode": body.community_mode})
    out = pv.delete_account(db, rt.storage, user, farmer, body.community_mode)
    out["verified_gone"] = pv.verify_gone(db, user["id"], farmer_id)
    out["message"] = ("Your account and its records have been deleted. The counts "
                      "below were measured after the deletion ran — every one is "
                      "zero, or the deletion did not finish.")
    out["message_mr"] = ("तुमचे खाते आणि नोंदी हटवल्या आहेत. खालील आकडे हटवल्यानंतर "
                         "मोजलेले आहेत.")
    return out
