"""
PRAHARI · is Gemini actually connected, end to end?

The bug these exist to prevent is the one that shipped: a key correctly set in
the deployment's environment, a backend that reads a DIFFERENT variable, and an
application that reports no error anywhere because every path falls back
silently and correctly to reference text. Everything looked healthy. Nothing
called Google.

So these tests do not ask "does the guard work" — test_llm_seam.py does that.
They ask the duller question that was actually wrong:

  · does GEMINI_API_KEY reach the code that needs a key
  · does a configured deployment report itself as configured
  · does the photograph reach the vision model when it is switched on
  · does an id the model invented score nothing
  · and does every one of those paths still answer when Google does not

The provider is never really called. `_call_gemini_vision` is the seam.
"""
from __future__ import annotations

import json

import httpx
import pytest
from conftest import _auth, scan

from app import llm
from app.config import reload_settings


# ── 1 · configuration loading ───────────────────────────────────────────────
def test_gemini_api_key_alone_configures_the_assistant(env, monkeypatch):
    """The shipped bug. GEMINI_API_KEY was set; nothing read it."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-real-one")
    s = reload_settings()
    assert s.llm_provider == "gemini"
    assert s.llm_api_key == "test-key-not-a-real-one"
    assert s.gemini_key == "test-key-not-a-real-one"


def test_an_explicit_llm_setting_is_never_overwritten_by_the_alias(env, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-side")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "openai-side")
    s = reload_settings()
    assert s.llm_provider == "openai"
    assert s.llm_api_key == "openai-side"


def test_with_no_key_the_assistant_reports_off_and_says_what_to_set(env):
    h = llm.assistant_health(env)
    assert h["configured"] is False
    assert "GEMINI_API_KEY" in h["reason"]


def test_the_health_view_never_contains_the_key(env, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-secret-value-9999")
    s = reload_settings()
    blob = json.dumps(llm.assistant_health(s)) + json.dumps(s.redacted())
    assert "sk-secret-value-9999" not in blob
    assert llm.assistant_health(s)["key_source"] == "GEMINI_API_KEY"


def test_ready_reports_the_assistant_so_render_can_be_checked(client):
    body = client.get("/api/ready").json()
    assert "assistant" in body["checks"]
    assert body["checks"]["assistant"]["configured"] is False
    assert any("language-model key" in w for w in body["soft_warnings"])
    assert "sk-" not in json.dumps(body)


# ── 2 · the vision seam ─────────────────────────────────────────────────────
def _reply(payload: dict):
    """Stand in for _call_gemini_vision, which is the only thing that would
    have talked to Google."""
    return lambda *a, **k: json.dumps(payload)


def test_the_photograph_reaches_the_model_and_the_ids_come_back(env, monkeypatch):
    seen = {}

    def fake(key, model, system, user, image_bytes, mime, timeout, max_tokens):
        seen.update(key=key, model=model, image=len(image_bytes), user=user)
        return json.dumps({"scores": {"early_blight": 0.7, "late_blight": 0.2}})

    monkeypatch.setattr(llm, "_call_gemini_vision", fake)
    out = llm.vision_scores(
        key="k", model="gemini-2.5-flash", crop="tomato",
        candidates=[{"id": "early_blight", "name": "Early blight", "scout": "target spots"},
                    {"id": "late_blight", "name": "Late blight", "scout": "water-soaked"}],
        image_bytes=b"\xff\xd8pretend-jpeg", settings=env)
    assert out["used"] is True
    assert out["scores"] == {"early_blight": 0.7, "late_blight": 0.2}
    assert seen["image"] == len(b"\xff\xd8pretend-jpeg")
    # the closed list is what the model is asked to score
    assert "early_blight" in seen["user"] and "target spots" in seen["user"]


def test_an_id_the_model_invented_scores_nothing(env, monkeypatch):
    monkeypatch.setattr(llm, "_call_gemini_vision",
                        _reply({"scores": {"early_blight": 0.4, "tobacco_mosaic": 0.9,
                                           "other": 0.8}}))
    out = llm.vision_scores(key="k", model=None, crop="tomato",
                            candidates=[{"id": "early_blight", "name": "Early blight"}],
                            image_bytes=b"x", settings=env)
    assert out["scores"] == {"early_blight": 0.4}


def test_a_model_that_cannot_read_the_photograph_returns_nothing_not_a_guess(env, monkeypatch):
    monkeypatch.setattr(llm, "_call_gemini_vision",
                        _reply({"scores": {}, "quality": "too blurred to judge"}))
    out = llm.vision_scores(key="k", model=None, crop="tomato",
                            candidates=[{"id": "early_blight", "name": "Early blight"}],
                            image_bytes=b"x", settings=env)
    assert out["used"] is False
    assert "blurred" in out["quality"]


def test_no_key_means_the_vision_model_is_never_called(env, monkeypatch):
    def explode(*a, **k):                       # pragma: no cover
        raise AssertionError("called Google without a key")
    monkeypatch.setattr(llm, "_call_gemini_vision", explode)
    out = llm.vision_scores(key="", model=None, crop="tomato",
                            candidates=[{"id": "early_blight"}], image_bytes=b"x",
                            settings=env)
    assert out["used"] is False
    assert "no Gemini key" in out["reason"]


def test_a_timeout_is_reported_as_a_timeout_and_not_as_an_empty_field(env, monkeypatch):
    def slow(*a, **k):
        raise httpx.TimeoutException("too slow")
    monkeypatch.setattr(llm, "_call_gemini_vision", slow)
    out = llm.vision_scores(key="k", model=None, crop="tomato",
                            candidates=[{"id": "early_blight"}], image_bytes=b"x",
                            settings=env)
    assert out["used"] is False
    assert "did not answer within" in out["reason"]


def test_a_quota_error_opens_a_cooldown_instead_of_hammering_the_provider(env, monkeypatch):
    calls = {"n": 0}

    def refuse(*a, **k):
        calls["n"] += 1
        raise httpx.HTTPStatusError(
            "429", request=httpx.Request("POST", "https://x"),
            response=httpx.Response(429, request=httpx.Request("POST", "https://x")))

    monkeypatch.setattr(llm, "_call_gemini_vision", refuse)
    args = {"key": "quota-key", "model": None, "crop": "tomato",
            "candidates": [{"id": "early_blight"}], "image_bytes": b"x", "settings": env}
    first = llm.vision_scores(**args)
    second = llm.vision_scores(**args)
    assert first["quota"] is True
    assert second["quota"] is True and "not retried" in second["reason"]
    assert calls["n"] == 1, "the second attempt must not reach the provider"


def test_a_malformed_body_is_rejected_rather_than_half_read(env, monkeypatch):
    monkeypatch.setattr(llm, "_call_gemini_vision", lambda *a, **k: "I think it's blight!")
    out = llm.vision_scores(key="k", model=None, crop="tomato",
                            candidates=[{"id": "early_blight"}], image_bytes=b"x",
                            settings=env)
    assert out["used"] is False


# ── 3 · through the real scan endpoint ──────────────────────────────────────
@pytest.fixture
def gemini_vision(env, monkeypatch):
    """A deployment with VISION_PROVIDER=gemini and a key."""
    monkeypatch.setenv("VISION_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-real-one")
    return reload_settings()


@pytest.fixture
def gemini_client(gemini_vision):
    from fastapi.testclient import TestClient

    from app.main import create_app
    with TestClient(create_app(gemini_vision)) as c:
        yield c


def _farmer_plot(c, phone: str):
    h = _auth(c.post("/api/auth/register", json={
        "full_name": "Rajesh Pawar", "password": "strong-pass-2026",
        "phone": phone, "lang": "mr", "taluka": "niphad", "village": "Niphad"}))
    p = c.post("/api/plots", headers=h, json={
        "name": "Tomato block 1", "crop": "tomato", "area_acre": 2.0,
        "sown_on": "2026-06-25", "lat": 20.0810, "lng": 74.1100,
        "location_source": "gps", "soil": "medium black", "irrigation": "drip"})
    assert p.status_code == 201, p.text
    return h, p.json()


def test_a_scan_runs_through_the_vision_model_and_says_which_engine_ran(
        gemini_client, monkeypatch):
    monkeypatch.setattr(
        llm, "_call_gemini_vision",
        _reply({"scores": {"early_blight": 0.82, "late_blight": 0.05,
                           "septoria_tomato": 0.04}}))
    h, p = _farmer_plot(gemini_client, "9812345678")
    r = scan(gemini_client, h, p["id"])
    assert r.status_code == 201, r.text
    out = r.json()

    dx = out["diagnosis"]
    assert dx["engine"]["engine"] == "gemini"
    assert dx["engine"]["is_neural_model"] is True
    assert "not trained on this crop" in dx["engine"]["label"]
    # a general model never carries an accuracy claim
    assert dx["engine"]["model_version"] == "gemini-2.5-flash"


def test_when_google_is_down_the_scan_still_returns_a_diagnosis(
        gemini_client, monkeypatch):
    """The whole point. A provider outage costs the engine label, not the
    farmer's answer."""
    def down(*a, **k):
        raise httpx.ConnectError("no route to host")
    monkeypatch.setattr(llm, "_call_gemini_vision", down)

    h, p = _farmer_plot(gemini_client, "9812345679")
    r = scan(gemini_client, h, p["id"])

    assert r.status_code == 201
    dx = r.json()["diagnosis"]
    assert dx is not None
    # fell back to the measured-feature engine, and says so rather than
    # claiming a neural model ran
    assert dx["engine"]["is_neural_model"] is False
    assert "not a neural network" in dx["engine"]["label"]


def test_the_vision_model_is_off_unless_it_is_switched_on(client):
    """A deployment that sets GEMINI_API_KEY for AgriDoc does not silently
    acquire a new diagnosis engine."""
    body = client.get("/api/ready").json()
    assert body["checks"]["vision"]["engine"] == "unavailable"


def test_a_partial_score_set_does_not_crash_the_scan(gemini_client, monkeypatch):
    """The regression. Tomato has six known problems; a model is free to
    mention two. The posterior indexes every candidate and multiplies, so a
    missing id used to be a TypeError halfway through — a 500 on a farmer's
    scan, from a model that answered correctly."""
    monkeypatch.setattr(llm, "_call_gemini_vision",
                        _reply({"scores": {"early_blight": 0.9}}))
    h, p = _farmer_plot(gemini_client, "9812345680")
    r = scan(gemini_client, h, p["id"])
    assert r.status_code == 201, r.text
    dx = r.json()["diagnosis"]
    assert dx["engine"]["engine"] == "gemini"
    # every problem for the crop is still in the differential, floored not deleted
    ids = {c["id"] for c in dx["differential"]}
    assert ids and "early_blight" in ids


def test_an_unscored_problem_is_floored_not_eliminated():
    from app.vision_service import _restrict
    out = _restrict({"early_blight": 0.8}, ["early_blight", "late_blight", "healthy"],
                    engine="gemini", model_name="m", version="v", ms=1,
                    display="d", is_neural=True)
    assert out.probs is not None
    assert set(out.probs) == {"early_blight", "late_blight", "healthy"}
    assert out.probs["early_blight"] > 0.9
    assert 0 < out.probs["late_blight"] < 0.01
    assert abs(sum(out.probs.values()) - 1.0) < 1e-9


# ── 4 · AgriDoc reaches the same key ────────────────────────────────────────
def test_agridoc_uses_the_deployment_gemini_key(env, monkeypatch):
    """The other half of the shipped bug: the assistant looked up
    LLM_PROVIDER/LLM_API_KEY, so a deployment configured with GEMINI_API_KEY
    reported `available: false` and answered from templates forever."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-real-one")
    s = reload_settings()

    from fastapi.testclient import TestClient

    from app.main import create_app
    seen = {}

    def fake(key, model, system, user, timeout, max_tokens):
        seen.update(key=key, model=model)
        return "Aaj tumchya shetat kahi faylay nahi."

    monkeypatch.setitem(llm._CALL, "gemini", fake)
    with TestClient(create_app(s)) as c:
        h, p = _farmer_plot(c, "9812345681")
        body = c.post("/api/saathi/ask", headers=h,
                      json={"question": "what should I do about the leaves",
                            "plot_id": p["id"], "lang": "en"}).json()

    assert body["llm"]["available"] is True, "the deployment key never reached AgriDoc"
    assert seen.get("key") == "test-key-not-a-real-one"
    assert seen.get("model") == "gemini-2.5-flash"


def test_agridoc_still_answers_when_google_is_down(env, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-real-one")
    s = reload_settings()

    from fastapi.testclient import TestClient

    from app.main import create_app

    def down(*a, **k):
        raise httpx.ConnectError("no route to host")
    monkeypatch.setitem(llm._CALL, "gemini", down)

    with TestClient(create_app(s)) as c:
        h, p = _farmer_plot(c, "9812345682")
        r = c.post("/api/saathi/ask", headers=h,
                   json={"question": "what should I do about the leaves",
                         "plot_id": p["id"], "lang": "en"})

    assert r.status_code == 200
    body = r.json()
    assert body["llm"]["used"] is False
    assert body["answer"], "the retrieved answer must still be there"
