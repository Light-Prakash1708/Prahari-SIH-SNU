"""
The whole loop, in one test, against a real database.

    register → field → weather → risk → scan → diagnosis → questions →
    count → threshold → decision → IPM → verified chemical → action →
    follow-up → outcome → passport → surveillance → officer → expert → learning

If this passes, the acceptance journey in the README works.
"""
from __future__ import annotations

import pytest

from conftest import leaf_image, scan


def test_the_whole_loop(client, admin, officer, expert):
    # 1 · register
    reg = client.post("/api/auth/register", json={
        "full_name": "Rajesh Pawar", "full_name_mr": "राजेश पवार",
        "password": "strong-pass-2026", "phone": "9812345678",
        "lang": "mr", "taluka": "niphad", "village": "Niphad"})
    assert reg.status_code == 201
    H = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    # 2 · create a field, with a drawn boundary
    plot = client.post("/api/plots", headers=H, json={
        "name": "Tomato block 1", "crop": "tomato", "area_acre": 2.0,
        "sown_on": "2026-06-25", "lat": 20.0810, "lng": 74.1100,
        "location_source": "gps", "soil": "medium black", "irrigation": "drip",
        "boundary": {"type": "Polygon", "coordinates": [[
            [74.1100, 20.0810], [74.1110, 20.0810],
            [74.1110, 20.0818], [74.1100, 20.0818], [74.1100, 20.0810]]]}})
    assert plot.status_code == 201
    P = plot.json()
    assert P["area_source"] == "polygon"
    assert "Approximate" in P["area_note"]
    assert P["crop_stage"]["stage"]
    PID = P["id"]

    client.post("/api/demo/scenario?key=threshold", headers=H)

    # 3 · weather and risk, from the field's own coordinates
    risk = client.get(f"/api/risk/{PID}", headers=H)
    assert risk.status_code == 200
    assert risk.json()["board"]
    assert risk.json()["model_provenance"]["hutton"]["source"]

    # 4 · what is coming
    fc = client.get(f"/api/risk/{PID}/forecast", headers=H).json()
    assert len(fc["forecast"]) == 4
    assert fc["headline"]["title"]

    # 5 · crop health and what changed
    h1 = client.get(f"/api/fields/{PID}/health", headers=H).json()
    assert h1["changed"]["first_visit"] is True

    # 6 · a bad photograph is refused
    bad = scan(client, H, PID, "blurry").json()
    assert bad["diagnosis"]["abstain"] is True
    assert bad["diagnosis"]["differential"] == []

    # 7 · a usable photograph produces a differential
    good = scan(client, H, PID, "blight").json()
    OID = good["observation"]["id"]
    assert good["diagnosis"]["differential"]
    assert good["next"]["do"] in ("count", "expert", "wait")

    # 8 · should I spray, with no count yet
    d0 = client.get(f"/api/decisions/{PID}/should-i-spray?target=helicoverpa",
                    headers=H).json()["decision"]
    assert d0["decision"] == "scout_again"
    assert d0["reason_code"] == "no_count"

    # 9 · trap, counts, and the rise
    trap = client.post("/api/traps", headers=H,
                       json={"plot_id": PID, "pest": "helicoverpa"}).json()
    for n in (2.0, 4.0):
        client.post(f"/api/traps/{trap['id']}/counts", headers=H, json={"count": n})
    below = client.get(f"/api/decisions/{PID}/should-i-spray?target=helicoverpa",
                       headers=H).json()
    assert below["decision"]["decision"] in ("do_not_spray", "non_chemical")
    assert below["chemical"]["recommended"] is None

    crossed = client.post(f"/api/traps/{trap['id']}/counts", headers=H,
                          json={"count": 22.0}).json()
    assert crossed["threshold"]["chemical_authorised"] is True
    assert crossed["trend"]["direction"] == "up"
    assert crossed["trend"].get("spike") is True
    CHECK = crossed["threshold"]["check_id"]

    # 10 · no verified chemical yet, so the answer is "see a human"
    gated = client.get(f"/api/decisions/{PID}/should-i-spray?target=helicoverpa",
                       headers=H).json()
    assert gated["decision"]["reason_code"] == "no_verified_chemical"
    assert gated["chemical"]["recommended"] is None

    # 11 · an administrator verifies one claim against a citation
    claims = client.get("/api/admin/claims?crop=tomato",
                        headers=admin["headers"]).json()["claims"]
    claim = next(c for c in claims if c["target"] == "helicoverpa")
    client.post(f"/api/admin/claims/{claim['id']}/verify", headers=admin["headers"], json={
        "source": "CIB&RC Major Uses of Pesticides, tomato / H. armigera, rev. 2025-11",
        "source_url": "https://ppqs.gov.in/divisions/cib-rc/major-uses-of-pesticides"})

    # 12 · now, and only now, a chemical option exists
    rec = client.get(f"/api/recommendations/{PID}?target=helicoverpa",
                     headers=H).json()["chemical"]["recommended"]
    assert rec and rec["verified"] is True
    assert rec["dose"]["plain"]

    # 13 · record the action; the follow-up is scheduled and harvest is gated
    act = client.post("/api/applications", headers=H, json={
        "plot_id": PID, "target": "helicoverpa", "kind": "chemical",
        "product": rec["product"], "claim_id": rec["claim_id"],
        "dose_text": rec["dose"]["plain"], "check_id": CHECK}).json()
    assert act["harvest_gate"]
    assert act["followup_due"]
    FU = act["followup_id"]

    due = client.get("/api/followups", headers=H).json()["followups"]
    assert any(f["id"] == FU for f in due)

    # 14 · the re-scan, compared as a direction
    after = client.post(f"/api/followups/{FU}/rescan", headers=H,
                        files={"image": ("a.jpg", leaf_image("improved"), "image/jpeg")}).json()
    assert after["outcome"] in ("better", "same", "worse")
    assert after["comparison"]["severity_percentages"] is None

    # 15 · the Field Health Passport carries the whole arc
    passport = client.get(f"/api/plots/{PID}/history", headers=H).json()
    kinds = {e["kind"] for e in passport["timeline"]}
    assert {"field", "scan", "count", "apply", "followup"} <= kinds
    assert passport["applications"]
    assert passport["threshold_checks"]

    # 16 · the farmer asks for a human
    case = client.post(f"/api/observations/{OID}/expert-review", headers=H,
                       json={"reason": "Please confirm", "urgency": "normal"}).json()["case"]
    CID = case["id"]
    assert CID.startswith("PRH-")

    # 17 · the expert sees everything and decides
    detail = client.get(f"/api/expert/cases/{CID}", headers=expert["headers"]).json()
    assert detail["images"] and detail["differential"] and detail["weather"]
    assert detail["field_history"]
    review = client.post(f"/api/expert/cases/{CID}/review", headers=expert["headers"], json={
        "action": "confirm", "verdict": "late_blight", "confidence": "high",
        "note": "Lesion margin and sporulation are consistent."}).json()
    assert review["status"] == "verified"
    assert review["prior_shift"]["alpha"] == 2.0
    assert "no gradient, no retraining" in review["learning_note"]

    # 18 · the learning is visible: the prior moved for the next diagnosis
    again = scan(client, H, PID, "blight").json()
    prior = again["diagnosis"]["prior"]
    assert prior["p"]["late_blight"] > prior["p"]["early_blight"]

    # 19 · the officer sees the case in scope
    summary = client.get("/api/officer/summary", headers=officer["headers"]).json()
    assert "niphad" in summary["scope"]
    assert summary["active_cases"] >= 1

    queue = client.get("/api/officer/queue?capacity=5", headers=officer["headers"]).json()
    assert queue["queue"]
    assert queue["queue"][0]["why"]
    assert "not by confidence" in queue["rationale"]

    route = client.get("/api/officer/route?capacity=5", headers=officer["headers"]).json()
    assert route["sequence"]
    assert "not an optimal route" in route["caveat"]

    # 20 · assign a visit and close it with a ground-truth finding
    assign = client.post("/api/officer/assignments", headers=officer["headers"], json={
        "observation_id": OID, "priority": "P1", "due_in_days": 2}).json()
    closed = client.post(f"/api/officer/assignments/{assign['id']}/close",
                         headers=officer["headers"], json={
                             "status": "confirmed", "confirmed_problem": "late_blight",
                             "finding": "Confirmed in the field."}).json()
    assert closed["prior_shift"]["alpha"] == 3.0

    # 21 · model-vs-expert monitoring is computed, not asserted
    agree = client.get("/api/expert/model-agreement", headers=expert["headers"]).json()
    assert agree["expert_reviewed"] >= 1
    assert agree["agreement_rate"] is None
    assert "will not print a rate from a sample this small" in agree["agreement_rate_note"]

    # 22 · notifications exist with honest delivery state
    notes = client.get("/api/notifications", headers=H).json()
    assert notes["notifications"]
    states = {d["state"] for n in notes["notifications"] for d in n["deliveries"]}
    assert states <= {"delivered", "sent", "skipped", "queued", "failed"}
    assert "sms" in {d["channel"] for n in notes["notifications"] for d in n["deliveries"]}

    # 23 · everything persists across a fresh sign-in
    client.post("/api/auth/logout", headers=H)
    again_login = client.post("/api/auth/login",
                              json={"identifier": "9812345678", "password": "strong-pass-2026"})
    H2 = {"Authorization": f"Bearer {again_login.json()['access_token']}"}
    plots = client.get("/api/plots", headers=H2).json()["plots"]
    assert [p["id"] for p in plots] == [PID]
    passport2 = client.get(f"/api/plots/{PID}/history", headers=H2).json()
    assert len(passport2["timeline"]) >= len(passport["timeline"])
    assert client.get(f"/api/fields/{PID}/health", headers=H2).status_code == 200
