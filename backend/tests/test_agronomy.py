"""
PRAHARI · soil, water and weeds
════════════════════════════════════════════════════════════════════════════
Three capabilities that are not disease detection but sit upstream of it. Each
has one property that is easy to get quietly wrong, and each of those is a test
here:

  SOIL   a MISSING laboratory value must stay missing. The failure mode is a
         blank potassium field arriving as 0.0 and the farmer being told their
         soil is severely deficient, which costs them a bag of MOP they did not
         need. There is no default.

  WATER  the balance must RESET when the farmer says they irrigated. Without
         that it accumulates depletion for ever and eventually tells a
         well-watered field it is parched — the classic silent drift of any
         modelled balance with no feedback.

  WEEDS  the index must refuse a frame it cannot read rather than return a
         number from it. A photograph of the canopy is 95% green and would
         otherwise be reported as catastrophic weed cover.

And one property common to all three: none of them can authorise a chemical.
"""
from __future__ import annotations

import io

import pytest


def _ground(green_frac: float, blobs: int = 18, size: int = 512) -> bytes:
    """Synthetic bare ground with green patches on it. Labelled synthetic — it
    exercises the index, and no accuracy claim is made from it."""
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(11)
    a = np.zeros((size, size, 3), np.uint8)
    a[:, :] = (132, 98, 62)
    target = int(size * size * green_frac)
    per = max(1, target // max(1, blobs))
    rad = max(2, int((per / 3.14159) ** 0.5))
    yy, xx = np.mgrid[0:size, 0:size]
    for _ in range(blobs):
        cy = int(rng.integers(rad, size - rad))
        cx = int(rng.integers(rad, size - rad))
        a[(yy - cy) ** 2 + (xx - cx) ** 2 <= rad * rad] = (58, 142, 48)
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, "JPEG", quality=92)
    return buf.getvalue()


# ── soil ────────────────────────────────────────────────────────────────────
def test_a_missing_lab_value_stays_missing_and_never_becomes_zero(client, farmer, plot):
    r = client.post("/api/agronomy/soil/lab", headers=farmer["headers"], json={
        "plot_id": plot["id"], "nitrogen_kg_ha": 240})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "potassium_kg_ha" in body["unmeasured"]
    k = next(p for p in body["plan"] if p["nutrient"].startswith("K"))
    assert k["soil_test_class"] is None
    assert k["adjustment"] == "no change"
    assert "no soil-test value entered" in k["why"].lower()
    assert "potassium_kg_ha" not in body["ratings"]


def test_a_lab_report_with_no_values_at_all_is_refused(client, farmer, plot):
    r = client.post("/api/agronomy/soil/lab", headers=farmer["headers"],
                    json={"plot_id": plot["id"]})
    assert r.status_code == 400
    assert r.json()["error"] == "no_values"


def test_a_low_rating_raises_the_dose_and_a_high_rating_lowers_it(client, farmer, plot):
    r = client.post("/api/agronomy/soil/lab", headers=farmer["headers"], json={
        "plot_id": plot["id"], "nitrogen_kg_ha": 200, "phosphorus_kg_ha": 40}).json()
    n = next(p for p in r["plan"] if p["nutrient"] == "N")
    p_ = next(p for p in r["plan"] if p["nutrient"].startswith("P"))
    assert n["soil_test_class"] == "low"
    assert n["recommended_kg_acre"] > n["general_kg_acre"]
    assert p_["soil_test_class"] == "high"
    assert p_["recommended_kg_acre"] < p_["general_kg_acre"]


def test_the_nutrient_plan_shows_its_arithmetic_and_names_no_brand(client, farmer, plot):
    r = client.post("/api/agronomy/soil/lab", headers=farmer["headers"], json={
        "plot_id": plot["id"], "nitrogen_kg_ha": 300}).json()
    for row in r["plan"]:
        assert row["arithmetic"]
        assert str(row["material_pct"]) in row["arithmetic"]
    assert "no brand" in r["no_brands"].lower()
    assert "not a Soil Health Card" in r["disclaimer"]


def test_the_self_test_refuses_a_partial_answer_set(client, farmer, plot):
    r = client.post("/api/agronomy/soil/self-test", headers=farmer["headers"], json={
        "plot_id": plot["id"], "answers": {"structure": 2, "earthworms": 1}})
    assert r.status_code == 400
    assert r.json()["error"] == "incomplete"


def test_the_self_test_scores_and_says_what_it_does_not_measure(client, farmer, plot):
    r = client.post("/api/agronomy/soil/self-test", headers=farmer["headers"], json={
        "plot_id": plot["id"],
        "answers": {"structure": 1, "infiltration": 0, "earthworms": 0,
                    "crust": 1, "colour": 1, "roots": 2}})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["score"] == 5 and body["out_of"] == 12
    assert body["band"] == "moderate"
    assert "nothing at all about nutrients" in body["note"].lower()
    assert body["findings"], "a soil scoring 5 of 12 produced no findings"
    for f in body["findings"]:
        assert f["fix"], f"{f['id']} has no fix"


def test_a_perfect_self_test_still_says_it_measured_no_nutrients(client, farmer, plot):
    r = client.post("/api/agronomy/soil/self-test", headers=farmer["headers"], json={
        "plot_id": plot["id"],
        "answers": dict.fromkeys(("structure", "infiltration", "earthworms", "crust", "colour", "roots"), 2)})
    body = r.json()
    assert body["band"] == "good"
    assert body["findings"] == []
    assert "nutrients" in body["note"].lower()


def test_a_farmer_cannot_record_a_soil_test_on_someone_elses_field(
        client, farmer_b, plot):
    r = client.post("/api/agronomy/soil/self-test", headers=farmer_b["headers"], json={
        "plot_id": plot["id"],
        "answers": dict.fromkeys(("structure", "infiltration", "earthworms", "crust", "colour", "roots"), 2)})
    assert r.status_code == 403


# ── water ───────────────────────────────────────────────────────────────────
def test_the_water_balance_is_computed_and_carries_its_method(client, farmer, plot):
    r = client.get(f"/api/agronomy/irrigation/{plot['id']}", headers=farmer["headers"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["available"] is True
    assert d["verdict"] in ("irrigate", "hold", "wait_for_rain", "rainfed")
    assert d["et0_today"] > 0
    assert d["kc"] > 0
    assert "Hargreaves" in d["method_note"]
    assert "FAO" in d["source"]
    assert "not a soil moisture reading" in d["caveat"].lower()


def test_recording_an_irrigation_resets_the_depletion(client, farmer, plot):
    before = client.get(f"/api/agronomy/irrigation/{plot['id']}",
                        headers=farmer["headers"]).json()
    assert before["depletion_mm"] > 0, "the demo weather produced no depletion at all"
    logged = client.post(f"/api/agronomy/irrigation/{plot['id']}", headers=farmer["headers"],
                         json={"mm_applied": 25})
    assert logged.status_code == 201, logged.text
    after = client.get(f"/api/agronomy/irrigation/{plot['id']}",
                       headers=farmer["headers"]).json()
    assert after["depletion_mm"] < before["depletion_mm"]
    assert after["last_irrigation"]


def test_hargreaves_matches_the_published_equation():
    """A closed-form check against the FAO-56 numbers rather than against
    whatever the code happens to return today."""
    import math

    from app.irrigation import et0_hargreaves, ra_mm_per_day
    # Ra at 20 N in late August is about 15.3 mm/day (FAO-56 Table 2.6)
    ra = ra_mm_per_day(20.0, 239)
    assert 14.5 < ra < 16.0, ra
    day = {"date": "2026-08-27", "tmax": 31.0, "tmin": 22.0, "tmean": 26.0, "rain_mm": 0.0}
    expect = 0.0023 * ra * (26.0 + 17.8) * math.sqrt(9.0)
    assert abs(et0_hargreaves(day, 20.0) - expect) < 0.02


def test_light_rain_is_not_counted_as_effective(client):
    from app.irrigation import effective_rain
    assert effective_rain(3.0) == 0.0, "3 mm wets the surface and evaporates"
    assert effective_rain(0.0) == 0.0
    assert 0 < effective_rain(20.0) < 20.0


def test_a_crop_with_no_published_coefficients_says_so_rather_than_guessing(
        client, farmer):
    from app import irrigation
    p = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Odd", "crop": "grape", "area_acre": 1, "sown_on": "2026-06-01",
        "lat": 20.08, "lng": 74.11, "location_source": "gps"}).json()
    saved = irrigation.CROP_WATER.pop("grape")
    try:
        r = client.get(f"/api/agronomy/irrigation/{p['id']}", headers=farmer["headers"]).json()
        assert r["available"] is False
        assert "no FAO crop coefficients" in r["reason"]
    finally:
        irrigation.CROP_WATER["grape"] = saved


# ── weeds ───────────────────────────────────────────────────────────────────
def test_weed_cover_is_measured_and_carries_its_index(client, farmer, plot):
    r = client.post("/api/agronomy/weeds", headers=farmer["headers"],
                    files={"image": ("g.jpg", _ground(0.18), "image/jpeg")},
                    data={"plot_id": plot["id"]})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["usable"] is True
    assert 5 < d["green_cover_pct"] < 40
    assert d["band"] in ("clean", "light", "moderate", "heavy")
    assert "ExG" in d["index"]
    assert "does not know the camera height" in d["limits"]


def test_a_photograph_of_the_canopy_is_refused_rather_than_scored(client, farmer, plot):
    import numpy as np
    from PIL import Image
    a = np.zeros((512, 512, 3), np.uint8)
    a[:, :] = (50, 150, 45)
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, "JPEG", quality=92)
    r = client.post("/api/agronomy/weeds", headers=farmer["headers"],
                    files={"image": ("c.jpg", buf.getvalue(), "image/jpeg")},
                    data={"plot_id": plot["id"]})
    d = r.json()
    assert d["usable"] is False
    assert d["reason"] == "all_canopy"
    assert d["green_cover_fraction"] is None


def test_a_dark_photograph_is_refused(client, farmer, plot):
    import numpy as np
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(np.zeros((512, 512, 3), np.uint8) + 8).save(buf, "JPEG")
    r = client.post("/api/agronomy/weeds", headers=farmer["headers"],
                    files={"image": ("d.jpg", buf.getvalue(), "image/jpeg")},
                    data={"plot_id": plot["id"]})
    assert r.json()["usable"] is False
    assert r.json()["reason"] == "too_dark"


def test_the_weed_advice_never_names_a_herbicide(client, farmer, plot):
    import json as _json
    for frac in (0.03, 0.2, 0.5):
        r = client.post("/api/agronomy/weeds", headers=farmer["headers"],
                        files={"image": ("g.jpg", _ground(frac), "image/jpeg")},
                        data={"plot_id": plot["id"]})
        blob = _json.dumps(r.json()).lower()
        for banned in ("glyphosate", "paraquat", "atrazine", "pendimethalin",
                       "2,4-d", "ml per", "gram per"):
            assert banned not in blob, f"weed advice named {banned}"


def test_the_weed_series_is_kept_because_the_comparison_is_the_point(
        client, farmer, plot):
    for frac in (0.05, 0.25):
        client.post("/api/agronomy/weeds", headers=farmer["headers"],
                    files={"image": ("g.jpg", _ground(frac), "image/jpeg")},
                    data={"plot_id": plot["id"]})
    r = client.get(f"/api/agronomy/weeds/{plot['id']}", headers=farmer["headers"]).json()
    assert len(r["checks"]) >= 2
    assert "week to week" in r["note"]


def test_a_farmer_cannot_run_a_weed_check_on_someone_elses_field(
        client, farmer_b, plot):
    r = client.post("/api/agronomy/weeds", headers=farmer_b["headers"],
                    files={"image": ("g.jpg", _ground(0.1), "image/jpeg")},
                    data={"plot_id": plot["id"]})
    assert r.status_code == 403


# ── the boundary that matters most ──────────────────────────────────────────
@pytest.mark.parametrize("path,method", [
    ("/api/agronomy/soil/lab", "post"),
    ("/api/agronomy/weeds", "post"),
])
def test_nothing_on_this_router_can_authorise_a_chemical(client, farmer, plot, path, method):
    """Soil and weed screens give agronomic advice. The chemical path runs
    through the economic threshold and a verified label claim, and no amount of
    nutrient or weed information opens it."""
    import json as _json
    if path.endswith("weeds"):
        r = client.post(path, headers=farmer["headers"],
                        files={"image": ("g.jpg", _ground(0.5), "image/jpeg")},
                        data={"plot_id": plot["id"]})
    else:
        r = client.post(path, headers=farmer["headers"],
                        json={"plot_id": plot["id"], "nitrogen_kg_ha": 100})
    blob = _json.dumps(r.json()).lower()
    for banned in ("chlorantraniliprole", "emamectin", "flubendiamide", "spinetoram",
                   "indoxacarb", "azoxystrobin", "phi_days", "reentry_hours"):
        assert banned not in blob, f"{path} surfaced {banned}"
