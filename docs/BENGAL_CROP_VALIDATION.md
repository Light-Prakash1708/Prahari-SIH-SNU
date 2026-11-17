# PRAHARI — Bengal crop validation register

Started 17 November 2026 for the Bengal AI Start-up Summit. This register tracks what PRAHARI would need before it advises a farmer in West Bengal. It also records what has been verified and by whom. Nothing below is a threshold, an incidence figure or a weather history that PRAHARI has invented. Where a value is unknown, the entry says **not sourced**.

**Status vocabulary:**
- **verified**: checked by a named agronomist against the primary source.
- **draft**: transcribed from a primary source and not yet checked.
- **candidate**: a published model or source exists, but its rule has not been transcribed in full.
- **not sourced**: no source has been found yet.

## 1. What the reference data covers today

Read from `backend/data/*.json` at commit `7ef5943`.

**Crops (7):** tomato, grape, onion, maize, cotton, soybean, pigeonpea. All are Maharashtra (Nashik) crops.

**Diseases and pests:** 24 diseases and 7 pests, all on those seven crops. Four infection models are implemented:
- Hutton
- TOMCAST
- Gubler-Thomas
- 3-10 rule

**Gap:** potato and paddy, the two crops that matter most for a Bengal pilot, are **not in the reference data**. No Bengal disease or pest has a model, a threshold, an IPM ladder or a label claim in PRAHARI. The summit build must not claim otherwise.

**Administrative units:**
- **Before this sprint:** 10 Nashik talukas only. Field coordinates in Bengal were silently assigned to the nearest Nashik taluka. Fixed in this sprint (see section 5).
- **Now:** 11 West Bengal blocks have been added.

## 2. Pilot crop 1 — potato (Hooghly / Purba Bardhaman potato belt)

| Problem | Host stage | Published risk model | Weather the model needs | Model caveats | Local agronomist verification | Image references | Source & status |
|---|---|---|---|---|---|---|---|
| Late blight (*Phytophthora infestans*) | Canopy formation to maturity (season stage table **not sourced** for WB) | **JHULSACAST, modified for the West Bengal plains** (Sharma, ICAR-CPRI). Tested on 7 years of BCKV Kalyani weather. Rule A: 7-day moving period with ≥105 h at RH ≥90% and ≥150 h at 7.2–26.6 °C, holding for 7 consecutive days. Rule B: 5-day moving ≥65 h at RH ≥90% and ≥105 h at 7.2–26.6 °C for 5 consecutive days, plus ≥2.5 mm rain over two consecutive days. | Hourly temperature, hourly RH, daily rain, 7 days of continuous history | The abstract reports "100%" prediction within 14 days on a small validation (two years). That is the authors' finding, not PRAHARI's, and must not be quoted as PRAHARI performance. The full paper has not been read: the rule above is from the abstract only. | **Not verified.** Candidate verifiers: BCKV AICRP on Potato (Kalyani), or a KVK in Hooghly or Purba Bardhaman. | PlantVillage has potato late-blight leaves taken under lab conditions. The lab-to-field gap (99% vs 19.73%, PlantDoc) applies. No Bengal field images in the repo. | Sharma S., *Potato Journal* 42(1), 2015. https://epubs.icar.org.in/index.php/PotatoJ/article/view/47731 — **candidate** |
| Late blight (alternative) | as above | **INDO-BLIGHTCAST** (ICAR-CPRI): pan-India web model. Spray scheduling with it cut fungicide use by 22.2–44.4% with no significant difference in terminal severity. These are field trials at CPRI Shimla, 2017–2019. | Not stated in the abstract | The trials were in Shimla, not Bengal. The weather rules are not in the abstract. | Not verified | as above | Sharma S., *Potato Journal* 46(2). https://epubs.icar.org.in/index.php/PotatoJ/article/view/100519 — **candidate** |
| Late blight (currently implemented elsewhere) | — | **Hutton criteria** (UK). Already implemented for tomato late blight; same pathogen. | Hourly min temperature and RH, 2 days | UK-derived. JHULSACAST was fine-tuned for the WB plains precisely because generic rules performed poorly there. In that study, 14 models were tested and only Wallin, Bhattacharyya's II and the Dutch rules predicted at all. **If Hutton is ever shown for Bengal potato, the screen must say it is a borrowed UK rule.** | Not verified | — | `reference.MODEL_PROVENANCE["hutton"]` — published criteria, implemented for tomato only |
| Early blight (*Alternaria solani*) | Mid to late season | **Not sourced for potato in Bengal.** TOMCAST is implemented for tomato early blight. | — | TOMCAST is a tomato model. Reusing it for potato must carry the caveat "model borrowed from tomato". | Not verified | PlantVillage: potato early blight (lab) | **not sourced** |
| Economic thresholds (any potato pest) | — | — | — | No potato ETL has been transcribed. | — | — | **not sourced** |

## 3. Pilot crop 2 — paddy (kharif and boro)

| Problem | Host stage | Published risk model | Weather | Caveats | Verification | Image references | Source & status |
|---|---|---|---|---|---|---|---|
| Rice blast (*Magnaporthe oryzae*) | Seedling, tillering, neck at heading | **EPIBLA**: a simulation model and forecasting system for tropical rice in India (FAO AGRIS record). A 2017 review of rice blast forecasting models exists (*Phytopathologia Mediterranea*). | Not transcribed | Neither source has been read in full. No rule is implemented. | Not verified | None in repo | AGRIS record "Epidemiology of blast (EPIBLA)…" — **candidate** |
| Brown spot, sheath blight, bacterial leaf blight | — | **Not sourced** | — | — | — | None | **not sourced** |
| Yellow stem borer, brown planthopper | — | No ETL transcribed | — | `etl.py` cites the Odisha NPSS compliance study for yellow stem borer as a reason for thresholds. That is not a threshold value. | — | — | **not sourced** |

## 4. What must be true before potato or paddy is switched on

1. **Crop stage table.** A crop stage table for each crop under West Bengal sowing windows, from a cited source. `crop_stage` drives every stage-scaled threshold.
2. **Rules transcribed.** Each model's rule transcribed from the full paper (not the abstract) into `riskmodels.py`. This includes a test that reproduces a worked example from the paper.
3. **Visible caveats.** Every borrowed model carries its caveat in `MODEL_PROVENANCE`, and the caveat is rendered on screen.
4. **Thresholds.** Thresholds go into `thresholds.json` with `source` and `status: draft`. They move to `verified` only after a named agronomist signs.
5. **Label claims.** Label claims for Bengal crops are verified against the CIB&RC register by a named person. Until then the chemical rung stays closed, which is what it does today.
6. **Bengali scouting text.** Written and reviewed for each problem.

None of this was done in this sprint. Adding potato or paddy with invented stages or thresholds would have broken PRAHARI's first rule.

## 5. Bengal geography added in this sprint

**Blocks added:** 11 community development blocks in `backend/data/talukas.json`.
- Hooghly: Arambagh, Pursurah, Tarakeswar, Haripal, Singur, Dhaniakhali, Pandua.
- Purba Bardhaman: Jamalpur, Memari I, Kalna I, Raina I.

**Fields recorded for each block:**
- English name and Bengali name.
- Coordinates: as printed on the block's English Wikipedia page, with the URL kept in `coord_source`.
- Status: `draft`.
- `farms: null`. The farm-household count is **not sourced**.

**Consequences in the code:**
- A field is placed in a covered unit only if one lies within 40 km. Otherwise registration answers `outside_coverage` instead of snapping to Nashik.
- Getis-Ord Gi* runs per region, and only over units with a sourced farm count. Bengal blocks are therefore not scored for hotspots until a count is sourced. Adding them does not change any Nashik z-score (test: `test_bengal_blocks_do_not_change_nashik_hotspot_statistics`).
- The outbreak spread front is fitted within the index case's own region only.

**Still to do:**
- Verify the block list and coordinates against the West Bengal government block directory.
- Source farm-household counts (Agricultural Census) so blocks can enter Gi*.

## 6. Language

**Bengali UI:**
- A reviewable Bengali dictionary is at `frontend/src/i18n/bn.js` (about 360 strings). It covers the farmer home, field onboarding, crop selection, scan and photo guidance, the refusal and diagnosis screens, the IPM decision screen, follow-up, navigation and the offline banners.
- Status: **draft, not yet reviewed by a native-speaking agronomist.**
- A missing entry shows English, never Marathi.

**Not translated (shown in English for Bengali users until server-side Bengali fields exist):**
- Server-composed agronomic text: scouting descriptions, decision reasons, model explanations.
- The language model is now told to answer Bengali users in Bengali. It was previously told Marathi. Its number guard still rejects any figure not present in the retrieved facts.

**Voice:** Bengali voice input is **not** claimed. Dictation support was not tested for Bengali in this sprint.

## Review log

| Date | Reviewer | Scope | Outcome |
|---|---|---|---|
| — | — | — | No review yet |
