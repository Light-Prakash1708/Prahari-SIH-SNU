"""
PRAHARI · deleting your own records, and closing your account

Every other test in this suite asserts that data is KEPT. These assert the
opposite, and the properties worth locking in are the ones that fail silently:

  · a deletion that reports success and leaves rows behind
  · a deletion that reaches across into another farmer's field
  · a "delete" that is really a hidden flag, so the record is still queryable
  · a confirmation that can be tapped through by accident

The last one is the reason the password and the typed word are both required
and are tested separately: a guard that is satisfied by either is one guard.
"""
from __future__ import annotations

PW = "strong-pass-2026"


def _seed(client, headers, plot_id):
    """A field with something in every category the screen offers."""
    client.post("/api/farm-ledger", headers=headers, json={
        "plot_id": plot_id, "category": "fertilizer", "title": "Urea 2 bags",
        "amount_inr": 1420, "spent_on": "2026-08-20"})
    client.post("/api/agronomy/soil/self-test", headers=headers, json={
        "plot_id": plot_id,
        "answers": {"structure": 1, "infiltration": 0, "earthworms": 0,
                    "crust": 1, "colour": 1, "roots": 2}})
    r = client.post("/api/community", headers=headers, json={
        "category": "disease",
        "body": "Dark spots with a yellow halo on the lower leaves, spreading after rain.",
        "symptoms": ["spots", "spreading_fast"], "suspected_problem": "late_blight",
        "plot_id": plot_id})
    assert r.status_code == 201, r.text


def test_the_summary_counts_what_is_actually_there(client, farmer, plot):
    before = client.get("/api/privacy/summary", headers=farmer["headers"]).json()
    assert before["fields"] == 1
    counts = {c["id"]: c["count"] for c in before["categories"]}
    assert counts["ledger"] == 0

    _seed(client, farmer["headers"], plot["id"])
    after = client.get("/api/privacy/summary", headers=farmer["headers"]).json()
    counts = {c["id"]: c["count"] for c in after["categories"]}
    assert counts["ledger"] == 1
    assert counts["soil"] >= 1
    assert counts["community"] >= 1
    # Every category is described in both languages — a deletion screen nobody
    # can read is not consent.
    for c in after["categories"]:
        assert c["label"] and c["label_mr"]
        assert c["note"] and c["note_mr"]


def test_deleting_one_category_leaves_the_others_alone(client, farmer, plot):
    _seed(client, farmer["headers"], plot["id"])
    r = client.post("/api/privacy/records/delete", headers=farmer["headers"], json={
        "categories": ["ledger"], "password": PW, "confirm": "DELETE"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["deleted"]["ledger"] >= 1

    counts = {c["id"]: c["count"] for c in out["remaining"]["categories"]}
    assert counts["ledger"] == 0
    assert counts["soil"] >= 1, "deleting money removed a soil record"
    assert counts["community"] >= 1, "deleting money removed a community post"

    # And the rows are gone from the feature's own endpoint, not merely from
    # the privacy count.
    led = client.get(f"/api/farm-ledger?plot_id={plot['id']}",
                     headers=farmer["headers"]).json()
    assert led["count"] == 0


def test_deletion_is_removal_not_a_hidden_flag(client, farmer, plot):
    """A soft delete would keep the row queryable and is not what was asked
    for. The count is taken from the table itself."""
    from app.db import get_db
    _seed(client, farmer["headers"], plot["id"])
    db = get_db()
    assert db.scalar("SELECT COUNT(*) FROM farm_entries WHERE plot_id = :p",
                     {"p": plot["id"]}) == 1
    client.post("/api/privacy/records/delete", headers=farmer["headers"], json={
        "categories": ["ledger"], "password": PW, "confirm": "DELETE"})
    assert db.scalar("SELECT COUNT(*) FROM farm_entries WHERE plot_id = :p",
                     {"p": plot["id"]}) == 0


def test_a_wrong_password_deletes_nothing(client, farmer, plot):
    _seed(client, farmer["headers"], plot["id"])
    r = client.post("/api/privacy/records/delete", headers=farmer["headers"], json={
        "categories": ["ledger"], "password": "not-my-password", "confirm": "DELETE"})
    assert r.status_code == 403
    led = client.get(f"/api/farm-ledger?plot_id={plot['id']}",
                     headers=farmer["headers"]).json()
    assert led["count"] == 1


def test_the_typed_word_is_a_separate_guard(client, farmer, plot):
    """The password proves who is holding the phone; the typed word proves they
    meant this. A correct password alone must not be enough."""
    _seed(client, farmer["headers"], plot["id"])
    r = client.post("/api/privacy/records/delete", headers=farmer["headers"], json={
        "categories": ["ledger"], "password": PW, "confirm": "yes"})
    assert r.status_code == 400
    assert r.json()["error"] == "confirmation_required"
    led = client.get(f"/api/farm-ledger?plot_id={plot['id']}",
                     headers=farmer["headers"]).json()
    assert led["count"] == 1


def test_deleting_my_account_never_touches_another_farmer(client, farmer, farmer_b, plot):
    """The single most important assertion in this file."""
    from app.db import get_db
    _seed(client, farmer["headers"], plot["id"])
    other = client.post("/api/plots", headers=farmer_b["headers"], json={
        "name": "Onion patch", "crop": "onion", "area_acre": 1.0,
        "sown_on": "2026-06-20", "taluka": "niphad"}).json()
    client.post("/api/farm-ledger", headers=farmer_b["headers"], json={
        "plot_id": other["id"], "category": "seed", "title": "Onion sets",
        "amount_inr": 900, "spent_on": "2026-06-19"})

    r = client.post("/api/privacy/account/delete", headers=farmer["headers"], json={
        "password": PW, "confirm": "DELETE"})
    assert r.status_code == 200, r.text
    assert r.json()["account_deleted"] is True
    assert all(v == 0 for v in r.json()["verified_gone"].values()), r.json()["verified_gone"]

    db = get_db()
    assert db.scalar("SELECT COUNT(*) FROM plots WHERE id = :p", {"p": other["id"]}) == 1
    assert db.scalar("SELECT COUNT(*) FROM farm_entries WHERE plot_id = :p",
                     {"p": other["id"]}) == 1
    # And the other farmer can still use the app.
    still = client.get(f"/api/farm-ledger?plot_id={other['id']}",
                       headers=farmer_b["headers"])
    assert still.status_code == 200
    assert still.json()["count"] == 1


def test_a_deleted_account_cannot_sign_back_in(client, farmer, plot):
    client.post("/api/privacy/account/delete", headers=farmer["headers"], json={
        "password": PW, "confirm": "DELETE"})
    again = client.post("/api/auth/login",
                        json={"identifier": "9812345678", "password": PW})
    assert again.status_code in (401, 403)
    # the live token is dead too — the session rows went with the account
    assert client.get("/api/privacy/summary", headers=farmer["headers"]).status_code == 401


def test_anonymising_keeps_the_post_and_removes_the_name(client, farmer, farmer_b, plot):
    """A post three neighbours acted on is evidence as well as writing. The
    account holder chooses; what must never happen is the name surviving."""
    from app.db import get_db
    _seed(client, farmer["headers"], plot["id"])
    db = get_db()
    post_id = db.scalar("SELECT id FROM community_posts LIMIT 1")
    assert post_id

    r = client.post("/api/privacy/account/delete", headers=farmer["headers"], json={
        "password": PW, "confirm": "DELETE", "community_mode": "anonymise"})
    assert r.status_code == 200, r.text

    row = db.one("SELECT author_display, author_farmer_id FROM community_posts"
                 " WHERE id = :i", {"i": post_id})
    assert row is not None, "the post should have survived anonymisation"
    assert row["author_display"] == "Deleted account"
    assert row["author_farmer_id"] is None
    assert "Rajesh" not in str(row["author_display"])
    # and it is still readable by the neighbour who acted on it
    assert client.get(f"/api/community/{post_id}",
                      headers=farmer_b["headers"]).status_code == 200


def test_deleting_the_posts_removes_them_entirely(client, farmer, plot):
    from app.db import get_db
    _seed(client, farmer["headers"], plot["id"])
    db = get_db()
    post_id = db.scalar("SELECT id FROM community_posts LIMIT 1")

    r = client.post("/api/privacy/account/delete", headers=farmer["headers"], json={
        "password": PW, "confirm": "DELETE", "community_mode": "delete"})
    assert r.status_code == 200, r.text
    assert db.scalar("SELECT COUNT(*) FROM community_posts WHERE id = :i",
                     {"i": post_id}) == 0


def test_the_export_contains_the_records_before_they_are_deleted(client, farmer, plot):
    _seed(client, farmer["headers"], plot["id"])
    out = client.get("/api/privacy/export", headers=farmer["headers"]).json()
    assert out["account"]["full_name"] == "Rajesh Pawar"
    assert len(out["plots"]) == 1
    assert len(out["farm_entries"]) == 1
    assert len(out["community_posts"]) == 1
    # A password hash is a credential, not a record about the farmer.
    assert "password_hash" not in out["account"]


def test_a_staff_account_cannot_delete_itself(client, expert):
    """An expert's verdicts are the basis of other farmers' records. Closing
    that account is an administrative act, not a self-service button."""
    r = client.post("/api/privacy/account/delete", headers=expert["headers"], json={
        "password": PW, "confirm": "DELETE"})
    assert r.status_code == 403


def test_the_audit_trail_survives_the_account(client, farmer, plot):
    """The audit log records what the SYSTEM did. It is detached from the
    deleted person rather than erased, so an operator can still answer a
    question about a decision without holding on to who made it."""
    from app.db import get_db
    db = get_db()
    _seed(client, farmer["headers"], plot["id"])
    before = db.scalar("SELECT COUNT(*) FROM audit_logs")
    client.post("/api/privacy/account/delete", headers=farmer["headers"], json={
        "password": PW, "confirm": "DELETE"})
    after = db.scalar("SELECT COUNT(*) FROM audit_logs")
    assert after >= before
    assert db.scalar("SELECT COUNT(*) FROM audit_logs WHERE user_id = :u",
                     {"u": farmer["user_id"]}) == 0
    assert db.scalar("SELECT COUNT(*) FROM audit_logs WHERE action = 'account.deleted'") == 1
