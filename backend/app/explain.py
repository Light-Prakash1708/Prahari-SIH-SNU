"""
PRAHARI · what the assistant is allowed to know about a problem
════════════════════════════════════════════════════════════════════════════
This module owns no agronomy and calls no model. It assembles, from rows that
already exist, the FACTS a language model may word — and by construction it is
also the list of things that model may say.

    reference.problems     name, scientific name, what to look for, how fast
                           it moves, the infection model it is forecast by
    reference.IPM          the published cultural and biological steps
    reference.THRESHOLDS   the economic threshold and who published it
    MODEL_PROVENANCE       the criteria that fire the model, and their source
    the diagnosis          what the vision model actually said, and how sure
    the field              crop, stage, and today's weather if it is available

Everything here is retrieved. Nothing is composed. That matters because of what
sits downstream: `llm.structured` requires every number in the model's reply to
appear in these facts, and rejects a product name that does not. So this
function is the boundary — a fact left out here is a sentence the assistant
cannot write, and a fact put in carelessly is one it can.

WHAT IS DELIBERATELY ABSENT: a chemical dose, a spray interval, and any claim
about how a disease spreads that the reference tables do not make. The tables
carry `speed` for some problems and nothing for others, and a card that filled
that gap from a model's general knowledge would be exactly the fabrication the
rest of this system refuses.
"""
from __future__ import annotations

from typing import Any

from . import chemicals, reference

# The card sections, and the order a farmer reads them in. Each is a key the
# model must return; an empty one is rendered as absent, never as a blank line.
FLASHCARD_KEYS = (
    "what_is_it",
    "symptoms",
    "causes",
    "what_to_look_for",
    "how_it_spreads",
    "prevention",
    "field_tip",
    "when_to_seek_help",
)

FLASHCARD_LABELS = {
    "what_is_it": ("What is it?", "हे काय आहे?"),
    "symptoms": ("Symptoms", "लक्षणे"),
    "causes": ("What causes it?", "कशामुळे होते?"),
    "what_to_look_for": ("What should I look for?", "काय पहावे?"),
    "how_it_spreads": ("How does it spread?", "कसे पसरते?"),
    "prevention": ("Prevention", "प्रतिबंध"),
    "field_tip": ("Field tip", "शेतातील टीप"),
    "when_to_seek_help": ("When to seek expert help", "तज्ज्ञांची मदत कधी"),
}

EXPLAIN_KEYS = (
    "what_was_found",
    "how_sure",
    "symptoms",
    "likely_causes",
    "severity",
    "inspect_next",
    "prevention",
    "management",
    "cautions",
)


# Formulation markers. A row naming one is a CHEMICAL product however the
# ladder files it, and a chemical reaches a farmer through the prescription
# screen — behind the threshold gate, against a verified label, with the
# arithmetic shown — or it does not reach them at all. A flashcard is not that
# screen, so these rows are kept out of the facts entirely: what the model
# never sees, it cannot name.
_FORMULATION = (" wp", " sc", " ec", " wg", " sl", " sp", " ws", "%",
                "mixture", "oxychloride", "sulphate", "sulfate")


def _non_chemical(steps: list[str]) -> list[str]:
    return [n for n in steps
            if not any(m in (n or "").lower() for m in _FORMULATION)]


def _problem_facts(problem_id: str, crop: str | None) -> dict[str, Any]:
    """Everything PRAHARI holds about one problem. Keys that have no row are
    left out entirely rather than set to null — the model is told to leave a
    field empty when the facts do not support it, and an absent key is the
    clearest possible way of not supporting one."""
    p = reference.problem(problem_id) or {}
    out: dict[str, Any] = {
        "id": problem_id,
        "name": p.get("name"),
        "name_marathi": p.get("mr"),
        "scientific_name": p.get("sci"),
        "kind": "pest" if problem_id in reference.PESTS else "disease",
    }
    if p.get("scout"):
        out["what_to_look_for_published"] = p["scout"]
    if p.get("speed"):
        # The only statement about spread rate this system has. Where it is
        # absent the card's "how it spreads" section stays empty.
        out["how_fast_it_moves_published"] = p["speed"]
    if p.get("no_model_note"):
        out["why_no_forecast"] = p["no_model_note"]
    if p.get("model_caveat"):
        out["model_caveat"] = p["model_caveat"]

    prov = reference.MODEL_PROVENANCE.get(p.get("model") or "", {})
    if prov:
        out["infection_model"] = {
            "name": prov.get("name"), "criteria": prov.get("rule"),
            "for": prov.get("for"), "source": prov.get("source"),
            "note": prov.get("note"),
        }

    ladder = reference.IPM.get(problem_id) or {}
    if ladder.get("cultural"):
        out["published_cultural_steps"] = _non_chemical(ladder["cultural"])
    if ladder.get("biological"):
        # NAMES ONLY. The `detail` on these rows carries concentrations —
        # "1 g/L, evening spray" — and a card is not where a dose belongs: the
        # prescription screen does that arithmetic in front of the farmer,
        # against a verified label, behind the threshold gate. Leaving the
        # numbers out of the facts is also what makes it impossible for the
        # model to print one, because `_numbers_agree` only permits a number
        # that is already here.
        bio = _non_chemical([b.get("n") for b in ladder["biological"] if b.get("n")])
        if bio:
            out["published_biological_steps"] = bio

    if crop:
        th = reference.threshold_for(problem_id, crop)
        if th:
            out["economic_threshold"] = {
                "value": th.get("etl"), "unit": th.get("unit"),
                "source": th.get("source"), "status": th.get("status", "draft"),
                "alternative_check": th.get("alt"),
            }
    return out


def flashcard_facts(problem_id: str, plot: dict[str, Any] | None,
                    weather: dict[str, Any] | None = None,
                    stage: dict[str, Any] | None = None) -> dict[str, Any]:
    """The grounding for a set of flashcards about one problem in one field."""
    crop = (plot or {}).get("crop")
    facts: dict[str, Any] = {
        "problem": _problem_facts(problem_id, crop),
        "policy": ("Everything above is what PRAHARI holds. Do not add symptoms, "
                   "causes, spread mechanisms, products or doses that are not "
                   "written here. Leave a field empty instead."),
    }
    if crop:
        facts["crop"] = reference.CROPS.get(crop, {}).get("name", crop)
    if stage and stage.get("label"):
        facts["crop_stage"] = {"stage": stage.get("stage"), "label": stage.get("label"),
                               "days_after_sowing": stage.get("days")}
    if weather and weather.get("days"):
        # TODAY only, and labelled as measured or generated. The card may say
        # what these conditions mean; it may not report a number that is not
        # here, and it may not call a generated series an observation.
        today = next((d for d in reversed(weather["days"]) if not d.get("future")), None)
        if today:
            facts["todays_weather"] = {
                "source": weather.get("source"),
                "is_generated_not_observed": weather.get("source_kind") == "generated",
                "min_temp_c": today.get("tmin"), "max_temp_c": today.get("tmax"),
                "mean_humidity_pct": today.get("rh_mean"),
                "hours_at_rh_above_90": today.get("rh90_hours"),
                "rain_mm": today.get("rain_mm"),
            }
    return facts


def explain_facts(db, problem_id: str | None, diagnosis: dict[str, Any] | None,
                  plot: dict[str, Any] | None, weather: dict[str, Any] | None = None,
                  stage: dict[str, Any] | None = None) -> dict[str, Any]:
    """The grounding for an explanation of one scan result.

    The diagnosis half is the part that has to be exact. A vision model that
    abstained did not identify anything, and the facts say so in those words —
    so the explanation cannot describe a disease as found when the engine
    declined to name one.
    """
    facts: dict[str, Any] = {
        "policy": ("Everything above is what PRAHARI holds. Do not name a disease the "
                   "diagnosis did not name, do not state a confidence the diagnosis "
                   "did not give, and do not add a product, a dose or an interval."),
    }
    dx = diagnosis or {}
    abstained = bool(dx.get("abstain") or dx.get("abstained"))
    top = dx.get("top") or {}
    facts["diagnosis"] = {
        "engine": (dx.get("engine") or {}).get("label"),
        "identified_a_problem": (not abstained) and bool(top),
        "abstained": abstained,
        "abstain_reason": dx.get("reason") or dx.get("abstain_reason"),
        "explanation_from_engine": dx.get("explain"),
    }
    if abstained or not top:
        facts["diagnosis"]["what_this_means"] = (
            "PRAHARI did NOT identify a problem from this photograph. Say so plainly. "
            "Do not name a likely disease, and do not describe symptoms as if something "
            "had been found.")
    else:
        conf = top.get("confidence")
        facts["diagnosis"]["named"] = top.get("name")
        facts["diagnosis"]["scientific_name"] = top.get("sci")
        facts["diagnosis"]["confidence_band"] = (
            "low" if conf is None or conf < 0.5 else
            "moderate" if conf < 0.7 else "high")
        facts["diagnosis"]["confidence_means"] = (
            "How sure PRAHARI is about WHAT this is. It says nothing about how much of "
            "it is in the field — only a count or a field assessment says that.")
        others = [d.get("name") for d in (dx.get("differential") or [])[1:3] if d.get("name")]
        if others:
            facts["diagnosis"]["other_candidates_considered"] = others

    if problem_id:
        facts["problem"] = _problem_facts(problem_id, (plot or {}).get("crop"))
        crop = (plot or {}).get("crop")
        if crop:
            verified = chemicals.verified_claims(db, crop, problem_id)
            # Whether a verified chemical option EXISTS. Never its name, never
            # its dose — those come from the prescription screen, which does
            # the arithmetic in front of the farmer and cites the label.
            facts["chemical_options"] = (
                "A verified chemical recommendation exists for this crop and problem. Tell "
                "the farmer to open the recommendation screen for it; do NOT name a product "
                "or a dose here." if verified else
                "PRAHARI has no verified chemical recommendation for this crop and problem. "
                "Do not name one.")
    sub = flashcard_facts(problem_id or "", plot, weather, stage) if problem_id else {}
    for k in ("crop", "crop_stage", "todays_weather"):
        if k in sub:
            facts[k] = sub[k]
    return facts


def fallback_cards(problem_id: str, lang: str = "en") -> dict[str, str]:
    """What the cards say when no model worded them — the retrieved text
    itself. Never empty, never generated, and the reason a Gemini outage costs
    wording rather than content."""
    p = reference.problem(problem_id) or {}
    ladder = reference.IPM.get(problem_id) or {}
    mr = lang == "mr"
    name = (p.get("mr") if mr else p.get("name")) or problem_id
    sci = p.get("sci")
    out = {
        "what_is_it": f"{name} ({sci})" if sci else name,
        "what_to_look_for": (p.get("mr_scout") if mr else p.get("scout")) or "",
        "symptoms": (p.get("mr_scout") if mr else p.get("scout")) or "",
        "how_it_spreads": p.get("speed") or "",
        "causes": "",
        "prevention": "  ".join(ladder.get("cultural", [])[:2]),
        "field_tip": "",
        "when_to_seek_help": "",
    }
    bio = _non_chemical([b.get("n") for b in (ladder.get("biological") or []) if b.get("n")])
    if bio:
        out["field_tip"] = bio[0]
    prov = reference.MODEL_PROVENANCE.get(p.get("model") or "", {})
    if prov.get("rule"):
        out["causes"] = f"{prov.get('name')}: {prov['rule']}"
    return out
