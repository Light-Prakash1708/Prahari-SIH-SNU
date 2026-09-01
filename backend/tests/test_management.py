"""
PRAHARI · the management screen

The screen that answers "should I spray?". The assertions worth having here are
about what must NEVER happen:

  · a model's confidence must never be readable as an amount in the field
  · a disease must never be asked for a trap count
  · the chemical rung must never open on a diagnosis alone
  · one farmer must never see another farmer's field

The first is the one this file exists for. `confidence` answers "what is this?"
and a count answers "how much is there?"; a system that lets the first stand in
for the second will recommend a spray because a photograph was sharp.
"""
from __future__ import annotations

PW = "strong-pass-2026"


def _mg(client, headers, plot_id, target=None):
    q = f"?target={target}" if target else ""
    r = client.get(f"/api/management/{plot_id}{q}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _assess(client, headers, plot_id, inspected, affected, problem="late_blight", **kw):
    return client.post(f"/api/management/{plot_id}/assessment", headers=headers,
                       json={"problem": problem, "plants_inspected": inspected,
                             "plants_affected": affected, **kw})


# ── the screen loads, and offers both kinds of problem ─────────────────────
def test_the_screen_offers_pests_and_diseases(client, farmer, plot):
    out = _mg(client, farmer["headers"], plot["id"])
    kinds = {t["kind"] for t in out["targets"]}
    assert "pest" in kinds
    assert "disease" in kinds, "a disease diagnosis had nowhere to go before this"
    # a diagnosis outcome is not a manageable problem and must not be offerable
    assert "healthy" not in {t["id"] for t in out["targets"]}


def test_a_pest_with_no_count_asks_for_a_count(client, farmer, plot):
    out = _mg(client, farmer["headers"], plot["id"], "helicoverpa")
    assert out["decision"]["reason_code"] == "no_count"
    assert out["threshold"] is None
    assert "COUNT" in out["decision"]["answer"].upper()


def test_a_disease_is_never_asked_for_a_trap_count(client, farmer, plot):
    """The dead end this work was done to remove.

    Before, asking about late blight returned "nothing counted yet, record a
    count" — a count that does not exist for a disease. A farmer arriving from a
    disease diagnosis could go no further."""
    out = _mg(client, farmer["headers"], plot["id"], "late_blight")
    assert out["target_kind"] == "disease"
    assert out["decision"]["reason_code"] == "no_observation"
    assert "COUNT" not in out["decision"]["answer"].upper()
    assert "ASSESS" in out["decision"]["answer"].upper()


# ── the assertion this file exists for ─────────────────────────────────────
def test_ai_confidence_is_never_used_as_a_field_measurement(client, farmer, plot):
    """Confidence and measurement are separate keys, separately explained, and a
    confident diagnosis with nothing counted stays undecided."""
    out = _mg(client, farmer["headers"], plot["id"], "helicoverpa")
    ev = out["evidence"]
    assert "diagnosis" in ev and "measurement" in ev
    # nothing has been counted, so the decision cannot have moved
    assert out["decision"]["reason_code"] == "no_count"
    assert out["threshold"] is None
    if ev["diagnosis"]:
        # the band describes the identification and says so, in both languages
        assert ev["diagnosis"]["confidence_band"] in ("low", "moderate", "high")
        assert "how much" in ev["diagnosis"]["means"].lower()
        assert ev["diagnosis"]["means_mr"]


def test_a_confident_diagnosis_alone_never_opens_the_chemical_rung(client, farmer, plot):
    for target in ("helicoverpa", "late_blight"):
        out = _mg(client, farmer["headers"], plot["id"], target)
        chem = out["chemical"]
        assert chem["recommended"] is None
        assert chem["options"] == []
        rung = next((s for s in out["ipm_ladder"] if s["key"] == "chemical"), None)
        assert rung is None or rung.get("withheld") is True


# ── the disease path, end to end ───────────────────────────────────────────
def test_an_assessment_shows_its_arithmetic_and_moves_the_decision(client, farmer, plot):
    before = _mg(client, farmer["headers"], plot["id"], "late_blight")
    assert before["assessment"] is None

    r = _assess(client, farmer["headers"], plot["id"], 20, 3,
                spread_band="few_spots", part="lower_leaves")
    assert r.status_code == 201, r.text
    a = r.json()["assessment"]
    assert a["incidence_pct"] == 15.0
    # the two numbers travel with the percentage so it can be re-derived
    assert a["arithmetic"] == "3 ÷ 20 plants"
    assert a["plants_inspected"] == 20 and a["plants_affected"] == 3

    after = _mg(client, farmer["headers"], plot["id"], "late_blight")
    assert after["assessment"]["incidence_pct"] == 15.0
    assert after["decision"]["reason_code"] != "no_observation"
    kinds = {e["kind"] for e in after["decision"]["evidence"]}
    assert "field_assessment" in kinds


def test_the_api_refuses_a_ready_made_percentage(client, farmer, plot):
    """Incidence is derived from two counts and never accepted as a figure.
    A percentage that arrives ready-made cannot be checked by anyone."""
    r = client.post(f"/api/management/{plot['id']}/assessment", headers=farmer["headers"],
                    json={"problem": "late_blight", "incidence_pct": 40})
    assert r.status_code == 422


def test_more_affected_than_inspected_is_rejected(client, farmer, plot):
    r = _assess(client, farmer["headers"], plot["id"], 5, 9)
    assert r.status_code == 400
    assert r.json()["error"] == "affected_exceeds_inspected"


def test_an_assessment_is_idempotent_on_client_ref(client, farmer, plot):
    ref = "off-line-ref-1"
    a = _assess(client, farmer["headers"], plot["id"], 10, 2, client_ref=ref)
    b = _assess(client, farmer["headers"], plot["id"], 10, 2, client_ref=ref)
    assert a.status_code == 201 and b.status_code == 201
    assert b.json()["duplicate"] is True


# ── trend ──────────────────────────────────────────────────────────────────
def test_a_single_observation_is_never_called_a_trend(client, farmer, plot):
    _assess(client, farmer["headers"], plot["id"], 10, 1)
    out = _mg(client, farmer["headers"], plot["id"], "late_blight")
    assert out["trend"]["direction"] is None
    assert "not enough" in out["trend"]["note"].lower()
    assert out["trend"]["note_mr"]


def test_a_rising_series_is_called_rising_and_a_flat_one_is_not(client, farmer, plot):
    _assess(client, farmer["headers"], plot["id"], 20, 1, assessed_on="2026-08-20")
    _assess(client, farmer["headers"], plot["id"], 20, 5, assessed_on="2026-08-25")
    out = _mg(client, farmer["headers"], plot["id"], "late_blight")
    assert out["trend"]["direction"] == "rising"
    assert len(out["trend"]["points"]) == 2


# ── the ladder ─────────────────────────────────────────────────────────────
def test_the_ladder_leads_with_monitoring_and_costs_nothing(client, farmer, plot):
    out = _mg(client, farmer["headers"], plot["id"], "helicoverpa")
    first = out["ipm_ladder"][0]
    assert first["key"] == "monitor"
    assert first["cost"] == 0
    assert first["items"], "the monitoring rung must say what to actually do"
    # bilingual, from the problem's own published scouting text
    assert any(i.get("text_mr") for i in first["items"])


# ── composition, not duplication ───────────────────────────────────────────
def test_the_screen_agrees_with_the_endpoint_it_composes(client, farmer, plot):
    """The management screen must not become a second decision engine. Its
    verdict has to be the one /should-i-spray already gives."""
    mg = _mg(client, farmer["headers"], plot["id"], "helicoverpa")
    old = client.get(f"/api/decisions/{plot['id']}/should-i-spray?target=helicoverpa",
                     headers=farmer["headers"]).json()
    assert mg["decision"]["decision"] == old["decision"]["decision"]
    assert mg["decision"]["reason_code"] == old["decision"]["reason_code"]


def test_the_existing_should_i_spray_endpoint_still_works(client, farmer, plot):
    r = client.get(f"/api/decisions/{plot['id']}/should-i-spray?target=helicoverpa",
                   headers=farmer["headers"])
    assert r.status_code == 200
    assert "ipm_ladder" in r.json()


# ── the boundary ───────────────────────────────────────────────────────────
def test_one_farmer_cannot_open_another_farmers_management_screen(
        client, farmer, farmer_b, plot):
    r = client.get(f"/api/management/{plot['id']}", headers=farmer_b["headers"])
    assert r.status_code == 403


def test_one_farmer_cannot_assess_another_farmers_field(client, farmer, farmer_b, plot):
    r = _assess(client, farmer_b["headers"], plot["id"], 10, 2)
    assert r.status_code == 403


def test_anonymous_access_is_refused(client, plot):
    assert client.get(f"/api/management/{plot['id']}").status_code == 401
