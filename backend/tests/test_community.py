"""
PRAHARI · the community, and the signal it produces
════════════════════════════════════════════════════════════════════════════
The community is the only part of PRAHARI where one farmer's data is shown to
another, so it is the only part where a privacy failure is possible at all.
These tests are organised around that.

The properties, in the order they matter:

  1  a public post NEVER carries a coordinate, a plot id, a phone number or an
     account id — asserted against the raw JSON of every community response,
     not against a hand-picked list of fields
  2  community advice is never called verified; only an identified expert moves
     the verification, and a farmer cannot do it at any price
  3  a reply that names a pesticide and a dose is flagged, loudly, wherever it
     is read
  4  a cluster needs INDEPENDENT reporters — one farmer posting four times is
     one farmer
  5  a signal is never called an outbreak, at any grade
  6  a farmer sees aggregate counts near their own field and never a list of
     other farmers
  7  an officer sees signals only in their assigned talukas
"""
from __future__ import annotations

import json


# ── helpers ─────────────────────────────────────────────────────────────────
def post_it(client, headers, plot_id=None, **over):
    body = {"category": "disease",
            "body": "Grey wet patches on the lower leaves, spreading after the rain.",
            "symptoms": ["spots", "spreading_fast"],
            "suspected_problem": "late_blight"}
    if plot_id:
        body["plot_id"] = plot_id
    body.update(over)
    return client.post("/api/community", headers=headers, json=body)


def farmer_n(client, n, taluka="niphad", crop="tomato"):
    """A farmer with a field, made through the real registration path."""
    phone = f"98123400{n:02d}"
    r = client.post("/api/auth/register", json={
        "full_name": f"Farmer {n}", "password": "strong-pass-2026", "phone": phone,
        "taluka": taluka, "village": f"Village{n}"})
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    p = client.post("/api/plots", headers=headers, json={
        "name": f"Block {n}", "crop": crop, "area_acre": 1.5, "sown_on": "2026-06-25",
        "lat": 20.08 + n * 0.01, "lng": 74.11 + n * 0.01, "location_source": "gps"})
    assert p.status_code == 201, p.text
    return {"headers": headers, "plot": p.json(), "phone": phone}


# ── 1 · privacy ─────────────────────────────────────────────────────────────
def test_a_public_post_carries_no_coordinate_plot_id_phone_or_account_id(
        client, farmer, farmer_b, plot):
    """The strongest form of this test: take the RAW JSON of every community
    response a second farmer can reach, and assert none of the private strings
    appears anywhere in it. A field-by-field assertion would pass while a new
    column leaked."""
    created = post_it(client, farmer["headers"], plot["id"], share_context=True)
    assert created.status_code == 201, created.text
    pid = created.json()["post"]["id"]

    secrets = [plot["id"], farmer["user_id"], "9812345678",
               str(plot["lat"]), str(plot["lng"])]

    for url in ("/api/community?tab=for_you", f"/api/community/{pid}",
                "/api/community/meta", "/api/community/signals/mine",
                "/api/community/search?q=grey"):
        r = client.get(url, headers=farmer_b["headers"])
        assert r.status_code == 200, f"{url} -> {r.text}"
        blob = json.dumps(r.json())
        for s in secrets:
            assert s not in blob, f"{url} leaked {s!r}"


def test_the_public_projection_is_an_allowlist_not_a_denylist(client, farmer, plot):
    """A column added to community_posts tomorrow must not appear in a response
    just because nobody remembered to remove it."""
    from app.community import PUBLIC_POST_FIELDS
    from app.db import get_db
    created = post_it(client, farmer["headers"], plot["id"])
    pid = created.json()["post"]["id"]
    row = get_db().one("SELECT * FROM community_posts WHERE id = :i", {"i": pid})
    private = set(row) - set(PUBLIC_POST_FIELDS)
    for col in ("plot_id", "observation_id", "diagnosis_id", "author_user_id",
                "author_farmer_id", "client_ref"):
        assert col in private, f"{col} is in the public allowlist"


def test_location_is_never_finer_than_village_and_taluka(client, farmer, plot):
    created = post_it(client, farmer["headers"], plot["id"])
    p = created.json()["post"]
    assert p["taluka"]
    assert "lat" not in p and "lng" not in p
    assert p["place"]


def test_use_my_field_attaches_a_summary_not_the_field(client, farmer, plot):
    created = post_it(client, farmer["headers"], plot["id"], share_context=True)
    ctx = created.json()["post"]["context"]
    assert ctx["crop"] == "tomato"
    assert ctx["crop_stage"]
    for banned in ("lat", "lng", "area_acre", "plot_id", "farmer_id", "phone"):
        assert banned not in ctx, f"context leaked {banned}"


def test_a_farmer_cannot_attach_another_farmers_scan(client, farmer, farmer_b, plot):
    from conftest import scan

    from app.db import get_db
    scan(client, farmer["headers"], plot["id"], "blight")
    dx = get_db().one("SELECT id FROM diagnoses WHERE plot_id = :p", {"p": plot["id"]})
    b_plot = client.post("/api/plots", headers=farmer_b["headers"], json={
        "name": "Theirs", "crop": "tomato", "area_acre": 1, "sown_on": "2026-06-25",
        "lat": 20.09, "lng": 74.12, "location_source": "gps"}).json()
    r = post_it(client, farmer_b["headers"], b_plot["id"], diagnosis_id=dx["id"],
                share_context=True)
    assert r.status_code == 403


# ── 2 · verification ────────────────────────────────────────────────────────
def test_a_post_starts_unverified_and_says_so_in_words(client, farmer, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    assert p["verification"] == "UNVERIFIED"
    assert "not verified" in p["verification_meta"]["label"].lower()
    assert p["notice"]


def test_agreement_from_other_farmers_never_verifies_anything(client, farmer, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    for n in range(1, 6):
        f = farmer_n(client, n)
        client.post(f"/api/community/{p['id']}/reactions", headers=f["headers"],
                    json={"kind": "same_problem"})
        client.post(f"/api/community/{p['id']}/comments", headers=f["headers"],
                    json={"body": "Yes I have exactly this, it is definitely late blight."})
    fresh = client.get(f"/api/community/{p['id']}", headers=farmer["headers"]).json()
    assert fresh["post"]["verification"] == "UNVERIFIED"
    assert fresh["post"]["same_problem_count"] >= 5


def test_a_farmer_cannot_write_an_expert_response(client, farmer, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    r = client.post(f"/api/community/{p['id']}/expert-response", headers=farmer["headers"],
                    json={"status": "CONFIRMED", "verdict_problem": "late_blight",
                          "body": "I am certain this is late blight, trust me."})
    assert r.status_code == 403


def test_an_expert_response_moves_verification_and_names_the_expert(
        client, farmer, expert, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    r = client.post(f"/api/community/{p['id']}/expert-response", headers=expert["headers"],
                    json={"status": "CONFIRMED", "verdict_problem": "late_blight",
                          "confidence": "high",
                          "body": "Confirmed late blight — the white fringe on the underside is "
                                  "the giveaway. Remove affected leaves first."})
    assert r.status_code == 201, r.text
    assert r.json()["verification"] == "CONFIRMED"
    detail = client.get(f"/api/community/{p['id']}", headers=farmer["headers"]).json()
    assert detail["expert_responses"][0]["expert_name"]
    assert detail["post"]["confirmed_problem"] == "late_blight"


def test_confirming_or_correcting_requires_naming_the_problem(client, farmer, expert, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    r = client.post(f"/api/community/{p['id']}/expert-response", headers=expert["headers"],
                    json={"status": "CONFIRMED",
                          "body": "Yes this looks about right to me, go ahead."})
    assert r.status_code == 400
    assert r.json()["error"] == "verdict_required"


def test_an_expert_cannot_assert_unverified(client, farmer, expert, plot):
    """UNVERIFIED is where a post STARTS. It is not a verdict an expert issues,
    and accepting it would let a review look like a downgrade."""
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    r = client.post(f"/api/community/{p['id']}/expert-response", headers=expert["headers"],
                    json={"status": "UNVERIFIED", "body": "I have not looked at this properly."})
    assert r.status_code == 422


def test_an_expert_confirmation_moves_the_taluka_prior(client, farmer, expert, plot):
    from app.db import get_db
    before = get_db().one(
        "SELECT alpha FROM priors WHERE taluka='niphad' AND crop='tomato'"
        " AND problem='late_blight'")
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    client.post(f"/api/community/{p['id']}/expert-response", headers=expert["headers"],
                json={"status": "CONFIRMED", "verdict_problem": "late_blight",
                      "body": "Confirmed late blight from the photograph and the weather."})
    after = get_db().one(
        "SELECT alpha FROM priors WHERE taluka='niphad' AND crop='tomato'"
        " AND problem='late_blight'")
    assert after is not None
    assert after["alpha"] > (before or {}).get("alpha", 1.0)


# ── 3 · unverified prescriptions ────────────────────────────────────────────
def test_a_reply_naming_a_product_and_a_dose_is_flagged(client, farmer, farmer_b, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    r = client.post(f"/api/community/{p['id']}/comments", headers=farmer_b["headers"],
                    json={"body": "Just put Mancozeb 45 gram per pump, it worked for me."})
    assert r.status_code == 201, r.text
    assert r.json()["advice_flagged"] is True
    warn = r.json()["comment"]["advice_warning"]
    assert warn and "not been checked" in warn["text"].lower()


def test_an_ordinary_reply_is_not_flagged(client, farmer, farmer_b, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    r = client.post(f"/api/community/{p['id']}/comments", headers=farmer_b["headers"],
                    json={"body": "Removing the affected leaves early helped us last year."})
    assert r.json()["advice_flagged"] is False
    assert r.json()["comment"]["advice_warning"] is None


def test_an_expert_reply_is_not_shown_with_the_amateur_warning(client, farmer, expert, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    client.post(f"/api/community/{p['id']}/expert-response", headers=expert["headers"],
                json={"status": "EXPERT_REVIEWED",
                      "body": "If you do spray, check the label rate — around 2 g per litre is "
                              "the usual range for a protectant. Open the recommendation screen."})
    detail = client.get(f"/api/community/{p['id']}", headers=farmer["headers"]).json()
    expert_comments = [c for c in detail["comments"] if c["is_expert"]]
    assert expert_comments
    assert all(c["advice_warning"] is None for c in expert_comments)


# ── 4 and 5 · the signal ────────────────────────────────────────────────────
def test_one_farmer_posting_repeatedly_is_not_a_cluster(client, farmer, plot):
    from app.runtime import get_runtime
    for i in range(5):
        post_it(client, farmer["headers"], plot["id"],
                body=f"Grey patches spreading on the lower leaves, week {i}, still worse.")
    a = get_runtime().signals.assess("niphad", "late_blight", crop="tomato", persist=False)
    assert a["counts"]["distinct_farmers"] == 1
    assert a["grade"] is None, "five posts from one account became a cluster"


def test_three_independent_farmers_make_a_possible_cluster(client):
    from app.runtime import get_runtime
    for n in range(1, 4):
        f = farmer_n(client, n)
        post_it(client, f["headers"], f["plot"]["id"])
    a = get_runtime().signals.assess("niphad", "late_blight", crop="tomato", persist=False)
    assert a["counts"]["distinct_farmers"] == 3
    assert a["grade"] == "possible_cluster"
    assert "not an outbreak" in a["what_this_is_not"].lower()


def test_no_grade_anywhere_uses_the_word_outbreak():
    from app.signals import GRADES
    for key, meta in GRADES.items():
        assert "outbreak" not in key
        assert "outbreak" not in meta["label"].lower()


def test_a_diagnosis_promotes_a_cluster_to_corroborated(client):
    from conftest import scan

    from app.runtime import get_runtime
    for n in range(1, 4):
        f = farmer_n(client, n)
        post_it(client, f["headers"], f["plot"]["id"])
        if n == 1:
            scan(client, f["headers"], f["plot"]["id"], "blight")
    a = get_runtime().signals.assess("niphad", "late_blight", crop="tomato", persist=False)
    # the scan may or may not land on late blight — assert the RULE, not the roll
    if a["counts"]["diagnoses"]:
        assert a["grade"] == "corroborated_signal"
    else:
        assert a["grade"] == "possible_cluster"


def test_only_an_officer_can_confirm_a_signal_and_only_in_scope(client, officer):
    from app.runtime import get_runtime
    for n in range(1, 4):
        f = farmer_n(client, n)
        post_it(client, f["headers"], f["plot"]["id"])
    get_runtime().signals.sweep()
    sigs = client.get("/api/community/signals", headers=officer["headers"]).json()["signals"]
    assert sigs, "the officer sees no signal in an assigned taluka"
    sid = sigs[0]["id"]

    f = farmer_n(client, 9)
    denied = client.post(f"/api/community/signals/{sid}/confirm", headers=f["headers"],
                         json={"confirmed": True, "note": "I say it is real."})
    assert denied.status_code == 403

    ok = client.post(f"/api/community/signals/{sid}/confirm", headers=officer["headers"],
                     json={"confirmed": True,
                           "note": "Visited two fields, late blight present on lower leaves."})
    assert ok.status_code == 200, ok.text
    assert ok.json()["grade"] == "confirmed_field_signal"


def test_an_officer_sees_no_signal_outside_their_talukas(client, officer):
    from app.runtime import get_runtime
    for n in range(1, 4):
        f = farmer_n(client, n, taluka="chandvad")
        post_it(client, f["headers"], f["plot"]["id"])
    get_runtime().signals.sweep()
    sigs = client.get("/api/community/signals", headers=officer["headers"]).json()["signals"]
    assert all(s["taluka"] != "chandvad" for s in sigs)


def test_the_alert_to_nearby_farmers_names_nobody(client, officer):
    from app.db import get_db
    from app.runtime import get_runtime
    names = []
    for n in range(1, 4):
        f = farmer_n(client, n)
        names.append(f"Farmer {n}")
        post_it(client, f["headers"], f["plot"]["id"])
    get_runtime().signals.sweep()
    sigs = client.get("/api/community/signals", headers=officer["headers"]).json()["signals"]
    sid = sigs[0]["id"]
    client.post(f"/api/community/signals/{sid}/confirm", headers=officer["headers"],
                json={"confirmed": True, "note": "Confirmed on the ground."})
    notes = get_db().rows(
        "SELECT title, body FROM notifications WHERE kind = 'community_signal'")
    assert notes, "no farmer was told"
    blob = json.dumps(notes)
    for name in names:
        assert name not in blob, f"the alert named {name}"
    for village in ("Village1", "Village2", "Village3"):
        assert village not in blob


# ── 6 · what a farmer sees ──────────────────────────────────────────────────
def test_a_farmer_gets_counts_not_a_list_of_other_farmers(client, farmer, plot):
    from app.runtime import get_runtime
    for n in range(1, 4):
        f = farmer_n(client, n)
        post_it(client, f["headers"], f["plot"]["id"])
    get_runtime().signals.sweep()
    mine = client.get("/api/community/signals/mine", headers=farmer["headers"]).json()
    assert mine["signals"]
    s = mine["signals"][0]
    assert isinstance(s["distinct_authors"], int)
    assert "posts" not in s and "farmers" not in s
    assert "aggregate" in mine["privacy"].lower() or "never" in mine["privacy"].lower()


def test_the_feed_is_ranked_by_relevance_and_says_why(client, farmer, plot):
    post_it(client, farmer["headers"], plot["id"])
    f = farmer_n(client, 4, taluka="chandvad", crop="cotton")
    post_it(client, f["headers"], f["plot"]["id"], category="pest",
            suspected_problem="pink_bollworm",
            body="Rosetted flowers and pinhole entries on the bolls this week.")
    feed = client.get("/api/community?tab=for_you", headers=farmer["headers"]).json()
    assert feed["posts"]
    top = feed["posts"][0]
    assert top["shown_because"], "the feed does not explain its own order"
    assert "popularity is not a ranking input" in feed["ranking"].lower()


def test_saathi_answers_are_others_seeing_this_from_counts_only(client, farmer, plot):
    for n in range(1, 4):
        f = farmer_n(client, n)
        post_it(client, f["headers"], f["plot"]["id"])
    r = client.post("/api/saathi/ask", headers=farmer["headers"], json={
        "question": "Are other farmers nearby seeing this?", "plot_id": plot["id"],
        "lang": "en"})
    assert r.status_code == 200
    d = r.json()
    assert d["grounded"] is True
    assert d["intent"] == "nearby_community"
    blob = json.dumps(d)
    assert "outbreak" not in blob.lower() or "not an outbreak" in blob.lower()
    for n in range(1, 4):
        assert f"Farmer {n}" not in blob
        assert f"Village{n}" not in blob


# ── 7 · moderation ──────────────────────────────────────────────────────────
def test_one_report_does_not_remove_a_post(client, farmer, farmer_b, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    r = client.post(f"/api/community/{p['id']}/report", headers=farmer_b["headers"],
                    json={"reason": "misinformation"})
    assert r.status_code == 200
    assert r.json()["action"] == "none"
    still = client.get(f"/api/community/{p['id']}", headers=farmer_b["headers"])
    assert still.status_code == 200


def test_repeated_independent_reports_flag_a_post(client, farmer, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    last = None
    for n in range(1, 4):
        f = farmer_n(client, n)
        last = client.post(f"/api/community/{p['id']}/report", headers=f["headers"],
                           json={"reason": "spam"})
    assert last.json()["action"] == "flagged"


def test_a_farmer_cannot_report_the_same_thing_twice(client, farmer, farmer_b, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    client.post(f"/api/community/{p['id']}/report", headers=farmer_b["headers"],
                json={"reason": "spam"})
    again = client.post(f"/api/community/{p['id']}/report", headers=farmer_b["headers"],
                        json={"reason": "spam"})
    assert again.status_code == 409


def test_a_post_that_is_too_short_is_refused(client, farmer, plot):
    r = client.post("/api/community", headers=farmer["headers"], json={
        "category": "disease", "body": "help", "plot_id": plot["id"]})
    assert r.status_code == 422


def test_a_client_ref_makes_posting_idempotent(client, farmer, plot):
    a = post_it(client, farmer["headers"], plot["id"], client_ref="q-abc-123456")
    b = post_it(client, farmer["headers"], plot["id"], client_ref="q-abc-123456")
    assert a.json()["post"]["id"] == b.json()["post"]["id"]
    assert b.json()["duplicate"] is True


def test_a_farmer_cannot_mark_their_own_post_as_me_too(client, farmer, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    r = client.post(f"/api/community/{p['id']}/reactions", headers=farmer["headers"],
                    json={"kind": "same_problem"})
    assert r.status_code == 400


def test_withdrawing_a_post_hides_the_text_but_keeps_the_count(client, farmer, plot):
    from app.db import get_db
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    r = client.delete(f"/api/community/{p['id']}", headers=farmer["headers"])
    assert r.status_code == 200
    row = get_db().one("SELECT status FROM community_posts WHERE id = :i", {"i": p["id"]})
    assert row["status"] == "removed"
    assert "not retracted" in r.json()["note"].lower()


def test_a_farmer_cannot_withdraw_someone_elses_post(client, farmer, farmer_b, plot):
    p = post_it(client, farmer["headers"], plot["id"]).json()["post"]
    r = client.delete(f"/api/community/{p['id']}", headers=farmer_b["headers"])
    assert r.status_code == 403


def test_signing_in_is_required_to_see_anything(client):
    assert client.get("/api/community").status_code == 401
    assert client.get("/api/community/meta").status_code == 401
