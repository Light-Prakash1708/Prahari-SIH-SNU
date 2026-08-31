-- ═══════════════════════════════════════════════════════════════════════════
-- PRAHARI · migration 003 — soil, water and weeds
--
-- Three tables, one principle each:
--
--   soil_tests        a soil report is DATED and it is the farmer's own datum.
--                     Two tests a year apart are the only way anyone finds out
--                     whether the manure worked, so the table keeps both rather
--                     than overwriting.
--
--   irrigation_events the water balance in irrigation.py is a MODEL, and a
--                     model that is never corrected drifts. This row is the
--                     correction: it resets the depletion to zero on the day
--                     the farmer says they watered.
--
--   weed_checks       green cover from one photograph is a weak absolute
--                     measurement and a strong RELATIVE one. Storing the series
--                     is what makes it useful — 8% in June and 34% in August is
--                     a finding; 34% on its own is a number.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS soil_tests (
  id              TEXT PRIMARY KEY,
  plot_id         TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  kind            TEXT NOT NULL DEFAULT 'self_test',   -- self_test | lab
  tested_on       TEXT NOT NULL,
  -- the visual assessment
  answers         {{JSON}},
  score           INTEGER,
  out_of          INTEGER,
  band            TEXT,
  -- the laboratory numbers, each nullable because most farmers have some and
  -- not others, and a missing value must stay missing rather than default to 0
  organic_carbon_pct {{FLOAT}},
  nitrogen_kg_ha  {{FLOAT}},
  phosphorus_kg_ha {{FLOAT}},
  potassium_kg_ha {{FLOAT}},
  ph              {{FLOAT}},
  lab_name        TEXT,
  report_ref      TEXT,
  findings        {{JSON}},
  created_at      {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_soil_plot ON soil_tests(plot_id, tested_on DESC);

CREATE TABLE IF NOT EXISTS irrigation_events (
  id          {{PK_SERIAL}},
  plot_id     TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  applied_on  TEXT NOT NULL,
  method      TEXT,
  mm_applied  {{FLOAT}},
  hours       {{FLOAT}},
  note        TEXT,
  source      TEXT NOT NULL DEFAULT 'farmer',   -- farmer | advisory_accepted
  created_at  {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_irr_plot ON irrigation_events(plot_id, applied_on DESC);

CREATE TABLE IF NOT EXISTS weed_checks (
  id              TEXT PRIMARY KEY,
  plot_id         TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  observation_id  TEXT REFERENCES observations(id) ON DELETE SET NULL,
  checked_on      TEXT NOT NULL,
  cover_fraction  {{FLOAT}},
  band            TEXT,
  pattern         TEXT,
  patches         INTEGER,
  usable          {{BOOL}} NOT NULL DEFAULT 1,
  reason          TEXT,
  detail          {{JSON}},
  created_at      {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weed_plot ON weed_checks(plot_id, checked_on DESC);
