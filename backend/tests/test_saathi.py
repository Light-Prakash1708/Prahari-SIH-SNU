"""
PRAHARI Saathi — the assistant that can only say what PRAHARI can prove.

The tests that matter here are the refusals. An assistant that answers a
question it has no source for is worse than no assistant, because a farmer
cannot tell the difference between the answers it should and should not trust.
"""
from __future__ import annotations

import json

import pytest

from conftest import scan


def ask(client, headers, q, plot_id=None, lang="en"):
    body = {"question": q, "lang": lang}
    if plot_id:
        body["plot_id"] = plot_id
    r = client.post("/api/saathi/ask", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ── refusal ─────────────────────────────────────────────────────────────────
def test_an_out_of_scope_question_is_refused_not_answered(client, farmer, plot):
    out = ask(client, farmer["headers"], "What is the mandi price of onions in Lasalgaon today?",
              plot["id"])
    assert out["grounded"] is False
    assert "don't have enough verified information" in out["answer"]
    assert out["sources"] == []
    assert out["data"]["scope"]


def test_a_refusal_names_what_it_can_do(client, farmer, plot):
    out = ask(client, farmer["headers"], "will it rain on my wedding day", plot["id"])
    assert out["grounded"] is False
    assert "economic threshold" in out["data"]["scope"]


def test_saathi_never_names_a_draft_product(client, farmer, plot, admin, monsoon):
    """Every shipped label claim is draft. Saathi must not print one, whatever
    it is asked, because naming an unverified product is half of recommending it."""
    client.post("/api/threshold", headers=farmer["headers"],
                json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 40})
    drafts = [c["product"] for c in
              client.get("/api/admin/claims", headers=admin["headers"]).json()["claims"]]
    questions = [
        "what should I spray for helicoverpa",
        "which pesticide is best for pod borer",
        "give me the dose for helicoverpa on tomato",
        "how do I control helicoverpa",
        "should I spray?",
    ]
    for q in questions:
        out = ask(client, farmer["headers"], q, plot["id"])
        blob = json.dumps(out)
        for product in drafts:
            active = product.split()[0]
            assert active not in blob, f"'{q}' leaked the draft product {product}"


def test_saathi_says_no_verified_recommendation_exists(client, farmer, plot, monsoon):
    client.post("/api/threshold", headers=farmer["headers"],
                json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 40})
    out = ask(client, farmer["headers"], "should I spray?", plot["id"])
    assert "VERIFIED" in out["answer"] or "verified" in out["answer"]
    assert "Krishi Sahayak" in out["answer"] or "KVK" in out["answer"]


# ── grounded answers ────────────────────────────────────────────────────────
def test_every_grounded_answer_carries_a_source(client, farmer, plot, monsoon):
    client.post("/api/threshold", headers=farmer["headers"],
                json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 1})
    for q in ["should I spray?", "what is the threshold for helicoverpa",
              "how is my field", "what is the risk this week",
              "how do I control late blight without chemicals",
              "when can I harvest"]:
        out = ask(client, farmer["headers"], q, plot["id"])
        if out["grounded"]:
            assert out["sources"], f"'{q}' answered with no source"


def test_below_threshold_saathi_says_no(client, farmer, plot, monsoon):
    client.post("/api/threshold", headers=farmer["headers"],
                json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 1})
    out = ask(client, farmer["headers"], "should I spray?", plot["id"])
    assert out["intent"] == "should_i_spray"
    assert out["data"]["crossed"] is False
    assert "No — not yet" in out["answer"]
    assert out["data"]["percent"] < 100


def test_with_no_count_saathi_asks_for_one_rather_than_guessing(client, farmer, plot):
    out = ask(client, farmer["headers"], "should I spray?", plot["id"])
    assert "nothing to judge against a threshold" in out["answer"] \
        or "Nothing has been counted" in out["answer"]
    assert any(a["do"] == "count" for a in out["actions"])


def test_threshold_answer_quotes_its_published_source(client, farmer, plot):
    out = ask(client, farmer["headers"], "what is the economic threshold for helicoverpa",
              plot["id"])
    assert out["grounded"]
    src = [s for s in out["sources"] if s["kind"] == "threshold"]
    assert src and src[0]["detail"]
    assert src[0]["status"] in ("draft", "verified")


def test_scouting_answer_comes_from_the_reference_not_from_prose(client, farmer, plot):
    out = ask(client, farmer["headers"], "what should I look for with late blight", plot["id"])
    assert out["grounded"]
    assert any(s["kind"] in ("reference", "model") for s in out["sources"])


def test_marathi_is_a_real_answer_not_a_fallback_to_english(client, farmer, plot, monsoon):
    client.post("/api/threshold", headers=farmer["headers"],
                json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 1})
    out = ask(client, farmer["headers"], "फवारणी करू का?", plot["id"], lang="mr")
    assert out["grounded"]
    assert any("ऀ" <= ch <= "ॿ" for ch in out["answer"]), "no Devanagari in the answer"
    assert out["answer"] != out["answer_en"]


def test_weather_failure_is_reported_not_papered_over(client, farmer, plot, monkeypatch):
    from app.runtime import get_runtime
    from app.weather import WeatherUnavailable
    rt = get_runtime()
    monkeypatch.setattr(rt.weather.provider, "series",
                        lambda *a, **k: (_ for _ in ()).throw(
                            WeatherUnavailable("open-meteo", "connection refused")))
    rt.db.execute("DELETE FROM weather_cache")
    out = ask(client, farmer["headers"], "what is the risk this week", plot["id"])
    assert "could not be retrieved" in out["answer"]
    assert "does not substitute invented weather" in out["answer"]


# ── access ──────────────────────────────────────────────────────────────────
def test_saathi_cannot_be_asked_about_someone_elses_field(client, farmer_b, plot):
    r = client.post("/api/saathi/ask", headers=farmer_b["headers"],
                    json={"question": "how is my field", "plot_id": plot["id"]})
    assert r.status_code == 403


def test_suggestions_declare_what_it_will_not_do(client, farmer):
    r = client.get("/api/saathi/suggestions?lang=en", headers=farmer["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["suggestions"]
    assert any("Invent a pesticide" in x for x in body["will_not_do"])


# ── the hazard of a keyword that fires on any sentence ──────────────────────
@pytest.mark.parametrize("question", [
    # These are the failures that actually happened during development. A bare
    # "will it", a bare "how many" and a bare "किती" each matched an agronomic
    # intent and answered a completely unrelated question — confidently.
    "will it rain on my wedding day",
    "what is the mandi price of onions in Lasalgaon",
    "कांद्याचा बाजारभाव किती?",
    "माझ्या मुलाचे वय किती?",
    "how much does a tractor cost",
    "who won the cricket match",
    "is my house safe",
    "how many children should I have",
    "what is the weather in Mumbai for my holiday",
])
def test_an_unrelated_question_is_never_answered_with_agronomy(client, farmer, plot, question):
    out = ask(client, farmer["headers"], question, plot["id"])
    assert out["grounded"] is False, (
        f"{question!r} was answered as '{out['intent']}' — a keyword that fires on any "
        f"sentence is not an intent, it is a hazard")
    assert out["sources"] == []
