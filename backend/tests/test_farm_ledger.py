"""
PRAHARI · the farm money ledger

The property that matters most here is a NEGATIVE one: money must not reach the
agronomic engines. A test asserting that a cost changed nothing is worth more
than any of the arithmetic tests below, because the arithmetic failing is
obvious and the boundary failing is silent.
"""
from __future__ import annotations


def _add(client, headers, plot_id, **kw):
    body = {"plot_id": plot_id, "category": "fertilizer", "title": "Urea 2 bags",
            "amount_inr": 1420, "spent_on": "2026-08-20"}
    body.update(kw)
    return client.post("/api/farm-ledger", headers=headers, json=body)


def test_an_entry_is_recorded_and_totalled(client, farmer, plot):
    r = _add(client, farmer["headers"], plot["id"])
    assert r.status_code == 201, r.text
    assert r.json()["entry"]["amount_inr"] == 1420
    assert r.json()["duplicate"] is False

    _add(client, farmer["headers"], plot["id"], category="labour",
         title="Weeding, 4 people", amount_inr=2400)

    out = client.get(f"/api/farm-ledger?plot_id={plot['id']}", headers=farmer["headers"]).json()
    assert out["count"] == 2
    assert out["summary"]["expense_inr"] == 3820
    cats = {c["category"]: c["amount_inr"] for c in out["summary"]["by_category"]}
    assert cats == {"labour": 2400, "fertilizer": 1420}
    # shares are of spend, and they sum to one
    assert abs(sum(c["share"] for c in out["summary"]["by_category"]) - 1.0) < 1e-6


def test_income_and_expense_net_off(client, farmer, plot):
    _add(client, farmer["headers"], plot["id"], amount_inr=5000)
    _add(client, farmer["headers"], plot["id"], direction="income", category="sale",
         title="Tomato, 400 kg", amount_inr=12000)
    s = client.get(f"/api/farm-ledger/summary?plot_id={plot['id']}",
                   headers=farmer["headers"]).json()
    assert s["total"]["expense_inr"] == 5000
    assert s["total"]["income_inr"] == 12000
    assert s["total"]["net_inr"] == 7000
    # income is never mixed into the expense breakdown
    assert all(c["category"] != "sale" for c in s["total"]["by_category"])


def test_an_empty_ledger_reports_zero_rather_than_nothing(client, farmer, plot):
    out = client.get(f"/api/farm-ledger?plot_id={plot['id']}", headers=farmer["headers"]).json()
    assert out["entries"] == []
    assert out["summary"]["expense_inr"] == 0
    assert out["summary"]["by_category"] == []


def test_cost_per_acre_divides_by_the_declared_area(client, farmer, plot):
    """`plots.area_acre` is NOT NULL, so in practice every field has an area and
    cost per acre is always reportable. The null branch in the handler is
    defensive and stays — but the behaviour worth testing is the arithmetic."""
    _add(client, farmer["headers"], plot["id"], amount_inr=4000)
    s = client.get(f"/api/farm-ledger/summary?plot_id={plot['id']}",
                   headers=farmer["headers"]).json()
    assert s["area_acre"] == 2.0
    assert s["per_acre_inr"] == 2000
    assert s["per_acre_note"] is None

    # income does not reduce the per-acre COST figure — that would quietly turn
    # a cost line into a margin
    _add(client, farmer["headers"], plot["id"], direction="income", category="sale",
         title="part sale", amount_inr=9000)
    s2 = client.get(f"/api/farm-ledger/summary?plot_id={plot['id']}",
                    headers=farmer["headers"]).json()
    assert s2["per_acre_inr"] == 2000


def test_a_resend_from_the_offline_queue_does_not_double_count(client, farmer, plot):
    a = _add(client, farmer["headers"], plot["id"], client_ref="q-abc-123")
    b = _add(client, farmer["headers"], plot["id"], client_ref="q-abc-123")
    assert a.status_code == 201 and b.status_code == 201
    assert b.json()["duplicate"] is True
    assert a.json()["entry"]["id"] == b.json()["entry"]["id"]
    out = client.get(f"/api/farm-ledger?plot_id={plot['id']}", headers=farmer["headers"]).json()
    assert out["count"] == 1


def test_a_bad_category_or_amount_is_refused(client, farmer, plot):
    assert _add(client, farmer["headers"], plot["id"], category="bitcoin").status_code == 400
    # an income category on an expense entry is also wrong
    assert _add(client, farmer["headers"], plot["id"], category="sale").status_code == 400
    # zero and negative are refused by the schema before the handler
    assert _add(client, farmer["headers"], plot["id"], amount_inr=0).status_code == 422
    assert _add(client, farmer["headers"], plot["id"], amount_inr=-5).status_code == 422


def test_an_entry_can_be_corrected_but_only_by_its_owner(client, farmer, farmer_b, plot):
    eid = _add(client, farmer["headers"], plot["id"]).json()["entry"]["id"]

    r = client.patch(f"/api/farm-ledger/{eid}", headers=farmer["headers"],
                     json={"amount_inr": 1500, "note": "price corrected from the bill"})
    assert r.status_code == 200 and r.json()["entry"]["amount_inr"] == 1500

    r2 = client.patch(f"/api/farm-ledger/{eid}", headers=farmer_b["headers"],
                      json={"amount_inr": 1})
    assert r2.status_code in (403, 404)


def test_another_farmers_ledger_is_not_readable(client, farmer, farmer_b, plot):
    _add(client, farmer["headers"], plot["id"])
    r = client.get(f"/api/farm-ledger?plot_id={plot['id']}", headers=farmer_b["headers"])
    assert r.status_code in (403, 404)
    assert client.get(f"/api/farm-ledger?plot_id={plot['id']}").status_code == 401


# ── the boundary that matters ───────────────────────────────────────────────

def test_money_never_reaches_the_agronomic_engines(client, farmer, plot):
    """Recording costs must not move the risk board, the crop calendar, the
    health score or the day's agenda by a single field.

    If this ever fails, PRAHARI has started giving agricultural advice on
    financial grounds — a cheap intervention scoring better than a correct one.
    """
    before = {
        "risk": client.get(f"/api/risk/{plot['id']}", headers=farmer["headers"]).json(),
        "cal": client.get(f"/api/crop-calendar/{plot['id']}", headers=farmer["headers"]).json(),
        "today": client.get(f"/api/fields/{plot['id']}/today", headers=farmer["headers"]).json(),
    }

    for cat, amt in (("pesticide", 3200), ("labour", 900), ("machinery", 5400)):
        _add(client, farmer["headers"], plot["id"], category=cat, amount_inr=amt,
             title=f"{cat} spend")

    after = {
        "risk": client.get(f"/api/risk/{plot['id']}", headers=farmer["headers"]).json(),
        "cal": client.get(f"/api/crop-calendar/{plot['id']}", headers=farmer["headers"]).json(),
        "today": client.get(f"/api/fields/{plot['id']}/today", headers=farmer["headers"]).json(),
    }

    assert before["risk"]["board"] == after["risk"]["board"]
    assert before["cal"]["prevention_window"] == after["cal"]["prevention_window"]
    assert before["cal"]["threat_windows"] == after["cal"]["threat_windows"]
    assert [i["key"] for i in before["today"]["items"]] == \
           [i["key"] for i in after["today"]["items"]]


def test_the_ledger_states_that_it_is_bookkeeping_only(client, farmer, plot):
    meta = client.get("/api/farm-ledger/meta", headers=farmer["headers"]).json()
    assert "never read by the risk engine" in meta["note"]
    s = client.get(f"/api/farm-ledger/summary?plot_id={plot['id']}",
                   headers=farmer["headers"]).json()
    assert "no yield or profit is projected" in s["note"]
