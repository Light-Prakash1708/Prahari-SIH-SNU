"""
DETECT, and the camera's right to refuse.

The first test in this file is the most important one in the suite: a
photograph that fails the quality gate must not produce a diagnosis, and no
amount of answering questions may talk the system out of that.
"""
from __future__ import annotations

import pytest

from conftest import leaf_image, scan


def test_a_bad_photograph_is_never_diagnosed(client, farmer, plot):
    for kind in ("blurry", "dark"):
        r = scan(client, farmer["headers"], plot["id"], kind)
        assert r.status_code == 201, r.text
        body = r.json()
        dx = body["diagnosis"]
        assert dx["abstain"] is True, kind
        assert dx["reason"] == "photo-quality", kind
        # No differential underneath an abstention for a quality failure.
        assert dx["differential"] == [], kind
        assert dx["top"] is None, kind
        # And the guidance that fixes it.
        assert body["quality"]["failures"], kind
        assert body["quality"]["failures"][0]["msg"]
        assert body["quality"]["failures"][0]["mr"]


def test_questions_cannot_override_a_quality_failure(client, farmer, plot):
    obs = scan(client, farmer["headers"], plot["id"], "blurry").json()["observation"]["id"]
    q = client.get(f"/api/observations/{obs}/questions", headers=farmer["headers"]).json()
    assert q["blocked"] is True
    assert q["questions"] == []
    a = client.post(f"/api/observations/{obs}/answers", headers=farmer["headers"],
                    json={"answers": {"onset": "today", "spread": "fast"}})
    assert a.status_code == 409
    assert a.json()["error"] == "quality_block"


def test_a_usable_photograph_produces_a_differential_with_evidence(client, farmer, plot):
    body = scan(client, farmer["headers"], plot["id"], "blight").json()
    dx = body["diagnosis"]
    assert dx["differential"], "a usable photograph must yield candidates"
    assert len(dx["differential"]) >= 2, "never a single forced answer"
    top = dx["differential"][0]
    assert 0 < top["confidence"] <= 0.99, "confidence is capped below certainty"
    assert top["supporting"] or top["contradicting"]
    ranked = [c["confidence"] for c in dx["differential"]]
    assert ranked == sorted(ranked, reverse=True)


def test_confidence_is_never_reported_as_certainty(client, farmer, plot):
    for kind in ("blight", "powdery", "improved"):
        body = scan(client, farmer["headers"], plot["id"], kind).json()
        for c in body["diagnosis"]["differential"]:
            assert c["confidence"] <= 0.99


def test_the_engine_is_never_called_ai_when_no_model_is_configured(client, farmer, plot):
    body = scan(client, farmer["headers"], plot["id"], "blight").json()
    engine = body["diagnosis"]["engine"]
    assert engine["is_neural_model"] is False
    label = engine["label"].lower()
    assert "not a neural network" in label
    assert "ai" not in label.replace("prahari", "")


def test_model_unavailable_is_stated_when_the_feature_engine_is_off(tmp_path, monkeypatch):
    """With no trained model AND the feature engine disabled, PRAHARI says the
    model is unavailable — it does not dress heuristics up as inference."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/p.db")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("WEATHER_PROVIDER", "demo")
    monkeypatch.setenv("VISION_PROVIDER", "none")
    monkeypatch.setenv("ALLOW_FEATURE_ENGINE", "false")
    monkeypatch.setenv("STORAGE_LOCAL_DIR", str(tmp_path / "u"))
    monkeypatch.setenv("JWT_SECRET", "test-secret-long-enough-to-be-accepted-1234567890")
    monkeypatch.setenv("PRAHARI_TODAY", "2026-08-27")
    monkeypatch.setenv("LOG_LEVEL", "CRITICAL")
    from app.config import reload_settings
    from app.db import reset_db
    from app.main import create_app
    from fastapi.testclient import TestClient
    reset_db()
    s = reload_settings()
    with TestClient(create_app(s)) as c:
        rr = c.post("/api/auth/register", json={
            "full_name": "Feature Off", "password": "strong-pass-2026",
            "phone": "9812345600", "taluka": "niphad"})
        assert rr.status_code == 201, rr.text
        H = {"Authorization": f"Bearer {rr.json()['access_token']}"}
        p = c.post("/api/plots", headers=H, json={
            "name": "p", "crop": "tomato", "area_acre": 1, "sown_on": "2026-06-25",
            "lat": 20.08, "lng": 74.11, "location_source": "gps"}).json()
        r = c.post("/api/observations", headers=H,
                   files={"image": ("l.jpg", leaf_image("blight"), "image/jpeg")},
                   data={"plot_id": p["id"]})
        dx = r.json()["diagnosis"]
        assert dx["abstain"] is True
        assert dx["reason"] == "model-unavailable"
        assert "AI model unavailable" in dx["explain"]
        assert dx["differential"] == []


def test_onnx_seam_actually_runs_a_model(tmp_path, monkeypatch):
    """A plumbing test for the ONNX path with a fixture model of RANDOM weights.
    It proves the seam loads, infers and restricts classes to the crop. It makes
    no accuracy claim whatsoever — the model was never trained."""
    from pathlib import Path
    fixture = Path(__file__).resolve().parent / "fixtures" / "tiny_vision.onnx"
    if not fixture.exists():
        pytest.skip("ONNX fixture not built — run tests/fixtures/build_fixture_model.py")
    monkeypatch.setenv("VISION_PROVIDER", "onnx")
    monkeypatch.setenv("VISION_MODEL_PATH", str(fixture))
    monkeypatch.setenv("VISION_MODEL_LABELS", str(fixture.parent / "labels.json"))
    monkeypatch.setenv("VISION_MODEL_VERSION", "test-plumbing-0.0")
    from app.config import reload_settings
    from app.vision_service import VisionService
    s = reload_settings()
    v = VisionService(s)
    assert v.health()["ready"] is True
    out = v.classify(leaf_image("blight"), "tomato",
                     ["late_blight", "early_blight", "healthy"])
    assert out.probs is not None
    assert set(out.probs) <= {"late_blight", "early_blight", "healthy"}
    assert abs(sum(out.probs.values()) - 1.0) < 1e-6
    assert out.engine == "onnx"
    desc = v.engine_descriptor(out)
    assert desc["is_neural_model"] is True
    assert desc["evaluated"] is False
    assert "makes no accuracy claim" in desc["caveat"]


def test_every_diagnosis_records_its_engine_and_version(client, farmer, plot):
    from app.db import get_db
    scan(client, farmer["headers"], plot["id"], "blight")
    rows = get_db().rows("SELECT engine, model_version FROM diagnoses")
    assert rows
    for r in rows:
        assert r["engine"]
        assert r["model_version"]


def test_every_covered_crop_has_a_reference_set_and_a_null_hypothesis(client, farmer):
    """Cotton, soybean and pigeonpea used to abstain with 'crop-not-covered' —
    the camera simply refused to look at three of the seven crops PRAHARI
    claims to serve. They now carry reference sets, and the property that
    matters is that each set contains BOTH real diseases and the healthy
    template: a differential with no null hypothesis has to name a disease."""
    from app import reference
    for crop in reference.CROPS:
        assert reference.crop_has_vision_reference(crop), f"{crop} has no reference set"
        problems = reference.problems_for_crop(crop)
        assert "healthy" in problems, f"{crop} has no healthy template to lose to"
        real = [k for k in problems if k not in ("healthy", "nitrogen_deficiency")]
        assert len(real) >= 2, f"{crop} has fewer than two real candidates"


def test_a_photograph_matching_nothing_in_this_crops_set_abstains(client, farmer):
    """A cotton field photographed with a tomato-blight symptom pattern must
    NOT be diagnosed as the nearest cotton disease. A posterior is a ratio and
    always names a winner; the out-of-distribution floor is what stops that
    winner from being an answer."""
    p = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Cotton east", "crop": "cotton", "area_acre": 3, "sown_on": "2026-06-01",
        "lat": 20.33, "lng": 74.24, "location_source": "gps"}).json()
    dx = scan(client, farmer["headers"], p["id"], "blight").json()["diagnosis"]
    assert dx["abstain"] is True
    assert dx["reason"] in ("unfamiliar-pattern", "no-clear-candidate", "evidence-conflict")


def test_a_disease_with_no_infection_model_says_why_instead_of_vanishing(client, farmer):
    """Three of the new diseases are vector-borne or soil-borne, so no weather
    model can forecast them. They stay on the risk board with level
    'unforecast' and the reason — an empty risk screen reads as 'this crop has
    no diseases', which is the opposite of true."""
    p = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Cotton east", "crop": "cotton", "area_acre": 3, "sown_on": "2026-06-01",
        "lat": 20.33, "lng": 74.24, "location_source": "gps"}).json()
    board = client.get(f"/api/risk/{p['id']}", headers=farmer["headers"]).json()
    diseases = [b for b in board["board"] if b["kind"] == "disease"]
    assert diseases, "the cotton risk board is empty"
    unforecast = [b for b in diseases if b.get("level") == "unforecast"]
    assert unforecast, "no cotton disease is marked unforecast"
    for b in unforecast:
        assert b["no_model_note"], f"{b['id']} is unforecast with no reason given"


def test_a_borrowed_model_carries_its_caveat_wherever_it_appears(client, farmer):
    """Pigeonpea Phytophthora blight runs the Hutton criteria, which were
    validated for a DIFFERENT Phytophthora on a different crop. Wherever that
    model fires, the borrowing is stated."""
    from app import reference
    p = reference.DISEASES["phytophthora_blight_pigeonpea"]
    assert p["model"] == "hutton"
    assert "not for this pathogen" in p["model_caveat"].lower()
    plot = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Tur block", "crop": "pigeonpea", "area_acre": 2, "sown_on": "2026-06-15",
        "lat": 20.33, "lng": 74.24, "location_source": "gps"}).json()
    board = client.get(f"/api/risk/{plot['id']}", headers=farmer["headers"]).json()
    row = next(b for b in board["board"] if b["id"] == "phytophthora_blight_pigeonpea")
    assert row["model_caveat"]


def test_uploads_are_validated_and_sanitised(client, farmer, plot):
    r = client.post("/api/observations", headers=farmer["headers"],
                    files={"image": ("evil.jpg", b"<?php system($_GET[0]); ?>", "image/jpeg")},
                    data={"plot_id": plot["id"]})
    assert r.status_code == 400
    assert r.json()["error"] == "not_an_image"


def test_stored_image_is_reencoded_not_the_uploaded_bytes(client, farmer, plot):
    from app.db import get_db
    raw = leaf_image("blight")
    obs = scan(client, farmer["headers"], plot["id"], "blight").json()["observation"]["id"]
    row = get_db().one("SELECT sha256, bytes FROM observation_images WHERE observation_id = :o",
                       {"o": obs})
    import hashlib
    assert row["sha256"] != hashlib.sha256(raw).hexdigest(), \
        "the stored image must be re-encoded, not the client's bytes"


def test_a_duplicate_client_ref_does_not_create_a_second_observation(client, farmer, plot):
    ref = "offline-abc-123"
    a = scan(client, farmer["headers"], plot["id"], "blight", client_ref=ref).json()
    b = scan(client, farmer["headers"], plot["id"], "blight", client_ref=ref).json()
    assert a["observation"]["id"] == b["observation"]["id"]
    assert b["deduplicated"] is True


def test_every_reference_template_is_recoverable_from_its_own_signature():
    """The reference set must be SEPARABLE. If two templates sit close enough in
    feature space that one recovers the other, the engine will confidently
    return the wrong disease for a textbook-perfect photograph — and there is no
    photograph that would reveal it, because the failure is in the reference
    data, not the image.

    This walks every crop's differential, feeds each disease its OWN published
    signature, and asserts the engine names it back."""
    from app import diagnose, reference
    misses = []
    for crop in reference.CROPS:
        problems = reference.problems_for_crop(crop)
        prior = {k: 1 / len(problems) for k in problems}
        for pid, p in problems.items():
            feats = dict(p["feat"])
            feats["exposure"] = 0.5
            feats["quality"] = {"ok": True, "failures": [], "score": 0.9}
            out = diagnose.diagnose(feats, crop, prior, problems, {}, None)
            top = out["ranked"][0]["id"] if out["ranked"] else None
            if top != pid:
                misses.append(f"{crop}/{pid} recovered as {top}")
    assert not misses, "reference templates collide: " + "; ".join(misses)


def test_close_templates_are_close_for_a_real_reason():
    """Purple blotch and Stemphylium blight on onion sit within a few points of
    each other. That is not a defect — they genuinely co-occur on the same leaf
    and the field distinction is subtle. The property worth asserting is that
    the engine does not manufacture a confident gap where none exists."""
    from app import diagnose, reference
    problems = reference.problems_for_crop("onion")
    prior = {k: 1 / len(problems) for k in problems}
    feats = dict(problems["purple_blotch"]["feat"])
    feats["exposure"] = 0.5
    feats["quality"] = {"ok": True, "failures": [], "score": 0.9}
    out = diagnose.diagnose(feats, "onion", prior, problems, {}, None)
    ranked = out["ranked"]
    assert ranked[0]["id"] == "purple_blotch"
    assert ranked[0]["posterior"] < 0.85, \
        "a confident answer between two look-alike onion blights is a calibration failure"
