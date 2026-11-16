"""
Module D — what happened after each kind of action.

The summary must count, not judge: measured outcomes and the farmer's own
account are kept apart, a share appears only from MIN_BASE measured outcomes,
it is grouped by kind of action rather than by product, and it is scoped to
what the caller may already see.
"""
from __future__ import annotations

from conftest import scan


def _apply(client, headers, plot_id, kind="cultural", target="late_blight",
           product="Remove and destroy infected leaves"):
    r = client.post("/api/applications", headers=headers, json={
        "plot_id": plot_id, "target": target, "kind": kind, "product": product})
    assert r.status_code == 201, r.text
    from app.db import get_db
    return get_db().one("SELECT id FROM followups WHERE plot_id = :p ORDER BY id DESC",
                        {"p": plot_id})["id"]


def test_empty_field_says_so_and_gives_no_share(client, farmer, plot):
    r = client.get(f"/api/followups/outcomes?plot_id={plot['id']}", headers=farmer["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["groups"] == []
    assert body["total"]["followups"] == 0
    assert body["total"]["better_share"] is None
    assert body["total"]["statement"] == "No measured follow-up yet."


def test_open_followup_is_counted_as_open(client, farmer, plot):
    _apply(client, farmer["headers"], plot["id"])
    body = client.get(f"/api/followups/outcomes?plot_id={plot['id']}",
                      headers=farmer["headers"]).json()
    g = body["groups"][0]
    assert g["kind"] == "cultural" and g["target"] == "late_blight"
    assert g["followups"] == 1 and g["open"] == 1
    assert g["measured_total"] == 0 and g["self_reported_total"] == 0


def test_self_reported_never_counts_as_measured(client, farmer, plot):
    fid = _apply(client, farmer["headers"], plot["id"])
    r = client.post(f"/api/followups/{fid}/outcome", headers=farmer["headers"],
                    json={"outcome": "better"})
    assert r.status_code == 200, r.text
    g = client.get(f"/api/followups/outcomes?plot_id={plot['id']}",
                   headers=farmer["headers"]).json()["groups"][0]
    assert g["self_reported"]["better"] == 1
    assert g["measured_total"] == 0
    assert g["better_share"] is None


def test_share_appears_only_from_the_minimum_base(client, farmer, plot):
    from app.db import get_db
    from app.interventions import MIN_BASE
    scan(client, farmer["headers"], plot["id"])
    db = get_db()
    oid = db.one("SELECT id FROM observations WHERE plot_id = :p", {"p": plot["id"]})["id"]

    def measured(outcome):
        fid = _apply(client, farmer["headers"], plot["id"])
        db.execute("UPDATE followups SET done_observation = :o, outcome = :out,"
                   " comparison = :c WHERE id = :i",
                   {"o": oid, "out": outcome, "c": '{"method": "rescan"}', "i": fid})

    for _ in range(MIN_BASE - 2):
        measured("better")
    measured("worse")
    g = client.get(f"/api/followups/outcomes?plot_id={plot['id']}",
                   headers=farmer["headers"]).json()["groups"][0]
    assert g["measured_total"] == MIN_BASE - 1
    assert g["better_share"] is None
    assert "too few" in g["statement"]

    measured("better")
    g = client.get(f"/api/followups/outcomes?plot_id={plot['id']}",
                   headers=farmer["headers"]).json()["groups"][0]
    assert g["measured_total"] == MIN_BASE
    assert g["better_share"] == round(100 * (MIN_BASE - 1) / MIN_BASE)
    assert f"{MIN_BASE - 1} of {MIN_BASE}" in g["statement"]


def test_grouped_by_kind_never_by_product(client, farmer, plot):
    _apply(client, farmer["headers"], plot["id"], product="Neem oil 1500 ppm brand A",
           kind="biological")
    _apply(client, farmer["headers"], plot["id"], product="Neem oil brand B", kind="biological")
    body = client.get(f"/api/followups/outcomes?plot_id={plot['id']}",
                      headers=farmer["headers"]).json()
    assert len(body["groups"]) == 1
    assert body["groups"][0]["followups"] == 2
    assert "brand" not in str(body)


def test_another_farmer_cannot_read_my_field(client, farmer, farmer_b, plot):
    r = client.get(f"/api/followups/outcomes?plot_id={plot['id']}", headers=farmer_b["headers"])
    assert r.status_code in (403, 404)


def test_farmer_without_plot_id_sees_only_their_own(client, farmer, farmer_b, plot):
    _apply(client, farmer["headers"], plot["id"])
    mine = client.get("/api/followups/outcomes", headers=farmer["headers"]).json()
    theirs = client.get("/api/followups/outcomes", headers=farmer_b["headers"]).json()
    assert mine["total"]["followups"] == 1
    assert theirs["total"]["followups"] == 0


def test_officer_sees_their_talukas(client, farmer, plot, officer):
    _apply(client, farmer["headers"], plot["id"])
    body = client.get("/api/followups/outcomes", headers=officer["headers"]).json()
    assert body["total"]["followups"] == 1


def test_expert_must_name_a_field(client, expert):
    r = client.get("/api/followups/outcomes", headers=expert["headers"])
    assert r.status_code == 403
