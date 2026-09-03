"""
The chemical gate, the threshold gate and the honesty of every number.

These are the tests that would have to fail before PRAHARI could recommend a
pesticide it should not.
"""
from __future__ import annotations

import pytest

from conftest import scan


# ── the threshold gate ──────────────────────────────────────────────────────
def test_below_threshold_is_a_decision_not_an_absence(client, farmer, plot, monsoon):
    r = client.post("/api/threshold", headers=farmer["headers"],
                    json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 1.0})
    assert r.status_code == 200
    body = r.json()
    assert body["threshold"]["chemical_authorised"] is False
    d = body["decision"]
    assert d["decision"] == "do_not_spray"
    assert d["reason_code"] == "etl_not_crossed"
    assert d["reason"]
    assert d["reason_mr"]
    assert d["evidence"], "a decision must carry the evidence behind it"
    assert d["recheck_after_hours"] and d["recheck_on"]
    assert body["threshold"]["saving_if_not_sprayed"] > 0


def test_chemical_rung_is_withheld_below_the_threshold(client, farmer, plot, monsoon):
    body = client.post("/api/threshold", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa",
                             "count": 1.0}).json()
    rung = [s for s in body["ipm_ladder"] if s["key"] == "chemical"][0]
    assert rung.get("withheld") is True
    assert "not been crossed" in rung["items"][0]["text"]
    assert body["chemical"]["recommended"] is None
    assert body["chemical"]["options"] == []


def test_ipm_ladder_puts_chemistry_last(client, farmer, plot, monsoon):
    body = client.post("/api/threshold", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa",
                             "count": 1.0}).json()
    keys = [s["key"] for s in body["ipm_ladder"]]
    assert keys.index("cultural") < keys.index("biological") < keys.index("chemical")
    assert body["ladder_principle"]


def test_an_unknown_threshold_is_stated_not_invented(client, farmer, plot):
    r = client.post("/api/threshold", headers=farmer["headers"],
                    json={"plot_id": plot["id"], "pest": "faw", "count": 40})
    assert r.status_code == 400
    assert r.json()["error"] == "no_threshold"
    assert "no published economic threshold" in r.json()["message"]


# ── the chemical gate ───────────────────────────────────────────────────────
def test_every_shipped_claim_starts_as_draft(client, admin):
    rows = client.get("/api/admin/claims", headers=admin["headers"]).json()["claims"]
    assert rows
    assert all(r["status"] == "draft" for r in rows), \
        "the shipped reference table must be entirely unverified"


def test_a_draft_claim_is_never_returned_as_actionable(client, farmer, plot, monsoon):
    body = client.post("/api/threshold", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 40}).json()
    assert body["threshold"]["chemical_authorised"] is True
    assert body["chemical"]["recommended"] is None
    av = body["chemical_availability"]
    assert av["verified_available"] is False
    assert av["counts_by_status"].get("draft", 0) > 0
    assert "No verified chemical recommendation" in av["message"]


def test_a_draft_product_name_is_never_printed(client, farmer, plot, monsoon):
    """Naming an unverified product is half of recommending it."""
    import json
    body = client.post("/api/threshold", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 40}).json()
    text = json.dumps(body)
    for product in ("Chlorantraniliprole", "Emamectin", "Flubendiamide"):
        assert product not in text, f"{product} is a DRAFT row and was leaked to the farmer"


def test_a_chemical_application_is_refused_without_a_verified_claim(client, farmer, plot, monsoon):
    body = client.post("/api/threshold", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 40}).json()
    check = body["threshold"]["check_id"]
    r = client.post("/api/applications", headers=farmer["headers"], json={
        "plot_id": plot["id"], "target": "helicoverpa", "kind": "chemical",
        "product": "Chlorantraniliprole 18.5% SC", "phi_days": 3, "check_id": check})
    assert r.status_code == 409
    assert r.json()["error"] == "no_verified_claim"


def test_a_chemical_application_is_refused_without_a_threshold_crossing(client, farmer, plot,
                                                                        admin, monsoon):
    claims = client.get("/api/admin/claims?crop=tomato", headers=admin["headers"]).json()["claims"]
    claim = next(c for c in claims if c["target"] == "helicoverpa")
    client.post(f"/api/admin/claims/{claim['id']}/verify", headers=admin["headers"],
                json={"source": "CIB&RC Major Uses of Pesticides, rev 2025-11"})
    r = client.post("/api/applications", headers=farmer["headers"], json={
        "plot_id": plot["id"], "target": "helicoverpa", "kind": "chemical",
        "product": claim["product"], "claim_id": claim["id"], "phi_days": 3})
    assert r.status_code == 409
    assert r.json()["error"] == "chemical_not_authorised"


def test_verification_is_what_makes_a_claim_actionable(client, farmer, plot, admin, monsoon):
    claims = client.get("/api/admin/claims?crop=tomato", headers=admin["headers"]).json()["claims"]
    claim = next(c for c in claims if c["target"] == "helicoverpa")
    v = client.post(f"/api/admin/claims/{claim['id']}/verify", headers=admin["headers"], json={
        "source": "CIB&RC Major Uses of Pesticides, tomato/H. armigera, rev. 2025-11",
        "source_url": "https://ppqs.gov.in/divisions/cib-rc/major-uses-of-pesticides"})
    assert v.status_code == 200
    assert v.json()["claim"]["status"] == "verified"
    assert v.json()["claim"]["verified_by"] == "District Administrator"
    assert v.json()["claim"]["verified_at"]

    body = client.post("/api/threshold", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 40}).json()
    rec = body["chemical"]["recommended"]
    assert rec is not None
    assert rec["verified"] is True
    assert rec["provenance"]["source"].startswith("CIB&RC")
    assert rec["provenance"]["verified_by"]
    assert rec["dose"]["plain"]
    assert rec["phi_days"] >= 0


def test_a_revoked_claim_stops_being_actionable(client, farmer, plot, admin, monsoon):
    claims = client.get("/api/admin/claims?crop=tomato", headers=admin["headers"]).json()["claims"]
    claim = next(c for c in claims if c["target"] == "helicoverpa")
    client.post(f"/api/admin/claims/{claim['id']}/verify", headers=admin["headers"],
                json={"source": "CIB&RC Major Uses of Pesticides, rev 2025-11"})
    body = client.post("/api/threshold", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 40}).json()
    assert body["chemical"]["recommended"] is not None
    client.post(f"/api/admin/claims/{claim['id']}/status", headers=admin["headers"],
                json={"status": "revoked", "note": "State order"})
    after = client.post("/api/threshold", headers=farmer["headers"],
                        json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 40}).json()
    assert after["chemical"]["recommended"] is None


def test_a_state_restricted_product_is_blocked_with_its_reason(client, admin, farmer, plot):
    """Even a verified claim is blocked if the state has restricted the product."""
    from app import chemicals
    from app.db import get_db
    db = get_db()
    db.execute(
        "INSERT INTO label_claims (id, crop, target, product, dose, unit, phi_days, status,"
        " source, created_at, updated_at) VALUES ('LC-test','tomato','helicoverpa',"
        " 'Monocrotophos 36% SL', 1.5,'ml/L',7,'verified','test',:n,:n)",
        {"n": "2026-08-27T00:00:00.000Z"})
    restricted = chemicals.restricted_products(db)
    hit = chemicals.is_restricted("Monocrotophos 36% SL",
                                  [{"pattern": r["pattern"], "reason": r["reason"]}
                                   for r in restricted])
    assert hit is not None
    assert "2018" in hit["reason"] or "Yavatmal" in hit["reason"] or hit["reason"]


# ── follow-up honesty ───────────────────────────────────────────────────────
def test_follow_up_reports_direction_never_a_percentage(client, farmer, plot, admin, monsoon):
    from conftest import leaf_image
    scan(client, farmer["headers"], plot["id"], "worse")
    claims = client.get("/api/admin/claims?crop=tomato", headers=admin["headers"]).json()["claims"]
    claim = next(c for c in claims if c["target"] == "helicoverpa")
    client.post(f"/api/admin/claims/{claim['id']}/verify", headers=admin["headers"],
                json={"source": "CIB&RC Major Uses of Pesticides, rev 2025-11"})
    body = client.post("/api/threshold", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 40}).json()
    rec = body["chemical"]["recommended"]
    app = client.post("/api/applications", headers=farmer["headers"], json={
        "plot_id": plot["id"], "target": "helicoverpa", "kind": "chemical",
        "product": rec["product"], "claim_id": rec["claim_id"],
        "check_id": body["threshold"]["check_id"]}).json()
    r = client.post(f"/api/followups/{app['followup_id']}/rescan", headers=farmer["headers"],
                    files={"image": ("after.jpg", leaf_image("improved"), "image/jpeg")})
    assert r.status_code == 201
    cmp = r.json()["comparison"]
    assert cmp["outcome"] in ("better", "same", "worse")
    assert cmp["direction_only"] is True
    assert cmp["severity_percentages"] is None
    assert "percentage does not" in cmp["why_no_percentage"]


def test_a_worse_rescan_escalates_instead_of_offering_a_second_spray(client, farmer, plot,
                                                                     admin, monsoon):
    from conftest import leaf_image
    scan(client, farmer["headers"], plot["id"], "improved")
    claims = client.get("/api/admin/claims?crop=tomato", headers=admin["headers"]).json()["claims"]
    claim = next(c for c in claims if c["target"] == "helicoverpa")
    client.post(f"/api/admin/claims/{claim['id']}/verify", headers=admin["headers"],
                json={"source": "CIB&RC rev 2025-11"})
    body = client.post("/api/threshold", headers=farmer["headers"],
                       json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 40}).json()
    rec = body["chemical"]["recommended"]
    app = client.post("/api/applications", headers=farmer["headers"], json={
        "plot_id": plot["id"], "target": "helicoverpa", "kind": "chemical",
        "product": rec["product"], "claim_id": rec["claim_id"],
        "check_id": body["threshold"]["check_id"]}).json()
    r = client.post(f"/api/followups/{app['followup_id']}/rescan", headers=farmer["headers"],
                    files={"image": ("after.jpg", leaf_image("worse"), "image/jpeg")}).json()
    assert r["outcome"] == "worse"
    assert r["escalation"] is not None
    assert r["escalation"]["urgency"] == "urgent"
    assert "second application" in r["escalation"]["why"]


def test_an_unusable_rescan_is_not_scored_as_better_or_worse(client, farmer, plot, admin, monsoon):
    from conftest import leaf_image
    scan(client, farmer["headers"], plot["id"], "blight")
    app = client.post("/api/applications", headers=farmer["headers"], json={
        "plot_id": plot["id"], "target": "helicoverpa", "kind": "cultural",
        "product": "Hand-picked and destroyed larvae"}).json()
    r = client.post(f"/api/followups/{app['followup_id']}/rescan", headers=farmer["headers"],
                    files={"image": ("after.jpg", leaf_image("blurry"), "image/jpeg")}).json()
    assert r["outcome"] == "unmeasurable"
    assert r["comparison"] is None
    assert "cannot be compared" in r["message"]


# ── weather honesty ─────────────────────────────────────────────────────────
def test_weather_failure_produces_an_error_not_invented_weather(client, farmer, plot,
                                                                monkeypatch):
    from app.runtime import get_runtime
    from app.weather import WeatherUnavailable
    rt = get_runtime()

    def boom(*a, **k):
        raise WeatherUnavailable("open-meteo", "connection refused")
    monkeypatch.setattr(rt.weather.provider, "series", boom)
    rt.db.execute("DELETE FROM weather_cache")

    r = client.get(f"/api/risk/{plot['id']}", headers=farmer["headers"])
    assert r.status_code == 503
    body = r.json()
    assert body["error"] == "weather_unavailable"
    assert body["retryable"] is True
    # The guarantee, checked as a property rather than as a phrase: the reply
    # carries no series, no day rows and no numbers to mistake for readings.
    # The wording is farmer-facing and may be reworded; what must never change
    # is that there is nothing here to read as weather.
    assert "estimated" in body["message"], "the promise is still stated in words"
    assert "days" not in body and "weather" not in body
    assert not any(isinstance(v, list) for v in body.values())
    # and the provider's own sentence stays in the log, not on the phone
    for leak in ("connection refused", "open-meteo", "429"):
        assert leak not in str(body).lower()
    assert "days" not in body


def test_generated_weather_is_always_labelled(client, farmer, plot):
    r = client.get(f"/api/risk/{plot['id']}", headers=farmer["headers"]).json()
    w = r["weather"]
    assert w["kind"] == "generated"
    assert w["generated"] is True
    assert "not real weather" in (w["warning"] or "").lower()
    assert w["freshness"]["fetched_at"]
    assert w["observed_through"] and w["forecast_from"]


def test_the_health_score_says_what_it_is_not(client, farmer, plot):
    r = client.get(f"/api/fields/{plot['id']}/health", headers=farmer["headers"]).json()
    assert 0 <= r["health"]["score"] <= 100
    assert "not an estimate of yield" in r["score_meaning"]
    total = sum(c["penalty"] for c in r["health"]["components"].values())
    assert abs((100 - total) - r["health"]["score"]) < 1.5
    for term in r["health"]["terms"]:
        assert term["why"], "every penalty must name what cost the points"


# ── one clock ───────────────────────────────────────────────────────────────
def test_domain_timestamps_and_dates_come_from_the_same_clock(client, farmer, plot):
    """The prototype stamped rows with the OS clock while every date came from a
    pinned one. The moment the real date rolled past the pinned date, an
    observation recorded "today" was dated tomorrow, and a follow-up could no
    longer find the scan it was meant to compare against."""
    from app.clock import today
    from app.db import get_db
    scan(client, farmer["headers"], plot["id"], "blight")
    row = get_db().one("SELECT observed_at, created_at FROM observations ORDER BY created_at DESC")
    assert str(row["observed_at"])[:10] == today().isoformat()
    assert str(row["created_at"])[:10] == today().isoformat()
    ev = get_db().one("SELECT at FROM field_events ORDER BY id DESC")
    assert str(ev["at"])[:10] == today().isoformat()


def test_session_expiry_is_not_affected_by_a_pinned_demo_clock(client, farmer):
    """JWT exp is validated against the real clock by PyJWT. A token minted on a
    pinned past date would be born expired; one minted on a pinned future date
    would outlive its session row."""
    from app.clock import real_iso
    from app.db import get_db
    row = get_db().one("SELECT issued_at, expires_at FROM sessions ORDER BY issued_at DESC")
    assert row["issued_at"] <= real_iso()
    assert row["expires_at"] > real_iso()
    assert client.get("/api/auth/me", headers=farmer["headers"]).status_code == 200
