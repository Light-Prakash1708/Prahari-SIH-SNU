-- ═══════════════════════════════════════════════════════════════════════════
-- PRAHARI · 007 — farmer producer organisations
--
-- An FPO is a group of farmers who market and buy together. What it needs
-- from PRAHARI is the picture across its members — which crops, how healthy,
-- what is spreading in their talukas, what worked after action — without
-- seeing any one member's field.
--
-- Three rules are built into the shape of these tables:
--
--   · membership is the FARMER's act. A row in fpo_members is written only by
--     the farmer joining, and carries when they consented. An FPO cannot add
--     a farmer, and an administrator cannot either.
--   · FPO staff are ordinary users with role 'fpo', created by an
--     administrator and linked to one FPO in fpo_staff — the same pattern as
--     officers and their taluka scopes.
--   · nothing here references a plot. The FPO view is computed from members'
--     plots at read time, and only counts leave the server.
--
-- Additive only: nothing existing is altered.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS fpos (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  name_mr     TEXT,
  district    TEXT,
  created_by  TEXT REFERENCES users(id),
  created_at  {{TS}} NOT NULL
);

CREATE TABLE IF NOT EXISTS fpo_staff (
  fpo_id      TEXT NOT NULL REFERENCES fpos(id) ON DELETE CASCADE,
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at  {{TS}} NOT NULL,
  PRIMARY KEY (fpo_id, user_id)
);

CREATE TABLE IF NOT EXISTS fpo_members (
  fpo_id      TEXT NOT NULL REFERENCES fpos(id) ON DELETE CASCADE,
  farmer_id   TEXT NOT NULL REFERENCES farmers(id) ON DELETE CASCADE,
  consented_at {{TS}} NOT NULL,
  PRIMARY KEY (fpo_id, farmer_id)
);
CREATE INDEX IF NOT EXISTS idx_fpo_members_farmer ON fpo_members(farmer_id);
