-- ═══════════════════════════════════════════════════════════════════════════
-- PRAHARI · 008 — observed weather days, kept
--
-- The incident: in production, Open-Meteo rate-limited Render's shared
-- outbound IP. WeatherAPI's free plan holds one day of history, the infection
-- models accumulate over twenty-one, and so every risk request fell through to
-- the generated fallback — while the real days PRAHARI had already been sent
-- were thrown away when each cache entry expired.
--
-- A PAST day does not change. This table keeps every live, observed day
-- PRAHARI receives (never a generated one, never today or a forecast), keyed
-- by ~1 km cell and date, with the provider that reported it. When a fresh
-- request comes back short, the missing older days are taken from here and
-- labelled as stored observations. Once a cell has been filled once,
-- WeatherAPI's single day of history each day keeps it topped up, so an
-- Open-Meteo outage no longer starves the models.
--
-- Additive only.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS weather_days (
  cell        TEXT NOT NULL,          -- "lat:lng" rounded to 2 dp, as the cache key
  day         TEXT NOT NULL,          -- ISO date, always before the day it was stored
  src         TEXT NOT NULL,          -- the provider that reported it
  payload     {{JSON}} NOT NULL,      -- the day exactly as the provider's series carried it
  stored_at   {{TS}} NOT NULL,
  PRIMARY KEY (cell, day)
);
