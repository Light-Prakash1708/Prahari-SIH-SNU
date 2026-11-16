# PRAHARI — Product Roadmap

Written 16 November 2026, after the repository audit (`docs/PRAHARI_AUDIT.md`). Every module below was checked against the code before being classified, so that nothing already built is built twice.

Classification key: EXISTS means shipped and tested; ENHANCE means shipped with a clear gap; PARTIAL means the foundation exists but the module does not; NEW means nothing equivalent exists; DEFER means deliberately not started until a precondition holds.

## Module classification

**A. Farmer Command Centre — EXISTS.** The Home screen carries the field health score, today's agenda, "my next best action", the weather card with an explicit unavailable state, and risk from published infection models. The multi-field view I first listed as a gap already exists: `GET /api/plots/board` (`fieldboard.py`) orders every field by what it asks for today and is rendered by the Fields screen. Nothing was rebuilt.

**B. Alert Orchestration — EXISTS (configuration only) / WhatsApp DEFERRED.** `notify.py` already has a generic HTTP SMS channel (`SMS_PROVIDER=http`, `SMS_API_URL`, `SMS_API_KEY`, `SMS_SENDER_ID`) and SMTP email, each recording an honest delivery state. Turning SMS on is a matter of a DLT-registered sender and those variables, not code. WhatsApp is deferred: it needs Meta business verification and approved templates, plus a farmer opt-in column, and only the official WhatsApp Business Platform will be used.

**C. FPO Intelligence — BUILT (16 Nov 2026, commit `d86f999`).** Migration `007_fpo`, role `fpo` created by an administrator, membership as the farmer's own consented act, and a counts-only summary with small-cell suppression. See the execution log.

**D. Intervention Intelligence — ENHANCED (16 Nov 2026, commit `e4c4879`).** The threshold gate, IPM ladder, ledger, re-scans and escalation were already shipped. Added `GET /api/followups/outcomes`: outcomes after each kind of action, measured and self-reported kept apart, a share only from five measured outcomes, grouped by kind and never by product.

**E. Expert / Officer operations — EXISTS.** Expert case queue and brief, officer overview, early signals, outbreak grading, Gi* hotspots, the reasoned priority queue, assignments and route planning are shipped. Enhancement only on request.

**F. DigiHaat marketplace — DEFER.** Precondition: the core has run for at least two weeks on a persistent (non-expiring) database with uploads in object storage. Even then, no listing, ranking or commission may influence a pesticide recommendation; the chemical gate stays the only path to a chemical.

**G. Commercial foundation — DEFER (test mode only when started).** Subscriptions or FPO billing through a payment provider's test mode. No live keys in the repository or the frontend.

## Reliability and AI track (cross-cutting)

Production stays up when a dependency fails: done for the database (degraded mode, 503 `database_unavailable`, self-recovery). Uploads to object storage: the S3 adapter already exists and works with Cloudflare R2 through `S3_ENDPOINT_URL`; set `STORAGE_PROVIDER=s3` and the five `S3_*` variables. Gemini remains wording-only with number and product guards; it never supplies weather, a count or a dose. Chemical label claims stay `draft` until verified by a named person.

## Priority matrix

| Item | User value | Risk if skipped | Effort | Order |
|---|---|---|---|---|
| Restore DATABASE_URL and a non-expiring database | Site exists at all | Total outage | Minutes | 1 |
| Degraded mode on dependency failure | Site visible during outages | Blank site | Small (done) | 2 |
| Uploads to object storage | Evidence photos persist | Photos lost on restart | Config only (S3/R2 adapter exists) | 3 |
| Verify chemical label claims | Chemical step becomes usable | Ladder stops at non-chemical rungs | Human review | 4 |
| SMS gateway credentials | Alerts reach phones | Alerts are in-app only | Config only (adapter exists) | 5 |
| Multi-field command strip | Faster triage for multi-plot farmers | — | Already exists | done |
| Intervention outcome summary | Evidence of what works | Minor | Small | done |
| FPO intelligence | New user group | None to existing users | Large | done (first version) |
| WhatsApp Business channel | Reach | None | Medium, needs Meta approval | 9 |
| DigiHaat | Revenue | Distraction from core | Large | 10, gated |
| Commercial layer | Revenue | None | Medium | 11, gated |
