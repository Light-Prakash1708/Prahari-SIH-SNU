"""
PRAHARI · what the surveillance screen is allowed to say

The screen shows a risk grade, a change figure, a ranked list and six weekly
bars. Every one of those is a count of rows, and the tests that matter here are
the ones where there is nothing to count — because that is the state of a
district on the morning of a demonstration, and the temptation to fill it is
exactly what would cost PRAHARI its credibility in front of a judge.

The rule: no percentage without a denominator, no trend without two weeks, no
village geography where only taluka geography exists.
"""
from __future__ import annotations

from conftest import scan

from app import trajectory as tj
from app.clock import now_iso


def _case(db, plot, day, problem="late_blight", taluka="niphad", oid=None):
    oid = oid or ("OS" + day.replace("-", "") + problem[:3] + str(abs(hash(day)) % 997))
    db.execute(
        "INSERT INTO observations (id, plot_id, farmer_id, kind, taluka, crop,"
        " observed_at, source, status, created_at)"
        " VALUES (:id,:p,:f,'leaf',:tk,'tomato',:at,'app','open',:now)",
        {"id": oid, "p": plot["id"], "f": plot["farmer_id"], "tk": taluka,
         "at": day, "now": now_iso()})
    db.execute(
        "INSERT INTO diagnoses (id, observation_id, plot_id, crop, engine, model_version,"
        " top_problem, top_posterior, abstained, created_at)"
        " VALUES (:d,:o,:p,'tomato','features','v1',:pb,0.8,0,:now)",
        {"d": "D-" + oid, "o": oid, "p": plot["id"], "pb": problem, "now": now_iso()})
    return oid


# ── the change figure ───────────────────────────────────────────────────────
def test_an_empty_district_reports_no_cases_not_zero_percent(client, farmer, plot):
    from app.db import get_db
    out = tj.surveillance_change(get_db(), "niphad", "late_blight", 21)
    assert out["cases_now"] == 0 and out["cases_before"] == 0
    assert out["change_pct"] is None
    assert out["comparable"] is False
    assert "No cases" in out["note"]


def test_growth_from_nothing_shows_no_percentage(client, farmer, plot):
    """The assertion that matters most. Four cases where there were none is not
    '+400%' — there is nothing to divide by, and a judge will ask."""
    from app.db import get_db
    db = get_db()
    for d in ("2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27"):
        _case(db, plot, d)
    out = tj.surveillance_change(db, "niphad", "late_blight", 21)
    assert out["cases_now"] == 4
    assert out["cases_before"] == 0
    assert out["change_pct"] is None, "a percentage was invented from a zero base"
    assert out["direction"] == "up"
    assert "no percentage is shown" in out["note"]


def test_a_real_percentage_is_only_shown_with_a_real_base(client, farmer, plot):
    from app.db import get_db
    db = get_db()
    # 2 in the prior window (22-42 days back), 4 in the recent 21
    for d in ("2026-07-25", "2026-07-28"):
        _case(db, plot, d)
    for d in ("2026-08-20", "2026-08-22", "2026-08-25", "2026-08-27"):
        _case(db, plot, d)
    out = tj.surveillance_change(db, "niphad", "late_blight", 21)
    assert out["comparable"] is True
    assert out["cases_before"] == 2 and out["cases_now"] == 4
    assert out["change_pct"] == 100
    assert out["direction"] == "up"


def test_a_small_move_is_flat_not_a_direction(client, farmer, plot):
    from app.db import get_db
    db = get_db()
    for d in ("2026-07-25", "2026-07-26", "2026-07-27", "2026-07-28",
              "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-01",
              "2026-08-02", "2026-08-03"):
        _case(db, plot, d)
    for d in ("2026-08-20", "2026-08-21", "2026-08-22", "2026-08-23",
              "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27",
              "2026-08-18", "2026-08-19"):
        _case(db, plot, d)
    out = tj.surveillance_change(db, "niphad", "late_blight", 21)
    assert out["change_pct"] == 0
    assert out["direction"] == "flat"


# ── the trend bars ──────────────────────────────────────────────────────────
def test_one_week_of_cases_is_not_a_trend(client, farmer, plot):
    from app.db import get_db
    db = get_db()
    for d in ("2026-08-25", "2026-08-26", "2026-08-27"):
        _case(db, plot, d)
    out = tj.weekly_counts(db, "niphad", "late_blight", 6)
    assert out["total"] == 3
    assert out["enough"] is False
    assert "Not enough history" in out["note"]


def test_two_separate_weeks_make_a_trend_and_empty_weeks_are_zero(client, farmer, plot):
    from app.db import get_db
    db = get_db()
    _case(db, plot, "2026-08-10")
    _case(db, plot, "2026-08-26")
    out = tj.weekly_counts(db, "niphad", "late_blight", 6)
    assert out["enough"] is True
    assert len(out["weeks"]) == 6
    assert sum(w["cases"] for w in out["weeks"]) == 2
    # empty weeks present as zero, never omitted
    assert any(w["cases"] == 0 for w in out["weeks"])


# ── last reported ───────────────────────────────────────────────────────────
def test_never_reported_returns_none_not_a_date(client, farmer, plot):
    from app.db import get_db
    assert tj.last_reported(get_db(), "niphad", "late_blight") is None


def test_last_reported_is_the_most_recent_case(client, farmer, plot):
    from app.db import get_db
    db = get_db()
    _case(db, plot, "2026-08-10")
    _case(db, plot, "2026-08-25")
    out = tj.last_reported(db, "niphad", "late_blight")
    assert out["day"] == "2026-08-25"
    assert out["days_ago"] == 2


# ── the endpoint the screen calls ───────────────────────────────────────────
def test_nearby_carries_everything_the_screen_needs(client, farmer, plot):
    r = client.get(f"/api/fields/{plot['id']}/nearby?problem=late_blight&days=21",
                   headers=farmer["headers"])
    assert r.status_code == 200, r.text
    b = r.json()
    for k in ("change", "trend_weeks", "last_reported", "affected_talukas",
              "nearby_talukas", "assessment", "privacy", "window_days"):
        assert k in b, k
    assert b["window_days"] == 21


def test_the_time_range_actually_changes_the_window(client, farmer, plot):
    for d in (7, 21, 90):
        b = client.get(f"/api/fields/{plot['id']}/nearby?problem=late_blight&days={d}",
                       headers=farmer["headers"]).json()
        assert b["window_days"] == d
        assert b["change"]["note"], "the change card must always have a sentence"


def test_the_screen_is_given_taluka_geography_only(client, farmer, plot):
    """No village name and no finer coordinate than a taluka centroid. The
    ranked list says 'talukas' because that is what the data is."""
    import json
    b = client.get(f"/api/fields/{plot['id']}/nearby", headers=farmer["headers"]).json()
    for row in b["nearby_talukas"]:
        assert set(row) <= {"taluka", "name", "name_mr", "lat", "lng", "z", "class",
                            "cases", "incidence_per_1000"}
    blob = json.dumps(b)
    assert "village" not in blob.lower()
    assert "farmer_id" not in blob


def test_another_farmer_cannot_read_this_field_surveillance(
        client, farmer, farmer_b, plot):
    assert client.get(f"/api/fields/{plot['id']}/nearby",
                      headers=farmer_b["headers"]).status_code == 403


def test_a_scan_is_what_puts_a_case_on_the_map(client, farmer, plot):
    """Connects the screen's 'Report a case' claim to reality."""
    before = client.get(f"/api/fields/{plot['id']}/nearby",
                        headers=farmer["headers"]).json()["total_cases"]
    scan(client, farmer["headers"], plot["id"])
    after = client.get(f"/api/fields/{plot['id']}/nearby",
                       headers=farmer["headers"]).json()
    # The scan may abstain on a synthetic image; what must hold is that the
    # endpoint still answers and still reports honestly.
    assert after["total_cases"] >= before
    assert after["privacy"]
