"""
Outbreak grading, the officer queue, and the words PRAHARI is allowed to use.
"""
from __future__ import annotations

import datetime as dt

import pytest

from conftest import scan


def _plant_reports(db, taluka: str, crop: str, problem: str, n: int, confirmed: int,
                   fields: int = 3, days_back: int = 4):
    """Write observation+diagnosis rows directly, the way real usage would."""
    import uuid
    from app.clock import now_iso, today
    day = today()
    plot_ids = []
    for i in range(fields):
        pid = f"P-SEED{i}{taluka[:3].upper()}"
        fid = f"F-SEED{i}{taluka[:3].upper()}"
        uid = f"U-SEED{i}{taluka[:3].upper()}"
        db.execute("INSERT INTO users (id,email,phone,password_hash,role,full_name,lang,"
                   "is_active,email_verified,created_at,updated_at) VALUES "
                   "(:u,NULL,NULL,'x','farmer','Seed Farmer','mr',1,0,:n,:n)",
                   {"u": uid, "n": now_iso()})
        db.execute("INSERT INTO farmers (id,user_id,name,taluka,lang,literacy,sms_opt_in,"
                   "ivr_opt_in,created_at) VALUES (:f,:u,'Seed Farmer',:t,'mr','reads',1,0,:n)",
                   {"f": fid, "u": uid, "t": taluka, "n": now_iso()})
        db.execute("INSERT INTO plots (id,farmer_id,name,crop,area_acre,area_source,sown_on,"
                   "lat,lng,location_source,taluka,tank_litres,archived,created_at,updated_at)"
                   " VALUES (:p,:f,'Seed plot',:c,1.0,'declared','2026-06-25',20.0,74.0,"
                   "'manual',:t,15,0,:n,:n)",
                   {"p": pid, "f": fid, "c": crop, "t": taluka, "n": now_iso()})
        plot_ids.append((pid, fid))
    for k in range(n):
        pid, fid = plot_ids[k % fields]
        at = (day - dt.timedelta(days=max(0, days_back - k))).isoformat() + "T08:00:00.000Z"
        oid = "O-" + uuid.uuid4().hex[:10].upper()
        db.execute("INSERT INTO observations (id,plot_id,farmer_id,kind,taluka,crop,observed_at,"
                   "source,status,created_at) VALUES (:o,:p,:f,'leaf',:t,:c,:at,'app','open',:n)",
                   {"o": oid, "p": pid, "f": fid, "t": taluka, "c": crop, "at": at,
                    "n": now_iso()})
        did = "D-" + uuid.uuid4().hex[:10].upper()
        db.execute("INSERT INTO diagnoses (id,observation_id,plot_id,crop,engine,model_version,"
                   "top_problem,top_posterior,abstained,created_at) VALUES "
                   "(:d,:o,:p,:c,'features','features-v1',:prob,0.7,0,:n)",
                   {"d": did, "o": oid, "p": pid, "c": crop, "prob": problem, "n": now_iso()})
        if k < confirmed:
            db.execute("UPDATE diagnoses SET confirmed=:prob, confirmed_by='Dr K',"
                       " confirmed_at=:n WHERE id=:d",
                       {"prob": problem, "n": now_iso(), "d": did})


def test_two_reports_are_not_a_cluster(client, officer):
    from app.db import get_db
    from app.runtime import get_runtime
    _plant_reports(get_db(), "niphad", "tomato", "late_blight", n=2, confirmed=0, fields=2)
    a = get_runtime().outbreak.assess("niphad", "late_blight")
    assert a["grade"] == "none"
    assert a["label"] == "No cluster"
    assert "below the 3-report" in a["evidence"][0]["detail"]


def test_reports_without_expert_confirmation_are_only_an_emerging_cluster(client, officer):
    from app.db import get_db
    from app.runtime import get_runtime
    _plant_reports(get_db(), "niphad", "tomato", "late_blight", n=8, confirmed=0, fields=3)
    a = get_runtime().outbreak.assess("niphad", "late_blight")
    assert a["grade"] in ("emerging_cluster", "suspected_hotspot")
    assert a["grade"] != "confirmed_hotspot"
    assert a["confirmed"] == 0
    assert "expert-confirmed" in " ".join(e["detail"] for e in a["evidence"])
    assert "cluster of photographs" in a["recommended_action"] or a["recommended_action"]


def test_the_word_outbreak_is_not_used_without_confirmations(client, officer):
    import json
    from app.db import get_db
    from app.runtime import get_runtime
    _plant_reports(get_db(), "niphad", "tomato", "late_blight", n=9, confirmed=0, fields=3)
    a = get_runtime().outbreak.assess("niphad", "late_blight")
    text = json.dumps(a).lower()
    assert "confirmed hotspot" not in text
    assert a["label"] in ("Emerging cluster", "Suspected hotspot")


def test_confirmations_are_what_promote_a_cluster_to_confirmed(client, officer):
    from app.db import get_db
    from app.runtime import get_runtime
    db = get_db()
    _plant_reports(db, "niphad", "tomato", "late_blight", n=10, confirmed=5, fields=4)
    a = get_runtime().outbreak.assess("niphad", "late_blight")
    assert a["confirmed"] >= 3
    if a["gi_z"] and a["gi_z"] > 1.96:
        assert a["grade"] == "confirmed_hotspot"
    else:
        assert a["grade"] == "emerging_cluster"
        assert "not a statistically significant cluster" in \
            " ".join(e["detail"] for e in a["evidence"])


def test_growth_rate_is_null_rather_than_infinite_on_a_first_appearance(client, officer):
    from app.db import get_db
    from app.runtime import get_runtime
    _plant_reports(get_db(), "dindori", "tomato", "late_blight", n=4, confirmed=0,
                   fields=2, days_back=1)
    a = get_runtime().outbreak.assess("dindori", "late_blight")
    assert a["growth_pct_72h"] is None or isinstance(a["growth_pct_72h"], float)


def test_the_officer_queue_ranks_uncertainty_not_confidence(client, farmer, plot, officer):
    scan(client, farmer["headers"], plot["id"], "blurry")
    scan(client, farmer["headers"], plot["id"], "blight")
    q = client.get("/api/officer/queue?capacity=5", headers=officer["headers"]).json()
    assert q["queue"]
    assert "not by confidence" in q["rationale"]
    assert all("why" in c for c in q["queue"])


def test_the_officer_route_is_labelled_a_suggestion(client, farmer, plot, officer):
    scan(client, farmer["headers"], plot["id"], "blight")
    r = client.get("/api/officer/route?capacity=5", headers=officer["headers"]).json()
    assert "not an optimal route" in r["caveat"]
    assert "straight-line" in r["caveat"]
    for i, s in enumerate(r["sequence"]):
        assert s["position"] == i + 1


def test_the_audit_views_are_group_bys_over_stored_rows(client, farmer, plot, officer, monsoon):
    client.post("/api/threshold", headers=farmer["headers"],
                json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 1.0})
    a = client.get("/api/officer/audit", headers=officer["headers"]).json()
    assert a["spray_ledger"]
    assert a["label_claims_by_status"]
    assert "GROUP BY over stored rows" in a["note"]
    ledger = a["spray_ledger"][0]
    assert ledger["checks"] >= 1
    assert ledger["not_sprayed"] >= 1


def test_the_spray_ledger_states_its_counterfactual(client, farmer, plot, monsoon):
    client.post("/api/threshold", headers=farmer["headers"],
                json={"plot_id": plot["id"], "pest": "helicoverpa", "count": 1.0})
    r = client.get(f"/api/ledger?plot_id={plot['id']}", headers=farmer["headers"]).json()
    s = r["summary"]
    assert "7-day prophylactic" in s["baseline"]
    assert "not a controlled trial" in s["caveat"]


def test_a_narrow_officer_scope_still_gets_a_hotspot_statistic(client, admin):
    """Gi* is a LOCAL statistic and needs neighbours. Computing it over a
    two-taluka scope returned an empty list — silently, which is the worst way
    for a statistic to fail."""
    from app.db import get_db
    r = client.post("/api/admin/users", headers=admin["headers"], json={
        "full_name": "Narrow Officer", "password": "strong-pass-2026", "role": "officer",
        "email": "narrow@prahari-test.example.com", "taluka": "niphad"})
    oid = r.json()["profile"]["id"]
    client.post(f"/api/admin/officers/{oid}/scopes?taluka=pimpalgaon", headers=admin["headers"])
    login = client.post("/api/auth/login", json={
        "identifier": "narrow@prahari-test.example.com", "password": "strong-pass-2026"})
    H = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert sorted(client.get("/api/auth/me", headers=H).json()["scopes"]) == ["niphad", "pimpalgaon"]

    _plant_reports(get_db(), "niphad", "tomato", "late_blight", n=6, confirmed=1, fields=3)
    out = client.get("/api/officer/hotspots?problem=late_blight", headers=H).json()
    assert len(out["hotspots"]) == 2, "a two-taluka scope must still get scored rows"
    assert {h["taluka"] for h in out["hotspots"]} == {"niphad", "pimpalgaon"}
    assert any(h["z"] != 0 for h in out["hotspots"])
    assert "filtered to the" in out["statistic"]
