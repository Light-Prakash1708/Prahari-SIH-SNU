-- PRAHARI · 004 — the farm money ledger
-- ════════════════════════════════════════════════════════════════════════════
-- A new table, and the audit that preceded it says why nothing existing fits.
--
--   `applications` records a CHEMICAL applied to a plot — product, dose,
--   pre-harvest interval, and the threshold check that authorised it. It is a
--   food-safety record. Bolting a rupee column onto it would mean a farmer
--   editing a cost could touch a row that governs when produce is safe to pick.
--
--   `/api/ledger` is the SPRAYS-AVOIDED ledger — threshold checks that came
--   back below threshold, counted against a prophylactic calendar. Same word,
--   entirely different quantity.
--
-- So money lives here, on its own, and deliberately does NOT feed the risk
-- engine. Cost must never become an input to a spray decision: the moment a
-- cheap intervention scores better than a correct one, the system is giving
-- agronomic advice on financial grounds.
--
-- Entries are additive. Editing is an UPDATE by the owner; there is no delete
-- endpoint, because a season's costs are a record.

CREATE TABLE IF NOT EXISTS farm_entries (
  id            {{PK_SERIAL}},
  plot_id       TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  crop_cycle_id TEXT REFERENCES crop_cycles(id),
  -- expense | income. Kept in one table because the dashboard's only useful
  -- number is the difference between them.
  direction     TEXT NOT NULL DEFAULT 'expense',
  category      TEXT NOT NULL,
  title         TEXT NOT NULL,
  amount_inr    {{FLOAT}} NOT NULL,
  quantity      {{FLOAT}},
  unit          TEXT,
  spent_on      TEXT NOT NULL,
  note          TEXT,
  -- When an entry was raised from a real spray this points at it, so the money
  -- view and the application record agree without either owning the other.
  application_id INTEGER REFERENCES applications(id),
  client_ref    TEXT,
  created_at    {{TS}} NOT NULL,
  updated_at    {{TS}}
);

CREATE INDEX IF NOT EXISTS idx_entries_plot ON farm_entries(plot_id, spent_on DESC);
CREATE INDEX IF NOT EXISTS idx_entries_cycle ON farm_entries(crop_cycle_id);

-- The offline queue re-sends on a flaky connection. A client_ref makes that
-- idempotent: the same entry arriving twice is one row, not two.
CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_ref
  ON farm_entries(plot_id, client_ref);
