"""
The privacy boundary. Every one of these would be a data breach if it passed.
"""
from __future__ import annotations

from conftest import scan


def test_farmer_b_cannot_read_farmer_a_field(client, plot, farmer_b):
    for path in (f"/api/plots/{plot['id']}",
                 f"/api/risk/{plot['id']}",
                 f"/api/risk/{plot['id']}/forecast",
                 f"/api/fields/{plot['id']}/health",
                 f"/api/fields/{plot['id']}/nearby",
                 f"/api/plots/{plot['id']}/history",
                 f"/api/observations?plot_id={plot['id']}",
                 f"/api/traps?plot_id={plot['id']}"):
        r = client.get(path, headers=farmer_b["headers"])
        assert r.status_code == 403, f"{path} leaked: {r.status_code}"
        assert r.json()["error"] == "forbidden"


def test_farmer_b_cannot_write_to_farmer_a_field(client, plot, farmer_b):
    r = client.post("/api/threshold", headers=farmer_b["headers"],
                    json={"plot_id": plot["id"], "pest": "tuta", "count": 5})
    assert r.status_code == 403
    r = client.post("/api/traps", headers=farmer_b["headers"],
                    json={"plot_id": plot["id"], "pest": "tuta"})
    assert r.status_code == 403
    r = scan(client, farmer_b["headers"], plot["id"])
    assert r.status_code == 403
    r = client.patch(f"/api/plots/{plot['id']}", headers=farmer_b["headers"],
                     json={"name": "hijacked"})
    assert r.status_code == 403


def test_plot_list_only_returns_your_own(client, plot, farmer_b):
    r = client.get("/api/plots", headers=farmer_b["headers"])
    assert r.status_code == 200
    assert r.json()["plots"] == []


def test_farmer_b_cannot_read_farmer_a_observation(client, plot, farmer, farmer_b):
    obs = scan(client, farmer["headers"], plot["id"]).json()["observation"]["id"]
    r = client.get(f"/api/observations/{obs}", headers=farmer_b["headers"])
    assert r.status_code == 403
    r = client.get(f"/api/observations/{obs}/image", headers=farmer_b["headers"])
    assert r.status_code == 403


def test_farmer_cannot_reach_the_officer_console(client, farmer):
    for path in ("/api/officer/summary", "/api/officer/queue", "/api/officer/hotspots",
                 "/api/officer/audit", "/api/officer/route"):
        r = client.get(path, headers=farmer["headers"])
        assert r.status_code == 403, path


def test_farmer_cannot_reach_the_expert_portal_or_admin(client, farmer):
    assert client.get("/api/expert/cases", headers=farmer["headers"]).status_code == 403
    assert client.get("/api/admin/claims", headers=farmer["headers"]).status_code == 403
    assert client.get("/api/admin/audit-log", headers=farmer["headers"]).status_code == 403


def test_officer_scope_is_enforced_not_advisory(client, admin, plot):
    """An officer scoped only to Dindori must not see a Niphad field."""
    r = client.post("/api/admin/users", headers=admin["headers"], json={
        "full_name": "Dindori Officer", "password": "strong-pass-2026", "role": "officer",
        "email": "dindori@prahari-test.example.com", "taluka": "dindori"})
    login = client.post("/api/auth/login",
                        json={"identifier": "dindori@prahari-test.example.com", "password": "strong-pass-2026"})
    H = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=H).json()["scopes"] == ["dindori"]
    got = client.get(f"/api/plots/{plot['id']}", headers=H)
    assert got.status_code == 403
    listed = client.get("/api/plots", headers=H).json()["plots"]
    assert all(p["taluka"] == "dindori" for p in listed)


def test_officer_in_scope_sees_the_field_but_not_the_farmer_identity(client, officer, plot):
    r = client.get("/api/plots", headers=officer["headers"])
    assert r.status_code == 200
    rows = r.json()["plots"]
    assert any(p["id"] == plot["id"] for p in rows)
    for p in rows:
        assert "farmer_id" not in p


def test_expert_cannot_browse_fields_with_no_case_assigned(client, expert, plot):
    r = client.get(f"/api/plots/{plot['id']}", headers=expert["headers"])
    assert r.status_code == 403


def test_expert_case_detail_does_not_carry_farmer_contact(client, farmer, plot, expert):
    import json
    obs = scan(client, farmer["headers"], plot["id"]).json()["observation"]["id"]
    case = client.post(f"/api/observations/{obs}/expert-review", headers=farmer["headers"],
                       json={"reason": "please check"}).json()["case"]["id"]
    detail = client.get(f"/api/expert/cases/{case}", headers=expert["headers"])
    assert detail.status_code == 200
    body = json.dumps(detail.json())
    assert "9812345678" not in body, "farmer phone number leaked to the expert portal"


def test_nearby_map_is_aggregated_and_names_nobody(client, farmer, plot):
    """A whitelist, deliberately, so a field-level leak fails here rather than
    being noticed in a demo.

    The list grew when the hotspot map was added: it now carries each taluka's
    own CENTROID and its incidence per 1,000 farms. Both are properties of a
    taluka — the centroid is reference data that ships in talukas.json and is
    the same for every farmer in it — so neither says anything about a person
    or a field. The assertions below are what keeps that true: the whitelist
    itself, and a check that this field's actual coordinates never appear.
    """
    import json
    r = client.get(f"/api/fields/{plot['id']}/nearby", headers=farmer["headers"])
    assert r.status_code == 200
    body = r.json()
    assert "privacy" in body
    text = json.dumps(body)
    assert "9812345678" not in text
    for entry in body["nearby_talukas"]:
        assert set(entry) <= {"taluka", "name", "name_mr", "lat", "lng",
                              "z", "class", "cases", "incidence_per_1000"}
    # The map plots taluka centroids and nothing finer. Checked structurally
    # rather than by searching the text for the field's coordinates: a taluka
    # centroid legitimately shares leading digits with a field inside it, so a
    # substring search reports a leak that is not one. Every coordinate that
    # leaves must be one of the published centroids, and none of them is this
    # field's — which is the actual property being protected.
    centroids = {(t["lat"], t["lng"]) for t in _talukas()}
    assert (plot["lat"], plot["lng"]) not in centroids, "fixture invalidates this test"
    for entry in body["nearby_talukas"]:
        assert (entry["lat"], entry["lng"]) in centroids, \
            "a coordinate that is not a published taluka centroid reached the map"


def _talukas():
    from app import reference
    return reference.TALUKAS
