-- ═══════════════════════════════════════════════════════════════════════════
-- PRAHARI · migration 002 — the farmer community, as a surveillance instrument
--
-- This is not a social network that happens to be about farming. Every table
-- here exists because a farmer noticing something in a field is the earliest
-- signal the system can get — earlier than a scan, far earlier than an
-- officer's visit — and that signal is worthless if it stays in one person's
-- head or in a WhatsApp group nobody can query.
--
-- Two rules are enforced by the SHAPE of these tables, not by a code path that
-- someone can forget to call:
--
--   1. A public record cannot leak a farm's position, because there is no
--      column to leak it from. community_posts has village / taluka / district
--      and nothing finer. The plot_id column exists only so authorised systems
--      (the signal engine, the owning farmer, an officer in scope) can join
--      back — it is never part of any public projection, and a test asserts it.
--
--   2. Community advice is not verified advice. A post starts UNVERIFIED and
--      can only leave that state through a row in community_expert_responses
--      written by a real, identified expert account. There is no code path that
--      promotes a post because it was popular.
--
-- Portability placeholders are the same as 001 — see app/db.py.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── the post ───────────────────────────────────────────────────────────────
-- Location columns are deliberately coarse. `taluka` is the unit the spatial
-- statistics already work in (see spatial.py, outbreak.py), so nothing about
-- surveillance needs a finer one.
CREATE TABLE IF NOT EXISTS community_posts (
  id                TEXT PRIMARY KEY,
  author_user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  author_farmer_id  TEXT REFERENCES farmers(id) ON DELETE SET NULL,
  author_role       TEXT NOT NULL DEFAULT 'farmer',
  author_display    TEXT NOT NULL,              -- the name shown; never the phone
  category          TEXT NOT NULL,              -- disease|pest|crop_problem|weather|cultivation|success|question
  crop              TEXT,
  crop_stage        TEXT,
  title             TEXT NOT NULL,
  body              TEXT NOT NULL,
  symptoms          {{JSON}},                   -- symptom tags chosen from a fixed list
  suspected_problem TEXT,                       -- problem id, if the author or PRAHARI names one
  confirmed_problem TEXT,                       -- set ONLY by an expert CONFIRMED/CORRECTED response

  -- location: coarse by construction
  village           TEXT,
  taluka            TEXT NOT NULL,
  district          TEXT NOT NULL DEFAULT 'Nashik',

  -- private joins. Never emitted by public_post(); asserted by a test.
  plot_id           TEXT REFERENCES plots(id) ON DELETE SET NULL,
  observation_id    TEXT REFERENCES observations(id) ON DELETE SET NULL,
  diagnosis_id      TEXT REFERENCES diagnoses(id) ON DELETE SET NULL,

  -- the PRAHARI context the author chose to attach, ALREADY REDACTED at write
  -- time. What is public is fixed when the post is written, so a later change
  -- to a projection function cannot retroactively widen it.
  share_context     {{BOOL}} NOT NULL DEFAULT 0,
  context           {{JSON}},

  verification      TEXT NOT NULL DEFAULT 'UNVERIFIED',  -- UNVERIFIED|EXPERT_REVIEWED|CONFIRMED|CORRECTED
  status            TEXT NOT NULL DEFAULT 'published',   -- published|hidden|removed
  moderation_state  TEXT NOT NULL DEFAULT 'ok',          -- ok|flagged|blocked
  moderation_note   TEXT,

  -- counters, kept for ranking and display. helpful_count is NOT a ranking
  -- input on its own — see community.py rank(). It is shown, not obeyed.
  comment_count     INTEGER NOT NULL DEFAULT 0,
  expert_count      INTEGER NOT NULL DEFAULT 0,
  helpful_count     INTEGER NOT NULL DEFAULT 0,
  same_problem_count INTEGER NOT NULL DEFAULT 0,
  report_count      INTEGER NOT NULL DEFAULT 0,

  -- whether this post may contribute to a cluster signal. A "success story" or
  -- a cultivation question must not inflate a disease signal.
  signal_eligible   {{BOOL}} NOT NULL DEFAULT 0,
  observed_on       TEXT,                        -- the day the farmer saw it
  client_ref        TEXT,
  created_at        {{TS}} NOT NULL,
  updated_at        {{TS}} NOT NULL,
  last_activity_at  {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cp_feed ON community_posts(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cp_taluka ON community_posts(taluka, category, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cp_crop ON community_posts(crop, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cp_author ON community_posts(author_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cp_signal ON community_posts(signal_eligible, taluka, suspected_problem);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cp_clientref ON community_posts(author_user_id, client_ref);

CREATE TABLE IF NOT EXISTS community_post_images (
  id            TEXT PRIMARY KEY,
  post_id       TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  storage_key   TEXT NOT NULL,
  content_type  TEXT NOT NULL,
  bytes         INTEGER NOT NULL,
  width         INTEGER,
  height        INTEGER,
  sha256        TEXT NOT NULL,
  quality       {{JSON}},                       -- the same gate the scan path uses
  created_at    {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cpi_post ON community_post_images(post_id);

-- ── replies ────────────────────────────────────────────────────────────────
-- One level of threading. Deeper threads make a conversation harder to read on
-- a phone in a field, and add nothing to the surveillance value.
CREATE TABLE IF NOT EXISTS community_comments (
  id             TEXT PRIMARY KEY,
  post_id        TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  parent_id      TEXT REFERENCES community_comments(id) ON DELETE CASCADE,
  author_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  author_role    TEXT NOT NULL DEFAULT 'farmer',
  author_display TEXT NOT NULL,
  taluka         TEXT,
  body           TEXT NOT NULL,
  -- A comment from an expert account is labelled as such, and separately from
  -- whether it carries a formal verdict — an expert chatting is not a review.
  is_expert      {{BOOL}} NOT NULL DEFAULT 0,
  expert_response_id TEXT,
  helpful_count  INTEGER NOT NULL DEFAULT 0,
  report_count   INTEGER NOT NULL DEFAULT 0,
  status         TEXT NOT NULL DEFAULT 'published',   -- published|hidden|removed
  created_at     {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cc_post ON community_comments(post_id, created_at);
CREATE INDEX IF NOT EXISTS idx_cc_author ON community_comments(author_user_id, created_at DESC);

-- ── reactions ──────────────────────────────────────────────────────────────
-- Four kinds, and only one of them is a vanity number:
--   helpful       "this reply helped me"       — shown, never ranked on alone
--   same_problem  "I am seeing this too"       — a corroboration signal
--   thanks        courtesy
--   saved         a private bookmark, visible to nobody else
-- There is no follower count and no like count anywhere in this schema.
CREATE TABLE IF NOT EXISTS community_reactions (
  id          {{PK_SERIAL}},
  target_type TEXT NOT NULL,                    -- post | comment
  target_id   TEXT NOT NULL,
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,                    -- helpful|same_problem|thanks|saved
  taluka      TEXT,
  created_at  {{TS}} NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cr_once
  ON community_reactions(target_type, target_id, user_id, kind);
CREATE INDEX IF NOT EXISTS idx_cr_user ON community_reactions(user_id, kind, created_at DESC);

-- ── moderation reports ─────────────────────────────────────────────────────
-- "Report" here means reporting CONTENT, not reporting a pest. The pest report
-- is the post itself.
CREATE TABLE IF NOT EXISTS community_reports (
  id            TEXT PRIMARY KEY,
  target_type   TEXT NOT NULL,                  -- post | comment
  target_id     TEXT NOT NULL,
  post_id       TEXT REFERENCES community_posts(id) ON DELETE CASCADE,
  reporter_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reason        TEXT NOT NULL,                  -- spam|misinformation|unsafe_advice|abuse|off_topic|other
  note          TEXT,
  state         TEXT NOT NULL DEFAULT 'open',   -- open|actioned|dismissed
  action        TEXT,                           -- hidden|removed|expert_correction_requested|none
  reviewed_by   TEXT REFERENCES users(id),
  reviewed_at   {{TS}},
  created_at    {{TS}} NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_crep_once
  ON community_reports(target_type, target_id, reporter_user_id);
CREATE INDEX IF NOT EXISTS idx_crep_open ON community_reports(state, created_at DESC);

-- ── the expert's formal response ───────────────────────────────────────────
-- This is the ONLY table that can change a post's verification. A response
-- written by an account that is not a real expert profile is refused at the
-- router; a response that exists carries the expert's identity because a
-- verdict without an author is not a verdict.
CREATE TABLE IF NOT EXISTS community_expert_responses (
  id             TEXT PRIMARY KEY,
  post_id        TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  expert_id      TEXT REFERENCES experts(id) ON DELETE SET NULL,
  expert_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expert_name    TEXT NOT NULL,
  institution    TEXT,
  status         TEXT NOT NULL,                 -- EXPERT_REVIEWED|CONFIRMED|CORRECTED
  verdict_problem TEXT,                         -- the problem the expert names
  corrects       TEXT,                          -- what the post claimed, when CORRECTED
  confidence     TEXT,                          -- low|moderate|high
  body           TEXT NOT NULL,
  advice_kind    TEXT NOT NULL DEFAULT 'ipm',   -- ipm|cultural|scouting|refer_officer|no_action
  comment_id     TEXT REFERENCES community_comments(id) ON DELETE SET NULL,
  superseded_by  TEXT,
  created_at     {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cer_post ON community_expert_responses(post_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cer_expert ON community_expert_responses(expert_user_id, created_at DESC);

-- ── topics ─────────────────────────────────────────────────────────────────
-- A topic is a durable subject a farmer can follow: a crop, a problem, a
-- category, or their own taluka. Following a topic is how a farmer subscribes
-- to a signal WITHOUT subscribing to a person — which is why there is no
-- follow-a-user table here.
CREATE TABLE IF NOT EXISTS community_topics (
  id          TEXT PRIMARY KEY,                 -- crop:tomato · problem:late_blight · taluka:dindori
  kind        TEXT NOT NULL,                    -- crop|problem|category|taluka
  ref         TEXT NOT NULL,
  label       TEXT NOT NULL,
  label_mr    TEXT,
  post_count  INTEGER NOT NULL DEFAULT 0,
  created_at  {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ct_kind ON community_topics(kind, post_count DESC);

CREATE TABLE IF NOT EXISTS community_topic_follows (
  topic_id   TEXT NOT NULL REFERENCES community_topics(id) ON DELETE CASCADE,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at {{TS}} NOT NULL,
  PRIMARY KEY (topic_id, user_id)
);

CREATE TABLE IF NOT EXISTS community_post_topics (
  post_id  TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
  topic_id TEXT NOT NULL REFERENCES community_topics(id) ON DELETE CASCADE,
  PRIMARY KEY (post_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_cpt_topic ON community_post_topics(topic_id);

-- ── blocks ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS community_blocks (
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  blocked_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at {{TS}} NOT NULL,
  PRIMARY KEY (user_id, blocked_id)
);

-- ── the signal ─────────────────────────────────────────────────────────────
-- What the community is FOR. Graded, and the grades stop short of the word
-- "outbreak" on purpose — that word belongs to outbreak_events, which needs
-- expert-confirmed diagnoses, not conversation.
--
--   possible_cluster        several independent farmers in one taluka
--                           describing the same thing
--   corroborated_signal     the above, AND independent evidence that is not
--                           conversation: a PRAHARI diagnosis, a trap count
--                           over threshold, or an expert response confirming
--   confirmed_field_signal  an officer went and looked, and said yes
--
-- A signal never becomes confirmed by volume. Only by a person.
CREATE TABLE IF NOT EXISTS community_cluster_signals (
  id             TEXT PRIMARY KEY,
  taluka         TEXT NOT NULL,
  district       TEXT NOT NULL DEFAULT 'Nashik',
  crop           TEXT NOT NULL DEFAULT '',    -- '' not NULL: the uniqueness index
                                               -- below must treat "no crop" as a
                                               -- value, and NULL is never equal to
                                               -- NULL in either dialect.
  problem        TEXT NOT NULL,
  grade          TEXT NOT NULL,                 -- possible_cluster|corroborated_signal|confirmed_field_signal
  community_posts_n   INTEGER NOT NULL DEFAULT 0,
  distinct_authors    INTEGER NOT NULL DEFAULT 0,
  distinct_villages   INTEGER NOT NULL DEFAULT 0,
  same_problem_votes  INTEGER NOT NULL DEFAULT 0,
  diagnoses_n         INTEGER NOT NULL DEFAULT 0,
  expert_confirmations INTEGER NOT NULL DEFAULT 0,
  trap_signals        INTEGER NOT NULL DEFAULT 0,
  officer_confirmations INTEGER NOT NULL DEFAULT 0,
  evidence       {{JSON}},
  window_days    INTEGER NOT NULL DEFAULT 14,
  state          TEXT NOT NULL DEFAULT 'open',  -- open|closed|dismissed
  confirmed_by   TEXT REFERENCES users(id),
  confirmed_at   {{TS}},
  officer_note   TEXT,
  outbreak_event_id TEXT REFERENCES outbreak_events(id) ON DELETE SET NULL,
  alerted_at     {{TS}},                        -- when nearby farmers were told
  first_seen_on  TEXT NOT NULL,
  last_seen_on   TEXT NOT NULL,
  created_at     {{TS}} NOT NULL,
  updated_at     {{TS}} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ccs_open ON community_cluster_signals(state, grade, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ccs_key
  ON community_cluster_signals(taluka, problem, crop, state);
