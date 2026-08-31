<div align="center">

# PRAHARI · प्रहरी

**Early detection and management of crop disease and pest infestation.**

*Prahari* means the one who keeps watch. The name is the thesis:
this is an early-warning and response platform, not a detection app.

Built for the Smart India Hackathon 2026 problem statement of the
**Maharashtra State Innovation Society**, Department of Skills, Employment,
Entrepreneurship and Innovation · Software · Agriculture, FoodTech & Rural Development.

</div>

---

## The loop

A diagnosis is not an outcome. Every screen in PRAHARI belongs to one of six steps:

```
PREDICT  → published infection models fire on real weather, days before a symptom exists
DETECT   → the camera measures a leaf, or refuses to
VERIFY   → contextual questions when they can settle it; a human expert when they cannot
ACT      → economic threshold gate → IPM ladder → verified-only prescription
MONITOR  → a scheduled re-scan compared with the first, in one direction
LEARN    → one expert confirmation moves one integer in that taluka's prior
```

Which answers the five questions a farmer actually has:

| Question | Where it is answered |
|---|---|
| What is likely to happen? | **Home → What's Coming** — four days of model output |
| What is happening now? | **Home → Farm Health Score** and its four terms |
| How certain are we? | every **Why?** drawer, and the abstention card |
| Should I actually intervene? | **Should I Spray?** — the economic-threshold verdict |
| Did the intervention work? | **Follow-up** — the re-scan, reported as a direction |
| Am I the only one seeing this? | **Community** — aggregated counts, graded into a signal |
| Anything else | **AgriDoc** — answered from records, or refused |

---

## The community, and why it is not a feed

A farmer notices something odd on a leaf three days before it is diagnosable
from a photograph and two weeks before an officer walks that road. That
noticing is the earliest signal this system can possibly receive, and today it
goes into a WhatsApp group where nobody can count it.

```
a farmer posts  →  neighbours tap "I am seeing this too"  →  an expert answers
   →  the verdict is recorded AS a verdict, not as a popular comment
   →  several INDEPENDENT posts in one taluka become a POSSIBLE CLUSTER
   →  an officer goes and looks  →  a CONFIRMED FIELD SIGNAL
```

Three refusals hold the whole thing up, and each is structural rather than
documented:

**It cannot publish a farm's position, because there is no column to publish
it from.** `community_posts` carries village, taluka and district and nothing
finer — taluka is the unit the spatial statistics already work in. The
`plot_id` column exists only so authorised systems can join back, and
`public_post()` builds every response from an **allowlist**, so a private
column added tomorrow cannot leak. The test asserts this against the raw JSON
of every community response, not against a hand-picked list of fields.

**It never calls community advice verified.** A post starts `UNVERIFIED` and
says so in words on every card. The only thing that moves it is a row in
`community_expert_responses` written by an identified expert account — no
amount of agreement promotes a post, and a farmer submitting a `CONFIRMED`
response gets a 403. A reply that names a pesticide **and** a dose is detected
and shown with a red warning above it, and raises an automatic moderation
report so an expert is asked to correct it.

**It never ranks by popularity.** `rank()` scores your taluka, your crops, the
problems those crops actually get, expert verification and recency. A "helpful"
mark contributes at most four points as a tie-break. Every card carries
`shown_because`, so a farmer can audit their own feed.

The word **outbreak** appears in no signal grade and never will. That word
moves budgets and triggers state advisories; it belongs to `outbreak_events`,
which requires expert-confirmed *diagnoses*. Three worried people is a lead.

```
possible_cluster       ≥3 posts from ≥2 DISTINCT accounts in one taluka
corroborated_signal    + evidence that is not conversation — a PRAHARI
                         diagnosis, a trap count over the ETL, or an expert
confirmed_field_signal + an officer went and looked, and said yes
```

Nearby farmers are alerted only from `corroborated_signal` upward, and the
alert is built from **counts**: "three different farmers in your taluka", never
whose. Recipients are chosen by their own field's taluka and crop; no identity
from the reporting posts is read or disclosed.

---

## What v4 added

The identity is Saurjya's; the engines are the ones that were already here.

**Visual identity.** Saurjya's Prahari brand — logo, palette, Plus Jakarta Sans,
the header/drawer/account-sheet chrome, the floating bar with its raised scan
FAB — rebuilt as React components over the existing design tokens, so every
screen inherited it without being rewritten. Font Awesome and Google Fonts were
inlined and bundled rather than fetched: this app is offline-first and a CDN
dependency would break its primary language on the phone it was built for.

Saurjya's static pages hard-code a farmer called Ramesh Kumar with 14 reports
and 98% accuracy. None of that shipped. The account sheet renders whatever
`/api/auth/me` returns, and shows only counts the app actually holds.

**Crop Journey** (`GET /api/crop-calendar/{plot_id}`). One aggregation endpoint
composing services that already existed — stage, risk board, trap state,
forecast, agenda, health history. It owns no agronomy. Two properties are
enforced by tests:

- *Disease bands appear only on the current stage.* A disease fires when weather
  satisfies a published infection model, so whether one threatens a stage six
  weeks out is a question about weather that does not exist yet. Those stages
  stay blank, with the reason on screen.
- *Pest vulnerability is banded per pest, not against a fixed cutoff.* The
  first attempt compared each `stage_factor` to absolute thresholds and put four
  of tomato's five stages at "high" — true of some pest in every case, and no
  help in deciding which weeks matter. Each pest is now banded against its own
  range across the crop's stages. Tomato singles out fruiting, where Tuta and
  Helicoverpa both bottom out; onion singles out bulb.

**Farm ledger** (`/api/farm-ledger`). The one genuinely new table. `applications`
is a food-safety record and `/api/ledger` is the sprays-avoided ledger — neither
is a place for money. The boundary that matters is negative and has its own test:
**cost never reaches the risk engine, the economic threshold or the IPM ladder.**
The moment a cheap intervention can score better than a correct one, the system
is giving agricultural advice on financial grounds.

**More than one photograph** (`POST /api/observations/{id}/images`). Roles —
whole plant, underside, close-up, stem — each telling the farmer *what* to
photograph next. Every extra image passes the same quality gate; one that fails
is kept as the farmer's record but never fed to the engine. A test uploads the
same leaf four times and asserts the engine cannot be talked out of an
abstention by repetition.

**Closing a follow-up without a photograph** (`POST /api/followups/{id}/outcome`).
For a farmer whose leaf has dropped or crop is off. Stored and displayed as
**self-reported**, never as the measured two-image comparison a rescan produces.
Adding it exposed a real bug: "open" was defined as *no rescan observation*, so a
self-reported follow-up would have been asked for forever. The predicate is now
*no observation AND no outcome*, in all five places that ask.

**Quick Tools** — Saurjya's bento hub over the tools that exist, plus the
Fertilizer Guide, which had an API and no screen. It shows the arithmetic
(`75.0 kg of N ÷ 46% = 163.0 kg of Urea per acre`) so a farmer can check the
shopkeeper's sum, names no brand, and lists what was left unmeasured rather
than treating a blank as adequate.

**237 backend tests pass.** No table was dropped, no migration rewritten, no
existing endpoint removed.

## What this build is, and what the prototype was

The v1.0 prototype had good agronomy and no production substance. This is what
changed, and why each one mattered.

| The prototype | This build |
|---|---|
| `/api/me` returned the **first row of the farmers table** — every phone was the same farmer | Real registration, sessions, four roles, and **every scope decision enforced server-side** in `app/deps.py` |
| SQLite only, one module-level connection | Portable layer over **SQLite *and* PostgreSQL**, versioned migrations, no runtime schema mutation |
| Weather defaulted to a **generated series** | `WeatherProvider` abstraction, Open-Meteo on real field coordinates, cached, and a **`503 weather_unavailable`** rather than substitute data |
| `vision.classify()` returned `None`, permanently | **ONNX and remote-API providers, both working**, a model registry, and an engine label that never says "AI" unless a trained model actually ran |
| 42 pesticide rows marked `draft`, screened anyway | Verification is a **row a named person signed**. A draft claim is never actionable and **its product name is never printed** |
| Images on local disk, EXIF intact | Validated, **re-encoded to strip GPS EXIF**, object storage abstraction (local / S3 / R2) |
| `allow_origins=["*"]`, no rate limit, no audit | CORS allowlist, rate limiting, security headers, structured errors, request IDs, audit log |
| No tests | **121 tests**, including the safety properties below and a 23-step end-to-end journey |
| No deployment | Dockerfile, Render blueprint, Vercel config, docker-compose, CI that blocks a failing deploy |

There was also a genuine `NameError` in the prototype's `/api/threshold` handler
(an undefined `target`) that fired whenever a below-threshold notification was
sent. It is gone with the module.

---

## Safety properties — the things that must never happen

These are not aspirations in a document. They are tests in `backend/tests/`,
and CI blocks a deploy if any of them fails.

| # | Property | Test |
|---|---|---|
| 1 | A photograph that fails the quality gate **produces no diagnosis and no candidate list** | `test_a_bad_photograph_is_never_diagnosed` |
| 2 | Answering questions **cannot talk the system out of** a quality failure | `test_questions_cannot_override_a_quality_failure` |
| 3 | A **draft** pesticide claim can never become actionable | `test_a_draft_claim_is_never_returned_as_actionable` |
| 4 | A draft product's **name is never printed** to a farmer | `test_a_draft_product_name_is_never_printed` |
| 5 | No threshold crossing → **chemical application refused** | `test_a_chemical_application_is_refused_without_a_threshold_crossing` |
| 6 | Farmer A cannot read or write **any** of Farmer B's data | `test_farmer_b_cannot_read_farmer_a_field` (+7 more) |
| 7 | An officer sees **only** their authorised talukas; an empty scope returns nothing, never everything | `test_officer_scope_is_enforced_not_advisory` |
| 8 | Expert confirmation is recorded and moves the prior by exactly 1 | `test_the_whole_loop` step 17 |
| 9 | A follow-up changes the field's history and **reports direction, never a percentage** | `test_follow_up_reports_direction_never_a_percentage` |
| 10 | An offline observation syncs **exactly once** | `test_an_offline_capture_syncs_and_does_not_duplicate` |
| 11 | Weather API failure produces an error, **never fabricated weather** | `test_weather_failure_produces_an_error_not_invented_weather` |
| 12 | A heuristic is **never labelled AI** | `test_the_engine_is_never_called_ai_when_no_model_is_configured` |
| 13 | An SMS with no gateway is `skipped`, **never claimed as sent** | `test_an_sms_with_no_gateway_is_skipped_not_claimed_as_sent` |
| 14 | Photograph clusters are **not called a confirmed outbreak** | `test_the_word_outbreak_is_not_used_without_confirmations` |
| 15 | Domain timestamps and dates come from **one clock** | `test_domain_timestamps_and_dates_come_from_the_same_clock` |
| 16 | The assistant **never names a draft product**, however it is asked | `test_saathi_never_names_a_draft_product` |
| 17 | An unrelated question is **refused, not answered with agronomy** | `test_an_unrelated_question_is_never_answered_with_agronomy` |
| 18 | Every grounded answer **carries the row it came from** | `test_every_grounded_answer_carries_a_source` |
| 19 | A community response **never carries a coordinate, plot id, phone number or account id** — asserted against raw JSON | `test_a_public_post_carries_no_coordinate_plot_id_phone_or_account_id` |
| 20 | Agreement from other farmers **never verifies anything** | `test_agreement_from_other_farmers_never_verifies_anything` |
| 21 | A farmer **cannot write an expert response** at any price | `test_a_farmer_cannot_write_an_expert_response` |
| 22 | A reply naming a product **and** a dose is **flagged wherever it is read** | `test_a_reply_naming_a_product_and_a_dose_is_flagged` |
| 23 | One farmer posting five times is **one farmer**, not a cluster | `test_one_farmer_posting_repeatedly_is_not_a_cluster` |
| 24 | **No signal grade uses the word "outbreak"** | `test_no_grade_anywhere_uses_the_word_outbreak` |
| 25 | The alert to nearby farmers **names nobody and no village** | `test_the_alert_to_nearby_farmers_names_nobody` |
| 26 | A **missing** soil-test value stays missing and never becomes `0.0` | `test_a_missing_lab_value_stays_missing_and_never_becomes_zero` |
| 27 | Weed advice **never names a herbicide** | `test_the_weed_advice_never_names_a_herbicide` |
| 28 | Nothing on the agronomy router **can authorise a chemical** | `test_nothing_on_this_router_can_authorise_a_chemical` |
| 29 | Every reference template is **recoverable from its own signature** — the set is separable | `test_every_reference_template_is_recoverable_from_its_own_signature` |
| 30 | A dataset adapter **refuses to cross a crop boundary** | `test_the_adapter_refuses_to_cross_a_crop_boundary` |

---

## Crop coverage — what changed, and what was actually broken

Cotton, soybean and pigeonpea carried `vision: false`. The camera abstained on
them with `crop-not-covered` — **three of the seven crops PRAHARI claims to
serve**, refusing to look at all. That was honest, and it was still a hole.

All seven now carry a reference set of at least two real candidates plus
`healthy` and `nitrogen_deficiency`: cotton bacterial blight, grey mildew and
leaf curl; soybean rust, yellow mosaic and frogeye leaf spot; pigeonpea wilt,
sterility mosaic and *Phytophthora* blight; and second candidates added for
onion, maize, grape and tomato, because a differential with one real candidate
is not a differential.

Three things are said out loud rather than smoothed over:

* A disease with **no implementable published infection model** carries
  `no_model_note` explaining why — vector-borne, soil-borne, or no rule that
  can be run on a public weather feed — and stays on the risk board marked
  `unforecast`. It does not vanish from it: an empty risk screen reads as
  "this crop has no diseases".
* A model **borrowed from a related pathogen** (TOMCAST on onion and maize,
  Hutton on pigeonpea *Phytophthora*) carries `model_caveat`, shown wherever
  that model fires.
* The two onion blights sit within a few points of each other in the
  differential. That is not a defect — they genuinely co-occur and the field
  distinction is subtle — and a test asserts the engine does **not** manufacture
  a confident gap where none exists.

`ml/datasets/cropdisease.py` reads the Kaggle crop-disease dataset and anything
using the PlantVillage folder convention. It was written without the files in
hand, so it discovers classes on disk, resolves them through a reviewable alias
table, and **reports every folder it could not map**. It refuses to merge
`Squash___Powdery_mildew` into grape `powdery_mildew` — different organism,
different host — because that adds several hundred images to a class, makes
every metric look better, and nothing downstream could ever detect it.

---

## Soil, water and weeds

Three things upstream of disease, each with the boundary of its own evidence
stated on every response.

**Soil** — a visual assessment a farmer does with a spade and a mug of water
(structure, infiltration, earthworms, crusting, colour, root form), plus the
nutrient gap for whoever has a Soil Health Card. A **missing** laboratory value
stays missing; a blank potassium field becoming `0.0` would tell a farmer their
soil is severely deficient and cost them a bag of MOP they did not need. No
brand is named and no purchase recommended — kilograms of nutrient, and the
arithmetic, so the shopkeeper's sum can be checked rather than replaced.

**Water** — an FAO-56 balance: Hargreaves-Samani ET₀ (which needs only Tmax,
Tmin and astronomical radiation — Penman-Monteith needs net radiation and 2 m
wind that no public feed for this district provides), the crop coefficient for
the current stage, effective rainfall, depletion since the last wetting event.
It is a **model**, and the response says so: the useful output is "push an auger
into the root zone and look", with a number attached. Recording an irrigation
resets the balance, which is what stops it drifting into telling a well-watered
field it is parched.

**Weeds** — the excess-green index (ExG = 2g − r − b, Woebbecke et al. 1995) on
a photograph of the ground between rows. It reports cover and pattern; it does
**not** identify a species, does not estimate weeds per square metre — PRAHARI
does not know the camera height — and never recommends a herbicide. Its value
is the series. It belongs in a crop-health system because weedy inter-rows are
the green bridge that carries whitefly and thrips, and the viruses they vector,
from one season into the next.

---

## Architecture

```
                          PRAHARI
                             │
        ┌────────────────────┼────────────────────┐
        ↓                    ↓                    ↓
     FARMER               OFFICER               EXPERT
   phone app          command centre        verification portal
  Home · Crop ·         (dark, dense)         (case review +
  Scan · Community                            community inbox)
  · AgriDoc
        └────────────────────┼────────────────────┘
                             ↓
                    FastAPI · 16 routers
         auth · plots · risk · observations · traps
   decisions · followups · expert · officer · community
      agronomy · saathi · notify · sync · reference · admin  (+ demo)
                             │
   ┌───────────┬─────────────┼─────────────┬──────────────┐
   ↓           ↓             ↓             ↓              ↓
PostgreSQL  Object       Weather        Vision       Notifications
 (SQLite    storage    OpenMeteo /     ONNX / API /   in-app / SMS /
  locally)  local/S3      none          features         email
   │
   └── users · farmers · officers · experts · plots · crop_cycles
       observations · observation_images · diagnoses · diagnosis_candidates
       priors · weather_cache · health_snapshots · risk_forecasts
       traps · trap_observations · threshold_checks · decisions
       label_claims · restricted_products · applications · followups
       expert_cases · expert_reviews · assignments · outbreak_events
       field_events · notifications · notification_deliveries · audit_logs
       community_posts · community_post_images · community_comments
       community_reactions · community_reports · community_expert_responses
       community_topics · community_topic_follows · community_post_topics
       community_blocks · community_cluster_signals
       soil_tests · irrigation_events · weed_checks
```

**Preserved from the prototype, refactored into services:** the Hutton criteria,
TOMCAST DSV accumulation, the Gubler-Thomas index, the 3-10 rule,
growing-degree-day phenology, the economic threshold engine, the IPM ladder,
explainable Bayesian diagnosis, five distinct abstention reasons, Getis-Ord Gi\*
hotspot detection, the officer priority queue, the crop-health score, and the
"don't spray yet" concept. None of that was thrown away; all of it now runs on
real data.

---

## Local setup

Requires Python 3.11+, Node 20+.

```bash
git clone <your-fork> prahari && cd prahari
cp .env.example .env          # then set JWT_SECRET

# demo build — seeded accounts, generated weather, works with no network
./run.sh --demo

# or a real build — real weather from Open-Meteo, no seeded data
./run.sh
```

Open <http://127.0.0.1:8000>. API documentation at `/docs`.

```bash
./run.sh --test               # 88 tests
./run.sh --reseed --demo      # wipe and rebuild the demo database
docker compose up --build     # the PostgreSQL path, before you deploy it
```

Frontend with hot reload, against a running API:

```bash
cd frontend && npm install && npm run dev      # :5173, proxies /api to :8000
```

### Demo credentials

**Demo environment only.** Created by `AUTO_SEED_DEMO=true`, which
`APP_ENV=production` refuses.

| Role | Sign in with | Password |
|---|---|---|
| Farmer | `9000000001` … `9000000009` | `prahari-demo-2026` |
| Officer | `officer@prahari.demo` | `prahari-demo-2026` |
| Expert | `expert@prahari.demo` | `prahari-demo-2026` |
| Admin | `admin@prahari.demo` | `prahari-demo-2026` |

---

## Deployment

### Backend + frontend together (recommended — one origin, no CORS surface)

**Render**, from `render.yaml`:

```bash
render blueprint launch          # or connect the repo in the Render dashboard
```

It provisions a PostgreSQL 16 instance, generates `JWT_SECRET`, mounts a disk
for uploads and health-checks `/api/health`. Then set `CORS_ORIGINS` and
`TRUSTED_HOSTS` to your actual domain.

**Any Docker host:**

```bash
docker build -t prahari .
docker run -p 8000:8000 \
  -e APP_ENV=production \
  -e DATABASE_URL='postgresql+psycopg://user:pw@host:5432/prahari' \
  -e JWT_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  -e CORS_ORIGINS=https://prahari.example.gov.in \
  -e TRUSTED_HOSTS=prahari.example.gov.in \
  prahari
```

Migrations apply on startup. To apply them separately:

```bash
cd backend && python -c "from app.db import Database; print(Database().migrate())"
```

### Split deployment (frontend on Vercel)

```bash
vercel --prod                                   # uses vercel.json
# then, on the frontend project:
#   VITE_API=https://prahari-api.onrender.com
# and on the API:
#   CORS_ORIGINS=https://prahari.vercel.app
```

### Object storage

`STORAGE_PROVIDER=local` is correct for a pilot on one box. For anything larger,
point it at S3, Cloudflare R2, MinIO or Backblaze B2 — the interface is
identical and image URLs become presigned and expiring:

```
STORAGE_PROVIDER=s3
S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
S3_BUCKET=prahari
S3_ACCESS_KEY=…
S3_SECRET_KEY=…
```

### Production refuses to start when

`APP_ENV=production` and any of: `JWT_SECRET` shorter than 32 characters ·
`DEMO_MODE=true` · `AUTO_SEED_DEMO=true` · `WEATHER_PROVIDER=demo` ·
`CORS_ORIGINS=*` · a `sqlite://` `DATABASE_URL` · `PRAHARI_TODAY` set.
Each raises at startup with the reason. CI asserts every one of them.

---

## The vision model

`VISION_PROVIDER=none` is the shipped default, and the API is explicit about
what that means: the ranking comes from a **symptom-feature classifier** —
measured necrotic, chlorotic and powdery area, lesion count, border sharpness —
combined with the taluka prior and the weather models. It is **not** a neural
network, and no screen calls it one.

To plug in a real model:

```bash
cd ml
pip install -r requirements.txt
python -m preprocessing.prepare  --manifest datasets/manifest.json --out data/prepared
python -m training.train         --data data/prepared --arch mobilenetv4_conv_small
python -m evaluation.evaluate    --checkpoint runs/latest/best.pt --split test
python -m export.export_onnx     --checkpoint runs/latest/best.pt --out models/prahari-vision-0.2.onnx
python -m export.register_model  --version 0.2
```

Then `VISION_PROVIDER=onnx`, `VISION_MODEL_PATH=…`, `VISION_MODEL_VERSION=0.2`.

`ml/README.md` carries the dataset strategy and the reason the test split is
grouped **by field, not by image**. The headline number to keep in mind:

> A model trained on PlantVillage scores **99% on PlantVillage** and
> **19.73% on real field photographs** (PlantDoc, arXiv:1911.10317).
> The best published result on the largest in-the-wild benchmark, PlantWild,
> is **67.20%**.

PRAHARI displays an accuracy figure only when `evaluation/evaluate.py` produced
it, and shows *"no evaluation recorded"* otherwise.

---

## PRAHARI Saathi — an assistant that can only say what PRAHARI can prove

`POST /api/saathi/ask` answers questions about a field. It contains **no language
model**, and that is the design rather than a missing dependency.

The brief is explicit that a language model must never invent pesticide dosage,
legal restriction, treatment or yield. The way to guarantee that is not to
instruct a model carefully — it is to build the answerer out of retrieval and
templates, so the set of sentences it can emit is finite, reviewable, and
traceable to a row.

```
question → intent → RETRIEVE from trusted sources → answer + the rows it used
                       ↓ nothing retrieved
                     "I don't have enough verified information to answer
                      that safely."
```

It draws on exactly three things: published agronomic references (thresholds,
IPM ladders, infection-model provenance), label claims a named reviewer has
**verified**, and the asker's own field records. Every answer renders the
sources underneath it, and a `draft` source is badged *unverified* on screen.

Two failures found while building it, both now regression tests:

* a bare `"will it"` keyword answered *"will it rain on my wedding day"* with a
  crop-disease forecast;
* a bare `"किती"` — Marathi for *how much* — answered *"कांद्याचा बाजारभाव किती?"*
  (what is the onion market price?) with a pest threshold.

Both were confident, plausible and about the wrong thing, which is precisely the
failure mode an agricultural assistant cannot afford. `test_saathi.py` now
parametrises nine unrelated questions and asserts every one is refused.

```
✓ "Should I spray?"            → No — not yet. 4 against a threshold of 7.2 (56%)…
                                 sources: your threshold check · ICAR-IIHR IPM package
✓ "फवारणी करू का?"              → नाही — अजून नाही. घाटे अळी ची शेवटची मोजणी 4 होती…
✗ "कांद्याचा बाजारभाव किती?"    → refused, with what it CAN answer listed
```

## API

`/docs` is generated and accurate. The shape:

```
POST   /api/auth/register  /login  /logout  /password/reset  /password/change
GET    /api/auth/me

GET    /api/plots            POST /api/plots
GET    /api/plots/{id}       PATCH /api/plots/{id}
POST   /api/plots/{id}/cycles
GET    /api/plots/{id}/history                     ← Field Health Passport

GET    /api/risk/{id}        GET /api/risk/{id}/forecast
GET    /api/fields/{id}/health                     ← score + What Changed
GET    /api/fields/{id}/nearby                     ← aggregated to taluka

POST   /api/observations                           ← multipart, idempotent
GET    /api/observations/{id}
GET    /api/observations/{id}/questions
POST   /api/observations/{id}/answers
POST   /api/observations/{id}/expert-review

POST   /api/traps            POST /api/traps/{id}/counts
POST   /api/traps/{id}/scan  GET  /api/traps/{id}/series

POST   /api/threshold                              ← the only path to a chemical
GET    /api/decisions/{id}/should-i-spray
GET    /api/recommendations/{id}?target=…
POST   /api/applications
GET    /api/ledger

GET    /api/followups        POST /api/followups/{id}/rescan

GET    /api/expert/cases     GET  /api/expert/cases/{id}
POST   /api/expert/cases/{id}/review
GET    /api/expert/model-agreement

GET    /api/officer/summary  /hotspots  /outbreaks  /queue  /route  /audit
POST   /api/officer/assignments
POST   /api/officer/assignments/{id}/close

POST   /api/saathi/ask                             ← grounded, or an honest refusal
GET    /api/saathi/suggestions

GET    /api/notifications    POST /api/notifications/read
POST   /api/sync                                   ← the offline queue

GET    /api/admin/claims     POST /api/admin/claims/{id}/verify
GET    /api/admin/audit-log

GET    /api/health  /api/ready  /api/reference
```

Errors are structured and honest about whether retrying will help:

```json
{ "error": "weather_unavailable",
  "message": "Weather data could not be retrieved for this field, so risk cannot be forecast. PRAHARI does not substitute invented weather.",
  "message_mr": "…",
  "retryable": true,
  "request_id": "b4de01b7783c" }
```

---

## Security and privacy

* scrypt password hashing (OWASP interactive parameters), JWT + a session row
  so **logout actually revokes**
* every scope decision in `app/deps.py`; **nothing is filtered in the browser**
* uploads validated by decoding, **re-encoded to strip GPS EXIF**, size and
  dimension capped, never stored under a client-supplied name, never executed
* CORS allowlist, TrustedHost, CSP, HSTS, `X-Frame-Options: DENY`, rate limiting
  (tighter on auth endpoints)
* audit log with request IDs; expert portal does **not** receive farmer phone
  numbers; officer sees contact details only on an assigned case
* surveillance aggregated to **taluka** resolution — no public map exposes an
  individual farm
* `DELETE /api/admin/me/data` removes the account, its fields, observations and
  images

---

## Known limitations

Stated plainly, because a system that hides these is not one an agriculture
department should deploy.

1. **No trained vision model ships with this repository** — but the path to one
   is now runnable rather than aspirational. `ml/datasets/plantdoc.py` turns the
   PlantDoc field-photograph dataset into a PRAHARI manifest in one command, and
   `preprocessing → training → evaluation → export` follows from it. Until you
   run it, the symptom-feature classifier runs and is labelled as exactly that.
2. **All 42 chemical label claims are `draft`.** They are transcriptions of
   combinations commonly published in state IPM packages, present so the engine
   could be built and tested. A production instance therefore recommends **no
   chemical at all** until a named reviewer verifies rows against the CIB&RC
   "Major Uses of Pesticides" list. That is the correct behaviour, and it is the
   first deployment task.
3. **Economic thresholds are `draft` too**, from published advisories, and
   carry their source on screen. They need the same verification pass.
4. **Trap photographs are stored, not counted.** Counting sticky insects is a
   detection problem the shipped model is not trained for, so PRAHARI asks for
   the farmer's own number rather than inventing one.
5. **Leaf wetness is a proxy** (hours at RH ≥ 90%). No public feed measures it
   directly and dedicated sensors report near-100% false positives above 90% RH.
6. **Mahavedh is not integrated.** Maharashtra's ~2,060 automatic weather
   stations would be the right source at plot level, but the data sits behind
   the WINDS portal and is not openly available to third parties. Only
   `OpenMeteoProvider` would change.
7. **"Sprays avoided" is the weakest available claim** — it counts
   below-threshold checks against the 7-day prophylactic calendar most growers
   run. A real reduction figure needs a season of paired untreated plots, and
   that is what a deployment should fund rather than assert.
8. **Rate limiting is per-process.** Behind several replicas, put it in the
   platform's own limiter or a shared Redis counter.
9. **The Gi\* statistic measures where reports cluster, not where disease is.**
   Reports also cluster where the app is used most, and that bias is real until
   coverage is even. The officer console says so on the same screen.
10. **Voice input and IVR dialling are not built.** IVR scripts are generated
    and stored; the telephony integration is not written.
11. **No formal accessibility audit** has been run, though targets are ≥ 48 px,
    colour is never the only carrier of a state, and every control is labelled.

---

## SIH demonstration — 4 minutes

Run `./run.sh --reseed --demo`, sign in as `9000000001`.

| Time | Screen | The point |
|---|---|---|
| 0:00 | Home | *"This is a tomato field near Pimpalgaon. Health 81. But look at day 3."* — **PREDICT**, before any symptom exists |
| 0:30 | What's Coming → Details | Risk rises on the forecast. Open **Why?**: Hutton criteria, RH-hour counts, the citation. Nothing here needed a photograph |
| 1:00 | Scan → a deliberately blurred leaf | **The camera refuses.** No diagnosis, no candidate list — and answering questions is *blocked*. This is the slide most teams do not have |
| 1:30 | Scan → a good leaf | A differential with three candidates, supporting *and* contradicting evidence, and the engine named honestly at the bottom |
| 2:00 | Should I Spray? · count 4 | **🟢 NO — NOT YET.** Below threshold, with the rupee value of not spraying and a re-check date. The chemical rung is visibly *withheld* |
| 2:30 | Trap → count 22 | Threshold crossed. Decision flips — and the chemical rung says **"no verified recommendation"**, because every shipped claim is `draft` |
| 3:00 | Admin verifies one claim | *Now* a product appears, with dose in the farmer's own tank size, PHI, resistance rotation, and the CIB&RC citation that unlocked it |
| 3:20 | Record it → Follow-up → re-scan | Direction only. **"We will not invent 38% → 21% from two hand-held photographs."** Field Health Passport shows the whole arc |
| 3:40 | Officer console | Emerging **cluster**, not "outbreak" — 4 reports, 2 confirmed, Gi\* z = 1.53. Priority queue ranks *uncertainty*, not confidence. Route plan labelled a suggestion |
| 4:00 | Expert portal | Everything the model saw, plus what it could not. Confirm → **α moves by exactly 1**. No gradient, no retraining, auditable by counting cases |

The closing line: *every refusal in that demonstration was the product working.*

---

## Working on PRAHARI — for the team

Four documents, in the order you need them. Read the first one before your first
commit; the rest when you reach them.

| Read | When | What it gives you |
|---|---|---|
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | before your first commit | five-minute setup, the five rules, branch names, what gets a PR sent back |
| **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** | before your first feature | where every file lives, one request traced end to end, the three config seams |
| **[docs/ROADMAP.md](docs/ROADMAP.md)** | when picking work | 13 issues sized S/M/L with the files to open — and five things we deliberately will not build |
| **[CLAUDE.md](CLAUDE.md)** | if you use an AI assistant here | the same rules plus the traps in this codebase that a model reliably gets wrong |

### Picking something up

```bash
git clone https://github.com/Light-Prakash1708/PRAHARI-SIH-2026.git
cd PRAHARI-SIH-2026 && cp .env.example .env      # set JWT_SECRET
./run.sh --demo                                   # API on :8000, seeded
cd frontend && npm install && npm run dev         # :5173
```

Take an item from the roadmap, open an issue with the same title (the templates
in `.github/ISSUE_TEMPLATE/` ask the right questions — the agronomy one requires
a citation), branch `feat/…`, `fix/…` or `data/…`, and open a PR. The PR
template's checklist is the five rules; it is short because the rules are few.

Two kinds of contribution need **no code at all** and are worth the most right
now: adding a crop, pest or threshold is a JSON edit in `backend/app/data/`
(sorghum, chickpea, wheat, sugarcane and banana are the obvious next ones), and
Marathi strings are missing on the newest screens.

### The five rules, in one line each

1. Never fabricate a number a farmer might act on — missing data says so.
2. Every number carries its source: ICAR citation, model name, or visible arithmetic.
3. The model may abstain; low confidence goes to a human, not to a guess.
4. Cost never reaches an agronomic decision.
5. Only a count against a threshold authorises a chemical.

Each is enforced by a test. If one blocks your change, the change is wrong —
`docs/ARCHITECTURE.md` lists which test guards which rule.

---

## Repository

```
backend/app/
  config.py      settings, and the guards that refuse an unsafe production start
  clock.py       one clock — domain time, and real time for protocol deadlines
  db.py          SQLite + PostgreSQL behind one interface, versioned migrations
  schema/        the DDL, with portability placeholders
  security.py    scrypt, JWT, session tokens
  accounts.py    registration, login, sessions, password reset
  deps.py        EVERY scope decision in the system
  errors.py      structured, bilingual, honest about retryability
  obs.py         structured logging, request IDs, audit
  reference.py   crops, problems, thresholds, talukas, model provenance
  chemicals.py   the verification gate — the highest-risk file, so the strictest
  weather.py     WeatherProvider · OpenMeteo · Demo · Null, with a cache
  vision.py      leaf segmentation, symptom features, the quality gate
  vision_service.py  ONNX / API / none, and the honesty rules about naming them
  storage.py     local / S3, validation, EXIF stripping, thumbnails
  notify.py      channels with a delivery state that is not a guess
  outbreak.py    graded cluster detection — the words PRAHARI may use
  saathi.py      the assistant: retrieval and templates, no language model
  routeplan.py   nearest-neighbour + 2-opt, labelled a suggestion
  riskmodels.py  Hutton · TOMCAST · Gubler-Thomas · 3-10 · GDD   (preserved)
  diagnose.py    Bayes, and five reasons to refuse                (preserved)
  etl.py         the economic threshold gate                      (preserved)
  prescribe.py   dose arithmetic, PHI, resistance rotation        (preserved)
  spatial.py     Getis-Ord Gi*, spread front, priority queue      (preserved)
  health.py      the crop-health score                            (preserved)
  loop.py        contextual questions, scan comparison            (preserved)
  forecast.py    per-day model output                             (preserved)
  services/      risk · diagnosis · decisions
  routers/       13 routers
backend/tests/   237 tests
frontend/src/    api.js · ui.jsx · screens/
ml/
  datasets/plantdoc.py   PlantDoc → PRAHARI manifest, with an honest class mapping
  preprocessing/         the FIELD-grouped split, and a leakage check that refuses
  training/ evaluation/ export/ inference/
```

---

<div align="center">

**PRAHARI** — *predict, detect, verify, act, monitor, learn.*

Built to be deployed, not screenshotted.

</div>
