-- ═══════════════════════════════════════════════════════════════════════════
-- PRAHARI · 005 — a farmer's own language-model key
--
-- Why this is a table rather than an environment variable: the key belongs to
-- the account holder, not to the deployment. A farmer or a team member brings
-- their own Gemini or OpenAI key, uses their own quota, and can remove it
-- again without anyone redeploying anything. A deployment-wide key still works
-- as a fallback (LLM_API_KEY), which is what a demo machine uses.
--
-- What is stored is a ciphertext, never the key. It is encrypted with a key
-- derived from JWT_SECRET (see llm.py), so rotating the deployment secret
-- invalidates stored credentials and live sessions together — the right
-- failure, rather than credentials left readable under a retired secret.
--
-- One key per account: `user_id` is the primary key, so setting a new one
-- replaces the old rather than accumulating credentials nobody remembers
-- granting.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS llm_keys (
  user_id     TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  provider    TEXT NOT NULL,                  -- gemini | openai
  model       TEXT,                           -- NULL means the provider default
  key_cipher  TEXT NOT NULL,                  -- AES-GCM, base64; never returned
  hint        TEXT NOT NULL,                  -- '••••abcd', so the owner can tell which
  verified_at {{TS}},                         -- when a live round trip last succeeded
  created_at  {{TS}} NOT NULL,
  updated_at  {{TS}} NOT NULL
);
