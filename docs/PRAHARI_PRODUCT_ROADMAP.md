# PRAHARI — Product Roadmap

Written 16 November 2026, after the repository audit (`docs/PRAHARI_AUDIT.md`). Every module below was checked against the code before being classified, so that nothing already built is built twice.

Classification key: EXISTS means shipped and tested; ENHANCE means shipped with a clear gap; PARTIAL means the foundation exists but the module does not; NEW means nothing equivalent exists; DEFER means deliberately not started until a precondition holds.

## Module classification

**A. Farmer Command Centre — EXISTS / ENHANCE.** The Home screen already carries the field health score, today's agenda, "my next best action" from `trajectory.next_best_action`, the weather card with an explicit unavailable state, and risk from published infection models. The gap is consolidation across several fields: a farmer with three plots sees them one at a time. Enhancement: a multi-field strip ranked by escalation level, reusing `management.py` escalation rather than a new scoring system.

**B. Alert Orchestration — PARTIAL.** `notify.py` records in-app, SMS and IVR deliveries with an honest state (`skipped` when no gateway). There is no outbound gateway configured and no WhatsApp channel. Next: an SMS provider adapter behind the existing `NotificationService` (MSG91 or Twilio, test mode first), then WhatsApp only through the official WhatsApp Business Platform with approved templates. Unofficial WhatsApp automation is excluded.

**C. FPO Intelligence — NEW.** No FPO entity, membership or role exists. It needs a migration (`fpo`, `fpo_members`), an `fpo` role provisioned by an administrator through the existing `/api/admin/users`, and aggregate views that reuse `outbreak.py`, `spatial.priority_queue` and `trajectory.early_signals` scoped to members' plots. No individual farmer's coordinates should reach an FPO view; talukas and counts only, as the officer views already do.

**D. Intervention Intelligence — EXISTS / ENHANCE.** The economic threshold gate, the IPM ladder, the decision ledger, follow-up re-scans and escalation on "worse after treatment" are all shipped. The gap is an outcome summary: across closed follow-ups, how often each ladder rung was followed by "better", stated as counts with their denominator and never as a percentage on a small base.

**E. Expert / Officer operations — EXISTS.** Expert case queue and brief, officer overview, early signals, outbreak grading, Gi* hotspots, the reasoned priority queue, assignments and route planning are shipped. Enhancement only on request.

**F. DigiHaat marketplace — DEFER.** Precondition: the core has run for at least two weeks on a persistent (non-expiring) database with uploads in object storage. Even then, no listing, ranking or commission may influence a pesticide recommendation; the chemical gate stays the only path to a chemical.

**G. Commercial foundation — DEFER (test mode only when started).** Subscriptions or FPO billing through a payment provider's test mode. No live keys in the repository or the frontend.

## Reliability and AI track (cross-cutting)

Production stays up when a dependency fails: done for the database (degraded mode, 503 `database_unavailable`, self-recovery). Uploads to object storage: next. Gemini remains wording-only with number and product guards; it never supplies weather, a count or a dose. Chemical label claims stay `draft` until verified by a named person.

## Priority matrix

| Item | User value | Risk if skipped | Effort | Order |
|---|---|---|---|---|
| Restore DATABASE_URL and a non-expiring database | Site exists at all | Total outage | Minutes | 1 |
| Degraded mode on dependency failure | Site visible during outages | Blank site | Small (done) | 2 |
| Uploads to object storage | Evidence photos persist | Photos lost on restart | Small | 3 |
| Verify chemical label claims | Chemical step becomes usable | Ladder stops at non-chemical rungs | Human review | 4 |
| SMS adapter (test mode) | Alerts reach phones | Alerts are in-app only | Medium | 5 |
| Multi-field command strip | Faster triage for multi-plot farmers | Minor | Small | 6 |
| Intervention outcome summary | Evidence of what works | Minor | Small | 7 |
| FPO intelligence | New user group | None to existing users | Large | 8 |
| WhatsApp Business channel | Reach | None | Medium, needs Meta approval | 9 |
| DigiHaat | Revenue | Distraction from core | Large | 10, gated |
| Commercial layer | Revenue | None | Medium | 11, gated |
