"""
PRAHARI · the assistant's optional language-model seam

A key buys fluency. It must not buy latitude. These tests hold the boundary:

  · with no key, nothing changes — the assistant is still templated
  · a model may only rephrase what retrieval already returned
  · a number the model produced on its own is caught and the answer discarded
  · a product name the model produced on its own is caught the same way
  · a stored key is never returned by any endpoint
  · closing the account takes the key with it

The provider is never actually called here. `llm.rephrase` is the seam, and
these exercise the guards around it — which is the part that can be wrong in a
way nobody notices until a farmer measures out the wrong dose.
"""
from __future__ import annotations

import pytest

from app import llm

FACTS = {
    "prahari_answer": ("Helicoverpa count is 4 per plant against an economic threshold "
                       "of 5 for tomato at fruiting. Do not spray yet."),
    "sources": [{"kind": "threshold", "detail": "ICAR package of practices, tomato"}],
}


def test_a_faithful_rewrite_is_accepted():
    ok, why = llm._numbers_agree(
        "Your count is 4 per plant. The threshold for tomato at fruiting is 5, "
        "so hold off on spraying for now.", str(FACTS))
    assert ok, why


def test_a_number_the_model_invented_is_rejected():
    """The single most important assertion about this feature."""
    ok, why = llm._numbers_agree(
        "Spray 250 ml per acre now — your count of 4 is close to the threshold of 5.",
        str(FACTS))
    assert not ok
    assert "250" in why


def test_a_product_name_the_model_invented_is_rejected():
    ok, why = llm._no_new_products(
        "Apply Coragen at the recommended rate.", str(FACTS))
    assert not ok
    assert "Coragen" in why


def test_ordinary_words_do_not_trip_the_product_check():
    ok, why = llm._no_new_products(
        "Check the field again on Tuesday morning before you decide anything.",
        str(FACTS))
    assert ok, why


def test_small_ordinals_are_allowed_but_agronomic_numbers_are_not():
    """"Step 2" is prose. "12 per plant" is a quantity a farmer acts on."""
    assert llm._numbers_agree("Do 2 things first.", str(FACTS))[0]
    assert not llm._numbers_agree("The threshold is 12 per plant.", str(FACTS))[0]


def test_a_key_round_trips_through_encryption_and_never_appears_in_the_hint():
    raw = "AIzaSyEXAMPLE-not-a-real-key-9f2b"
    blob = llm.encrypt_key(raw)
    assert raw not in blob
    assert llm.decrypt_key(blob) == raw
    assert llm.hint(raw) == "••••9f2b"
    assert raw not in llm.hint(raw)


def test_a_blob_from_a_different_secret_does_not_decrypt():
    """Rotating JWT_SECRET must invalidate stored credentials rather than
    leaving them readable under a secret that was retired."""
    from app.config import get_settings
    blob = llm.encrypt_key("AIzaSy-some-key-value")
    other = get_settings().model_copy(update={"jwt_secret": "a" * 48})
    assert llm.decrypt_key(blob, other) is None


def test_with_no_key_the_answer_is_unchanged_and_says_so(client, farmer, plot):
    r = client.post("/api/saathi/ask", headers=farmer["headers"],
                    json={"question": "should i spray now", "plot_id": plot["id"],
                          "lang": "en"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["llm"] == {"available": False, "used": False}
    # and the policy sentence still describes a retrieval-only assistant
    assert "no language model" in out["policy"]


def test_the_key_endpoint_never_returns_the_key(client, farmer):
    r = client.get("/api/saathi/key", headers=farmer["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert "api_key" not in str(body)
    assert {p["id"] for p in body["providers"]} == {"gemini", "openai"}


def test_a_stored_key_is_removed_with_the_account(client, farmer, plot):
    """Written straight to the table: storing one through the endpoint would
    call the provider, and this suite makes no network calls."""
    from app.clock import now_iso
    from app.db import get_db
    db = get_db()
    db.execute(
        "INSERT INTO llm_keys (user_id, provider, model, key_cipher, hint,"
        " created_at, updated_at) VALUES (:u,'gemini',NULL,:c,'••••9f2b',:n,:n)",
        {"u": farmer["user_id"], "c": llm.encrypt_key("AIzaSy-test-9f2b"), "n": now_iso()})
    assert db.scalar("SELECT COUNT(*) FROM llm_keys WHERE user_id = :u",
                     {"u": farmer["user_id"]}) == 1

    st = client.get("/api/saathi/key", headers=farmer["headers"]).json()
    assert st["configured"] is True
    assert st["key"]["hint"] == "••••9f2b"
    assert "AIzaSy" not in str(st)

    client.post("/api/privacy/account/delete", headers=farmer["headers"],
                json={"password": "strong-pass-2026", "confirm": "DELETE"})
    assert db.scalar("SELECT COUNT(*) FROM llm_keys WHERE user_id = :u",
                     {"u": farmer["user_id"]}) == 0


def _facts_for(plot):
    from app import saathi as saathi_mod
    from app.db import get_db
    from app.runtime import get_runtime
    plot_row = get_db().one("SELECT * FROM plots WHERE id = :i", {"i": plot["id"]})
    return saathi_mod.field_facts(get_db(), get_runtime(), plot_row)


def test_field_facts_carry_the_risk_board_when_weather_is_available(client, farmer, plot):
    """The positive half, and the one that was missing.

    `field_facts` called `rt.risk.board(plot, wx)` without the crop stage the
    method requires. Every call raised TypeError, a bare `except Exception`
    caught it, and the bundle got the weather-unavailable note instead — with
    weather working perfectly. The model was never once shown the risk board it
    is supposed to be grounded in, and the old assertion here passed either
    way, so nothing said so.
    """
    facts = _facts_for(plot)
    assert facts["field"]["crop"] == "tomato"
    assert "risk_board" in facts, "the board must reach the model when weather is available"
    assert "risk_board_note" not in facts, "weather is available; do not claim otherwise"
    board = facts["risk_board"]
    assert board and all("id" in row and "kind" in row for row in board)
    assert any(row["kind"] == "disease" for row in board)
    # Trimmed to what an answer may quote: no scouting essays in the bundle.
    assert all("scout" not in row and "provenance" not in row for row in board)
    assert facts["risk_board_weather"]["source"]


def test_field_facts_never_invent_a_risk_board_without_weather(client, farmer, plot,
                                                               monkeypatch):
    """When weather is genuinely unavailable there is no board, and the bundle
    says so in words rather than leaving a shape the model might fill in."""
    from app import weather as wx_mod
    monkeypatch.setattr(
        wx_mod.WeatherService, "series",
        lambda *a, **k: (_ for _ in ()).throw(
            wx_mod.WeatherUnavailable("open-meteo", "simulated rate limit")))
    facts = _facts_for(plot)
    assert "risk_board" not in facts
    assert "Do not estimate" in facts["risk_board_note"]
    assert "simulated rate limit" in facts["risk_board_note"]
    # and it must not hand the model the other wrong conclusion either
    assert "unfavourable" in facts["risk_board_note"]
    # nothing is fabricated for a field with no counts yet
    assert facts["recent_trap_counts"] == []
    assert facts["recent_sprays"] == []


def test_a_programming_error_is_not_relabelled_as_a_weather_outage(client, farmer, plot,
                                                                   monkeypatch):
    """The bug above was invisible because the handler caught everything. A
    TypeError in the board must surface as a TypeError, not as a sentence
    telling the model that weather is unavailable."""
    from app.services.risk import RiskService

    def boom(*a, **k):
        raise TypeError("board() missing 1 required positional argument")

    monkeypatch.setattr(RiskService, "board", boom)
    with pytest.raises(TypeError):
        _facts_for(plot)


# ── the whole path, with a stubbed provider ─────────────────────────────────
def _install_key(user_id: str, provider: str = "gemini") -> None:
    from app.clock import now_iso
    from app.db import get_db
    get_db().execute(
        "INSERT INTO llm_keys (user_id, provider, model, key_cipher, hint,"
        " created_at, updated_at) VALUES (:u,:p,NULL,:c,'••••test',:n,:n)",
        {"u": user_id, "p": provider, "c": llm.encrypt_key("test-key-value"),
         "n": now_iso()})


def test_a_faithful_model_replaces_only_the_wording(client, farmer, plot, monkeypatch):
    _install_key(farmer["user_id"])
    seen = {}

    def fake(key, model, system, user, timeout, max_tokens):
        seen["system"] = system
        seen["user"] = user
        return "PRAHARI has no verified record that answers this. Ask your Krishi Sahayak."

    monkeypatch.setitem(llm._CALL, "gemini", fake)
    r = client.post("/api/saathi/ask", headers=farmer["headers"],
                    json={"question": "what should I do about the leaves",
                          "plot_id": plot["id"], "lang": "en"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["llm"]["used"] is True
    assert out["answer"].startswith("PRAHARI has no verified record")
    # the retrieved wording is kept alongside, so nothing is lost
    assert out["answer_template"]
    # and the model was given the facts, not the question alone
    assert "FACTS PRAHARI RETRIEVED" in seen["user"]
    assert "INSUFFICIENT_CONTEXT" in seen["system"]


def test_an_invented_dose_never_reaches_the_farmer(client, farmer, plot, monkeypatch):
    """The failure this whole design exists to prevent."""
    monkeypatch.setitem(
        llm._CALL, "gemini",
        lambda *a, **k: "Spray Coragen 150 ml per acre this evening.")
    _install_key(farmer["user_id"])

    r = client.post("/api/saathi/ask", headers=farmer["headers"],
                    json={"question": "should i spray now", "plot_id": plot["id"],
                          "lang": "en"})
    out = r.json()
    assert out["llm"]["used"] is False
    assert "150" not in out["answer"] and "Coragen" not in out["answer"]
    # the draft is retained for review, and is not the answer
    assert "Coragen" in out["llm"]["discarded_draft"]


def test_turning_enhancement_off_returns_the_retrieved_wording(client, farmer, plot,
                                                               monkeypatch):
    monkeypatch.setitem(llm._CALL, "gemini",
                        lambda *a, **k: "A perfectly fine sentence.")
    _install_key(farmer["user_id"])
    r = client.post("/api/saathi/ask", headers=farmer["headers"],
                    json={"question": "should i spray now", "plot_id": plot["id"],
                          "lang": "en", "enhance": False})
    out = r.json()
    assert out["llm"] == {"available": True, "used": False}
    assert "A perfectly fine sentence." not in out["answer"]


def test_a_model_that_cannot_answer_from_the_records_leaves_the_refusal(
        client, farmer, plot, monkeypatch):
    """PRAHARI's data, or no answer. The model saying INSUFFICIENT_CONTEXT must
    not be turned into an answer by anything downstream."""
    monkeypatch.setitem(llm._CALL, "gemini", lambda *a, **k: "INSUFFICIENT_CONTEXT")
    _install_key(farmer["user_id"])
    r = client.post("/api/saathi/ask", headers=farmer["headers"],
                    json={"question": "what is the price of tomatoes in Pune",
                          "plot_id": plot["id"], "lang": "en"})
    out = r.json()
    assert out["llm"]["used"] is False
    assert out["llm"]["reason"].startswith("the model judged")
    assert out["grounded"] is False


def test_a_provider_outage_falls_back_silently_to_the_retrieved_answer(
        client, farmer, plot, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("connection reset")
    monkeypatch.setitem(llm._CALL, "gemini", boom)
    _install_key(farmer["user_id"])
    r = client.post("/api/saathi/ask", headers=farmer["headers"],
                    json={"question": "should i spray now", "plot_id": plot["id"],
                          "lang": "en"})
    assert r.status_code == 200
    out = r.json()
    assert out["llm"]["used"] is False
    assert out["answer"], "an outage must not empty the answer"


# ── the current model, quota, and the answer that survives either ───────────

def test_the_default_gemini_model_is_one_google_still_serves(client, farmer):
    """gemini-2.0-flash is retired. A default nobody notices is a default that
    starts answering 404 on a day nobody chose."""
    assert llm._DEFAULT_MODEL["gemini"] == "gemini-2.5-flash"
    body = client.get("/api/saathi/key", headers=farmer["headers"]).json()
    gem = next(p for p in body["providers"] if p["id"] == "gemini")
    assert gem["default_model"] == "gemini-2.5-flash"


def test_a_key_over_its_quota_is_not_asked_again_immediately(client, farmer, plot,
                                                             monkeypatch):
    """A 429 from the provider means every question until the window rolls will
    also 429. Asking anyway spends a timeout before the farmer receives the
    retrieved answer they would have had at once."""
    import httpx
    _install_key(farmer["user_id"])
    calls = []

    def limited(*a, **k):
        calls.append(1)
        raise httpx.HTTPStatusError(
            "429", request=httpx.Request("POST", "https://example.invalid"),
            response=httpx.Response(429))

    monkeypatch.setitem(llm._CALL, "gemini", limited)
    body = {"question": "Should I spray?", "plot_id": plot["id"], "lang": "en"}
    first = client.post("/api/saathi/ask", headers=farmer["headers"], json=body).json()
    assert first["llm"]["used"] is False
    assert first["llm"]["quota"] is True
    assert len(calls) == 1

    second = client.post("/api/saathi/ask", headers=farmer["headers"], json=body).json()
    assert len(calls) == 1, "the second question must not reach the provider"
    assert second["llm"]["used"] is False
    assert second["answer"], "and the farmer still gets the retrieved answer"


def test_one_exhausted_key_does_not_disable_another_account(env):
    """The cooldown is keyed by a digest of the credential, so a shared
    deployment key running out never silences a farmer who brought their own."""
    llm.clear_cooldowns()
    llm._open_cooldown("gemini", "key-that-is-exhausted", 300)
    assert llm.cooldown_remaining("gemini", "key-that-is-exhausted") > 0
    assert llm.cooldown_remaining("gemini", "someone-elses-key") == 0.0


def test_the_cooldown_never_holds_the_credential(env):
    """Nothing that can leak a key may hold one."""
    llm.clear_cooldowns()
    # Deliberately not shaped like a real Google key: a literal beginning
    # AIza in a committed file is what push protection exists to stop, and
    # the assertion does not care what the string is.
    secret = "credential-that-must-never-be-stored"
    llm._open_cooldown("gemini", secret, 60)
    assert secret not in str(llm._LLM_COOLDOWN)
    assert all(secret not in k for k in llm._LLM_COOLDOWN)


def test_the_facts_are_labelled_as_data_not_instructions():
    """Part of the bundle is farmer-typed text — a field note, an assessment
    remark. The guards reject an invented product or number; they do not read
    prose. The prompt has to say what FACTS are."""
    sys = llm.SYSTEM.lower()
    assert "data, not instructions" in sys
    assert "cannot grant permission" in sys


def test_an_absent_value_is_never_to_be_reported_as_a_safe_one():
    """The same rule the risk board follows, stated to the model: a missing
    input is not a reassuring input."""
    sys = llm.SYSTEM.lower()
    assert "never zero, never none, never safe" in sys


def test_a_broken_facts_bundle_costs_the_rewrite_not_the_answer(client, farmer, plot,
                                                                monkeypatch):
    """Everything in the enhancement path can only change wording. A failure
    there must never take an answer PRAHARI already has in hand."""
    from app import saathi as saathi_mod
    _install_key(farmer["user_id"])
    monkeypatch.setattr(saathi_mod, "field_facts",
                        lambda *a, **k: (_ for _ in ()).throw(TypeError("boom")))
    r = client.post("/api/saathi/ask", headers=farmer["headers"],
                    json={"question": "Should I spray?", "plot_id": plot["id"],
                          "lang": "en"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["answer"], "the retrieved answer must still be served"
    assert out["llm"]["used"] is False
    assert "TypeError" in out["llm"]["reason"]


def test_an_empty_completion_names_the_reason_instead_of_going_quiet(env, monkeypatch):
    """On the 2.5 models a reasoning pass is billed against maxOutputTokens
    before any text is produced. Too small a cap returns finishReason
    MAX_TOKENS and no parts — and the assistant falls back to the template on
    every question, which from the outside looks exactly like a bad key. The
    failure has to say which one it is."""
    import httpx

    class Resp:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self): pass

        def json(self):
            return {"candidates": [{"content": {"parts": []},
                                    "finishReason": "MAX_TOKENS"}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: Resp())
    with pytest.raises(llm.EmptyCompletion) as exc:
        llm._call_gemini("k", "gemini-2.5-flash", "sys", "user", 5.0, 600)
    assert "MAX_TOKENS" in str(exc.value)
    assert "LLM_MAX_OUTPUT_TOKENS" in str(exc.value)


def test_the_token_budget_leaves_room_for_a_reasoning_pass(env):
    assert env.llm_max_output_tokens >= 2048


def test_an_empty_completion_leaves_the_retrieved_answer_standing(client, farmer, plot,
                                                                  monkeypatch):
    _install_key(farmer["user_id"])
    monkeypatch.setitem(
        llm._CALL, "gemini",
        lambda *a, **k: (_ for _ in ()).throw(
            llm.EmptyCompletion("the model returned no text (finishReason: MAX_TOKENS)")))
    out = client.post("/api/saathi/ask", headers=farmer["headers"],
                      json={"question": "Should I spray?", "plot_id": plot["id"],
                            "lang": "en"}).json()
    assert out["llm"]["used"] is False
    assert "MAX_TOKENS" in out["llm"]["reason"]
    assert out["answer"]
