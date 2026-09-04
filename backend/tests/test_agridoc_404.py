"""
PRAHARI · the AgriDoc 404

What was on the screen: a correct answer about weather and risk, and under it
"Model version discarded — provider returned HTTP 404". Which reads like the
answer is broken. It was not — the answer was the retrieved one, which is the
one PRAHARI trusts anyway. What had failed was the rewording.

The 404 came from Google, not from PRAHARI's router: `/api/saathi/ask` returned
200 the whole time. Scan worked because it calls the id in GEMINI_VISION_MODEL;
AgriDoc failed because it calls whatever is stored against the account's key or
set in LLM_MODEL — a value typed once that outlived the model it named. Same
key, same host, same API version. A 404 from generateContent means "no such
model", never "bad key".

Three ways that id goes wrong, all three exercised here: retired, prefixed with
"models/", and simply wrong.
"""
from __future__ import annotations

import httpx
import pytest
from conftest import _auth

from app import llm
from app.config import reload_settings


def _404(*a, **k):
    raise httpx.HTTPStatusError(
        "404", request=httpx.Request("POST", "https://x"),
        response=httpx.Response(404, request=httpx.Request("POST", "https://x")))


# ── the id, before the call ─────────────────────────────────────────────────
def test_an_unset_model_uses_the_default():
    assert llm.resolve_model("gemini", None) == ("gemini-2.5-flash", None)
    assert llm.resolve_model("gemini", "   ") == ("gemini-2.5-flash", None)


def test_a_retired_model_is_replaced_and_the_substitution_is_named():
    got, note = llm.resolve_model("gemini", "gemini-1.5-flash")
    assert got == "gemini-2.5-flash"
    assert "retired" in note and "gemini-1.5-flash" in note


def test_the_models_prefix_is_stripped_because_the_url_adds_it():
    """`models/gemini-2.5-flash` produces
    .../v1beta/models/models/gemini-2.5-flash:generateContent — a 404 for a
    model id that is otherwise perfectly current."""
    got, note = llm.resolve_model("gemini", "models/gemini-2.5-flash")
    assert got == "gemini-2.5-flash"
    assert "models/" in note


def test_a_current_model_is_left_exactly_alone():
    assert llm.resolve_model("gemini", "gemini-2.5-pro") == ("gemini-2.5-pro", None)


# ── the id, after the call ──────────────────────────────────────────────────
def test_a_404_falls_back_to_the_default_and_answers(env, monkeypatch):
    """A model id nothing can repair in advance. The key is fine — 404 is not
    401 — so the question is still answerable."""
    calls = []

    def gemini(key, model, system, user, timeout, max_tokens):
        calls.append(model)
        if model == "typo-flash-9":
            _404()
        return "Your count is below the threshold."

    monkeypatch.setitem(llm._CALL, "gemini", gemini)
    out = llm.rephrase(provider="gemini", key="k", model="typo-flash-9",
                       question="how is my field", facts={"prahari_answer": "x"},
                       lang="en", settings=env)
    assert out["used"] is True, out.get("reason")
    assert calls == ["typo-flash-9", "gemini-2.5-flash"]
    assert out["model"] == "gemini-2.5-flash"
    assert "not available" in out["model_note"]


def test_a_dead_model_is_not_retried_on_every_later_question(env, monkeypatch):
    calls = []

    def gemini(key, model, system, user, timeout, max_tokens):
        calls.append(model)
        if model == "typo-flash-9":
            _404()
        return "Your count is below the threshold."

    monkeypatch.setitem(llm._CALL, "gemini", gemini)
    args = {"provider": "gemini", "key": "k", "model": "typo-flash-9",
            "question": "how is my field", "facts": {"prahari_answer": "x"},
            "lang": "en", "settings": env}
    llm.rephrase(**args)
    calls.clear()
    llm.rephrase(**args)
    assert calls == ["gemini-2.5-flash"], "the dead id must not be tried twice"


def test_a_404_on_the_default_itself_is_reported_in_words_not_a_status(env, monkeypatch):
    monkeypatch.setitem(llm._CALL, "gemini", _404)
    out = llm.rephrase(provider="gemini", key="k", model=None,
                       question="how is my field", facts={"prahari_answer": "x"},
                       lang="en", settings=env)
    assert out["used"] is False
    assert "HTTP 404" not in out["reason"]
    assert "is not available from gemini" in out["reason"]
    assert "LLM_MODEL" in out["reason"]


def test_a_bad_key_is_still_reported_as_a_bad_key(env, monkeypatch):
    """404 must not swallow 401. An operator chasing a model id when the key is
    revoked is worse off than before."""
    def unauthorised(*a, **k):
        raise httpx.HTTPStatusError(
            "401", request=httpx.Request("POST", "https://x"),
            response=httpx.Response(401, request=httpx.Request("POST", "https://x")))

    monkeypatch.setitem(llm._CALL, "gemini", unauthorised)
    out = llm.rephrase(provider="gemini", key="k", model=None,
                       question="q", facts={"prahari_answer": "x"}, lang="en",
                       settings=env)
    assert "rejected the key" in out["reason"]


# ── through the real endpoint, which is where it was seen ───────────────────
@pytest.fixture
def deployment(env, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-a-real-one")
    monkeypatch.setenv("LLM_MODEL", "gemini-1.5-flash")   # the retired id
    return reload_settings()


def _farmer_plot(c, phone="9812345678"):
    h = _auth(c.post("/api/auth/register", json={
        "full_name": "Rajesh Pawar", "password": "strong-pass-2026",
        "phone": phone, "lang": "mr", "taluka": "niphad", "village": "Niphad"}))
    p = c.post("/api/plots", headers=h, json={
        "name": "Tomato block 1", "crop": "tomato", "area_acre": 2.0,
        "sown_on": "2026-06-25", "lat": 20.0810, "lng": 74.1100,
        "location_source": "gps", "soil": "medium black", "irrigation": "drip"})
    assert p.status_code == 201, p.text
    return h, p.json()


def test_agridoc_no_longer_reports_a_discarded_model(deployment, monkeypatch):
    """The regression. With LLM_MODEL naming a retired model, the farmer used to
    get 'Model version discarded — provider returned HTTP 404' under a correct
    answer. Now the substitution happens before the call and the answer is
    worded."""
    seen = []

    def gemini(key, model, system, user, timeout, max_tokens):
        seen.append(model)
        if model == "gemini-1.5-flash":
            _404()
        return "PRAHARI has no verified record that answers this. Ask your Krishi Sahayak."

    monkeypatch.setitem(llm._CALL, "gemini", gemini)

    from fastapi.testclient import TestClient

    from app.main import create_app
    with TestClient(create_app(deployment)) as c:
        h, p = _farmer_plot(c)
        r = c.post("/api/saathi/ask", headers=h,
                   json={"question": "what should I do about the leaves",
                         "plot_id": p["id"], "lang": "en"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert seen == ["gemini-2.5-flash"], "the retired id must never be dialled"
    assert body["llm"]["used"] is True, body["llm"].get("reason")
    assert "404" not in str(body["llm"])


def test_the_endpoint_itself_was_never_the_404(deployment):
    """Worth pinning: the route exists and answers, with or without a model."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    with TestClient(create_app(deployment)) as c:
        h, p = _farmer_plot(c, "9812345679")
        r = c.post("/api/saathi/ask", headers=h,
                   json={"question": "how is my field", "plot_id": p["id"], "lang": "en"})
    assert r.status_code == 200
    assert r.json()["answer"]


def test_ready_names_the_model_that_will_actually_be_called(deployment):
    from fastapi.testclient import TestClient

    from app.main import create_app
    with TestClient(create_app(deployment)) as c:
        a = c.get("/api/ready").json()["checks"]["assistant"]
    assert a["configured"] is True
    assert a["model_configured"] == "gemini-1.5-flash"
    assert a["model"] == "gemini-2.5-flash"
    assert "retired" in a["model_note"]


def test_a_provider_failure_never_costs_the_farmer_the_answer(deployment, monkeypatch):
    monkeypatch.setitem(llm._CALL, "gemini", _404)
    from fastapi.testclient import TestClient

    from app.main import create_app
    with TestClient(create_app(deployment)) as c:
        h, p = _farmer_plot(c, "9812345681")
        r = c.post("/api/saathi/ask", headers=h,
                   json={"question": "how is my field", "plot_id": p["id"], "lang": "en"})
    body = r.json()
    assert r.status_code == 200
    assert body["answer"], "the retrieved answer must survive a dead model"
    assert body["llm"]["used"] is False


# ── the sectioned answer ────────────────────────────────────────────────────
def test_sections_are_off_unless_asked_for(deployment, monkeypatch):
    calls = []
    monkeypatch.setitem(llm._CALL, "gemini",
                        lambda k, m, s_, u, t, mx: calls.append(m) or "Reworded.")
    from fastapi.testclient import TestClient

    from app.main import create_app
    with TestClient(create_app(deployment)) as c:
        h, p = _farmer_plot(c, "9812345690")
        body = c.post("/api/saathi/ask", headers=h,
                      json={"question": "what should I do about the leaves",
                            "plot_id": p["id"], "lang": "en"}).json()
    assert "sections" not in body
    assert len(calls) == 1, "one call for the wording, and no more"


def test_sections_come_back_named_and_guarded(deployment, monkeypatch):
    import json as _json

    def gemini(key, model, system, user, timeout, max_tokens):
        if "six short named parts" in user:
            return _json.dumps({
                "answer": "Watch the lower leaves.",
                "why": "Your field records show no threshold crossed.",
                "what_to_check": "The oldest leaves, and the underside.",
                "what_to_do_now": "Remove badly affected leaves by hand.",
                "when_to_escalate": "If the spots reach the growing point.",
                "sources": "Your field records and the ICAR package of practices.",
            })
        return "Watch the lower leaves this week."

    monkeypatch.setitem(llm._CALL, "gemini", gemini)
    from fastapi.testclient import TestClient

    from app.main import create_app
    with TestClient(create_app(deployment)) as c:
        h, p = _farmer_plot(c, "9812345691")
        body = c.post("/api/saathi/ask", headers=h,
                      json={"question": "what should I look for with late blight",
                            "plot_id": p["id"], "lang": "en", "sections": True}).json()

    assert body["sections"]["available"] is True, body["sections"].get("reason")
    f = body["sections"]["fields"]
    assert "why" in f and "what_to_check" in f and "when_to_escalate" in f
    # the prose answer is untouched by the sectioned pass
    assert body["answer"] == "Watch the lower leaves this week."


def test_an_invented_dose_never_reaches_a_section(deployment, monkeypatch):
    import json as _json

    def gemini(key, model, system, user, timeout, max_tokens):
        if "six short named parts" in user:
            return _json.dumps({"answer": "Spray now.",
                                "what_to_do_now": "Apply Coragen 150 ml per acre this evening."})
        return "Watch the lower leaves this week."

    monkeypatch.setitem(llm._CALL, "gemini", gemini)
    from fastapi.testclient import TestClient

    from app.main import create_app
    with TestClient(create_app(deployment)) as c:
        h, p = _farmer_plot(c, "9812345692")
        body = c.post("/api/saathi/ask", headers=h,
                      json={"question": "what should I look for with late blight",
                            "plot_id": p["id"], "lang": "en", "sections": True}).json()

    assert body["sections"]["available"] is False
    assert "Coragen" not in _json.dumps(body["sections"])
    assert body["answer"], "the answer survives a rejected section pass"


def test_a_section_failure_never_costs_the_prose_answer(deployment, monkeypatch):
    def gemini(key, model, system, user, timeout, max_tokens):
        if "six short named parts" in user:
            raise httpx.ConnectError("no route to host")
        return "Watch the lower leaves this week."

    monkeypatch.setitem(llm._CALL, "gemini", gemini)
    from fastapi.testclient import TestClient

    from app.main import create_app
    with TestClient(create_app(deployment)) as c:
        h, p = _farmer_plot(c, "9812345693")
        r = c.post("/api/saathi/ask", headers=h,
                   json={"question": "what should I look for with late blight",
                         "plot_id": p["id"], "lang": "en", "sections": True})
    assert r.status_code == 200
    assert r.json()["answer"] == "Watch the lower leaves this week."
    assert r.json()["sections"]["available"] is False
