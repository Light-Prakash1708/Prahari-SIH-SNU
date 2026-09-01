-- ═══════════════════════════════════════════════════════════════════════════
-- PRAHARI · 006 — a recorded disease assessment
--
-- Why this table has to exist. Every management decision in PRAHARI is gated on
-- a measured field observation, and for a PEST that measurement is a count in
-- `threshold_checks`, weighed against an ICAR economic threshold. A DISEASE has
-- neither: there is no trap to count and no economic threshold in the reference
-- tables, because foliar disease is not managed that way.
--
-- The consequence was a dead end that this audit found in the running app: ask
-- for `should-i-spray?target=late_blight` and the answer was "nothing counted
-- yet, record a count" — a count that does not exist for a disease. A farmer
-- arriving from a disease diagnosis could go no further.
--
-- What a farmer CAN measure is incidence: walk the field, inspect a fixed
-- number of plants, and record how many show the symptom. That is arithmetic
-- they can check — affected ÷ inspected — not a number anyone invented. It is
-- stored here rather than squeezed into `threshold_checks`, whose every other
-- column (etl_base, etl_effective, chemical_authorised) is meaningless for a
-- disease and would have to be filled with nulls that later readers would
-- mistake for measurements.
--
-- Additive only. Nothing is dropped, renamed or reseeded, and no existing
-- read path changes: a plot with no row here behaves exactly as before.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS disease_assessments (
  id              TEXT PRIMARY KEY,
  plot_id         TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  cycle_id        TEXT,
  problem         TEXT NOT NULL,              -- the disease id, e.g. late_blight
  crop            TEXT NOT NULL,
  crop_stage      TEXT,
  plants_inspected INTEGER NOT NULL,          -- how many were actually walked
  plants_affected  INTEGER NOT NULL,          -- how many showed the symptom
  -- The farmer's own words for how far it has gone on an affected plant. A
  -- band, never a percentage: nobody standing in a field measures leaf area,
  -- and a number that looks measured but was guessed is worse than a band.
  spread_band     TEXT,                       -- few_spots | several_leaves | most_leaves
  part            TEXT,                       -- lower_leaves | upper_leaves | stem | fruit
  observation_id  TEXT REFERENCES observations(id) ON DELETE SET NULL,
  note            TEXT,
  assessed_on     TEXT NOT NULL,
  client_ref      TEXT,                       -- idempotency for the offline queue
  created_at      {{TS}} NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_disease_assess_plot
  ON disease_assessments (plot_id, problem, assessed_on);
CREATE UNIQUE INDEX IF NOT EXISTS ux_disease_assess_ref
  ON disease_assessments (plot_id, client_ref);
