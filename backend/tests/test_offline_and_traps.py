"""The offline queue, trap monitoring and notification delivery honesty."""
from __future__ import annotations

import pytest

from conftest import leaf_image, scan


def test_an_offline_capture_syncs_and_does_not_duplicate(client, farmer, plot, monsoon):
    item = {"client_ref": "queue-0001", "kind": "threshold", "plot_id": plot["id"],
            "payload": {"pest": "helicoverpa", "count": 2.0},
            "captured_at": "2026-08-26T07:30:00"}
    first = client.post("/api/sync", headers=farmer["headers"], json={"items": [item]}).json()
    assert first["results"][0]["state"] == "accepted"
    assert first["results"][0]["check_id"]

    # The phone re-sends because the acknowledgement was lost on a bad line.
    again = client.post("/api/sync", headers=farmer["headers"], json={"items": [item]}).json()
    assert again["results"][0]["state"] == "duplicate"

    from app.db import get_db
    n = get_db().scalar("SELECT COUNT(*) FROM threshold_checks WHERE plot_id = :p",
                        {"p": plot["id"]})
    assert n == 1, "a re-sent offline item must not create a second threshold check"


def test_sync_refuses_items_for_someone_elses_field(client, farmer_b, plot):
    r = client.post("/api/sync", headers=farmer_b["headers"], json={"items": [{
        "client_ref": "queue-x", "kind": "threshold", "plot_id": plot["id"],
        "payload": {"pest": "helicoverpa", "count": 2.0},
        "captured_at": "2026-08-26T07:30:00"}]}).json()
    assert r["results"][0]["state"] == "rejected"
    assert r["results"][0]["error"] == "forbidden"


def test_sync_says_what_it_cannot_take_without_the_image(client, farmer, plot):
    r = client.post("/api/sync", headers=farmer["headers"], json={"items": [{
        "client_ref": "queue-img", "kind": "trap_count", "plot_id": plot["id"],
        "payload": {}, "captured_at": "2026-08-26T07:30:00"}]}).json()
    assert r["results"][0]["state"] == "rejected"
    assert "same client_ref" in r["results"][0]["message"]


def test_a_trap_needs_a_published_threshold_to_be_installed(client, farmer, plot):
    r = client.post("/api/traps", headers=farmer["headers"],
                    json={"plot_id": plot["id"], "pest": "faw"})
    assert r.status_code == 400
    assert r.json()["error"] == "no_threshold_for_crop"


def test_trap_counts_build_a_series_with_a_trend(client, farmer, plot, monsoon):
    trap = client.post("/api/traps", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa"}).json()
    for n in (8, 14, 21, 33):
        out = client.post(f"/api/traps/{trap['id']}/counts", headers=farmer["headers"],
                          json={"count": float(n)}).json()
    series = client.get(f"/api/traps/{trap['id']}/series",
                        headers=farmer["headers"]).json()
    assert [c["count"] for c in series["counts"]] == [8, 14, 21, 33]
    assert series["trend"]["direction"] == "up"
    assert series["trend"]["consecutive_rises"] is True
    assert series["etl"] == 8.0
    assert series["etl_source"]


def test_a_trap_photograph_does_not_invent_a_count(client, farmer, plot, monsoon):
    trap = client.post("/api/traps", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa",
                             "trap_type": "sticky_yellow"}).json()
    r = client.post(f"/api/traps/{trap['id']}/scan", headers=farmer["headers"],
                    files={"image": ("trap.jpg", leaf_image("powdery"), "image/jpeg")})
    assert r.status_code == 201
    body = r.json()
    assert body["image_estimate"] is None
    assert body["image_confidence"] == "unavailable"
    assert body["count_recorded"] is False
    assert "cannot estimate" in body["note"]
    assert body["next"]


def test_a_trap_photograph_with_the_farmers_own_count_is_recorded(client, farmer, plot, monsoon):
    trap = client.post("/api/traps", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa"}).json()
    r = client.post(f"/api/traps/{trap['id']}/scan", headers=farmer["headers"],
                    files={"image": ("trap.jpg", leaf_image("powdery"), "image/jpeg")},
                    data={"manual_count": "12", "nights": "1"})
    assert r.status_code == 201
    assert r.json()["count_recorded"] is True
    assert r.json()["threshold"]["chemical_authorised"] is True


def test_an_sms_with_no_gateway_is_skipped_not_claimed_as_sent(client, farmer, plot, monsoon):
    client.post("/api/threshold", headers=farmer["headers"],
                json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 1.0})
    notes = client.get("/api/notifications", headers=farmer["headers"]).json()
    assert notes["notifications"]
    sms = [d for n in notes["notifications"] for d in n["deliveries"] if d["channel"] == "sms"]
    assert sms
    assert all(d["state"] == "skipped" for d in sms)
    assert all("not configured" in (d["error"] or "") for d in sms)
    assert "Only a provider callback" in notes["delivery_note"]


def test_only_a_webhook_can_mark_a_delivery_delivered(client, farmer, plot, monsoon):
    from app.db import get_db
    client.post("/api/threshold", headers=farmer["headers"],
                json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 1.0})
    states = get_db().rows(
        "SELECT channel, state FROM notification_deliveries WHERE channel <> 'inapp'")
    assert states
    assert all(s["state"] != "delivered" for s in states)


def test_the_delivery_webhook_needs_the_shared_secret(client, farmer, plot, monsoon):
    client.post("/api/threshold", headers=farmer["headers"],
                json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 1.0})
    from app.db import get_db
    nid = get_db().one("SELECT id FROM notifications ORDER BY created_at DESC")["id"]
    bad = client.post(f"/api/notifications/webhook/delivery?notification_id={nid}&channel=sms")
    assert bad.status_code == 403
    good = client.post(
        f"/api/notifications/webhook/delivery?notification_id={nid}&channel=sms",
        headers={"X-Prahari-Signature": client.settings.jwt_secret})
    assert good.status_code == 200
