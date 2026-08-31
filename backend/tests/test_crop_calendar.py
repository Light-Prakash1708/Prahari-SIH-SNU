"""
PRAHARI · crop calendar — the acceptance tests

The brief's acceptance criterion is that the calendar must MOVE. Changing the
crop, the field or the sowing date must change what is returned; history must
come from real records; and nothing on the screen may be fabricated.

The last of those is what most of this file actually checks, because it is the
easy thing to get wrong: a threat-window timeline is very tempting to fill in
with plausible colour for stages the models cannot see.
"""
from __future__ import annotations


def _cal(client, headers, plot_id):
    r = client.get(f"/api/crop-calendar/{plot_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ── it moves ────────────────────────────────────────────────────────────────

def test_the_sowing_date_moves_the_whole_calendar(client, farmer):
    """Two identical fields sown eleven weeks apart are at different stages,
    and every date on the timeline shifts with the sowing date."""
    early = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Sown early", "crop": "tomato", "area_acre": 1.0,
        "sown_on": "2026-06-01", "taluka": "niphad"}).json()
    late = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Sown late", "crop": "tomato", "area_acre": 1.0,
        "sown_on": "2026-08-18", "taluka": "niphad"}).json()

    a = _cal(client, farmer["headers"], early["id"])
    b = _cal(client, farmer["headers"], late["id"])

    assert a["crop_stage"]["days"] > b["crop_stage"]["days"]
    assert a["crop_stage"]["stage"] != b["crop_stage"]["stage"]

    # the timeline is real dates derived from the sowing date, not day numbers
    assert a["timeline"][0]["from"] == "2026-06-01"
    assert b["timeline"][0]["from"] == "2026-08-18"
    assert a["timeline"][0]["from"] != b["timeline"][0]["from"]

    # exactly one stage is current, and it agrees with crop_stage
    cur = [s for s in a["timeline"] if s["current"]]
    assert len(cur) == 1
    assert cur[0]["stage"] == a["crop_stage"]["stage"]


def test_the_crop_changes_the_threats(client, farmer):
    """A tomato field and an onion field do not carry the same watchlist —
    the threats come from the crop's own problem set, not a shared list."""
    tom = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Tomato", "crop": "tomato", "area_acre": 1.0,
        "sown_on": "2026-06-15", "taluka": "niphad"}).json()
    onion = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Onion", "crop": "onion", "area_acre": 1.0,
        "sown_on": "2026-06-15", "taluka": "niphad"}).json()

    a = _cal(client, farmer["headers"], tom["id"])
    b = _cal(client, farmer["headers"], onion["id"])

    assert a["crop"]["id"] == "tomato" and b["crop"]["id"] == "onion"
    assert [s["stage"] for s in a["timeline"]] != [s["stage"] for s in b["timeline"]] \
        or a["threat_windows"] != b["threat_windows"]

    pests_a = {p["id"] for w in a["threat_windows"] for p in w["pests"]}
    pests_b = {p["id"] for w in b["threat_windows"] for p in w["pests"]}
    assert pests_a and pests_b
    assert pests_a != pests_b


def test_a_field_with_no_sowing_date_gets_day_numbers_not_invented_dates(client, farmer):
    p = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "No date", "crop": "tomato", "area_acre": 1.0,
        "sown_on": "2026-06-15", "taluka": "niphad"}).json()
    # Blank the sowing date the way an incomplete registration would. The
    # active crop cycle is the authority for the date and the plot row is the
    # fallback, so a genuinely unknown sowing date means clearing both — which
    # is itself worth asserting, since clearing only the plot must NOT make the
    # calendar forget a date the cycle still holds.
    from app.db import get_db
    db = get_db()
    db.execute("UPDATE plots SET sown_on = NULL WHERE id = :i", {"i": p["id"]})
    still = _cal(client, farmer["headers"], p["id"])
    assert still["crop"]["sown_on"] == "2026-06-15", "the cycle's date must still win"

    # crop_cycles.sown_on is NOT NULL by design — a cycle always knows when it
    # started. So the genuine "no sowing date" case is a field with no open
    # cycle and no date on the plot row.
    db.execute("DELETE FROM crop_cycles WHERE plot_id = :i", {"i": p["id"]})

    cal = _cal(client, farmer["headers"], p["id"])
    assert cal["crop"]["sown_on"] is None
    assert cal["crop_stage"]["stage"] is None
    for st in cal["timeline"]:
        assert st["from"] is None and st["to"] is None
        assert st["day_from"] is not None      # the band is still known


# ── it does not fabricate ───────────────────────────────────────────────────

def test_disease_bands_appear_only_on_the_current_stage(client, farmer, plot):
    """The central honesty rule. A disease fires on weather; weather beyond the
    forecast horizon does not exist; so a future stage cannot carry a disease
    band. If this test ever fails, someone has started colouring in the future.
    """
    cal = _cal(client, farmer["headers"], plot["id"])
    current = cal["crop_stage"]["stage"]
    for w in cal["threat_windows"]:
        if w["stage"] != current:
            assert w["diseases"] == [], (
                f"stage {w['stage']} carries disease bands but is not the current stage")
    assert "weather that does not exist yet" in cal["disease_note"]


def test_every_pest_band_carries_its_source_and_its_arithmetic(client, farmer, plot):
    """Pest vulnerability per stage is read off the ICAR threshold tables. Each
    row must show the factor, the base threshold, the adjusted threshold and the
    citation — so an agronomist can check it rather than take it."""
    cal = _cal(client, farmer["headers"], plot["id"])
    rows = [p for w in cal["threat_windows"] for p in w["pests"]]
    assert rows, "tomato has thresholds with stage factors; none came through"
    for p in rows:
        assert p["source"], f"{p['id']} has no citation"
        assert p["etl"] and p["stage_factor"]
        assert p["etl_at_this_stage"] == round(p["etl"] * p["stage_factor"], 2)
        assert p["band"] in ("high", "watch", "normal", "tolerant")


def test_the_threat_timeline_discriminates_between_stages(client, farmer, plot):
    """A timeline where every stage is red tells a farmer nothing.

    Each pest is banded against its own range across this crop's stages, and a
    stage is banded by how many pests peak there — so the stages must not all
    come back the same. Tomato in particular must single out fruiting, where
    both Tuta and Helicoverpa are at their lowest thresholds.
    """
    cal = _cal(client, farmer["headers"], plot["id"])
    bands = [w["band"] for w in cal["threat_windows"]]
    assert len(set(bands)) > 1, f"every stage came back the same band: {bands}"
    assert bands.count("high") <= max(1, len(bands) // 2), (
        f"most stages are 'high', which is the failure this banding exists to avoid: {bands}")

    # every pest must be at its own peak somewhere on the timeline, and not
    # at its peak everywhere
    by_pest = {}
    for w in cal["threat_windows"]:
        for p in w["pests"]:
            by_pest.setdefault(p["id"], []).append(p["band"])
    for pid, seq in by_pest.items():
        if len(seq) > 2:
            assert len(set(seq)) > 1, f"{pid} carries one band at every stage: {seq}"


def test_a_pest_peak_is_relative_to_that_pest_not_an_absolute_cutoff(client, farmer, plot):
    """Whitefly on tomato sits at 0.5–0.6 early and Tuta at 0.7 late. Under an
    absolute cutoff both read 'high' and the screen says everything is urgent.
    Banded against each pest's own range, each one peaks where it actually
    does — whitefly at the seedling stages, Tuta at fruiting."""
    cal = _cal(client, farmer["headers"], plot["id"])
    peak_stage = {}
    for w in cal["threat_windows"]:
        for p in w["pests"]:
            if p["band"] == "high":
                peak_stage.setdefault(p["id"], []).append(w["stage"])

    assert "whitefly" in peak_stage and "tuta" in peak_stage
    assert peak_stage["whitefly"] != peak_stage["tuta"], (
        "two pests with different seasons peaked at the same stages")
    assert "fruiting" in peak_stage["tuta"]
    assert "fruiting" not in peak_stage["whitefly"]

    # peak_factor is the pest's own minimum, and is returned so the relative
    # judgement can be checked rather than taken on trust
    for w in cal["threat_windows"]:
        for p in w["pests"]:
            assert p["peak_factor"] <= p["stage_factor"]


def test_prevention_window_factors_are_evidence_not_placeholders(client, farmer, plot):
    """Every factor must be a statement about a record that exists. None may be
    a 'no data available' filler line."""
    cal = _cal(client, farmer["headers"], plot["id"])
    pw = cal["prevention_window"]
    assert pw["level"] in ("low", "watch", "rising", "high")
    assert isinstance(pw["factors"], list)
    for f in pw["factors"]:
        assert f["kind"] in ("weather", "stage", "trap", "regional")
        assert f["text"] and f["text"].strip()
        low = f["text"].lower()
        assert "no data" not in low and "unknown" not in low and "n/a" not in low


def test_history_comes_from_records_and_is_empty_when_there_are_none(client, farmer):
    """A brand-new field has no history. The endpoint must say so with an empty
    list rather than seeding a plausible-looking past."""
    fresh = client.post("/api/plots", headers=farmer["headers"], json={
        "name": "Brand new", "crop": "tomato", "area_acre": 1.0,
        "sown_on": "2026-08-20", "taluka": "niphad"}).json()
    cal = _cal(client, farmer["headers"], fresh["id"])
    assert cal["history"] == []


def test_history_picks_up_a_real_trap_count(client, farmer, plot):
    """Record a trap count through the existing API; it must appear in the
    calendar's history, proving the history is read from the field's own rows
    and not assembled separately."""
    trap = client.post("/api/traps", headers=farmer["headers"], json={
        "plot_id": plot["id"], "pest": "helicoverpa", "kind": "pheromone"}).json()
    client.post(f"/api/traps/{trap['id']}/counts", headers=farmer["headers"],
                json={"count": 4, "counted_on": "2026-08-26"})

    cal = _cal(client, farmer["headers"], plot["id"])
    traps = [h for h in cal["history"] if h["kind"] == "trap"]
    assert traps, "a recorded trap count did not reach the calendar history"
    assert any("4" in t["title"] for t in traps)


# ── it reuses, rather than duplicates ───────────────────────────────────────

def test_the_mission_is_the_existing_agenda_not_a_second_system(client, farmer, plot):
    """The brief forbids a duplicate mission system. The calendar's mission must
    be byte-identical to what /api/fields/{id}/today already returns."""
    cal = _cal(client, farmer["headers"], plot["id"])
    today = client.get(f"/api/fields/{plot['id']}/today",
                       headers=farmer["headers"]).json()
    assert cal["mission"]["plot_id"] == today["plot_id"]
    assert [i["key"] for i in cal["mission"]["items"]] == [i["key"] for i in today["items"]]


def test_the_stage_agrees_with_the_risk_endpoint(client, farmer, plot):
    """Two screens must never disagree about what stage the crop is in."""
    cal = _cal(client, farmer["headers"], plot["id"])
    risk = client.get(f"/api/risk/{plot['id']}", headers=farmer["headers"]).json()
    assert cal["crop_stage"] == risk["crop_stage"]


# ── it is scoped ────────────────────────────────────────────────────────────

def test_another_farmers_field_is_not_readable(client, farmer, farmer_b, plot):
    r = client.get(f"/api/crop-calendar/{plot['id']}", headers=farmer_b["headers"])
    assert r.status_code in (403, 404)


def test_signing_out_closes_the_calendar(client, plot):
    r = client.get(f"/api/crop-calendar/{plot['id']}")
    assert r.status_code == 401
