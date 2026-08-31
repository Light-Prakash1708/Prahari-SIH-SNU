"""
PRAHARI · closing a follow-up without a photograph

The distinction this file exists to protect: a MEASURED outcome (two
photographs compared) and a SELF-REPORTED one (a farmer's account) both close
the loop, and PRAHARI must never quietly treat the second as the first. An
outcome nobody measured cannot be counted as evidence that a treatment worked.
"""
from __future__ import annotations

from tests.conftest import leaf_image


def _open_followup(client, farmer, plot):
    """Drive a real follow-up into existence: observe, then record an
    application, which is what schedules the re-check."""
    client.post("/api/observations", headers=farmer["headers"],
                data={"plot_id": plot["id"], "kind": "leaf"},
                files={"image": ("l.jpg", leaf_image("blight"), "image/jpeg")})
    from app.db import get_db
    from app.clock import now_iso
    db = get_db()
    db.execute(
        "INSERT INTO followups (plot_id, due_on, created_at) VALUES (:p, :d, :n)",
        {"p": plot["id"], "d": "2026-08-27", "n": now_iso()})
    return db.one("SELECT * FROM followups WHERE plot_id = :p ORDER BY id DESC",
                  {"p": plot["id"]})["id"]


def test_a_farmer_can_close_a_followup_they_cannot_photograph(client, farmer, plot):
    fid = _open_followup(client, farmer, plot)

    r = client.post(f"/api/followups/{fid}/outcome", headers=farmer["headers"],
                    json={"outcome": "better", "note": "spots stopped spreading"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"] == "better"
    assert body["measured"] is False
    assert "not counted as a measured outcome" in body["note"]

    # It is gone from the due list. Before the self-report path existed, "open"
    # meant "no rescan observation"; a follow-up closed by a report has no
    # observation, so the predicate had to become "no observation AND no
    # outcome" in every place that asks the question — the due list, the day's
    # agenda and the field-health card.
    due = client.get(f"/api/followups?plot_id={plot['id']}", headers=farmer["headers"]).json()
    assert all(f["id"] != fid for f in due["followups"])

    agenda = client.get(f"/api/fields/{plot['id']}/today", headers=farmer["headers"]).json()
    assert not any(i["key"] == "followup" for i in agenda["items"]), \
        "a closed follow-up is still being asked for on the home screen"

    health = client.get(f"/api/fields/{plot['id']}/health", headers=farmer["headers"]).json()
    assert all(f["id"] != fid for f in health["followups_due"])


def test_a_self_report_is_stored_as_self_reported(client, farmer, plot):
    """The row itself must carry the method, so anything reading it later —
    a report, an expert, a retraining export — can tell the two kinds apart."""
    fid = _open_followup(client, farmer, plot)
    client.post(f"/api/followups/{fid}/outcome", headers=farmer["headers"],
                json={"outcome": "same"})

    from app.db import get_db, loads
    row = get_db().one("SELECT * FROM followups WHERE id = :i", {"i": fid})
    cmp = loads(row["comparison"], {})
    assert cmp["method"] == "self_reported"
    assert cmp["measured"] is False
    assert row["outcome"] == "same"
    # a self-report never invents the observation that a rescan would have made
    assert row["done_observation"] is None


def test_unmeasurable_is_an_allowed_answer(client, farmer, plot):
    """The crop was harvested, the leaf dropped. Forcing better/same/worse here
    would manufacture data."""
    fid = _open_followup(client, farmer, plot)
    r = client.post(f"/api/followups/{fid}/outcome", headers=farmer["headers"],
                    json={"outcome": "unmeasurable", "note": "crop harvested"})
    assert r.status_code == 200
    assert r.json()["outcome"] == "unmeasurable"


def test_a_reported_worsening_escalates(client, farmer, plot):
    """Nothing was measured, but a person standing in the field saw it get
    worse. That is still a reason to escalate."""
    fid = _open_followup(client, farmer, plot)
    r = client.post(f"/api/followups/{fid}/outcome", headers=farmer["headers"],
                    json={"outcome": "worse"})
    assert r.json()["escalated"] is True

    from app.db import get_db
    assert get_db().one("SELECT * FROM followups WHERE id = :i", {"i": fid})["escalated"]


def test_a_closed_followup_cannot_be_closed_twice(client, farmer, plot):
    fid = _open_followup(client, farmer, plot)
    assert client.post(f"/api/followups/{fid}/outcome", headers=farmer["headers"],
                       json={"outcome": "better"}).status_code == 200
    second = client.post(f"/api/followups/{fid}/outcome", headers=farmer["headers"],
                         json={"outcome": "worse"})
    assert second.status_code == 409
    assert second.json()["error"] == "followup_already_closed"


def test_an_invented_outcome_is_refused(client, farmer, plot):
    fid = _open_followup(client, farmer, plot)
    r = client.post(f"/api/followups/{fid}/outcome", headers=farmer["headers"],
                    json={"outcome": "cured_completely"})
    assert r.status_code == 422


def test_another_farmer_cannot_close_it(client, farmer, farmer_b, plot):
    fid = _open_followup(client, farmer, plot)
    r = client.post(f"/api/followups/{fid}/outcome", headers=farmer_b["headers"],
                    json={"outcome": "better"})
    assert r.status_code in (403, 404)
    assert client.post(f"/api/followups/{fid}/outcome",
                       json={"outcome": "better"}).status_code == 401
