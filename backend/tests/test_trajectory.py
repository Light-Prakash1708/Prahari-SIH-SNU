"""
PRAHARI · the derivations, and their honest empty answers

Four functions that name a conclusion the engines already support, plus a
report page. None of them is allowed to invent the conclusion, so most of what
follows tests the case where there is nothing to conclude — which is the case
that actually ships on a field a farmer opened yesterday.

The rule under test throughout: a derivation may state only what the rows
support, and when they support nothing it says so rather than defaulting to a
value that reads like information.
"""
from __future__ import annotations

import json

from conftest import scan

from app import trajectory as tj


def _n():
    from app.clock import now_iso
    return now_iso()


# ── trajectory ──────────────────────────────────────────────────────────────
def test_a_field_seen_once_has_no_trajectory(client, farmer, plot):
    """The assertion that matters most here. One reading is not a direction,
    and calling it 'stable' is the most dangerous default available."""
    out = client.get(f"/api/fields/{plot['id']}/health",
                     headers=farmer["headers"]).json()["trajectory"]
    assert out["state"] == "unknown"
    assert "Not enough field history yet" in out["note"]
    assert out["delta"] is None


def test_a_falling_score_is_worsening_and_says_by_how_much(client, farmer, plot, env):
    from app.db import get_db
    db = get_db()
    for day, score in (("2026-08-20", 88.0), ("2026-08-27", 62.0)):
        db.execute("INSERT INTO health_snapshots (plot_id, day, score, disease, pest, weather,"
                   " nearby, drivers, created_at) VALUES (:p,:d,:s,0,0,0,0,'{}',:now)",
                   {"p": plot["id"], "d": day, "s": score, "now": _n()})
    out = tj.trajectory(db, plot["id"])
    assert out["state"] == "worsening"
    assert out["delta"] == -26.0
    assert any("fallen 26" in r["text"] for r in out["reasons"]), out["reasons"]


def test_a_rising_score_is_improving(client, farmer, plot):
    from app.db import get_db
    db = get_db()
    for day, score in (("2026-08-20", 55.0), ("2026-08-27", 91.0)):
        db.execute("INSERT INTO health_snapshots (plot_id, day, score, disease, pest, weather,"
                   " nearby, drivers, created_at) VALUES (:p,:d,:s,0,0,0,0,'{}',:now)",
                   {"p": plot["id"], "d": day, "s": score, "now": _n()})
    assert tj.trajectory(db, plot["id"])["state"] == "improving"


def test_movement_below_the_threshold_is_not_called_a_direction(client, farmer, plot):
    """Two points of wobble is the weather term breathing, not the field
    changing, and naming it would make the state flicker day to day."""
    from app.db import get_db
    db = get_db()
    for day, score in (("2026-08-20", 70.0), ("2026-08-27", 72.0)):
        db.execute("INSERT INTO health_snapshots (plot_id, day, score, disease, pest, weather,"
                   " nearby, drivers, created_at) VALUES (:p,:d,:s,0,0,0,0,'{}',:now)",
                   {"p": plot["id"], "d": day, "s": score, "now": _n()})
    out = tj.trajectory(db, plot["id"])
    assert out["state"] == "stable"
    assert any("not a change this score can distinguish" in r["text"] for r in out["reasons"])


def test_the_farmers_own_worse_report_outranks_a_flat_score(client, farmer, plot):
    """What the farmer saw in the field beats what the model scored from a
    forecast. A 'worse' outcome they typed is the strongest signal available."""
    from app.clock import now_iso
    from app.db import get_db
    db = get_db()
    for day, score in (("2026-08-20", 70.0), ("2026-08-27", 71.0)):
        db.execute("INSERT INTO health_snapshots (plot_id, day, score, disease, pest, weather,"
                   " nearby, drivers, created_at) VALUES (:p,:d,:s,0,0,0,0,'{}',:now)",
                   {"p": plot["id"], "d": day, "s": score, "now": _n()})
    db.execute("INSERT INTO followups (plot_id, due_on, outcome, done_on, created_at)"
               " VALUES (:p,'2026-08-27','worse','2026-08-27',:now)",
               {"p": plot["id"], "now": now_iso()})
    out = tj.trajectory(db, plot["id"])
    assert out["state"] == "worsening"
    assert any(r["kind"] == "followup" for r in out["reasons"])


# ── escalation ──────────────────────────────────────────────────────────────
def test_with_nothing_wrong_escalation_is_low_and_offers_the_route_anyway():
    out = tj.escalation(decision=None, diagnosis=None, traj=None,
                        chemical_available=None, open_followups=0)
    assert out["level"] == "low"
    assert out["reasons"] == []
    assert "still ask" in out["note"]


def test_an_abstention_is_high_and_names_itself():
    out = tj.escalation(decision=None, diagnosis={"abstained": True}, traj=None,
                        chemical_available=None, open_followups=0)
    assert out["level"] == "high"
    assert any("declined to name" in r["text"] for r in out["reasons"])


def test_a_worsening_field_is_high():
    out = tj.escalation(decision=None, diagnosis=None,
                        traj={"state": "worsening"}, chemical_available=None)
    assert out["level"] == "high"


def test_low_confidence_alone_is_medium_not_high():
    out = tj.escalation(decision=None, diagnosis={"confidence_band": "low"},
                        traj=None, chemical_available=None)
    assert out["level"] == "medium"


def test_the_level_is_the_highest_band_not_an_average():
    """Three mediums must not add up to a high, and one high must not be
    diluted by two lows. Categorical findings are not averaged."""
    out = tj.escalation(decision=None, diagnosis={"confidence_band": "low"},
                        traj={"state": "watch"}, chemical_available=False,
                        open_followups=3)
    assert out["level"] == "medium"
    assert len(out["reasons"]) >= 3
    out2 = tj.escalation(decision=None, diagnosis={"abstained": True}, traj=None,
                         chemical_available=None)
    assert out2["level"] == "high" and len(out2["reasons"]) == 1


def test_the_management_screen_carries_the_same_verdict(client, farmer, plot):
    m = client.get(f"/api/management/{plot['id']}", headers=farmer["headers"]).json()
    assert m["escalation"]["level"] in ("low", "medium", "high")
    assert "trajectory" in m
    assert m["trajectory"]["state"] in tj.STATES


def test_the_expert_brief_receives_the_escalation_automatically(
        client, farmer, plot, expert, leaf):
    """The feature requirement: the expert must not have to reconstruct why the
    case was sent. It arrives with the brief, from the same function."""
    obs = scan(client, farmer["headers"], plot["id"]).json()
    r = client.post(f"/api/observations/{obs['observation']['id']}/expert-review",
                    headers=farmer["headers"], json={"note": "spreading"})
    assert r.status_code in (200, 201), r.text
    cases = client.get("/api/expert/cases", headers=expert["headers"]).json()
    items = cases.get("items") or cases.get("cases") or []
    assert items, cases
    brief = client.get(f"/api/expert/cases/{items[0]['id']}",
                       headers=expert["headers"]).json()
    assert brief["escalation"]["level"] in ("low", "medium", "high")
    assert "information_missing" in brief
    assert isinstance(brief["information_missing"], list)


def test_the_brief_names_what_it_does_not_have(client, farmer, plot, expert):
    obs = scan(client, farmer["headers"], plot["id"]).json()
    client.post(f"/api/observations/{obs['observation']['id']}/expert-review",
                headers=farmer["headers"], json={"note": "spreading"})
    items = client.get("/api/expert/cases", headers=expert["headers"]).json()
    items = items.get("items") or items.get("cases") or []
    brief = client.get(f"/api/expert/cases/{items[0]['id']}",
                       headers=expert["headers"]).json()
    kinds = {m["kind"] for m in brief["information_missing"]}
    # one photograph and no answered questions is the state of a fresh scan
    assert "farmer_answers" in kinds or "image" in kinds, brief["information_missing"]


# ── next best action ────────────────────────────────────────────────────────
def test_an_empty_agenda_produces_no_action_rather_than_a_blank_card():
    assert tj.next_best_action({"items": []}) is None
    assert tj.next_best_action(None) is None


def test_the_next_action_is_the_agendas_first_item_unchanged():
    agenda = {"items": [
        {"key": "phi", "tone": "urgent", "icon": "🚫", "title": "Do not harvest",
         "title_mr": "काढणी नको", "detail": "d", "detail_mr": "d", "evidence": [{"kind": "x"}]},
        {"key": "scout", "tone": "act", "icon": "🍂", "title": "Scout"},
    ]}
    out = tj.next_best_action(agenda)
    assert out["key"] == "phi"
    assert out["title"] == "Do not harvest"
    assert out["also_due"] == 1
    assert "already ordered" in out["basis"]


def test_today_exposes_one_next_action(client, farmer, plot):
    out = client.get(f"/api/fields/{plot['id']}/today", headers=farmer["headers"]).json()
    assert "next_action" in out
    if out.get("items"):
        assert out["next_action"]["title"] == out["items"][0]["title"]
    else:
        assert out["next_action"] is None


# ── officer early signals ───────────────────────────────────────────────────
def test_no_scope_is_said_plainly(client):
    from app.db import get_db
    assert early_note(early_signals_for(get_db(), []))


def early_signals_for(db, talukas):
    return tj.early_signals(db, talukas)


def early_note(out):
    return bool(out["note"]) and out["signals"] == []


def test_a_quiet_district_reports_insufficient_data_not_normal(client, farmer, plot):
    from app.db import get_db
    out = tj.early_signals(get_db(), ["niphad", "pimpalgaon"])
    assert out["signals"] == []
    assert "Insufficient data" in out["note"]


def test_a_signal_needs_growth_over_the_previous_window(client, farmer, plot):
    """The whole point: a count that has always been five is not news."""
    from app.clock import now_iso
    from app.db import get_db
    db = get_db()

    def case(oid: str, day: str) -> None:
        db.execute(
            "INSERT INTO observations (id, plot_id, farmer_id, kind, taluka, crop,"
            " observed_at, source, status, created_at)"
            " VALUES (:id,:p,:f,'leaf','niphad','tomato',:at,'app','open',:now)",
            {"id": oid, "p": plot["id"], "f": plot["farmer_id"], "at": day, "now": now_iso()})
        db.execute(
            "INSERT INTO diagnoses (id, observation_id, plot_id, crop, engine, model_version,"
            " top_problem, top_posterior, abstained, created_at)"
            " VALUES (:d,:o,:p,'tomato','features','v1','late_blight',0.8,0,:now)",
            {"d": "D-" + oid, "o": oid, "p": plot["id"], "now": now_iso()})

    # four in the recent window, none before it
    for i, day in enumerate(("2026-08-25", "2026-08-26", "2026-08-26", "2026-08-27")):
        case(f"OT{i}", day)
    out = tj.early_signals(db, ["niphad"], days=7)
    assert out["signals"], out
    sig = out["signals"][0]
    assert sig["problem"] == "late_blight"
    assert sig["cases_now"] == 4 and sig["cases_before"] == 0
    assert sig["confidence"] == "moderate", sig["confidence"]
    assert "4 diagnosed cases in the last 7 days" in sig["what_changed"]
    assert sig["check"]


def test_a_signal_below_the_minimum_is_not_reported(client, farmer, plot):
    from app.clock import now_iso
    from app.db import get_db
    db = get_db()
    db.execute("INSERT INTO observations (id, plot_id, farmer_id, kind, taluka, crop,"
               " observed_at, source, status, created_at)"
               " VALUES ('OX1',:p,:f,'leaf','niphad','tomato','2026-08-27','app','open',:now)",
               {"p": plot["id"], "f": plot["farmer_id"], "now": now_iso()})
    db.execute("INSERT INTO diagnoses (id, observation_id, plot_id, crop, engine, model_version,"
               " top_problem, top_posterior, abstained, created_at)"
               " VALUES ('D-OX1','OX1',:p,'tomato','features','v1','late_blight',0.8,0,:now)",
               {"p": plot["id"], "now": now_iso()})
    out = tj.early_signals(db, ["niphad"], days=7)
    assert out["signals"] == []
    assert "at least 3" in out["note"]


def test_the_officer_summary_carries_early_signals(client, officer):
    out = client.get("/api/officer/summary", headers=officer["headers"]).json()
    assert "early_signals" in out
    assert "signals" in out["early_signals"]


def test_a_farmer_cannot_read_officer_signals(client, farmer):
    assert client.get("/api/officer/summary",
                      headers=farmer["headers"]).status_code == 403


# ── the field report ────────────────────────────────────────────────────────
def test_the_report_works_on_a_field_with_no_history(client, farmer, plot):
    r = client.get(f"/api/fields/{plot['id']}/report", headers=farmer["headers"])
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["latest_diagnosis"] is None
    assert b["expert_verdict"] is None
    assert b["trajectory"]["state"] == "unknown"
    assert "decision support" in b["disclaimer"]


def test_the_report_carries_the_disclaimer_in_both_languages(client, farmer, plot):
    b = client.get(f"/api/fields/{plot['id']}/report",
                   headers=farmer["headers"]).json()
    assert "not an official agricultural recommendation" in b["disclaimer"]
    assert any("ऀ" <= ch <= "ॿ" for ch in b["disclaimer_mr"])


def test_the_report_never_carries_the_farmers_identity_or_coordinates(
        client, farmer, plot):
    """It is made to be handed to someone else."""
    b = client.get(f"/api/fields/{plot['id']}/report",
                   headers=farmer["headers"]).json()
    blob = json.dumps(b)
    assert "farmer_id" not in blob
    assert "lat" not in b["plot"] and "lng" not in b["plot"]


def test_the_report_shows_a_real_diagnosis_once_one_exists(client, farmer, plot):
    scan(client, farmer["headers"], plot["id"])
    b = client.get(f"/api/fields/{plot['id']}/report",
                   headers=farmer["headers"]).json()
    assert b["latest_diagnosis"] is not None


def test_another_farmer_cannot_read_this_report(client, farmer, farmer_b, plot):
    assert client.get(f"/api/fields/{plot['id']}/report",
                      headers=farmer_b["headers"]).status_code == 403
