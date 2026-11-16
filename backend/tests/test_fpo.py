"""
Module C — farmer producer organisations.

The guarantees under test: only an administrator creates an FPO or links its
staff; membership is the farmer's own act and can be withdrawn; staff see
counts across members only — never a name, phone, village, coordinate or
plot id — and any count below 3 is suppressed; staff of one FPO cannot read
another; a field never scored is "not scored", never "safe".
"""
from __future__ import annotations

import pytest


@pytest.fixture
def fpo(client, admin):
    r = client.post("/api/fpo", headers=admin["headers"],
                    json={"name": "Niphad Tomato Growers FPC", "district": "nashik"})
    assert r.status_code == 201, r.text
    return r.json()


def _staff(client, admin, fpo_id, email="fpo@prahari-test.example.com"):
    r = client.post("/api/admin/users", headers=admin["headers"], json={
        "full_name": "FPO Coordinator", "password": "strong-pass-2026", "role": "fpo",
        "email": email})
    assert r.status_code == 201, r.text
    uid = r.json()["user_id"]
    r = client.post(f"/api/fpo/{fpo_id}/staff", headers=admin["headers"], json={"user_id": uid})
    assert r.status_code == 201, r.text
    login = client.post("/api/auth/login",
                        json={"identifier": email, "password": "strong-pass-2026"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_only_an_administrator_creates_an_fpo(client, farmer):
    r = client.post("/api/fpo", headers=farmer["headers"], json={"name": "My own FPO"})
    assert r.status_code == 403


def test_fpo_role_cannot_be_self_registered(client):
    r = client.post("/api/auth/register", json={
        "full_name": "Not Staff", "password": "strong-pass-2026", "role": "fpo",
        "email": "selfserve@prahari-test.example.com"})
    assert r.status_code == 400
    assert r.json()["error"] == "role_not_self_serviceable"


def test_only_fpo_accounts_can_be_linked_as_staff(client, admin, fpo, farmer):
    r = client.post(f"/api/fpo/{fpo['id']}/staff", headers=admin["headers"],
                    json={"user_id": farmer["user_id"]})
    assert r.status_code == 400
    assert r.json()["error"] == "not_fpo_staff"


def test_farmer_sees_the_list_and_what_sharing_means(client, farmer, fpo):
    body = client.get("/api/fpo", headers=farmer["headers"]).json()
    assert body["fpos"][0]["id"] == fpo["id"]
    assert body["fpos"][0]["member"] is False
    assert "never sees your name" in body["sharing"]


def test_join_and_leave_are_the_farmers_own_act(client, farmer, fpo, admin):
    # An administrator cannot join a farmer on their behalf.
    assert client.post(f"/api/fpo/{fpo['id']}/join", headers=admin["headers"]).status_code == 403
    assert client.post(f"/api/fpo/{fpo['id']}/join", headers=farmer["headers"]).status_code == 200
    assert client.get("/api/fpo", headers=farmer["headers"]).json()["fpos"][0]["member"] is True
    assert client.delete(f"/api/fpo/{fpo['id']}/join", headers=farmer["headers"]).status_code == 200
    assert client.get("/api/fpo", headers=farmer["headers"]).json()["fpos"][0]["member"] is False


def test_summary_is_counts_only_and_small_cells_are_suppressed(client, admin, fpo, farmer, plot):
    staff = _staff(client, admin, fpo["id"])
    client.post(f"/api/fpo/{fpo['id']}/join", headers=farmer["headers"])
    r = client.get(f"/api/fpo/{fpo['id']}/summary", headers=staff)
    assert r.status_code == 200, r.text
    body = r.json()
    # one member, one field: both below the minimum cell
    assert body["members"] == {"count": None, "suppressed": True, "label": "fewer than 3",
                               "label_mr": "3 पेक्षा कमी"}
    assert body["fields"]["suppressed"] is True
    text = r.text
    assert "\"village\"" not in text
    for leaked in (plot["id"], "Rajesh", "9812345678", "20.081", "74.11",
                   plot["farmer_id"]):
        assert leaked not in text, leaked


def test_unscored_field_is_not_scored_not_safe(client, admin, fpo, farmer, farmer_b):
    staff = _staff(client, admin, fpo["id"])
    # three members with one field each, so the cells are reportable
    heads = [farmer["headers"], farmer_b["headers"]]
    r = client.post("/api/auth/register", json={
        "full_name": "Third Member", "password": "strong-pass-2026",
        "phone": "9812345670", "taluka": "niphad"})
    heads.append({"Authorization": f"Bearer {r.json()['access_token']}"})
    for i, h in enumerate(heads):
        client.post("/api/plots", headers=h, json={
            "name": f"Plot {i}", "crop": "tomato", "area_acre": 1.0, "sown_on": "2026-06-25",
            "lat": 20.08 + i / 100, "lng": 74.11, "location_source": "gps"})
        client.post(f"/api/fpo/{fpo['id']}/join", headers=h)
    body = client.get(f"/api/fpo/{fpo['id']}/summary", headers=staff).json()
    assert body["members"]["count"] == 3
    assert body["fields"]["count"] == 3
    assert body["crops"][0]["crop"] == "tomato" and body["crops"][0]["count"] == 3
    # the cell's own label must not overwrite the crop's name
    assert body["crops"][0]["name"] == "Tomato" and body["crops"][0]["label"] == "3"
    assert body["health"]["not_scored"]["count"] == 3
    assert all(b["count"] == 0 for b in body["health"]["bands"])


def test_staff_of_one_fpo_cannot_read_another(client, admin, fpo):
    other = client.post("/api/fpo", headers=admin["headers"], json={"name": "Other FPC"}).json()
    staff = _staff(client, admin, fpo["id"])
    assert client.get(f"/api/fpo/{other['id']}/summary", headers=staff).status_code == 403
    mine = client.get("/api/fpo/mine", headers=staff).json()["fpos"]
    assert [f["id"] for f in mine] == [fpo["id"]]


def test_farmer_and_officer_cannot_read_a_summary(client, farmer, officer, fpo):
    for h in (farmer["headers"], officer["headers"]):
        assert client.get(f"/api/fpo/{fpo['id']}/summary", headers=h).status_code == 403


def test_demo_fpo_console_links_a_demo_organisation(client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "demo_console_access", True)
    r = client.post("/api/auth/demo-console?role=fpo")
    if r.status_code == 404:
        pytest.skip("demo console route is mounted at app build time")
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    mine = client.get("/api/fpo/mine", headers=h).json()["fpos"]
    assert mine and mine[0]["id"] == "FPO-DEMO"
    s = client.get("/api/fpo/FPO-DEMO/summary", headers=h).json()
    assert s["members"]["count"] == 0       # nobody is joined on their behalf
