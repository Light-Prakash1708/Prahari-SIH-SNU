"""
PRAHARI · soil health — the self-test, the report, and the nutrient gap
════════════════════════════════════════════════════════════════════════════
Two things, kept apart on purpose because they are made of different evidence:

  THE SELF-TEST is a Visual Soil Assessment a farmer performs with a spade and
  a mug of water. Six observations — aggregate structure, infiltration,
  earthworms, surface crusting, topsoil colour, root form — each scored 0/1/2.
  It costs nothing, needs no laboratory, and it is the only soil information
  most smallholders will ever have. It is not a chemical analysis and this
  module never lets its output be read as one.

  THE NUTRIENT GAP needs laboratory numbers — the Soil Health Card the farmer
  already has, or a soil-testing lab report. Given N, P, K, pH and organic
  carbon it rates each against the standard ICAR classes, adjusts the general
  recommended dose up or down by a quarter accordingly, and shows the
  arithmetic in kilograms of urea, SSP and MOP.

WHAT THIS DELIBERATELY IS NOT
-----------------------------
It is not a machine-learning "crop recommender". The published versions of that
idea take N-P-K-temperature-humidity-pH-rainfall into a random forest and emit
a crop name with no reasoning attached, trained on a synthetic Kaggle table
whose provenance nobody can trace. A farmer who has already sown cannot act on
"grow coffee", and an officer cannot audit it. What is offered instead is the
gap between what the soil has and what the crop in the ground needs, with every
number visible and every threshold citable.

It also names no fertiliser brand and recommends no purchase. It gives
kilograms of nutrient per acre and the arithmetic for the three straight
fertilisers, so a farmer can check the shopkeeper's sum rather than be given a
different one to trust.

Every response carries the same sentence: a general recommendation is not a
soil health card, and a sodic or strongly acidic soil needs a laboratory
recommendation, not an app.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import reference

DATA = json.loads((Path(__file__).resolve().parent.parent / "data" / "soil.json")
                  .read_text(encoding="utf-8"))
RATINGS: dict[str, Any] = DATA["ratings"]
RDF: dict[str, Any] = DATA["rdf"]
STRAIGHTS: list[dict] = DATA["straights"]
VSA: list[dict] = DATA["vsa"]
SOURCES: dict[str, str] = DATA["sources"]

DISCLAIMER = (
    "A general recommendation is not a Soil Health Card. These doses are district-level "
    "starting points from state package-of-practice literature, adjusted by whatever soil-test "
    "values you entered. A strongly acidic (pH under 5.5) or sodic (pH over 8.5) soil needs a "
    "laboratory recommendation from your KVK or soil-testing laboratory — not an app.")
DISCLAIMER_MR = (
    "ही सर्वसाधारण शिफारस आहे — मृदा आरोग्य पत्रिका नाही. pH ५.५ पेक्षा कमी किंवा ८.५ पेक्षा जास्त "
    "असल्यास प्रयोगशाळेची शिफारस घ्या.")

SELF_TEST_NOTE = (
    "This is a Visual Soil Assessment — what you can see and feel with a spade. It says a great "
    "deal about STRUCTURE and biology and nothing at all about nutrients. A soil can score full "
    "marks here and still be short of potassium; only a laboratory number can tell you that.")
SELF_TEST_NOTE_MR = (
    "ही डोळ्यांनी करायची तपासणी आहे — जमिनीची रचना व जिवाणूंबद्दल ती बरेच काही सांगते, पण "
    "अन्नद्रव्यांबद्दल काहीही सांगत नाही. त्यासाठी प्रयोगशाळेची तपासणी लागते.")


# ── the self-test ───────────────────────────────────────────────────────────
def questions(lang: str = "en") -> list[dict[str, Any]]:
    return VSA


def score_self_test(answers: dict[str, int]) -> dict[str, Any]:
    """answers: {question_id: option value 0|1|2}."""
    known = {q["id"]: {o["v"] for o in q["options"]} for q in VSA}
    bad = [k for k, v in answers.items() if k not in known or v not in known[k]]
    if bad:
        from .errors import bad_request
        raise bad_request("bad_answer", f"'{bad[0]}' is not a question or answer PRAHARI knows.")
    answered = [q for q in VSA if q["id"] in answers]
    if len(answered) < len(VSA):
        missing = [q["id"] for q in VSA if q["id"] not in answers]
        from .errors import bad_request
        raise bad_request(
            "incomplete", f"Answer all {len(VSA)} observations — {len(missing)} still missing. "
                          f"A partial score would not mean anything.")
    total = sum(answers[q["id"]] for q in VSA)
    out_of = len(VSA) * 2
    pct = round(total / out_of * 100)
    band = "good" if pct >= 70 else "moderate" if pct >= 40 else "poor"

    findings: list[dict[str, Any]] = []
    for q in VSA:
        v = answers[q["id"]]
        if v < 2:
            findings.append({
                "id": q["id"], "score": v, "of": 2,
                "observation": next(o["label"] for o in q["options"] if o["v"] == v),
                "observation_mr": next(o["label_mr"] for o in q["options"] if o["v"] == v),
                **_FIX[q["id"]][0 if v == 0 else 1],
            })
    return {
        "score": total, "out_of": out_of, "percent": pct, "band": band,
        **_BAND[band],
        "findings": findings,
        "note": SELF_TEST_NOTE, "note_mr": SELF_TEST_NOTE_MR,
        "why_it_matters": (
            "Soil structure is a crop-health input, not a separate subject. A crusted, compacted "
            "soil waterlogs after rain, and standing water is what turns a Phytophthora from a "
            "risk into a loss. A soil with no earthworms is a soil with no residue breakdown, and "
            "undecomposed residue is where next season's inoculum overwinters."),
    }


_BAND = {
    "good": {"label": "Good structure", "label_mr": "जमिनीची रचना चांगली", "tone": "ok",
             "summary": ("This soil takes water in, holds together in crumbs and has life in it. "
                         "Protect it: it is easier to keep than to rebuild.")},
    "moderate": {"label": "Workable, with problems", "label_mr": "बरी, पण अडचणी आहेत",
                 "tone": "warn",
                 "summary": ("The soil works but is losing structure. The fixes below are cheap "
                             "and slow — none of them shows a result this season, and all of them "
                             "compound.")},
    "poor": {"label": "Degraded structure", "label_mr": "जमिनीची रचना खराब", "tone": "bad",
             "summary": ("This soil is compacted or depleted enough that it is limiting the crop "
                         "regardless of what you feed it. Fertiliser applied to a soil that "
                         "cannot take water in mostly runs off.")},
}

# Two levels of fix for each observation: the serious one (score 0) and the
# mild one (score 1). Nothing here costs money a smallholder does not have.
_FIX = {
    "structure": [
        {"fix": ("Compaction. Break the pan with a subsoiler or a deep tine ONCE, when the soil "
                 "is dry enough to crack rather than smear, then keep machinery off it when wet. "
                 "Ploughing wet soil is what made the pan."),
         "fix_mr": "जमीन दबली आहे. कोरडी असताना एकदा खोल नांगरट करा; ओली असताना यंत्र फिरवू नका."},
        {"fix": ("Structure is starting to go. Add organic matter — farmyard manure, compost, or "
                 "a green manure crop turned in — and reduce the number of tillage passes."),
         "fix_mr": "सेंद्रिय खत किंवा हिरवळीचे खत घाला आणि नांगरटीच्या फेऱ्या कमी करा."},
    ],
    "infiltration": [
        {"fix": ("Water is not entering. Until it does, irrigation and rain both run off and take "
                 "topsoil with them. Break the surface, add organic matter, and consider contour "
                 "bunds if the field slopes."),
         "fix_mr": "पाणी जिरत नाही — वाहून जाते. वरचा थर मोकळा करा, सेंद्रिय खत घाला."},
        {"fix": ("Slow infiltration. Mulch the surface between rows; a covered soil does not seal."),
         "fix_mr": "ओळींमध्ये आच्छादन करा — झाकलेली जमीन कडक होत नाही."},
    ],
    "earthworms": [
        {"fix": ("No earthworms means no residue breakdown and, usually, either heavy tillage or "
                 "repeated broad-spectrum insecticide reaching the soil. Leave crop residue on "
                 "the surface and cut back on soil-applied insecticide."),
         "fix_mr": "गांडुळे नाहीत — पिकाचे अवशेष जमिनीवर ठेवा आणि जमिनीत टाकायचे कीटकनाशक कमी करा."},
        {"fix": ("Some life, not much. Adding well-rotted manure feeds it faster than anything "
                 "else you can buy."),
         "fix_mr": "कुजलेले शेणखत घातल्यास गांडुळांची संख्या वाढते."},
    ],
    "crust": [
        {"fix": ("A hard crust kills germination and is a direct yield loss before the crop even "
                 "starts. Mulch, or a light harrow after the rain before the crust sets."),
         "fix_mr": "कडक कवचामुळे उगवण कमी होते. पावसानंतर हलकी कोळपणी करा किंवा आच्छादन वापरा."},
        {"fix": "Light crusting. Surface mulch between the rows prevents it.",
         "fix_mr": "ओळींमध्ये आच्छादन केल्यास कवच तयार होत नाही."},
    ],
    "colour": [
        {"fix": ("Topsoil the same colour as subsoil usually means the topsoil has been eroded or "
                 "the organic matter is gone. Both are slow to fix and neither fixes itself: "
                 "manure, residue retention, and stopping the erosion."),
         "fix_mr": "वरची माती वाहून गेली आहे किंवा सेंद्रिय पदार्थ संपले आहेत. शेणखत व अवशेष ठेवा."},
        {"fix": "Organic matter is thinning. Manure or compost, every season, is the whole answer.",
         "fix_mr": "दरवर्षी शेणखत किंवा कंपोस्ट घाला."},
    ],
    "roots": [
        {"fix": ("Roots turning sideways means a hard layer they cannot cross. The crop is living "
                 "on the top 15 cm, which is why it wilts three days after irrigation. Break the "
                 "pan when the soil is dry."),
         "fix_mr": "मुळे आडवी वळतात — खाली कठीण थर आहे. कोरड्या जमिनीत खोल नांगरट करा."},
        {"fix": "Shallow rooting. Deeper, less frequent irrigation trains roots downward.",
         "fix_mr": "पाणी कमी वेळा पण जास्त प्रमाणात दिल्यास मुळे खोल जातात."},
    ],
}


# ── the laboratory numbers ──────────────────────────────────────────────────
def rate(key: str, value: float | None) -> dict[str, Any] | None:
    spec = RATINGS.get(key)
    if spec is None or value is None:
        return None
    if key == "ph":
        cls = ("acidic" if value < spec["low"] else
               "alkaline" if value > spec["high"] else "neutral")
        means = (spec["means_low"] if cls == "acidic" else
                 spec["means_high"] if cls == "alkaline" else
                 "Neutral — the range in which most nutrients are available.")
        tone = "ok" if cls == "neutral" else "warn"
    else:
        cls = "low" if value < spec["low"] else "high" if value > spec["high"] else "medium"
        means = (spec["means_low"] if cls == "low" else
                 spec["means_high"] if cls == "high" else
                 "Medium — the general recommended dose applies as published.")
        tone = "warn" if cls == "low" else "ok"
    return {"key": key, "value": value, "unit": spec["unit"], "class": cls,
            "tone": tone, "means": means,
            "thresholds": {"low_below": spec["low"], "high_above": spec["high"]}}


def report(crop: str, values: dict[str, float | None], area_acre: float = 1.0) -> dict[str, Any]:
    """The nutrient gap for the crop that is actually in the ground."""
    rated = {k: rate(k, values.get(k)) for k in RATINGS}
    rated = {k: v for k, v in rated.items() if v is not None}
    base = RDF.get(crop)
    if base is None:
        return {"available": False, "ratings": rated,
                "reason": f"PRAHARI has no published recommended dose on file for {crop}.",
                "sources": SOURCES, "disclaimer": DISCLAIMER}

    adjust = {"low": 1.25, "medium": 1.0, "high": 0.75}
    plan: list[dict[str, Any]] = []
    for nutrient, rating_key, oxide in (("n", "nitrogen_kg_ha", "N"),
                                        ("p", "phosphorus_kg_ha", "P₂O₅"),
                                        ("k", "potassium_kg_ha", "K₂O")):
        general = base[nutrient]
        r = rated.get(rating_key)
        factor = adjust.get((r or {}).get("class", "medium"), 1.0)
        dose = round(general * factor, 1)
        straight = next(s for s in STRAIGHTS if s["nutrient"] == nutrient)
        material = round(dose * 100 / straight["pct"], 1)
        plan.append({
            "nutrient": oxide, "general_kg_acre": general,
            "soil_test_class": (r or {}).get("class"),
            "adjustment": f"×{factor}" if factor != 1.0 else "no change",
            "recommended_kg_acre": dose,
            "total_kg": round(dose * area_acre, 1),
            "material": straight["name"], "material_pct": straight["pct"],
            "material_kg_acre": material,
            "material_total_kg": round(material * area_acre, 1),
            "arithmetic": (f"{dose} kg of {oxide} ÷ {straight['pct']}% = {material} kg of "
                           f"{straight['name']} per acre"),
            "why": ((r or {}).get("means") if r else
                    "No soil-test value entered for this nutrient, so the general recommended "
                    "dose is shown unadjusted."),
        })

    warnings: list[str] = []
    ph = rated.get("ph")
    if ph and ph["class"] != "neutral":
        warnings.append(ph["means"])
    if (values.get("ph") or 7.0) > 8.5 or (values.get("ph") or 7.0) < 5.5:
        warnings.append("This pH is outside the range a general recommendation covers. Take the "
                        "soil report to your KVK before spending anything on amendments.")
    oc = rated.get("organic_carbon_pct")
    if oc and oc["class"] == "low":
        warnings.append("Low organic carbon limits how much of any fertiliser the crop actually "
                        "takes up. Manure is not an alternative to fertiliser here; it is what "
                        "makes the fertiliser work.")

    return {
        "available": True, "crop": crop,
        "crop_label": (reference.CROPS.get(crop, {}) or {}).get("name", crop),
        "area_acre": area_acre,
        "ratings": rated, "plan": plan,
        "split": base.get("split"),
        "unmeasured": [k for k in RATINGS if values.get(k) is None],
        "warnings": warnings,
        "sources": SOURCES,
        "disclaimer": DISCLAIMER, "disclaimer_mr": DISCLAIMER_MR,
        "method": ("The general recommended dose for this crop, moved up a quarter where your "
                   "soil tests LOW and down a quarter where it tests HIGH — standard soil-test "
                   "crop-response practice. Every step is shown so you can check it, and the "
                   "material quantity is just the nutrient divided by the percentage on the bag."),
        "no_brands": ("PRAHARI names the three straight fertilisers and the arithmetic, and no "
                      "brand. What you buy and from whom is your decision — this is here so you "
                      "can check the sum, not so you can be given a different one to trust."),
    }
