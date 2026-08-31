"""
PRAHARI · what we hold about a farmer, and how they get rid of it.

Every other module in this system is written to KEEP records: a diagnosis is
evidence, a trap count is the basis of a spray decision, a follow-up is the
only proof a treatment worked. That is correct, and it is also exactly why this
module has to exist. An account holder who cannot leave is not a user of a
service, and a farmer being asked to photograph their own field is entitled to
know what that produces and to end it.

Three operations, in increasing order of finality:

    summary()   what is held, counted by category, in the farmer's words
    export()    all of it, as JSON, before deciding anything
    delete()    a category, or the account

Two decisions in here are worth arguing with rather than inheriting:

**Community contributions are the farmer's choice, not ours.** A post that
three neighbours corroborated is simultaneously the farmer's writing and the
evidence behind a regional signal an officer may have acted on. Deleting it
silently weakens a public-health record; keeping it silently overrides someone
who asked to be forgotten. So the account holder is asked which, told the
consequence of each in plain language, and neither is the quiet default.

**The regional signal itself is not deleted, and we say so.** Rows in
`community_cluster_signals` hold counts, talukas and problem names — no
identity, no field, no name — and they are what an officer's outbreak response
was based on. Removing a person from the count retrospectively would rewrite a
public record of what was known at the time. Nothing in those rows can be
traced back to the person, and the screen states this rather than hiding it.

Deletion here is real. Rows are removed, not flagged, and the stored images go
with them. `verify()` re-counts afterwards and the endpoint returns the result,
because "we deleted your data" is a claim that should be checkable by the
person who asked for it.
"""
from __future__ import annotations

from typing import Any

from .clock import now_iso
from .db import Database
from .storage import Storage

# ── the categories a farmer can see and remove separately ──────────────────
#
# Each entry names the tables it covers. The order is the order they are
# deleted in: children before parents, so nothing is ever orphaned mid-way.
# `label`/`label_mr` are what the farmer reads; the table names never surface.
CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "scans",
        "label": "Photographs and diagnoses",
        "label_mr": "फोटो आणि निदान",
        "note": ("Every leaf photograph you took, what the system concluded from it, "
                 "and the follow-up re-scans."),
        "note_mr": "तुम्ही काढलेले प्रत्येक पानाचे फोटो, त्यावरील निदान आणि पुन्हा तपासणी.",
    },
    {
        "id": "traps",
        "label": "Trap counts and spray decisions",
        "label_mr": "सापळ्यांची मोजणी आणि फवारणी निर्णय",
        "note": ("Pheromone and sticky trap counts, the threshold checks they fed, "
                 "and the spray decisions and applications recorded against them."),
        "note_mr": "सापळ्यांची मोजणी, त्यावरील उंबरठा तपासणी आणि नोंदवलेली फवारणी.",
    },
    {
        "id": "soil",
        "label": "Soil, water and weed records",
        "label_mr": "माती, पाणी आणि तण नोंदी",
        "note": "Soil self-tests and lab reports, irrigation events, weed checks.",
        "note_mr": "मातीची स्वयं-तपासणी व प्रयोगशाळा अहवाल, पाणी व तण नोंदी.",
    },
    {
        "id": "ledger",
        "label": "Farm expenses and income",
        "label_mr": "शेतीचा खर्च आणि उत्पन्न",
        "note": "The money you recorded. Nothing here was ever used to advise you.",
        "note_mr": "तुम्ही नोंदवलेला पैसा. याचा वापर कधीही सल्ल्यासाठी झालेला नाही.",
    },
    {
        "id": "community",
        "label": "Community posts and comments",
        "label_mr": "समुदायातील पोस्ट आणि प्रतिक्रिया",
        "note": ("What you posted, your comments, and your reactions on other "
                 "farmers' posts."),
        "note_mr": "तुमच्या पोस्ट, प्रतिक्रिया आणि इतरांच्या पोस्टवरील तुमचे प्रतिसाद.",
    },
    {
        "id": "notifications",
        "label": "Alerts sent to you",
        "label_mr": "तुम्हाला पाठवलेले इशारे",
        "note": "The alert history, and the record of how each was delivered.",
        "note_mr": "इशाऱ्यांचा इतिहास आणि ते कसे पोहोचले याची नोंद.",
    },
]
CATEGORY_IDS = {c["id"] for c in CATEGORIES}


# ── counting ───────────────────────────────────────────────────────────────
def _plot_ids(db: Database, farmer_id: str) -> list[str]:
    return [r["id"] for r in db.rows(
        "SELECT id FROM plots WHERE farmer_id = :f", {"f": farmer_id})]


def _count(db: Database, sql: str, params: dict[str, Any]) -> int:
    return int(db.scalar(sql, params) or 0)


def _in_clause(ids: list[str], prefix: str) -> tuple[str, dict[str, Any]]:
    """A named-parameter IN list.

    `db._check` rejects '?' placeholders because they are SQLite-only, so the
    list has to be expanded into :p0, :p1 … by hand. An empty list yields a
    predicate that is false rather than invalid SQL.
    """
    if not ids:
        return "(NULL)", {}
    keys = [f"{prefix}{i}" for i in range(len(ids))]
    return "(" + ", ".join(f":{k}" for k in keys) + ")", dict(zip(keys, ids, strict=True))


def summary(db: Database, user: dict[str, Any], farmer: dict[str, Any] | None) -> dict[str, Any]:
    """What PRAHARI holds, counted, in the categories a farmer can act on."""
    uid = user["id"]
    plots = _plot_ids(db, farmer["id"]) if farmer else []
    pin, pp = _in_clause(plots, "p")

    def per_plot(table: str) -> int:
        if not plots:
            return 0
        return _count(db, f"SELECT COUNT(*) FROM {table} WHERE plot_id IN {pin}", pp)

    counts = {
        "scans": (per_plot("observations") + per_plot("diagnoses") + per_plot("followups")),
        "traps": (per_plot("traps") + per_plot("threshold_checks")
                  + per_plot("decisions") + per_plot("applications")),
        "soil": (per_plot("soil_tests") + per_plot("irrigation_events") + per_plot("weed_checks")),
        "ledger": per_plot("farm_entries"),
        "community": (
            _count(db, "SELECT COUNT(*) FROM community_posts WHERE author_user_id = :u", {"u": uid})
            + _count(db, "SELECT COUNT(*) FROM community_comments WHERE author_user_id = :u", {"u": uid})
            + _count(db, "SELECT COUNT(*) FROM community_reactions WHERE user_id = :u", {"u": uid})
        ),
        "notifications": _count(
            db, "SELECT COUNT(*) FROM notifications WHERE user_id = :u", {"u": uid}),
    }

    images = 0
    if plots:
        images = _count(db, f"""
            SELECT COUNT(*) FROM observation_images
             WHERE observation_id IN (SELECT id FROM observations WHERE plot_id IN {pin})
        """, pp)

    return {
        "account": {
            "name": user.get("full_name"),
            "role": user.get("role"),
            "created_at": user.get("created_at"),
            # The phone number is the sign-in identifier, so it is shown to
            # confirm WHICH account this is — never anyone else's.
            "phone": user.get("phone"),
            "email": user.get("email"),
        },
        "fields": len(plots),
        "images": images,
        "categories": [{**c, "count": counts.get(c["id"], 0)} for c in CATEGORIES],
        "total": sum(counts.values()),
        "retained_note": (
            "Regional signals your reports contributed to are stored as counts by "
            "taluka and problem — no name, no field, no location of yours. Those "
            "counts are what an officer's outbreak response was based on and are "
            "not reversed, because they are a record of what was known at the time. "
            "Nothing in them can be traced back to you."),
        "retained_note_mr": (
            "तुमच्या नोंदींतून तयार झालेले प्रादेशिक संकेत फक्त तालुका व रोगाच्या "
            "संख्येच्या स्वरूपात राहतात — नाव, शेत किंवा ठिकाण नाही. त्यावरून तुमची "
            "ओळख पटत नाही."),
    }


# ── export ─────────────────────────────────────────────────────────────────
_EXPORT_PER_PLOT = [
    "crop_cycles", "observations", "diagnoses", "followups", "health_snapshots",
    "traps", "trap_observations", "threshold_checks", "decisions", "applications",
    "soil_tests", "irrigation_events", "weed_checks", "farm_entries", "field_events",
]


def export(db: Database, user: dict[str, Any], farmer: dict[str, Any] | None) -> dict[str, Any]:
    """Everything held about this account, as plain JSON.

    Offered BEFORE deletion rather than after, because a farmer deciding whether
    to delete a season of records should be able to look at them first.
    """
    uid = user["id"]
    plots = _plot_ids(db, farmer["id"]) if farmer else []
    pin, pp = _in_clause(plots, "p")

    out: dict[str, Any] = {
        "exported_at": now_iso(),
        "account": {k: user.get(k) for k in
                    ("id", "full_name", "phone", "email", "role", "lang", "created_at")},
        "farmer": dict(farmer) if farmer else None,
        "plots": db.rows("SELECT * FROM plots WHERE farmer_id = :f",
                         {"f": farmer["id"]}) if farmer else [],
    }
    for t in _EXPORT_PER_PLOT:
        out[t] = db.rows(f"SELECT * FROM {t} WHERE plot_id IN {pin}", pp) if plots else []
    out["community_posts"] = db.rows(
        "SELECT * FROM community_posts WHERE author_user_id = :u", {"u": uid})
    out["community_comments"] = db.rows(
        "SELECT * FROM community_comments WHERE author_user_id = :u", {"u": uid})
    out["notifications"] = db.rows(
        "SELECT * FROM notifications WHERE user_id = :u", {"u": uid})
    return out


# ── deletion ───────────────────────────────────────────────────────────────
def _image_keys(db: Database, plots: list[str], uid: str,
                scopes: set[str]) -> list[str]:
    """Storage keys to remove alongside the rows that reference them.

    Collected BEFORE the rows go, because after the delete there is nothing
    left to find them by and the bytes would sit on disk forever.
    """
    keys: list[str] = []
    pin, pp = _in_clause(plots, "p")
    if "scans" in scopes and plots:
        for r in db.rows(f"""
            SELECT storage_key, thumb_key FROM observation_images
             WHERE observation_id IN (SELECT id FROM observations WHERE plot_id IN {pin})
        """, pp):
            keys += [k for k in (r.get("storage_key"), r.get("thumb_key")) if k]
    if "community" in scopes:
        for r in db.rows("""
            SELECT storage_key FROM community_post_images
             WHERE post_id IN (SELECT id FROM community_posts WHERE author_user_id = :u)
        """, {"u": uid}):
            if r.get("storage_key"):
                keys.append(r["storage_key"])
    return keys


# The account a kept-but-anonymised post is re-parented to.
#
# `community_posts.author_user_id` is NOT NULL and cascades from `users`, so a
# post cannot simply be detached when its author leaves — deleting the user row
# would take the post with it, whatever the farmer chose. Re-pointing at one
# shared tombstone keeps the writing, satisfies the constraint, and leaves
# nothing to trace: the row carries no phone, no email and no farmer profile,
# and every departed author shares it, so two anonymised posts cannot be linked
# to each other either.
TOMBSTONE_ID = "U-DELETED-ACCOUNT"
TOMBSTONE_NAME = "Deleted account"


def _tombstone(db: Database) -> str:
    if not db.one("SELECT id FROM users WHERE id = :i", {"i": TOMBSTONE_ID}):
        stamp = now_iso()
        db.execute(
            "INSERT INTO users (id, email, phone, password_hash, role, full_name,"
            " lang, is_active, email_verified, created_at, updated_at)"
            " VALUES (:i, NULL, NULL, :h, 'farmer', :n, 'en', 0, 0, :now, :now)",
            # Not a hash of anything: scrypt output has a known shape and this
            # deliberately is not one, so no password can ever verify against it.
            {"i": TOMBSTONE_ID, "h": "!deleted-account-no-login", "n": TOMBSTONE_NAME,
             "now": stamp})
    return TOMBSTONE_ID


def _delete_scope(db: Database, scope: str, plots: list[str], uid: str,
                  community_mode: str) -> int:
    """Remove one category. Returns the number of rows removed.

    Children first in every case. The database's own ON DELETE CASCADE would
    handle most of this, but it is spelled out because SQLite enforces cascades
    only with a pragma set and because a reader of this file should be able to
    see exactly what leaves — a deletion path that relies on something
    invisible is one nobody can audit.
    """
    pin, pp = _in_clause(plots, "p")
    n = 0

    def run(sql: str, params: dict[str, Any] | None = None) -> None:
        nonlocal n
        n += db.execute(sql, params or {})

    if scope == "scans" and plots:
        run(f"""DELETE FROM observation_images WHERE observation_id IN
                (SELECT id FROM observations WHERE plot_id IN {pin})""", pp)
        run(f"""DELETE FROM diagnosis_candidates WHERE diagnosis_id IN
                (SELECT id FROM diagnoses WHERE plot_id IN {pin})""", pp)
        run(f"""DELETE FROM diagnosis_context WHERE diagnosis_id IN
                (SELECT id FROM diagnoses WHERE plot_id IN {pin})""", pp)
        run(f"DELETE FROM followups WHERE plot_id IN {pin}", pp)
        run(f"DELETE FROM expert_cases WHERE plot_id IN {pin}", pp)
        run(f"DELETE FROM diagnoses WHERE plot_id IN {pin}", pp)
        run(f"DELETE FROM observations WHERE plot_id IN {pin}", pp)
        run(f"DELETE FROM health_snapshots WHERE plot_id IN {pin}", pp)

    elif scope == "traps" and plots:
        run(f"""DELETE FROM trap_observations WHERE trap_id IN
                (SELECT id FROM traps WHERE plot_id IN {pin})""", pp)
        run(f"DELETE FROM traps WHERE plot_id IN {pin}", pp)
        run(f"DELETE FROM threshold_checks WHERE plot_id IN {pin}", pp)
        run(f"DELETE FROM applications WHERE plot_id IN {pin}", pp)
        run(f"DELETE FROM decisions WHERE plot_id IN {pin}", pp)

    elif scope == "soil" and plots:
        run(f"DELETE FROM soil_tests WHERE plot_id IN {pin}", pp)
        run(f"DELETE FROM irrigation_events WHERE plot_id IN {pin}", pp)
        run(f"DELETE FROM weed_checks WHERE plot_id IN {pin}", pp)

    elif scope == "ledger" and plots:
        run(f"DELETE FROM farm_entries WHERE plot_id IN {pin}", pp)

    elif scope == "community":
        run("DELETE FROM community_reactions WHERE user_id = :u", {"u": uid})
        run("DELETE FROM community_topic_follows WHERE user_id = :u", {"u": uid})
        if community_mode == "anonymise":
            # The writing stays and stops being attributable. The display name
            # is the only identity a reader ever sees — the phone number was
            # never in the row — so replacing it, dropping the farmer link and
            # re-parenting to the shared tombstone is the whole of it.
            tomb = _tombstone(db)
            run("""UPDATE community_posts
                      SET author_display = :n, author_farmer_id = NULL,
                          author_user_id = :t
                    WHERE author_user_id = :u""",
                {"u": uid, "t": tomb, "n": TOMBSTONE_NAME})
            run("""UPDATE community_comments SET author_display = :n, author_user_id = :t
                    WHERE author_user_id = :u""",
                {"u": uid, "t": tomb, "n": TOMBSTONE_NAME})
            # An expert's verdict ON one of those posts is the expert's record,
            # not the farmer's, and stays where it is.
        else:
            run("""DELETE FROM community_post_images WHERE post_id IN
                   (SELECT id FROM community_posts WHERE author_user_id = :u)""", {"u": uid})
            run("""DELETE FROM community_expert_responses WHERE post_id IN
                   (SELECT id FROM community_posts WHERE author_user_id = :u)""", {"u": uid})
            run("""DELETE FROM community_comments WHERE post_id IN
                   (SELECT id FROM community_posts WHERE author_user_id = :u)""", {"u": uid})
            run("DELETE FROM community_comments WHERE author_user_id = :u", {"u": uid})
            run("""DELETE FROM community_reports WHERE post_id IN
                   (SELECT id FROM community_posts WHERE author_user_id = :u)""", {"u": uid})
            run("DELETE FROM community_reports WHERE reporter_user_id = :u", {"u": uid})
            run("DELETE FROM community_posts WHERE author_user_id = :u", {"u": uid})

    elif scope == "notifications":
        run("""DELETE FROM notification_deliveries WHERE notification_id IN
               (SELECT id FROM notifications WHERE user_id = :u)""", {"u": uid})
        run("DELETE FROM notifications WHERE user_id = :u", {"u": uid})

    return n


def delete_records(db: Database, storage: Storage, user: dict[str, Any],
                   farmer: dict[str, Any] | None, scopes: list[str],
                   community_mode: str = "delete") -> dict[str, Any]:
    """Delete the named categories. Returns what went, and what remains."""
    uid = user["id"]
    plots = _plot_ids(db, farmer["id"]) if farmer else []
    wanted = [s for s in scopes if s in CATEGORY_IDS]

    keys = _image_keys(db, plots, uid, set(wanted))
    removed = {s: _delete_scope(db, s, plots, uid, community_mode) for s in wanted}

    # Files last: a row without its image is a broken record, a file without
    # its row is only wasted disk. If storage is unreachable the rows are
    # already gone and the orphaned bytes are reported rather than swallowed.
    files, failed = 0, 0
    for k in keys:
        try:
            storage.delete(k)
            files += 1
        except Exception:
            failed += 1

    return {
        "deleted": removed,
        "rows": sum(removed.values()),
        "images_removed": files,
        "images_unreachable": failed,
        "remaining": summary(db, user, farmer),
        "at": now_iso(),
    }


def delete_account(db: Database, storage: Storage, user: dict[str, Any],
                   farmer: dict[str, Any] | None,
                   community_mode: str = "delete") -> dict[str, Any]:
    """Close the account and remove everything behind it.

    The audit row written at the end deliberately carries no user id — the
    point of the operation is that the id stops existing. It records that a
    deletion happened, when, and how many rows went, which is what an operator
    needs to answer "did the system honour it" without keeping the person.
    """
    uid = user["id"]
    result = delete_records(
        db, storage, user, farmer, list(CATEGORY_IDS), community_mode)

    extra = 0
    if farmer:
        plots = _plot_ids(db, farmer["id"])
        pin, pp = _in_clause(plots, "p")
        if plots:
            extra += db.execute(f"DELETE FROM field_events WHERE plot_id IN {pin}", pp)
            extra += db.execute(f"DELETE FROM risk_forecasts WHERE plot_id IN {pin}", pp)
            extra += db.execute(f"DELETE FROM crop_cycles WHERE plot_id IN {pin}", pp)
        extra += db.execute("DELETE FROM plots WHERE farmer_id = :f", {"f": farmer["id"]})
        extra += db.execute("DELETE FROM farmers WHERE id = :f", {"f": farmer["id"]})

    extra += db.execute("DELETE FROM community_blocks WHERE user_id = :u", {"u": uid})
    # The stored language-model key is a credential the farmer entrusted to us,
    # so it goes first among the account rows rather than relying on a cascade.
    extra += db.execute("DELETE FROM llm_keys WHERE user_id = :u", {"u": uid})
    extra += db.execute("DELETE FROM password_resets WHERE user_id = :u", {"u": uid})
    extra += db.execute("DELETE FROM sessions WHERE user_id = :u", {"u": uid})
    # Past audit rows are detached rather than removed: they record what the
    # SYSTEM did, they are how an operator answers a later question about a
    # decision, and they hold no name once the id is cleared.
    db.execute("UPDATE audit_logs SET user_id = NULL WHERE user_id = :u", {"u": uid})
    extra += db.execute("DELETE FROM users WHERE id = :u", {"u": uid})

    db.execute("""INSERT INTO audit_logs (at, action, entity, detail)
                  VALUES (:at, 'account.deleted', 'user', :d)""",
               {"at": now_iso(), "d": f'{{"rows": {result["rows"] + extra}}}'})

    return {
        **result,
        "rows": result["rows"] + extra,
        "account_deleted": True,
        "remaining": None,
    }


def verify_gone(db: Database, uid: str, farmer_id: str | None) -> dict[str, int]:
    """Re-count after a deletion, so the answer is measured rather than asserted."""
    return {
        "users": _count(db, "SELECT COUNT(*) FROM users WHERE id = :u", {"u": uid}),
        "farmers": _count(db, "SELECT COUNT(*) FROM farmers WHERE id = :f",
                          {"f": farmer_id or ""}),
        "plots": _count(db, "SELECT COUNT(*) FROM plots WHERE farmer_id = :f",
                        {"f": farmer_id or ""}),
        "sessions": _count(db, "SELECT COUNT(*) FROM sessions WHERE user_id = :u", {"u": uid}),
    }
