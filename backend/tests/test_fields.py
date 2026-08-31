"""Field onboarding: location, area, crop cycles and the passport."""
from __future__ import annotations

import pytest


def test_gps_field_creation(client, farmer):
    r = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Grape plot A", "crop": "grape", "variety": "Thompson Seedless",
        "area_acre": 2.4, "sown_on": "2026-05-10", "lat": 20.0821, "lng": 74.1109,
        "location_source": "gps", "soil": "medium black", "irrigation": "drip",
        "tank_litres": 20, "expected_harvest": "2026-12-01"})
    assert r.status_code == 201
    p = r.json()
    assert p["taluka"] == "niphad"          # derived from the coordinates
    assert p["area_source"] == "declared"
    assert p["crop_stage"]["stage"]
    assert p["tank_litres"] == 20


def test_manual_taluka_selection_is_accepted(client, farmer):
    r = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Onion west", "crop": "onion", "area_acre": 1.1,
        "sown_on": "2026-07-10", "taluka": "lasalgaon", "location_source": "manual"})
    assert r.status_code == 201
    assert r.json()["taluka"] == "lasalgaon"
    assert r.json()["lat"] is not None     # falls back to the taluka centroid


def test_polygon_gives_an_approximate_area_and_says_so(client, farmer):
    r = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Drawn plot", "crop": "tomato", "area_acre": 99.0,
        "sown_on": "2026-06-25", "location_source": "map",
        "lat": 20.081, "lng": 74.110,
        "boundary": {"type": "Polygon", "coordinates": [[
            [74.1100, 20.0810], [74.1120, 20.0810],
            [74.1120, 20.0826], [74.1100, 20.0826], [74.1100, 20.0810]]]}})
    assert r.status_code == 201
    p = r.json()
    assert p["area_source"] == "polygon"
    assert p["area_acre"] != 99.0
    assert 5 < p["area_acre"] < 15          # ~209 m × 177 m
    assert "not a survey measurement" in p["area_note"]


def test_an_unmodelled_crop_is_refused_with_the_covered_list(client, farmer):
    r = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Quinoa", "crop": "quinoa", "area_acre": 1, "sown_on": "2026-06-25",
        "taluka": "niphad"})
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_crop"
    assert "tomato" in r.json()["message"]


def test_a_future_sowing_date_is_refused(client, farmer):
    r = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Next season", "crop": "tomato", "area_acre": 1,
        "sown_on": "2027-06-25", "taluka": "niphad"})
    assert r.status_code == 422


def test_gps_without_coordinates_is_refused(client, farmer):
    r = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "x", "crop": "tomato", "area_acre": 1, "sown_on": "2026-06-25",
        "location_source": "gps"})
    assert r.status_code == 422


def test_a_new_crop_cycle_keeps_the_field_history(client, farmer, plot):
    before = client.get(f"/api/plots/{plot['id']}/history",
                        headers=farmer["headers"]).json()["timeline"]
    r = client.post(f"/api/plots/{plot['id']}/cycles", headers=farmer["headers"], json={
        "crop": "onion", "sown_on": "2026-08-01"})
    assert r.status_code == 201
    after = client.get(f"/api/plots/{plot['id']}/history",
                       headers=farmer["headers"]).json()
    assert len(after["timeline"]) > len(before)
    assert len(after["cycles"]) == 2
    assert after["plot"]["crop"] == "onion"
    assert any(c["ended_on"] for c in after["cycles"])


def test_patch_updates_only_what_was_sent(client, farmer, plot):
    r = client.patch(f"/api/plots/{plot['id']}", headers=farmer["headers"],
                     json={"name": "Renamed block", "tank_litres": 16})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed block"
    assert r.json()["tank_litres"] == 16
    assert r.json()["crop"] == plot["crop"]


def test_a_field_with_no_location_falls_back_to_the_farmers_own_taluka(client, farmer):
    """The Add-field form offers "Use my account taluka" as its default. That
    promise was being broken by a schema rule that rejected the request before
    the router — which already resolves exactly this — could run. Adding a
    second field is the ordinary case, so this path must work with nothing
    filled in but a name, a crop, an area and a date."""
    r = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Maize strip", "crop": "maize", "area_acre": 2.5,
        "sown_on": "2026-08-01", "location_source": "manual"})
    assert r.status_code == 201, r.text
    out = r.json()
    # niphad is the taluka the farmer fixture registered with
    assert out["taluka"] == "niphad"
    # and it is given that taluka's coordinates, not left without a location:
    # every infection model needs a point to fetch weather for.
    assert out["lat"] is not None and out["lng"] is not None


def test_a_taluka_prahari_does_not_cover_is_still_refused(client, farmer):
    """Moving the location rule out of the schema must not have loosened it."""
    r = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Far field", "crop": "tomato", "area_acre": 1.0,
        "sown_on": "2026-08-01", "location_source": "manual", "taluka": "atlantis"})
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_taluka"


def test_a_second_field_keeps_the_first_one_intact(client, farmer, plot):
    """Switching fields is only meaningful if each carries its own records."""
    second = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Onion patch", "crop": "onion", "area_acre": 1.0,
        "sown_on": "2026-07-01", "location_source": "manual"}).json()
    assert second["id"] != plot["id"]
    assert second["crop"] == "onion"

    listed = client.get("/api/plots", headers=farmer["headers"]).json()["plots"]
    by_id = {p["id"]: p for p in listed}
    assert len(listed) == 2
    assert by_id[plot["id"]]["crop"] == "tomato"
    assert by_id[second["id"]]["crop"] == "onion"

    # each field's calendar is its own — the crop, not the account's, decides
    a = client.get(f"/api/crop-calendar/{plot['id']}", headers=farmer["headers"])
    b = client.get(f"/api/crop-calendar/{second['id']}", headers=farmer["headers"])
    if a.status_code == 200 and b.status_code == 200:
        assert a.json()["crop"]["id"] == "tomato"
        assert b.json()["crop"]["id"] == "onion"
        assert a.json()["field"]["name"] != b.json()["field"]["name"]
