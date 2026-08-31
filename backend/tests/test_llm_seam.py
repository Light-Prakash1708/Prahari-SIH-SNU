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


def test_field_facts_never_invent_a_risk_board_without_weather(client, farmer, plot):
    """What the model is allowed to see is assembled from rows. When weather is
    unavailable there is no board, and the bundle says so in words rather than
    leaving a shape the model might fill in."""
    from app import saathi as saathi_mod
    from app.db import get_db
    from app.runtime import get_runtime
    plot_row = get_db().one("SELECT * FROM plots WHERE id = :i", {"i": plot["id"]})
    facts = saathi_mod.field_facts(get_db(), get_runtime(), plot_row)
    assert facts["field"]["crop"] == "tomato"
    assert "risk_board" in facts or "risk_board_note" in facts
    if "risk_board_note" in facts:
        assert "Do not estimate" in facts["risk_board_note"]
    # nothing is fabricated for a field with no counts yet
    assert facts["recent_trap_counts"] == []
    assert facts["recent_sprays"] == []


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
