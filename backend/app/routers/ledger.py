"""
PRAHARI · /api/farm-ledger — what the season cost.

The one deliberate boundary: **cost is never an input to an agronomic
decision.** Nothing on this router is read by the risk engine, the economic
threshold, or the IPM ladder. The moment a cheap intervention can score better
than a correct one, the system is giving agricultural advice on financial
grounds, and a farmer following it loses the crop and the money.

So this is bookkeeping, kept next to the crop record rather than inside it.
It answers "where did this season's money go", and stops there.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..clock import now_iso
from ..clock import today as _today
from ..db import Database
from ..deps import current_user, db_dep, owned_plot, visible_plot
from ..errors import bad_request, not_found
from ..schemas import FarmEntryIn, FarmEntryPatch

router = APIRouter(prefix="/api/farm-ledger", tags=["farm-ledger"])

# Categories are a fixed list so the dashboard can group without a free-text
# pile of "labour", "Labour", "labor". `other` exists so nothing is unrecordable.
CATEGORIES = [
    {"id": "seed", "en": "Seed & planting material", "mr": "बियाणे", "em": "🌱"},
    {"id": "fertilizer", "en": "Fertilizer & nutrients", "mr": "खत", "em": "🧪"},
    {"id": "pesticide", "en": "Pesticide & biologicals", "mr": "कीडनाशक", "em": "🛡"},
    {"id": "labour", "en": "Labour", "mr": "मजुरी", "em": "🧑‍🌾"},
    {"id": "irrigation", "en": "Irrigation & power", "mr": "पाणी व वीज", "em": "💧"},
    {"id": "machinery", "en": "Machinery & fuel", "mr": "यंत्र व इंधन", "em": "🚜"},
    {"id": "transport", "en": "Transport & market", "mr": "वाहतूक", "em": "🛻"},
    {"id": "other", "en": "Other", "mr": "इतर", "em": "📦"},
]
CATEGORY_IDS = {c["id"] for c in CATEGORIES}
INCOME_CATEGORIES = [
    {"id": "sale", "en": "Produce sale", "mr": "विक्री", "em": "💰"},
    {"id": "subsidy", "en": "Subsidy or scheme", "mr": "अनुदान", "em": "🏛"},
    {"id": "other_income", "en": "Other income", "mr": "इतर उत्पन्न", "em": "📥"},
]
INCOME_IDS = {c["id"] for c in INCOME_CATEGORIES}


@router.get("/meta", summary="Categories the ledger groups by")
def meta(user: dict[str, Any] = Depends(current_user)):
    return {
        "expense_categories": CATEGORIES,
        "income_categories": INCOME_CATEGORIES,
        "note": ("Costs recorded here are bookkeeping only. They are never read by the risk "
                 "engine, the economic threshold or the IPM ladder — a spray decision must "
                 "not turn on what a product costs."),
    }


def _row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"], "plot_id": r["plot_id"], "crop_cycle_id": r.get("crop_cycle_id"),
        "direction": r["direction"], "category": r["category"], "title": r["title"],
        "amount_inr": float(r["amount_inr"]),
        "quantity": r.get("quantity"), "unit": r.get("unit"),
        "spent_on": str(r["spent_on"])[:10], "note": r.get("note"),
        "application_id": r.get("application_id"),
        "created_at": r.get("created_at"),
    }


@router.get("", summary="Entries for a field, newest first",
            description="Scoped to fields the caller owns. `from`/`to` bound the period; "
                        "omit both for the whole record.")
def list_entries(plot_id: str = Query(...),
                 since: str | None = Query(None, alias="from"),
                 until: str | None = Query(None, alias="to"),
                 cycle_id: str | None = Query(None),
                 limit: int = Query(200, le=1000),
                 user: dict[str, Any] = Depends(current_user),
                 db: Database = Depends(db_dep)):
    visible_plot(db, user, plot_id)
    sql = "SELECT * FROM farm_entries WHERE plot_id = :p"
    args: dict[str, Any] = {"p": plot_id, "n": limit}
    if since:
        sql += " AND spent_on >= :since"
        args["since"] = since
    if until:
        sql += " AND spent_on <= :until"
        args["until"] = until
    if cycle_id:
        sql += " AND crop_cycle_id = :c"
        args["c"] = cycle_id
    sql += " ORDER BY spent_on DESC, id DESC LIMIT :n"
    rows = [_row(r) for r in db.rows(sql, args)]
    return {"plot_id": plot_id, "entries": rows, "count": len(rows),
            "summary": _summarise(rows)}


def _summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals and the split by category.

    Returns zeroes and an empty breakdown for an empty ledger rather than
    omitting the block — a screen showing "₹0 across 0 entries" is a true
    statement about a field nobody has recorded costs for.
    """
    spend = sum(r["amount_inr"] for r in rows if r["direction"] == "expense")
    income = sum(r["amount_inr"] for r in rows if r["direction"] == "income")
    by_cat: dict[str, float] = {}
    for r in rows:
        if r["direction"] == "expense":
            by_cat[r["category"]] = by_cat.get(r["category"], 0.0) + r["amount_inr"]
    label = {c["id"]: c for c in CATEGORIES + INCOME_CATEGORIES}
    breakdown = [
        {"category": k, "amount_inr": round(v, 2),
         "share": round(v / spend, 4) if spend else 0.0,
         "label": label.get(k, {}).get("en", k),
         "label_mr": label.get(k, {}).get("mr"),
         "em": label.get(k, {}).get("em", "📦")}
        for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])
    ]
    return {
        "expense_inr": round(spend, 2),
        "income_inr": round(income, 2),
        "net_inr": round(income - spend, 2),
        "entries": len(rows),
        "by_category": breakdown,
    }


@router.post("", status_code=201, summary="Record an expense or an income entry")
def create(data: FarmEntryIn, user: dict[str, Any] = Depends(current_user),
           db: Database = Depends(db_dep)):
    plot = owned_plot(db, user, data.plot_id)
    valid = INCOME_IDS if data.direction == "income" else CATEGORY_IDS
    if data.category not in valid:
        raise bad_request("unknown_category",
                          f"'{data.category}' is not a {data.direction} category.",
                          "ही श्रेणी उपलब्ध नाही.")
    if data.amount_inr <= 0:
        raise bad_request("invalid_amount", "An amount must be greater than zero.",
                          "रक्कम शून्यापेक्षा जास्त असावी.")

    # Idempotent on client_ref, so the offline queue re-sending an entry does
    # not double-count a season's costs.
    if data.client_ref:
        dup = db.one("SELECT * FROM farm_entries WHERE plot_id = :p AND client_ref = :r",
                     {"p": plot["id"], "r": data.client_ref})
        if dup:
            return {"entry": _row(dup), "duplicate": True}

    cycle = db.one("SELECT id FROM crop_cycles WHERE plot_id = :p AND ended_on IS NULL"
                   " ORDER BY sown_on DESC", {"p": plot["id"]})
    now = now_iso()
    db.execute(
        "INSERT INTO farm_entries (plot_id, crop_cycle_id, direction, category, title,"
        " amount_inr, quantity, unit, spent_on, note, client_ref, created_at)"
        " VALUES (:p, :c, :d, :cat, :t, :a, :q, :u, :on, :n, :r, :ts)",
        {"p": plot["id"], "c": (cycle or {}).get("id"), "d": data.direction,
         "cat": data.category, "t": data.title.strip(), "a": float(data.amount_inr),
         "q": data.quantity, "u": data.unit, "on": data.spent_on or _today().isoformat(),
         "n": data.note, "r": data.client_ref, "ts": now})
    row = db.one("SELECT * FROM farm_entries WHERE plot_id = :p ORDER BY id DESC",
                 {"p": plot["id"]})
    return {"entry": _row(row), "duplicate": False}


@router.patch("/{entry_id}", summary="Correct an entry")
def patch(entry_id: int, data: FarmEntryPatch,
          user: dict[str, Any] = Depends(current_user), db: Database = Depends(db_dep)):
    row = db.one("SELECT * FROM farm_entries WHERE id = :i", {"i": entry_id})
    if not row:
        raise not_found("farm entry", str(entry_id))
    owned_plot(db, user, row["plot_id"])

    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        return {"entry": _row(row), "changed": False}
    if "category" in fields:
        valid = INCOME_IDS if row["direction"] == "income" else CATEGORY_IDS
        if fields["category"] not in valid:
            raise bad_request("unknown_category", "That category is not available.",
                              "ही श्रेणी उपलब्ध नाही.")
    if "amount_inr" in fields and float(fields["amount_inr"]) <= 0:
        raise bad_request("invalid_amount", "An amount must be greater than zero.",
                          "रक्कम शून्यापेक्षा जास्त असावी.")

    sets = ", ".join(f"{k} = :{k}" for k in fields)
    db.execute(f"UPDATE farm_entries SET {sets}, updated_at = :ts WHERE id = :i",
               {**fields, "ts": now_iso(), "i": entry_id})
    return {"entry": _row(db.one("SELECT * FROM farm_entries WHERE id = :i", {"i": entry_id})),
            "changed": True}


@router.get("/summary", summary="Cost by category and by crop cycle",
            description="The dashboard figures. Cost per acre is reported only when the field "
                        "has a declared area; it is never inferred.")
def summary(plot_id: str = Query(...), user: dict[str, Any] = Depends(current_user),
            db: Database = Depends(db_dep)):
    plot = visible_plot(db, user, plot_id)
    rows = [_row(r) for r in db.rows(
        "SELECT * FROM farm_entries WHERE plot_id = :p ORDER BY spent_on DESC", {"p": plot_id})]
    total = _summarise(rows)

    cycles = []
    for cyc in db.rows("SELECT * FROM crop_cycles WHERE plot_id = :p ORDER BY sown_on DESC",
                       {"p": plot_id}):
        part = [r for r in rows if r["crop_cycle_id"] == cyc["id"]]
        s = _summarise(part)
        cycles.append({"cycle_id": cyc["id"], "crop": cyc.get("crop"),
                       "sown_on": str(cyc.get("sown_on"))[:10],
                       "ended_on": str(cyc["ended_on"])[:10] if cyc.get("ended_on") else None,
                       **s})

    area = plot.get("area_acre")
    return {
        "plot_id": plot_id, "area_acre": area,
        "total": total,
        "per_acre_inr": round(total["expense_inr"] / area, 2) if area else None,
        "per_acre_note": (None if area else
                          "This field has no declared area, so cost per acre is not reported."),
        "cycles": cycles,
        "note": ("Bookkeeping only. These figures are not read by the risk engine or the "
                 "spray decision, and no yield or profit is projected from them."),
    }
