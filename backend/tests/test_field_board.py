"""
PRAHARI · the multi-field board

The board exists so a farmer with four fields does not have to open each one to
find the one in trouble. Two properties matter, and both fail silently:

  · the board and the field's own screen must never disagree. They are the
    same services; a second implementation here would drift and nobody would
    notice until a farmer acted on the wrong number.
  · a field with no weather gets NO score. Not zero, not the last one, not the
    average of the others — the rule the whole app is built on does not stop
    applying because a field is one row in a list.

And the ordering: the point of the board is the top card, so a field that is
asking for something must outrank one that is not.
"""
from __future__ import annotations


def _field(client, headers, name, crop, sown, **kw):
    body = {"name": name, "crop": crop, "area_acre": 1.5, "sown_on": sown,
            "lat": 20.0810, "lng": 74.1100, "location_source": "gps"}
    body.update(kw)
    r = client.post("/api/plots", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_a_farmer_can_run_several_fields_with_different_crops(client, farmer, plot):
    onion = _field(client, farmer["headers"], "Onion patch", "onion", "2026-06-20")
    grape = _field(client, farmer["headers"], "Grape block", "grape", "2026-05-01")

    out = client.get("/api/plots", headers=farmer["headers"]).json()
    crops = {p["name"]: p["crop"] for p in out["plots"]}
    assert crops == {"Tomato block 1": "tomato", "Onion patch": "onion",
                     "Grape block": "grape"}
    # each carries its own stage, computed from its own sowing date
    stages = {p["name"]: (p.get("crop_stage") or {}).get("days") for p in out["plots"]}
    assert stages["Onion patch"] != stages["Grape block"]
    assert onion["id"] != grape["id"]


def test_the_board_returns_one_card_per_field_with_its_own_state(client, farmer, plot, monsoon):
    _field(client, farmer["headers"], "Onion patch", "onion", "2026-06-20")
    r = client.get("/api/plots/board?lang=en", headers=farmer["headers"])
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["count"] == 2
    names = {f["name"] for f in b["fields"]}
    assert names == {"Tomato block 1", "Onion patch"}
    for f in b["fields"]:
        assert f["crop_label"]
        assert "attention" in f
        # a score, or an explicit statement that there is none — never a
        # placeholder standing in for a reading
        assert f["score"] is not None or f.get("unavailable")


def test_the_board_agrees_with_the_field_its_own_screen(client, farmer, plot, monsoon):
    """The assertion that stops the board becoming a second implementation."""
    _field(client, farmer["headers"], "Onion patch", "onion", "2026-06-20")
    b = client.get("/api/plots/board?lang=en", headers=farmer["headers"]).json()
    card = next(f for f in b["fields"] if f["plot_id"] == plot["id"])

    own = client.get(f"/api/fields/{plot['id']}/health", headers=farmer["headers"]).json()
    assert card["score"] == round(own["health"]["score"])
    assert card["band"] == own["health"]["band"]

    day = client.get(f"/api/fields/{plot['id']}/today", headers=farmer["headers"]).json()
    assert card["item_count"] == day["count"]
    if day["items"]:
        assert card["items"][0]["title"] == day["items"][0]["title"]


def test_a_field_that_needs_something_sorts_above_one_that_does_not(client, farmer,
                                                                    plot, monsoon):
    _field(client, farmer["headers"], "Onion patch", "onion", "2026-06-20")
    _field(client, farmer["headers"], "Grape block", "grape", "2026-05-01")
    b = client.get("/api/plots/board?lang=en", headers=farmer["headers"]).json()

    rank = {"urgent": 0, "act": 1, "calm": 2, "none": 3}
    tones = [rank[f["attention"]] for f in b["fields"]]
    assert tones == sorted(tones), f"board is not ordered by urgency: {tones}"
    assert b["needs_attention"] == sum(
        1 for f in b["fields"] if f["attention"] in ("urgent", "act"))


def test_the_board_never_shows_another_farmers_field(client, farmer, farmer_b, plot):
    _field(client, farmer_b["headers"], "Not mine", "onion", "2026-06-20")
    b = client.get("/api/plots/board?lang=en", headers=farmer["headers"]).json()
    assert {f["name"] for f in b["fields"]} == {"Tomato block 1"}


def test_a_field_with_no_weather_gets_no_score(client, farmer, plot, monkeypatch):
    """Not zero, not the last one, not borrowed from the field beside it."""
    from app.services.risk import RiskService
    from app.weather import WeatherUnavailable

    def refuse(*a, **k):
        raise WeatherUnavailable("openmeteo", "the weather provider is unreachable")
    monkeypatch.setattr(RiskService, "weather_series", refuse)

    r = client.get("/api/plots/board?lang=en", headers=farmer["headers"])
    assert r.status_code == 200, (
        "one field without weather must not take the whole board down: " + r.text[:200])
    b = r.json()
    card = b["fields"][0]
    assert card["score"] is None, "a field with no weather was given a score"
    assert card["band"] is None
    assert "Nothing is estimated" in card["unavailable"]
    assert b["weather_unavailable"] == 1
    # its records are still there — the field is shown, only the score is not
    assert card["crop_label"] and card["name"] == "Tomato block 1"


def test_last_seen_counts_scouting_not_app_opens(client, farmer, plot, monsoon):
    """A field nobody has looked at says so. Opening the app is not scouting."""
    b = client.get("/api/plots/board?lang=en", headers=farmer["headers"]).json()
    card = b["fields"][0]
    # the demo fixture has no observations on this field yet
    assert card["last_seen"] is None or card["last_seen"]["kind"] in (
        "scan", "trap count", "soil test")


def test_starting_a_new_crop_keeps_the_fields_history(client, farmer, plot):
    """The passport outlives the crop — that is what makes a field worth
    registering once rather than once per season."""
    client.post("/api/farm-ledger", headers=farmer["headers"], json={
        "plot_id": plot["id"], "category": "seed", "title": "Tomato seedlings",
        "amount_inr": 3000, "spent_on": "2026-06-24"})

    r = client.post(f"/api/plots/{plot['id']}/cycles", headers=farmer["headers"],
                    json={"crop": "onion", "sown_on": "2026-08-25", "end_previous": True})
    assert r.status_code == 201, r.text
    assert r.json()["plot"]["crop"] == "onion"

    # same field id, so nothing attached to it was orphaned
    assert r.json()["plot"]["id"] == plot["id"]
    led = client.get(f"/api/farm-ledger?plot_id={plot['id']}",
                     headers=farmer["headers"]).json()
    assert led["count"] == 1, "the previous season's records were lost"

    # and the stage now counts from the NEW sowing date
    fresh = client.get(f"/api/plots/{plot['id']}", headers=farmer["headers"]).json()
    assert fresh["sown_on"] == "2026-08-25"
    assert fresh["crop_stage"]["days"] < 60


def test_a_crop_prahari_has_no_models_for_is_refused(client, farmer, plot):
    r = client.post(f"/api/plots/{plot['id']}/cycles", headers=farmer["headers"],
                    json={"crop": "dragonfruit", "sown_on": "2026-08-25"})
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_crop"


def test_a_new_cycle_on_someone_elses_field_is_refused(client, farmer_b, plot):
    r = client.post(f"/api/plots/{plot['id']}/cycles", headers=farmer_b["headers"],
                    json={"crop": "onion", "sown_on": "2026-08-25"})
    assert r.status_code in (403, 404)
