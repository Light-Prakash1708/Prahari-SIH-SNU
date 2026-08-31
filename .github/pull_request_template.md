## What this changes

<!-- One or two sentences. What can a farmer or officer do now that they could not? -->

## How I know it works

<!-- The test you added, the screen you walked through, the command you ran.
     "I did not test X" is a useful and welcome answer. -->

- [ ] `cd backend && python -m pytest tests -q` passes
- [ ] `cd frontend && npm run build` is clean
- [ ] I opened the screen and tried it, including its empty and error states

## The five rules

Tick the ones this PR touches, and say how it holds them.

- [ ] **No fabricated numbers** — nothing on screen that no record produced
- [ ] **Every number cites its source** — thresholds, models and doses show provenance
- [ ] **The model may abstain** — no path turns "not confident" into a guess
- [ ] **Cost never reaches an agronomic decision**
- [ ] **Only a count against a threshold authorises a chemical**
- [ ] None of the above — this is UI, docs, tooling or refactoring

## Database

- [ ] No schema change
- [ ] New additive migration (`schema/00N_name.sql`), nothing dropped or altered

<!-- If you altered or dropped anything, say why here. It will be looked at closely:
     existing farmer, diagnosis and trap records are not replaceable. -->

## Anything you are unsure about

<!-- Genuinely useful. Say what you would want a second pair of eyes on. -->
