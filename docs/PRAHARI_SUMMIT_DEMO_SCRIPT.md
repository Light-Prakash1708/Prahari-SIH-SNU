# PRAHARI — summit demo script (8 minutes)

**Where:** https://prahari-staging.onrender.com is the staging service: synthetic data and generated, labelled weather.

**Never present from production.** Production holds real farmers' records and does not run demo mode.

## Before you go on stage (T − 10 min)

1. **Wake both services.** Open staging and production about 2 minutes early. The free plan sleeps and takes around 50 s to wake.
2. **Sign in.** On staging, sign in → **Farmer** demo.
3. **Reset.** Menu → **PRAHARI consoles** → **Judge mode** → **↺ Reset the demo**. Check the panel shows no warning (the FPO needs 3 members; reset adds them).
4. **Photos.** Keep `samples/bad_photo.jpg` and `samples/late_blight.jpg` on the presenting phone.
5. **Language.** Set it to **বাংলা** from Profile or the sign-in chips if the room is Bengali-speaking. Agronomic detail text from the server is still English, and you should say so if asked.

## The eight cases

Each **Judge** button in the panel signs in the right console and, for farmer cases, opens the right screen.

| # | Show | Do | Say (the honest line) |
|---|---|---|---|
| 1 | Weather-linked risk | Farmer → Risk Forecast | "This weather is generated — the banner says so. The Hutton and TOMCAST models are the production models. On production, risk only runs once 21 days of real history exist." |
| 2 | Bad photo refused | Scan → Gallery → `bad_photo.jpg` | "No diagnosis. It tells the farmer what to fix. Refusing is the feature." |
| 3 | Usable photo → differential | Scan → `late_blight.jpg` | "Ranked candidates with confidence and evidence. The engine is a symptom-feature classifier — not a neural network — and we claim no field accuracy." |
| 4 | Below threshold: no spray | What should I do? → Fruit borer → type **2** → watch the preview → **Save count** | "The preview and the saved decision use the same arithmetic. Below the published threshold the answer is *do not spray*, with the saving." |
| 5 | Expert review | From case 3: *Request expert review* → Expert console | "No verdict is pre-filled. A person confirms." |
| 6 | Graded community signal | Nearby hotspots | "Reports are graded by evidence. A possible cluster is never called a confirmed outbreak." |
| 7 | Officer priority queue | Officer console | "Cases ranked with reasons, and Gi* hotspots with z-scores — computed from synthetic history on staging." |
| 8 | FPO aggregate | FPO console | "Counts across consenting members only. Anything under 3 shows as 'fewer than 3'. The FPO never sees a field." |

## If something fails

- **Weather unavailable on staging.** This cannot happen there: weather is the deterministic generator. If it does, the service restarted mid-demo. Reset.
- **Scan result is an abstention instead of a differential.** Say so, and show it as case 2 behaviour. Do not retry until it "works".
- **Cold start.** Keep talking through the slide while it wakes. Do not refresh repeatedly.

## Questions to expect

| Question | Answer |
|---|---|
| "What is your accuracy?" | "We do not have a labelled field dataset, so we do not quote one. A lab-trained model in the PlantDoc study scored 19.73% on field photos. That is why PRAHARI refuses and escalates." |
| "Is this Bengal-ready?" | "The interface is in Bengali (draft, under review), and Hooghly / Purba Bardhaman blocks are mapped. Potato and paddy models are the pilot's first deliverable. The candidates — JHULSACAST for the WB plains, INDO-BLIGHTCAST, EPIBLA — are in our validation register with citations." |
| "Is production live?" | "Yes: on PostgreSQL, with live weather. Disease risk on production needs a history-weather plan we are buying. Until then it says the model cannot run, rather than guessing." |
