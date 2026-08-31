"""
PRAHARI · the chemical gate
════════════════════════════════════════════════════════════════════════════
The highest-risk module in the system, so it is also the most restrictive.

One rule, enforced in one place:

    ONLY a label claim with status = 'verified' — verified by a named person,
    on a recorded date, against a cited source, and not past its expiry — may
    be returned as an actionable chemical recommendation.

Everything else (draft, expired, revoked, or simply absent) produces the same
answer:

    "No verified chemical recommendation is available for this combination.
     Consult your Krishi Sahayak or KVK before applying anything."

The 42 rows shipped in backend/data/label_claims.json are ALL status='draft'.
They are transcriptions of combinations commonly published in state IPM
packages, present so the engine can be built and tested — they are NOT a
pesticide recommendation and this module will not serve them as one. Verifying
them against the CIB&RC 'Major Uses of Pesticides' list is a named deployment
task, and until it is done a production instance recommends no chemical at all.
That is the correct behaviour, not a limitation to be worked around.

No language model is anywhere near this file. Doses come from table rows.
"""
from __future__ import annotations

import re
from typing import Any

from . import reference
from .clock import now_iso
from .clock import today as _today
from .db import Database

VERIFIED, DRAFT, EXPIRED, REVOKED = "verified", "draft", "expired", "revoked"
ACTIONABLE_STATUSES = (VERIFIED,)

UNAVAILABLE_MESSAGE = (
    "No verified chemical recommendation is available for this crop and target in "
    "PRAHARI's reference table. Consult your Krishi Sahayak, KVK or an authorised "
    "agriculture professional before applying anything.")
UNAVAILABLE_MESSAGE_MR = (
    "या पिकासाठी व या किडीसाठी प्रहरीकडे तपासलेली रासायनिक शिफारस उपलब्ध नाही. "
    "फवारणीपूर्वी कृषी सहाय्यक किंवा कृषी विज्ञान केंद्राचा सल्ला घ्या.")


# ── loading the reference table into the database ───────────────────────────
def sync_reference_claims(db: Database) -> dict[str, int]:
    """Copy backend/data/label_claims.json into `label_claims`, preserving any
    status a reviewer has already set in the database.

    The JSON file is the draft corpus. The database is where verification
    lives, because verification is an act by a person on a date and belongs in
    a row someone signed, not in a file anyone can edit in a pull request.
    """
    inserted = updated = 0
    stamp = now_iso()
    for c in reference.CLAIMS:
        cid = claim_id(c)
        existing = db.one("SELECT id, status FROM label_claims WHERE id = :id", {"id": cid})
        params = {
            "id": cid, "crop": c["crop"], "target": c["target"], "product": c["product"],
            "ai": _active_ingredient(c["product"]), "form": _formulation(c["product"]),
            "moa": c.get("moa"), "dose": float(c["dose"]), "unit": c["unit"],
            "water": c.get("water_l_per_acre"), "phi": int(c["phi"]),
            "reentry": c.get("reentry_h"), "tox": c.get("toxicity"), "bee": c.get("bee"),
            "cost": c.get("cost_acre"),
            "source": c.get("source") or "State IPM package transcription (unverified)",
            "source_url": c.get("source_url"),
            "now": stamp,
        }
        if existing:
            # Never downgrade or overwrite a verification decision.
            db.execute(
                "UPDATE label_claims SET crop=:crop, target=:target, product=:product,"
                " active_ingredient=:ai, formulation=:form, moa_group=:moa, dose=:dose,"
                " unit=:unit, water_l_per_acre=:water, phi_days=:phi, reentry_hours=:reentry,"
                " toxicity=:tox, bee_hazard=:bee, cost_per_acre=:cost, source=:source,"
                " source_url=:source_url, updated_at=:now WHERE id=:id", params)
            updated += 1
        else:
            db.execute(
                "INSERT INTO label_claims (id, crop, target, product, active_ingredient,"
                " formulation, moa_group, dose, unit, water_l_per_acre, phi_days, reentry_hours,"
                " toxicity, bee_hazard, cost_per_acre, status, source, source_url,"
                " created_at, updated_at)"
                " VALUES (:id,:crop,:target,:product,:ai,:form,:moa,:dose,:unit,:water,:phi,"
                " :reentry,:tox,:bee,:cost,'draft',:source,:source_url,:now,:now)", params)
            inserted += 1

    for entry in reference.RESTRICTED:
        rid = "R-" + re.sub(r"[^a-z0-9]+", "-", entry["product"].lower()).strip("-")[:48]
        if not db.one("SELECT id FROM restricted_products WHERE id=:id", {"id": rid}):
            db.execute(
                "INSERT INTO restricted_products (id, pattern, scope, reason, source, created_at)"
                " VALUES (:id, :pattern, 'maharashtra', :reason, :source, :now)",
                {"id": rid, "pattern": entry["product"], "reason": entry["reason"],
                 "source": entry.get("source") or
                 "Maharashtra Section 27 order, Extraordinary Gazette No. 183 (2018)",
                 "now": stamp})
    return {"inserted": inserted, "updated": updated}


def claim_id(c: dict[str, Any]) -> str:
    key = f"{c['crop']}|{c['target']}|{c['product']}".lower()
    return "LC-" + re.sub(r"[^a-z0-9]+", "-", key).strip("-")[:56]


def _active_ingredient(product: str) -> str:
    return re.split(r"\s+\d", product)[0].strip()


def _formulation(product: str) -> str | None:
    m = re.search(r"\b(SL|SP|SC|EC|WG|WP|OD|SG|GR|ZC|WDG|CS|FS)\b", product)
    return m.group(1) if m else None


# ── the gate ────────────────────────────────────────────────────────────────
def verified_claims(db: Database, crop: str, target: str) -> list[dict[str, Any]]:
    """The ONLY function that may return a row a farmer can act on."""
    rows = db.rows(
        "SELECT * FROM label_claims WHERE crop=:crop AND target=:target AND status=:st"
        " ORDER BY product", {"crop": crop, "target": target, "st": VERIFIED})
    out = []
    day = _today().isoformat()
    for r in rows:
        if r.get("expires_on") and str(r["expires_on"]) < day:
            continue
        out.append(r)
    return out


def all_claims(db: Database, crop: str, target: str) -> list[dict[str, Any]]:
    return db.rows(
        "SELECT * FROM label_claims WHERE crop=:crop AND target=:target ORDER BY status, product",
        {"crop": crop, "target": target})


def restricted_products(db: Database) -> list[dict[str, Any]]:
    return db.rows("SELECT * FROM restricted_products")


def is_restricted(product: str, restricted: list[dict[str, Any]]) -> dict[str, Any] | None:
    p = product.lower()
    for r in restricted:
        pat = r["pattern"].lower()
        if pat in p or p in pat or _active_ingredient(pat) == _active_ingredient(p):
            return r
    return None


def availability(db: Database, crop: str, target: str) -> dict[str, Any]:
    """What the UI needs to explain WHY there is no chemical option — without
    naming a single draft product, because naming it is half of recommending
    it."""
    every = all_claims(db, crop, target)
    ok = verified_claims(db, crop, target)
    by_status: dict[str, int] = {}
    for r in every:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {
        "verified_available": bool(ok),
        "verified_count": len(ok),
        "counts_by_status": by_status,
        "message": None if ok else UNAVAILABLE_MESSAGE,
        "message_mr": None if ok else UNAVAILABLE_MESSAGE_MR,
        "why": None if ok else (
            f"{by_status.get(DRAFT, 0)} candidate combination(s) for this crop and target are "
            f"present in the reference table but are marked DRAFT — they have not been verified "
            f"against the CIB&RC 'Major Uses of Pesticides' list by a named reviewer. PRAHARI "
            f"will not print an unverified dose."),
        "verification_process": (
            "A claim becomes actionable when a reviewer records the CIB&RC source, their name and "
            "the date against it (POST /api/admin/claims/{id}/verify, admin role). Nothing else "
            "changes its status."),
    }


def verify_claim(db: Database, claim_id_: str, *, verified_by: str, source: str,
                 source_url: str | None = None, expires_on: str | None = None
                 ) -> dict[str, Any] | None:
    row = db.one("SELECT * FROM label_claims WHERE id=:id", {"id": claim_id_})
    if not row:
        return None
    db.execute(
        "UPDATE label_claims SET status='verified', verified_by=:by, verified_at=:at,"
        " source=:source, source_url=:url, expires_on=:exp, updated_at=:at WHERE id=:id",
        {"by": verified_by, "at": now_iso(), "source": source, "url": source_url,
         "exp": expires_on, "id": claim_id_})
    return db.one("SELECT * FROM label_claims WHERE id=:id", {"id": claim_id_})


def set_status(db: Database, claim_id_: str, status: str, note: str = "") -> dict[str, Any] | None:
    if status not in (DRAFT, VERIFIED, EXPIRED, REVOKED):
        raise ValueError("unknown status")
    db.execute("UPDATE label_claims SET status=:s, updated_at=:at WHERE id=:id",
               {"s": status, "at": now_iso(), "id": claim_id_})
    return db.one("SELECT * FROM label_claims WHERE id=:id", {"id": claim_id_})


def to_prescribe_shape(row: dict[str, Any]) -> dict[str, Any]:
    """Adapt a database row to the dict shape prescribe.screen() already
    understands, so the dose arithmetic, PHI and rotation logic are unchanged."""
    return {
        "id": row["id"], "crop": row["crop"], "target": row["target"],
        "product": row["product"], "moa": row.get("moa_group"),
        "dose": row["dose"], "unit": row["unit"],
        "water_l_per_acre": row.get("water_l_per_acre") or 200,
        "phi": row["phi_days"], "reentry_h": row.get("reentry_hours"),
        "toxicity": row.get("toxicity"), "bee": row.get("bee_hazard"),
        "cost_acre": row.get("cost_per_acre"), "status": row["status"],
        "source": row.get("source"), "source_url": row.get("source_url"),
        "verified_by": row.get("verified_by"), "verified_at": row.get("verified_at"),
        "active_ingredient": row.get("active_ingredient"),
        "formulation": row.get("formulation"),
    }
