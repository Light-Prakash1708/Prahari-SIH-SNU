-- ═══════════════════════════════════════════════════════════════════════════
-- PRAHARI · migration 001 — the production core
--
-- Portability contract (see app/db.py):
--   {{PK_SERIAL}}  auto-incrementing integer primary key
--   {{BOOL}}       0/1 integer in both dialects, so behaviour is identical
--   {{JSON}}       serialised JSON as TEXT — read/written through json.dumps
--   {{TS}}         ISO-8601 UTC string. Lexicographic ordering is chronological
--                  ordering, which is the only property any query here needs.
--   {{FLOAT}}      double precision
--
-- Timestamps are strings on purpose. Every date calculation in this system
-- happens in Python against one clock (app/clock.py); pushing it into SQL is
-- how the prototype ended up with julianday() calls that a Postgres deploy
-- would have silently returned NULL for.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── identity ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id              TEXT PRIMARY KEY,
  email           TEXT UNIQUE,
  phone           TEXT UNIQUE,
  password_hash   TEXT NOT NULL,
  role            TEXT NOT NULL,            -- farmer | officer | expert | admin
  full_name       TEXT NOT NULL,
  full_name_mr    TEXT,
  lang            TEXT NOT NULL DEFAULT 'mr',
  is_active       {{BOOL}} NOT NULL DEFAULT 1,
  email_verified  {{BOOL}} NOT NULL DEFAULT 0,
  last_login_at   {{TS}},
  created_at      {{TS}} NOT NULL,
  updated_at      {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- A session row is what makes logout mean something. The JWT carries a jti;
-- this table decides whether that jti is still allowed to act.
CREATE TABLE IF NOT EXISTS sessions (
  jti          TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  issued_at    {{TS}} NOT NULL,
  expires_at   {{TS}} NOT NULL,
  revoked_at   {{TS}},
  user_agent   TEXT,
  ip           TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, expires_at);

CREATE TABLE IF NOT EXISTS password_resets (
  token_hash   TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at   {{TS}} NOT NULL,
  used_at      {{TS}}
);

-- ── role profiles ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS farmers (
  id                  TEXT PRIMARY KEY,
  user_id             TEXT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name                TEXT NOT NULL,
  name_mr             TEXT,
  phone               TEXT,
  farmer_id_agristack TEXT,
  taluka              TEXT NOT NULL,
  village             TEXT,
  lang                TEXT NOT NULL DEFAULT 'mr',
  literacy            TEXT NOT NULL DEFAULT 'reads',   -- reads | voice_only
  sms_opt_in          {{BOOL}} NOT NULL DEFAULT 1,
  ivr_opt_in          {{BOOL}} NOT NULL DEFAULT 0,
  created_at          {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_farmers_taluka ON farmers(taluka);

CREATE TABLE IF NOT EXISTS officers (
  id              TEXT PRIMARY KEY,
  user_id         TEXT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  role            TEXT NOT NULL DEFAULT 'krishi_sahayak',  -- krishi_sahayak|kvk|sau|district
  taluka          TEXT,
  district        TEXT,
  visits_per_week INTEGER NOT NULL DEFAULT 5,
  created_at      {{TS}} NOT NULL
);

-- An officer's authorisation is a list of talukas, checked server-side on every
-- district query. An officer for Dindori does not receive Niphad's farmers.
CREATE TABLE IF NOT EXISTS officer_scopes (
  officer_id TEXT NOT NULL REFERENCES officers(id) ON DELETE CASCADE,
  taluka     TEXT NOT NULL,
  PRIMARY KEY (officer_id, taluka)
);

CREATE TABLE IF NOT EXISTS experts (
  id            TEXT PRIMARY KEY,
  user_id       TEXT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  institution   TEXT,
  specialism    TEXT,
  crops         {{JSON}},
  created_at    {{TS}} NOT NULL
);

-- ── fields ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plots (
  id           TEXT PRIMARY KEY,
  farmer_id    TEXT NOT NULL REFERENCES farmers(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  crop         TEXT NOT NULL,
  variety      TEXT,
  area_acre    {{FLOAT}} NOT NULL DEFAULT 1.0,
  area_source  TEXT NOT NULL DEFAULT 'declared',   -- declared | polygon
  sown_on      TEXT,
  expected_harvest TEXT,
  lat          {{FLOAT}},
  lng          {{FLOAT}},
  location_source TEXT NOT NULL DEFAULT 'manual',  -- gps | map | manual
  taluka       TEXT NOT NULL,
  village      TEXT,
  soil         TEXT,
  irrigation   TEXT,
  tank_litres  INTEGER NOT NULL DEFAULT 15,
  boundary     {{JSON}},                            -- GeoJSON Polygon, optional
  archived     {{BOOL}} NOT NULL DEFAULT 0,
  created_at   {{TS}} NOT NULL,
  updated_at   {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plots_farmer ON plots(farmer_id);
CREATE INDEX IF NOT EXISTS idx_plots_taluka ON plots(taluka, crop);

-- One plot can carry several seasons. The active cycle is the one with no
-- ended_on; crop stage is always computed from it, never from a bare date.
CREATE TABLE IF NOT EXISTS crop_cycles (
  id          TEXT PRIMARY KEY,
  plot_id     TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  crop        TEXT NOT NULL,
  variety     TEXT,
  sown_on     TEXT NOT NULL,
  ended_on    TEXT,
  outcome     TEXT,
  created_at  {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cycles_plot ON crop_cycles(plot_id, sown_on DESC);

-- ── observations and images ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS observations (
  id             TEXT PRIMARY KEY,
  plot_id        TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  farmer_id      TEXT NOT NULL REFERENCES farmers(id) ON DELETE CASCADE,
  cycle_id       TEXT REFERENCES crop_cycles(id),
  kind           TEXT NOT NULL DEFAULT 'leaf',      -- leaf | trap | symptom | followup
  taluka         TEXT NOT NULL,
  crop           TEXT NOT NULL,
  crop_stage     TEXT,
  observed_at    {{TS}} NOT NULL,
  lat            {{FLOAT}},
  lng            {{FLOAT}},
  notes          TEXT,
  source         TEXT NOT NULL DEFAULT 'app',       -- app | offline_sync | ivr | officer
  client_ref     TEXT,                              -- idempotency key from the offline queue
  status         TEXT NOT NULL DEFAULT 'open',      -- open|confirmed|corrected|rejected|closed
  created_at     {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_plot ON observations(plot_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_taluka ON observations(taluka, status, observed_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_obs_clientref ON observations(farmer_id, client_ref);

CREATE TABLE IF NOT EXISTS observation_images (
  id            TEXT PRIMARY KEY,
  observation_id TEXT NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
  role          TEXT NOT NULL DEFAULT 'affected',   -- whole_plant|affected|closeup|underside|stem|trap
  storage_key   TEXT NOT NULL,
  thumb_key     TEXT,
  content_type  TEXT NOT NULL,
  bytes         INTEGER NOT NULL,
  width         INTEGER,
  height        INTEGER,
  sha256        TEXT NOT NULL,
  quality       {{JSON}},                           -- the gate's verdict, stored
  features      {{JSON}},                           -- measured symptom features
  created_at    {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_img_obs ON observation_images(observation_id);

-- ── diagnosis ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS model_versions (
  id             TEXT PRIMARY KEY,
  kind           TEXT NOT NULL,             -- vision | risk | trap
  name           TEXT NOT NULL,
  version        TEXT NOT NULL,
  provider       TEXT NOT NULL,             -- onnx | api | features | rule
  trained_on     TEXT,
  eval_set       TEXT,
  metrics        {{JSON}},                  -- NULL until an evaluation has been run
  deployed_at    {{TS}} NOT NULL,
  active         {{BOOL}} NOT NULL DEFAULT 1,
  notes          TEXT
);

CREATE TABLE IF NOT EXISTS diagnoses (
  id             TEXT PRIMARY KEY,
  observation_id TEXT NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
  plot_id        TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  crop           TEXT NOT NULL,
  engine         TEXT NOT NULL,             -- onnx | api | features | unavailable
  model_version  TEXT,
  top_problem    TEXT,
  top_posterior  {{FLOAT}},
  margin         {{FLOAT}},
  abstained      {{BOOL}} NOT NULL DEFAULT 0,
  abstain_reason TEXT,
  explain        TEXT,
  evidence       {{JSON}},
  prior_used     {{JSON}},
  weather_used   {{JSON}},
  confirmed      TEXT,                      -- expert verdict, NULL until reviewed
  confirmed_by   TEXT,
  confirmed_at   {{TS}},
  created_at     {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dx_obs ON diagnoses(observation_id);
CREATE INDEX IF NOT EXISTS idx_dx_plot ON diagnoses(plot_id, created_at DESC);

CREATE TABLE IF NOT EXISTS diagnosis_candidates (
  id            {{PK_SERIAL}},
  diagnosis_id  TEXT NOT NULL REFERENCES diagnoses(id) ON DELETE CASCADE,
  rank          INTEGER NOT NULL,
  problem       TEXT NOT NULL,
  posterior     {{FLOAT}} NOT NULL,
  prior         {{FLOAT}},
  image_fit     {{FLOAT}},
  weather_factor {{FLOAT}},
  supporting    {{JSON}},
  contradicting {{JSON}}
);
CREATE INDEX IF NOT EXISTS idx_dxc_dx ON diagnosis_candidates(diagnosis_id, rank);

-- Contextual questions and what the farmer answered.
CREATE TABLE IF NOT EXISTS diagnosis_context (
  id            {{PK_SERIAL}},
  diagnosis_id  TEXT NOT NULL REFERENCES diagnoses(id) ON DELETE CASCADE,
  question_id   TEXT NOT NULL,
  question      TEXT NOT NULL,
  answer        TEXT NOT NULL,
  answer_label  TEXT,
  effect        {{JSON}},
  answered_at   {{TS}} NOT NULL
);

-- ── the Dirichlet prior — the whole learning step, as a count ───────────────
CREATE TABLE IF NOT EXISTS priors (
  taluka     TEXT NOT NULL,
  crop       TEXT NOT NULL,
  problem    TEXT NOT NULL,
  alpha      {{FLOAT}} NOT NULL DEFAULT 1.0,
  updated_at {{TS}} NOT NULL,
  PRIMARY KEY (taluka, crop, problem)
);

-- ── weather ────────────────────────────────────────────────────────────────
-- Cached provider responses, keyed by rounded coordinates. A cache row records
-- WHICH provider answered and WHEN, because the UI shows both.
CREATE TABLE IF NOT EXISTS weather_cache (
  cache_key    TEXT PRIMARY KEY,
  lat          {{FLOAT}} NOT NULL,
  lng          {{FLOAT}} NOT NULL,
  provider     TEXT NOT NULL,
  fetched_at   {{TS}} NOT NULL,
  expires_at   {{TS}} NOT NULL,
  payload      {{JSON}} NOT NULL
);

-- ── risk ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS health_snapshots (
  plot_id  TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  day      TEXT NOT NULL,
  score    {{FLOAT}} NOT NULL,
  disease  {{FLOAT}} NOT NULL,
  pest     {{FLOAT}} NOT NULL,
  weather  {{FLOAT}} NOT NULL,
  nearby   {{FLOAT}} NOT NULL,
  drivers  {{JSON}},
  weather_source TEXT,
  created_at {{TS}} NOT NULL,
  PRIMARY KEY (plot_id, day)
);

CREATE TABLE IF NOT EXISTS risk_forecasts (
  id         {{PK_SERIAL}},
  plot_id    TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  made_on    TEXT NOT NULL,
  for_day    TEXT NOT NULL,
  level      TEXT NOT NULL,
  drivers    {{JSON}},
  weather_source TEXT NOT NULL,
  created_at {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rf_plot ON risk_forecasts(plot_id, for_day);

-- ── traps ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS traps (
  id          TEXT PRIMARY KEY,
  plot_id     TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  pest        TEXT NOT NULL,
  trap_type   TEXT NOT NULL,                  -- pheromone | sticky_yellow | sticky_blue | light
  installed_on TEXT NOT NULL,
  lure_changed_on TEXT,
  active      {{BOOL}} NOT NULL DEFAULT 1,
  created_at  {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traps_plot ON traps(plot_id, active);

CREATE TABLE IF NOT EXISTS trap_observations (
  id             TEXT PRIMARY KEY,
  trap_id        TEXT NOT NULL REFERENCES traps(id) ON DELETE CASCADE,
  plot_id        TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  observation_id TEXT REFERENCES observations(id) ON DELETE SET NULL,
  counted_on     TEXT NOT NULL,
  count          {{FLOAT}} NOT NULL,
  count_source   TEXT NOT NULL,                -- manual | image_assisted
  image_estimate {{FLOAT}},
  image_confidence TEXT,                       -- low | moderate | high | unavailable
  nights         INTEGER NOT NULL DEFAULT 1,
  created_at     {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trapobs ON trap_observations(plot_id, counted_on DESC);

-- ── the threshold gate ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS threshold_checks (
  id            {{PK_SERIAL}},
  plot_id       TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  crop          TEXT NOT NULL,
  crop_stage    TEXT,
  pest          TEXT NOT NULL,
  count         {{FLOAT}} NOT NULL,
  etl_base      {{FLOAT}} NOT NULL,
  etl_effective {{FLOAT}} NOT NULL,
  band          TEXT NOT NULL,
  chemical_authorised {{BOOL}} NOT NULL DEFAULT 0,
  acted         {{BOOL}} NOT NULL DEFAULT 0,
  saving        {{FLOAT}},
  trap_obs_id   TEXT REFERENCES trap_observations(id),
  checked_on    TEXT NOT NULL,
  checked_at    {{TS}} NOT NULL,
  demo          {{BOOL}} NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tc_plot ON threshold_checks(plot_id, pest, checked_at DESC);

-- ── the spray decision, stored as an object ────────────────────────────────
-- "Do not spray" is a decision with evidence and a re-check date, not the
-- absence of a recommendation. It gets a row like any other.
CREATE TABLE IF NOT EXISTS decisions (
  id             TEXT PRIMARY KEY,
  plot_id        TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  target         TEXT NOT NULL,
  decision       TEXT NOT NULL,              -- monitor|scout_again|non_chemical|intervene|expert_review|do_not_spray
  reason_code    TEXT NOT NULL,
  reason         TEXT NOT NULL,
  reason_mr      TEXT,
  evidence       {{JSON}},
  recheck_after_hours INTEGER,
  recheck_on     TEXT,
  threshold_check_id INTEGER REFERENCES threshold_checks(id),
  diagnosis_id   TEXT REFERENCES diagnoses(id),
  created_at     {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dec_plot ON decisions(plot_id, created_at DESC);

-- ── chemical reference, with a verification status that gates it ───────────
-- A DRAFT row can never reach a farmer as an actionable recommendation. That
-- rule is enforced in chemicals.py and asserted by a test.
CREATE TABLE IF NOT EXISTS label_claims (
  id             TEXT PRIMARY KEY,
  crop           TEXT NOT NULL,
  target         TEXT NOT NULL,
  product        TEXT NOT NULL,
  active_ingredient TEXT,
  formulation    TEXT,
  moa_group      TEXT,
  dose           {{FLOAT}} NOT NULL,
  unit           TEXT NOT NULL,
  water_l_per_acre {{FLOAT}},
  phi_days       INTEGER NOT NULL,
  reentry_hours  INTEGER,
  toxicity       TEXT,
  bee_hazard     TEXT,
  cost_per_acre  {{FLOAT}},
  status         TEXT NOT NULL DEFAULT 'draft',   -- draft|verified|expired|revoked
  source         TEXT,
  source_url     TEXT,
  verified_by    TEXT,
  verified_at    {{TS}},
  expires_on     TEXT,
  created_at     {{TS}} NOT NULL,
  updated_at     {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims ON label_claims(crop, target, status);

CREATE TABLE IF NOT EXISTS restricted_products (
  id          TEXT PRIMARY KEY,
  pattern     TEXT NOT NULL,
  scope       TEXT NOT NULL DEFAULT 'maharashtra',
  reason      TEXT NOT NULL,
  source      TEXT,
  source_url  TEXT,
  effective_from TEXT,
  created_at  {{TS}} NOT NULL
);

-- ── applications, follow-ups, the case ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS applications (
  id           {{PK_SERIAL}},
  plot_id      TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  crop         TEXT NOT NULL,
  target       TEXT,
  kind         TEXT NOT NULL DEFAULT 'chemical',   -- cultural|mechanical|biological|chemical
  product      TEXT NOT NULL,
  moa_group    TEXT,
  dose_text    TEXT,
  phi_days     INTEGER NOT NULL DEFAULT 0,
  applied_on   TEXT NOT NULL,
  clears_on    TEXT NOT NULL,
  claim_id     TEXT REFERENCES label_claims(id),
  authorised_by_check INTEGER REFERENCES threshold_checks(id),
  decision_id  TEXT REFERENCES decisions(id),
  created_at   {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_app_plot ON applications(plot_id, clears_on DESC);

CREATE TABLE IF NOT EXISTS followups (
  id             {{PK_SERIAL}},
  plot_id        TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  origin_observation TEXT REFERENCES observations(id),
  application_id INTEGER REFERENCES applications(id),
  due_on         TEXT NOT NULL,
  done_observation TEXT REFERENCES observations(id),
  done_on        TEXT,
  outcome        TEXT,                          -- better|same|worse|not_done|unmeasurable
  comparison     {{JSON}},
  escalated      {{BOOL}} NOT NULL DEFAULT 0,
  created_at     {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fu_plot ON followups(plot_id, due_on);

-- ── expert verification ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS expert_cases (
  id            TEXT PRIMARY KEY,               -- PRH-2026-0001
  observation_id TEXT REFERENCES observations(id) ON DELETE CASCADE,
  diagnosis_id  TEXT REFERENCES diagnoses(id),
  plot_id       TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  farmer_id     TEXT NOT NULL REFERENCES farmers(id) ON DELETE CASCADE,
  taluka        TEXT NOT NULL,
  crop          TEXT NOT NULL,
  reason        TEXT,
  urgency       TEXT NOT NULL DEFAULT 'normal',  -- normal | urgent
  status        TEXT NOT NULL DEFAULT 'submitted', -- submitted|reviewing|verified|rejected|info_requested
  assigned_to   TEXT REFERENCES experts(id),
  submitted_at  {{TS}} NOT NULL,
  reviewed_at   {{TS}},
  verdict       TEXT,
  created_at    {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ec_status ON expert_cases(status, submitted_at DESC);

CREATE TABLE IF NOT EXISTS expert_reviews (
  id           {{PK_SERIAL}},
  case_id      TEXT NOT NULL REFERENCES expert_cases(id) ON DELETE CASCADE,
  expert_id    TEXT REFERENCES experts(id),
  expert_name  TEXT NOT NULL,
  action       TEXT NOT NULL,                   -- confirm|reject|change|request_info|field_visit|mark_urgent
  verdict      TEXT,
  confidence   TEXT,                            -- low|moderate|high
  note         TEXT,
  created_at   {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_er_case ON expert_reviews(case_id, created_at);

-- ── officer work ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS assignments (
  id          {{PK_SERIAL}},
  observation_id TEXT REFERENCES observations(id) ON DELETE CASCADE,
  case_id     TEXT REFERENCES expert_cases(id),
  officer_id  TEXT REFERENCES officers(id),
  taluka      TEXT,
  priority    TEXT NOT NULL DEFAULT 'P2',
  due_on      TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'assigned',
  finding     TEXT,
  assigned_at {{TS}} NOT NULL,
  closed_at   {{TS}}
);
CREATE INDEX IF NOT EXISTS idx_as_officer ON assignments(officer_id, status);

CREATE TABLE IF NOT EXISTS outbreak_events (
  id           TEXT PRIMARY KEY,
  taluka       TEXT NOT NULL,
  crop         TEXT NOT NULL,
  problem      TEXT NOT NULL,
  grade        TEXT NOT NULL,                  -- emerging_cluster|suspected_hotspot|confirmed_hotspot
  reports      INTEGER NOT NULL,
  confirmed    INTEGER NOT NULL,
  gi_z         {{FLOAT}},
  growth_pct_72h {{FLOAT}},
  radius_km    {{FLOAT}},
  evidence     {{JSON}},
  opened_on    TEXT NOT NULL,
  closed_on    TEXT,
  created_at   {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oe_open ON outbreak_events(problem, closed_on);

-- ── the field's own history ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS field_events (
  id        {{PK_SERIAL}},
  plot_id   TEXT NOT NULL REFERENCES plots(id) ON DELETE CASCADE,
  at        TEXT NOT NULL,
  kind      TEXT NOT NULL,
  severity  TEXT NOT NULL DEFAULT 'info',
  title     TEXT NOT NULL,
  title_mr  TEXT,
  detail    TEXT,
  detail_mr TEXT,
  ref       TEXT,
  created_at {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fe_plot ON field_events(plot_id, at DESC);

-- ── notifications, with a delivery state that is not a guess ───────────────
CREATE TABLE IF NOT EXISTS notifications (
  id        TEXT PRIMARY KEY,
  user_id   TEXT REFERENCES users(id) ON DELETE CASCADE,
  plot_id   TEXT REFERENCES plots(id) ON DELETE CASCADE,
  at        TEXT NOT NULL,
  kind      TEXT NOT NULL,
  severity  TEXT NOT NULL DEFAULT 'watch',
  title     TEXT NOT NULL,
  title_mr  TEXT,
  body      TEXT,
  body_mr   TEXT,
  read_at   {{TS}},
  created_at {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nt_user ON notifications(user_id, at DESC);

CREATE TABLE IF NOT EXISTS notification_deliveries (
  id              {{PK_SERIAL}},
  notification_id TEXT NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
  channel         TEXT NOT NULL,               -- inapp | sms | email | ivr
  address         TEXT,
  state           TEXT NOT NULL DEFAULT 'queued', -- queued|sent|delivered|failed|skipped
  provider        TEXT,
  provider_ref    TEXT,
  error           TEXT,
  body            TEXT,
  segments        INTEGER,
  queued_at       {{TS}} NOT NULL,
  updated_at      {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nd_note ON notification_deliveries(notification_id);

-- ── audit ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
  id          {{PK_SERIAL}},
  at          {{TS}} NOT NULL,
  request_id  TEXT,
  user_id     TEXT,
  role        TEXT,
  action      TEXT NOT NULL,
  entity      TEXT,
  entity_id   TEXT,
  ip          TEXT,
  detail      {{JSON}}
);
CREATE INDEX IF NOT EXISTS idx_audit ON audit_logs(at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id, at DESC);

-- ── demo state (only ever read when DEMO_MODE is on) ───────────────────────
CREATE TABLE IF NOT EXISTS demo_state (
  id       INTEGER PRIMARY KEY,
  scenario TEXT NOT NULL DEFAULT 'emerging',
  set_at   {{TS}} NOT NULL
);
