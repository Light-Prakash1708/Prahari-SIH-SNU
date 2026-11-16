"""
PRAHARI · /api/fpo — farmer producer organisations.

What an FPO gets: the picture across its members — crops, field health, what
is spreading in their talukas, what worked after action — as COUNTS. What it
never gets: a member's name, phone, village, coordinates or field.

Membership is the farmer's own act (POST /api/fpo/{id}/join) and can be
withdrawn the same way. Staff accounts (role 'fpo') are created by an
administrator through /api/admin/users and linked to one FPO here, the same
way an officer is granted a taluka.

Small numbers identify people. Any breakdown cell below MIN_CELL is reported
as "fewer than 3" rather than as a number, so a crop grown by one member of a
small FPO does not point at that member.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import interventions, reference
from ..clock import now_iso
from ..clock import today as _today
from ..db import Database
from ..deps import current_user, db_dep, farmer_of, require_roles
from ..errors import bad_request, forbidden, not_found
from ..health import band_for
from ..obs import audit

router = APIRouter(prefix="/api/fpo", tags=["fpo"])

MIN_CELL = 3
BAND_ORDER = ("safe", "watch", "rising", "high")


class FpoIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    name_mr: str | None = Field(default=None, max_length=160)
    district: str | None = Field(default=None, max_length=80)


class StaffIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)


def _cell(n: int) -> dict[str, Any]:
    if 0 < n < MIN_CELL:
        return {"count": None, "suppressed": True, "label": f"fewer than {MIN_CELL}",
                "label_mr": f"{MIN_CELL} पेक्षा कमी"}
    return {"count": n, "suppressed": False, "label": str(n), "label_mr": str(n)}


def _load(db: Database, fpo_id: str) -> dict[str, Any]:
    row = db.one("SELECT * FROM fpos WHERE id = :i", {"i": fpo_id})
    if not row:
        raise not_found("fpo", fpo_id)
    return row


def _staff_of(db: Database, user: dict[str, Any], fpo_id: str) -> None:
    if user["role"] == "admin":
        return
    if user["role"] != "fpo" or not db.one(
            "SELECT 1 AS x FROM fpo_staff WHERE fpo_id = :f AND user_id = :u",
            {"f": fpo_id, "u": user["id"]}):
        raise forbidden("this producer organisation")


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {"id": row["id"], "name": row["name"], "name_mr": row.get("name_mr"),
            "district": row.get("district")}


# ── administration ─────────────────────────────────────────────────────────
@router.post("", status_code=201, summary="Create a producer organisation (administrator)")
def create_fpo(data: FpoIn, user: dict[str, Any] = Depends(require_roles("admin")),
               db: Database = Depends(db_dep)):
    fid = "FPO-" + uuid.uuid4().hex[:8].upper()
    db.execute("INSERT INTO fpos (id, name, name_mr, district, created_by, created_at)"
               " VALUES (:i,:n,:nm,:d,:u,:now)",
               {"i": fid, "n": data.name.strip(), "nm": data.name_mr, "d": data.district,
                "u": user["id"], "now": now_iso()})
    audit("fpo.create", entity="fpo", entity_id=fid, user_id=user["id"], role=user["role"])
    return _public(_load(db, fid))


@router.post("/{fpo_id}/staff", status_code=201,
             summary="Link an FPO staff account to an organisation (administrator)",
             description="The account must already exist with role 'fpo' "
                         "(create it through /api/admin/users).")
def add_staff(fpo_id: str, data: StaffIn,
              user: dict[str, Any] = Depends(require_roles("admin")),
              db: Database = Depends(db_dep)):
    _load(db, fpo_id)
    staff = db.one("SELECT id, role FROM users WHERE id = :u", {"u": data.user_id})
    if not staff:
        raise not_found("user", data.user_id)
    if staff["role"] != "fpo":
        raise bad_request("not_fpo_staff", "Only an account with role 'fpo' can be linked to "
                          "a producer organisation.")
    if not db.one("SELECT 1 AS x FROM fpo_staff WHERE fpo_id = :f AND user_id = :u",
                  {"f": fpo_id, "u": staff["id"]}):
        db.execute("INSERT INTO fpo_staff (fpo_id, user_id, created_at) VALUES (:f,:u,:now)",
                   {"f": fpo_id, "u": staff["id"], "now": now_iso()})
    audit("fpo.staff_add", entity="fpo", entity_id=fpo_id, user_id=user["id"],
          role=user["role"], detail={"staff_user": staff["id"]})
    return {"fpo_id": fpo_id, "user_id": staff["id"], "linked": True}


# ── discovery and membership (farmer) ──────────────────────────────────────
@router.get("", summary="Producer organisations a farmer can join")
def list_fpos(user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    rows = db.rows("SELECT * FROM fpos ORDER BY name")
    mine: set[str] = set()
    if user["role"] == "farmer":
        farmer = farmer_of(db, user)
        mine = {r["fpo_id"] for r in db.rows(
            "SELECT fpo_id FROM fpo_members WHERE farmer_id = :f", {"f": farmer["id"]})}
    return {
        "fpos": [{**_public(r), "member": r["id"] in mine} for r in rows],
        "sharing": ("Joining lets the organisation see COUNTS across its members — crops, "
                    "field health bands, follow-up outcomes, and what is spreading in your "
                    "taluka. It never sees your name, phone, village, location or any one field. "
                    "You can leave at any time."),
        "sharing_mr": ("सामील झाल्यावर संस्थेला सर्व सदस्यांची फक्त एकत्रित संख्या दिसते — पिके, "
                       "शेत आरोग्य, पुनर्तपासणी निकाल आणि तालुक्यातील प्रादुर्भाव. तुमचे नाव, फोन, "
                       "गाव, ठिकाण किंवा कोणतेही एक शेत दिसत नाही. तुम्ही कधीही बाहेर पडू शकता."),
    }


@router.post("/{fpo_id}/join", summary="Join a producer organisation (the farmer's consent)")
def join(fpo_id: str, user: dict[str, Any] = Depends(require_roles("farmer")),
         db: Database = Depends(db_dep)):
    if user["role"] != "farmer":
        raise forbidden("membership on a farmer's behalf")
    _load(db, fpo_id)
    farmer = farmer_of(db, user)
    if not db.one("SELECT 1 AS x FROM fpo_members WHERE fpo_id = :f AND farmer_id = :m",
                  {"f": fpo_id, "m": farmer["id"]}):
        db.execute("INSERT INTO fpo_members (fpo_id, farmer_id, consented_at)"
                   " VALUES (:f,:m,:now)", {"f": fpo_id, "m": farmer["id"], "now": now_iso()})
    audit("fpo.join", entity="fpo", entity_id=fpo_id, user_id=user["id"], role="farmer")
    return {"fpo_id": fpo_id, "member": True}


@router.delete("/{fpo_id}/join", summary="Leave a producer organisation")
def leave(fpo_id: str, user: dict[str, Any] = Depends(require_roles("farmer")),
          db: Database = Depends(db_dep)):
    if user["role"] != "farmer":
        raise forbidden("membership on a farmer's behalf")
    _load(db, fpo_id)
    farmer = farmer_of(db, user)
    db.execute("DELETE FROM fpo_members WHERE fpo_id = :f AND farmer_id = :m",
               {"f": fpo_id, "m": farmer["id"]})
    audit("fpo.leave", entity="fpo", entity_id=fpo_id, user_id=user["id"], role="farmer")
    return {"fpo_id": fpo_id, "member": False}


# ── the FPO's own view ─────────────────────────────────────────────────────
@router.get("/mine", summary="The organisations this staff account belongs to")
def mine(user: dict[str, Any] = Depends(require_roles("fpo")), db: Database = Depends(db_dep)):
    if user["role"] == "admin":
        rows = db.rows("SELECT * FROM fpos ORDER BY name")
    else:
        rows = db.rows("SELECT f.* FROM fpos f JOIN fpo_staff s ON s.fpo_id = f.id"
                       " WHERE s.user_id = :u ORDER BY f.name", {"u": user["id"]})
    return {"fpos": [_public(r) for r in rows]}


@router.get("/{fpo_id}/summary", summary="Counts across an organisation's members",
            description=(
                "Members, fields, crops, latest field-health bands, open and overdue "
                "follow-ups, outbreak events in members' talukas, and follow-up outcomes after "
                "action. Counts only; any cell below 3 is reported as 'fewer than 3'. A field "
                "with no health snapshot is counted as 'not scored', never given a band."))
def summary(fpo_id: str, user: dict[str, Any] = Depends(current_user),
            db: Database = Depends(db_dep)):
    fpo = _load(db, fpo_id)
    _staff_of(db, user, fpo_id)

    members = [r["farmer_id"] for r in db.rows(
        "SELECT farmer_id FROM fpo_members WHERE fpo_id = :f", {"f": fpo_id})]
    plots: list[dict[str, Any]] = []
    if members:
        ph = ",".join(f":m{i}" for i in range(len(members)))
        plots = db.rows(f"SELECT id, crop, taluka FROM plots WHERE archived = 0"
                        f" AND farmer_id IN ({ph})",
                        {f"m{i}": m for i, m in enumerate(members)})
    plot_ids = [p["id"] for p in plots]
    talukas = sorted({p["taluka"] for p in plots if p.get("taluka")})

    crops: dict[str, int] = {}
    by_taluka: dict[str, int] = {}
    for p in plots:
        crops[p["crop"]] = crops.get(p["crop"], 0) + 1
        if p.get("taluka"):
            by_taluka[p["taluka"]] = by_taluka.get(p["taluka"], 0) + 1

    bands = dict.fromkeys(BAND_ORDER, 0)
    not_scored = 0
    for pid in plot_ids:
        snap = db.one("SELECT score FROM health_snapshots WHERE plot_id = :p"
                      " ORDER BY day DESC LIMIT 1", {"p": pid})
        if not snap or snap.get("score") is None:
            not_scored += 1
        else:
            bands[band_for(float(snap["score"]))["key"]] += 1

    open_fu = overdue = 0
    if plot_ids:
        ph = ",".join(f":p{i}" for i in range(len(plot_ids)))
        params = {f"p{i}": p for i, p in enumerate(plot_ids)}
        today = _today().isoformat()
        for r in db.rows(f"SELECT due_on FROM followups WHERE plot_id IN ({ph})"
                         f" AND done_observation IS NULL AND outcome IS NULL", params):
            open_fu += 1
            if str(r["due_on"])[:10] < today:
                overdue += 1

    events = []
    if talukas:
        ph = ",".join(f":t{i}" for i in range(len(talukas)))
        for e in db.rows(f"SELECT taluka, crop, problem, grade, reports, confirmed, opened_on"
                         f" FROM outbreak_events WHERE closed_on IS NULL AND taluka IN ({ph})"
                         f" ORDER BY opened_on DESC",
                         {f"t{i}": t for i, t in enumerate(talukas)}):
            events.append({**e,
                           "taluka_name": reference.taluka_name(e["taluka"]),
                           "problem_name": reference.problem_name(e["problem"]),
                           "problem_name_mr": reference.problem_name(e["problem"], "mr")})

    def crop_label(c: str) -> tuple[str, str | None]:
        meta = reference.CROPS.get(c, {})
        return meta.get("name", c), meta.get("mr")

    return {
        "fpo": _public(fpo),
        "members": _cell(len(members)),
        "fields": _cell(len(plots)),
        "crops": sorted(
            [{"crop": c, "name": crop_label(c)[0], "name_mr": crop_label(c)[1], **_cell(n)}
             for c, n in crops.items()], key=lambda x: -(x["count"] or 0)),
        "talukas": [{"taluka": t, "name": reference.taluka_name(t), **_cell(n)}
                    for t, n in sorted(by_taluka.items())],
        "health": {
            "bands": [{"band": b, **_cell(bands[b])} for b in BAND_ORDER],
            "not_scored": _cell(not_scored),
            "note": ("The latest stored crop-health score of each member field, by band. A field "
                     "that has never been scored is counted as not scored, not as safe."),
        },
        "followups": {"open": _cell(open_fu), "overdue": _cell(overdue)},
        "outbreaks": {
            "events": events,
            "note": ("Open outbreak events in the talukas where members farm. These are area "
                     "signals graded by PRAHARI's outbreak rules, not reports about members."),
        },
        "outcomes": interventions.summarise(db, plot_ids=plot_ids),
        "privacy": (f"Counts only. No member's name, phone, village, location or field leaves "
                    f"the server, and any count below {MIN_CELL} is shown as 'fewer than "
                    f"{MIN_CELL}'."),
        "min_cell": MIN_CELL,
    }
