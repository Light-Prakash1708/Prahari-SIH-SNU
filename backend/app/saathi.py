"""
PRAHARI · साथी — the agricultural assistant
════════════════════════════════════════════════════════════════════════════
An assistant that can only say what PRAHARI can already prove.

    question → intent → RETRIEVE from trusted structured sources → answer + source
                          ↓ nothing retrieved
                        "I don't have enough verified information to answer
                         that safely."

There is no language model in this file, and that is a design decision rather
than a missing dependency. The master brief is explicit: a language model must
never invent pesticide dosage, legal restriction, treatment or yield. The way to
guarantee that is not to instruct a model carefully — it is to build the
answerer out of retrieval and templates, so that the set of sentences it can
emit is finite, reviewable, and traceable to a row.

What it can draw on, and nothing else:

    · reference.py        crops, problems, published thresholds, IPM ladders,
                          infection-model provenance (ICAR / state advisories /
                          published criteria)
    · label_claims        VERIFIED rows only — never a draft, never its name
    · the farmer's OWN    risk board, forecast, trap counts, threshold checks,
      field state         decisions, applications, field history

Every answer carries where it came from. An answer with no source is a bug.
"""
from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import chemicals, reference
from .clock import today as _today
from .db import Database
from .weather import WeatherUnavailable

# ── intents ─────────────────────────────────────────────────────────────────
# Keyword sets, English and Marathi/Devanagari, plus common Latin-script Marathi
# because a farmer typing on an English keyboard writes "kid" not "कीड".
INTENTS: dict[str, dict[str, Any]] = {
    "should_i_spray": {
        "en": ["should i spray", "spray now", "do i need to spray", "pesticide now",
               "when to spray", "need spraying"],
        "mr": ["फवारणी", "फवारू", "फवारायचे", "औषध मारायचे"],
        "lat": ["favarni", "phavarni", "spray karu"],
    },
    "nearby_community": {
        # "Are other farmers seeing this?" — the question the community exists to
        # answer. Anchored to OTHER PEOPLE plus a place or a seeing-verb, because
        # a bare "nearby" or "गावात" appears in half of all questions and would
        # turn "which shop in the village sells trays" into an outbreak report.
        "en": ["other farmers", "others seeing", "anyone else", "anybody else",
               "nearby farmers", "in my village", "in my taluka", "around me",
               "other fields", "same problem nearby", "is it spreading in",
               "community", "how many farmers"],
        "mr": ["इतर शेतकरी", "इतर शेतकऱ्यांना", "दुसऱ्यांना", "आजूबाजूच्या शेतात",
               "गावात कोणाला", "तालुक्यात किती", "इतरांना पण"],
        "lat": ["itar shetkari", "dusryanna", "gavat konala"],
    },
    "what_is_wrong": {
        "en": ["what is wrong", "what disease", "which disease", "what is this",
               "diagnosis", "identify", "what pest"],
        "mr": ["काय झाले", "कोणता रोग", "रोग कोणता", "हे काय आहे", "निदान"],
        "lat": ["kay jhale", "kontha rog", "rog konta"],
    },
    "risk_forecast": {
        # Deliberately anchored to agronomy. An earlier version matched on the
        # bare phrase "will it", and answered "will it rain on my wedding day"
        # with a crop-disease forecast — confidently, and about the wrong thing.
        # A keyword that fires on any sentence is not an intent, it is a hazard.
        "en": ["disease risk", "pest risk", "risk forecast", "risk this week",
               "what is the risk", "forecast", "next few days", "coming days",
               "crop risk", "infection risk", "weather risk", "outbreak risk"],
        "mr": ["धोका", "धोक्याचा अंदाज", "हवामान धोका", "पुढील दिवस", "संसर्ग"],
        "lat": ["dhoka", "havaman dhoka"],
    },
    "threshold": {
        # "किती" alone means "how much / how many" and appears in almost every
        # Marathi question — it once matched "कांद्याचा बाजारभाव किती?" (what is
        # the onion market price?) and answered with a pest threshold. The same
        # hazard as a bare English "how many". Anchor every keyword to the thing
        # being counted.
        "en": ["threshold", "etl", "economic threshold", "how much is too much",
               "how many insects", "how many moths", "how many larvae",
               "how many per trap", "trap count", "action level"],
        "mr": ["मर्यादा", "आर्थिक मर्यादा", "किती किडे", "किती अळ्या", "किती संख्या",
               "मोजणी", "किती झाल्यावर"],
        "lat": ["maryada", "arthik maryada"],
    },
    "treatment": {
        "en": ["how to control", "how do i treat", "treatment", "remedy", "manage",
               "cure", "get rid of", "control"],
        "mr": ["उपाय", "नियंत्रण", "कसे थांबवायचे", "इलाज", "व्यवस्थापन"],
        "lat": ["upay", "niyantran", "ilaj"],
    },
    "organic": {
        "en": ["organic", "without chemical", "natural", "bio", "neem", "no pesticide"],
        "mr": ["सेंद्रिय", "जैविक", "रासायनिक नको", "कडुनिंब", "नैसर्गिक"],
        "lat": ["sendriya", "jaivik", "kadunimb", "neem"],
    },
    "safety": {
        "en": ["harvest", "pre-harvest", "phi", "waiting period", "residue",
               "how long after spraying", "re-entry", "safe to harvest",
               "safe to pick", "safe to eat"],
        "mr": ["काढणी", "प्रतीक्षा कालावधी", "किती दिवसांनी काढणी", "फवारणीनंतर किती दिवस",
               "अवशेष"],
        "lat": ["kadhani", "pratiksha kalavadhi"],
    },
    "scouting": {
        "en": ["what to look for", "how to check", "scout", "inspect", "signs",
               "symptoms", "where to look"],
        "mr": ["काय पहावे", "कसे तपासावे", "लक्षणे", "कुठे पहावे"],
        "lat": ["kay pahave", "lakshane"],
    },
    "field_status": {
        "en": ["my field", "my crop", "how is my field", "how is my crop",
               "health score", "field status", "crop status", "what changed"],
        "mr": ["माझे शेत", "माझे पीक", "पीक आरोग्य", "शेताची स्थिती", "काय बदलले"],
        "lat": ["majhe shet", "majhe pik"],
    },
    "trap": {
        "en": ["trap", "pheromone", "sticky", "how many traps", "trap count"],
        "mr": ["सापळा", "सापळे", "कामगंध"],
        "lat": ["sapala", "sapale"],
    },
    "about": {
        "en": ["what is prahari", "who are you", "how does this work", "how accurate",
               "can you", "what can you"],
        "mr": ["प्रहरी काय", "तू कोण", "हे कसे चालते", "किती अचूक"],
        "lat": ["prahari kay"],
    },
}

REFUSAL = {
    "en": ("I don't have enough verified information to answer that safely. "
           "PRAHARI only answers from published thresholds, verified label claims and "
           "your own field records — it does not guess. Your Krishi Sahayak or the "
           "nearest KVK can help with this one."),
    "mr": ("हे सुरक्षितपणे सांगण्याइतकी तपासलेली माहिती माझ्याकडे नाही. प्रहरी फक्त प्रकाशित "
           "मर्यादा, तपासलेल्या शिफारशी आणि तुमच्या स्वतःच्या शेताच्या नोंदींवरून उत्तर देते — "
           "अंदाज लावत नाही. यासाठी कृषी सहाय्यक किंवा जवळचे कृषी विज्ञान केंद्र मदत करेल."),
}

SCOPE = {
    "en": ("I can answer about: what is happening in your field, what the weather models "
           "expect next, whether a count has crossed its economic threshold, what "
           "non-chemical management exists for a problem, what to look for when scouting, "
           "and pre-harvest safety intervals. I will not invent a pesticide dose."),
    "mr": ("मी या गोष्टींबद्दल सांगू शकतो: तुमच्या शेतात काय चालले आहे, हवामान मॉडेल पुढे काय "
           "सांगतात, मोजणीने आर्थिक मर्यादा ओलांडली का, रासायनिकाशिवाय कोणते उपाय आहेत, "
           "तपासणी करताना काय पहावे, आणि काढणीपूर्वीचा प्रतीक्षा कालावधी. "
           "मी औषधाची मात्रा स्वतःहून सांगणार नाही."),
}


@dataclass
class Answer:
    intent: str
    text: str
    text_mr: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    grounded: bool = True
    actions: list[dict[str, str]] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def dict(self, lang: str = "en") -> dict[str, Any]:
        return {
            "intent": self.intent,
            "answer": self.text_mr if (lang == "mr" and self.text_mr) else self.text,
            "answer_en": self.text,
            "answer_mr": self.text_mr,
            "grounded": self.grounded,
            "sources": self.sources,
            "actions": self.actions,
            "data": self.data,
            "policy": ("PRAHARI Saathi answers only from published agronomic references, "
                       "VERIFIED chemical label claims and your own field records. It is "
                       "assembled from retrieved rows, not generated — there is no language "
                       "model in this path, so it cannot invent a dose, a restriction or a "
                       "yield figure."),
        }


def detect_intent(q: str) -> tuple[str, float]:
    text = " " + q.lower().strip() + " "
    best, score = "unknown", 0.0
    for name, kw in INTENTS.items():
        hits = 0
        for group in ("en", "mr", "lat"):
            for phrase in kw.get(group, []):
                if phrase in text:
                    hits += 2 if " " in phrase else 1
        if hits > score:
            best, score = name, float(hits)
    return best, score


def find_problem(q: str, crop: str | None = None) -> str | None:
    """Which problem is the farmer asking about? Matched on English name, Marathi
    name and scientific name — never fuzzy-guessed into something else."""
    text = q.lower()
    pool = {**reference.DISEASES, **reference.PESTS}
    if crop:
        scoped = {k: v for k, v in pool.items() if crop in v.get("crops", [])}
        pool = scoped or pool
    for pid, p in pool.items():
        names = [p.get("name", ""), p.get("mr", ""), p.get("sci", ""), pid.replace("_", " ")]
        for n in names:
            if n and n.lower() in text:
                return pid
    # a couple of common colloquialisms that are not the reference name
    for alias, pid in (("blight", "late_blight"), ("करपा", "late_blight"),
                       ("mildew", "downy_mildew"), ("बुरशी", "powdery_mildew"),
                       ("caterpillar", "helicoverpa"), ("अळी", "helicoverpa"),
                       ("whitefly", "whitefly"), ("पांढरी माशी", "whitefly"),
                       ("thrips", "thrips"), ("फुलकिडे", "thrips")):
        if alias in text and pid in pool:
            return pid
    return None


class Saathi:
    """Every handler must either return a grounded Answer or return None, in
    which case the caller emits the refusal. There is no path that produces a
    sentence with no row behind it."""

    def __init__(self, db: Database, runtime=None):
        self.db = db
        self.rt = runtime

    # ── the entry point ────────────────────────────────────────────────────
    def ask(self, question: str, *, plot: dict | None = None,
            lang: str = "mr") -> Answer:
        q = (question or "").strip()
        if not q:
            return self._refuse("empty")
        if len(q) > 500:
            q = q[:500]

        intent, score = detect_intent(q)
        crop = (plot or {}).get("crop")
        problem = find_problem(q, crop)

        handlers: dict[str, Callable[..., Answer | None]] = {
            "about": self._about,
            "should_i_spray": self._should_i_spray,
            "threshold": self._threshold,
            "risk_forecast": self._risk,
            "field_status": self._field_status,
            "treatment": self._treatment,
            "organic": self._organic,
            "safety": self._safety,
            "scouting": self._scouting,
            "trap": self._trap,
            "what_is_wrong": self._what_is_wrong,
            "nearby_community": self._nearby,
        }
        handler = handlers.get(intent)
        if handler is None or score == 0:
            # A named problem with no clear intent is still answerable: tell them
            # what it is and what to look for.
            if problem:
                return self._scouting(q, plot, problem) or self._refuse(intent)
            return self._refuse("unknown")

        out = handler(q, plot, problem)
        return out or self._refuse(intent)

    # ── handlers ───────────────────────────────────────────────────────────
    def _about(self, q, plot, problem) -> Answer:
        return Answer(
            intent="about",
            text=("I am PRAHARI Saathi. I answer from three places and nowhere else: "
                  "published agronomic references, chemical label claims that a named "
                  "reviewer has verified against the CIB&RC list, and your own field's "
                  "records.\n\n" + SCOPE["en"] + "\n\nWhen none of those cover your "
                  "question, I say so rather than guessing."),
            text_mr=("मी प्रहरी साथी. मी फक्त तीन ठिकाणांहून उत्तर देतो: प्रकाशित कृषी संदर्भ, "
                     "तपासलेल्या रासायनिक शिफारशी, आणि तुमच्या स्वतःच्या शेताच्या नोंदी.\n\n"
                     + SCOPE["mr"] + "\n\nयापैकी काहीही तुमच्या प्रश्नाला लागू नसेल, तर मी "
                     "अंदाज न लावता तसे सांगतो."),
            sources=[{"kind": "policy", "detail": "PRAHARI Saathi answer policy"}])

    def _should_i_spray(self, q, plot, problem) -> Answer | None:
        if not plot:
            return None
        target = problem or self._latest_counted_pest(plot["id"])
        if not target:
            return Answer(
                intent="should_i_spray",
                text=("Nothing has been counted in this field yet, so there is nothing to "
                      "judge against a threshold. A diagnosis says what is there; only a "
                      "count says whether it is worth acting on. Count the trap or the "
                      "plants first, and I can answer properly."),
                text_mr=("या शेतात अजून काहीही मोजलेले नाही, त्यामुळे मर्यादेशी तुलना करता येत नाही. "
                         "निदान काय आहे ते सांगते; कृती करावी का हे फक्त मोजणी सांगते. "
                         "आधी सापळा किंवा झाडे मोजा."),
                sources=[{"kind": "field_record", "detail": "no threshold check on this field"}],
                actions=[{"do": "count", "label": "Record a count"}])
        check = self.db.one(
            "SELECT * FROM threshold_checks WHERE plot_id = :p AND pest = :t"
            " ORDER BY checked_at DESC, id DESC LIMIT 1", {"p": plot["id"], "t": target})
        if not check:
            return None
        row = reference.threshold_for(target, plot["crop"])
        name = reference.problem_name(target)
        name_mr = reference.problem_name(target, "mr")
        pct = round(check["count"] / check["etl_effective"] * 100) if check["etl_effective"] else 0
        crossed = bool(check["chemical_authorised"])
        verified = chemicals.verified_claims(self.db, plot["crop"], target)

        if not crossed:
            text = (f"No — not yet. Your last count for {name} was {check['count']:g} against "
                    f"an effective threshold of {check['etl_effective']:g}, which is {pct}% of "
                    f"it. Below the threshold a spray costs more than the damage it prevents, "
                    f"and it removes the natural enemies holding the population down. "
                    f"Count again in five days.")
            text_mr = (f"नाही — अजून नाही. {name_mr} ची शेवटची मोजणी {check['count']:g} होती, "
                       f"मर्यादा {check['etl_effective']:g} आहे — म्हणजे {pct}%. मर्यादेखाली "
                       f"फवारणीचा खर्च नुकसानापेक्षा जास्त होतो आणि मित्रकीटक मरतात. "
                       f"पाच दिवसांनी पुन्हा मोजा.")
        elif verified:
            text = (f"The threshold has been crossed — {check['count']:g} against "
                    f"{check['etl_effective']:g} ({pct}%). An intervention is justified. Work "
                    f"down the IPM ladder first: cultural, then mechanical, then biological. "
                    f"A verified chemical option does exist for {name} on {plot['crop']}; open "
                    f"the recommendation screen to see the dose worked out in your own tank size, "
                    f"with its pre-harvest interval and the resistance rotation applied.")
            text_mr = (f"मर्यादा ओलांडली आहे — {check['count']:g} विरुद्ध "
                       f"{check['etl_effective']:g} ({pct}%). उपाय करणे योग्य आहे. आधी मशागत, "
                       f"मग यांत्रिक, मग जैविक उपाय करा. {name_mr} साठी तपासलेली रासायनिक शिफारस "
                       f"उपलब्ध आहे — शिफारस स्क्रीनवर तुमच्या पंपाच्या मापात मात्रा दिली आहे.")
        else:
            text = (f"The threshold has been crossed — {check['count']:g} against "
                    f"{check['etl_effective']:g} ({pct}%) — so an intervention is justified. "
                    f"But PRAHARI has no VERIFIED chemical recommendation for {name} on "
                    f"{plot['crop']}, so I will not name a product. Use the cultural and "
                    f"biological rungs of the IPM ladder now, and ask your Krishi Sahayak or "
                    f"KVK about a chemical.")
            text_mr = (f"मर्यादा ओलांडली आहे — {check['count']:g} विरुद्ध "
                       f"{check['etl_effective']:g} ({pct}%). उपाय करणे योग्य आहे. पण "
                       f"{name_mr} साठी प्रहरीकडे तपासलेली रासायनिक शिफारस नाही, त्यामुळे मी "
                       f"कोणत्याही औषधाचे नाव सांगणार नाही. मशागत व जैविक उपाय करा आणि "
                       f"कृषी सहाय्यकाचा सल्ला घ्या.")

        return Answer(
            intent="should_i_spray", text=text, text_mr=text_mr,
            sources=[
                {"kind": "field_record",
                 "detail": f"your threshold check on {str(check['checked_on'])[:10]}"},
                {"kind": "threshold", "detail": (row or {}).get("source"),
                 "status": (row or {}).get("status", "draft")},
            ],
            data={"count": check["count"], "etl": check["etl_effective"],
                  "percent": pct, "crossed": crossed,
                  "verified_chemical_available": bool(verified)},
            actions=[{"do": "decide", "target": target, "label": "Open the decision card"}])

    def _threshold(self, q, plot, problem) -> Answer | None:
        crop = (plot or {}).get("crop")
        target = problem or (self._latest_counted_pest(plot["id"]) if plot else None)
        if not target or not crop:
            rows = [r for r in reference.THRESHOLDS if not crop or r["crop"] == crop]
            if not rows:
                return None
            lines = [f"· {reference.problem_name(r['pest'])} on {r['crop']}: "
                     f"{r['etl']} {r['unit']}" for r in rows[:8]]
            return Answer(
                intent="threshold",
                text=("The published economic thresholds PRAHARI carries"
                      + (f" for {crop}" if crop else "") + ":\n" + "\n".join(lines) +
                      "\n\nA threshold quoted without a crop stage is agronomically "
                      "meaningless, so PRAHARI scales each one by the stage your field is "
                      "actually at."),
                text_mr=("प्रहरीकडे असलेल्या प्रकाशित आर्थिक नुकसान मर्यादा:\n" + "\n".join(lines) +
                         "\n\nपिकाच्या अवस्थेशिवाय मर्यादा सांगणे चुकीचे ठरते, म्हणून प्रहरी "
                         "तुमच्या शेताच्या सध्याच्या अवस्थेनुसार ती बदलते."),
                sources=[{"kind": "threshold", "detail": r.get("source"),
                          "status": r.get("status", "draft")} for r in rows[:4]])

        row = reference.threshold_for(target, crop)
        if not row:
            return Answer(
                intent="threshold",
                text=(f"PRAHARI has no published economic threshold for "
                      f"{reference.problem_name(target)} on {crop}. Without one it cannot "
                      f"judge whether an intervention is justified, and it will not invent a "
                      f"number. Ask your Krishi Sahayak for the local recommendation."),
                text_mr=(f"{crop} वरील {reference.problem_name(target, 'mr')} साठी प्रहरीकडे "
                         f"प्रकाशित आर्थिक मर्यादा नाही. ती नसताना उपाय योग्य आहे का हे ठरवता येत "
                         f"नाही, आणि प्रहरी स्वतःहून आकडा तयार करत नाही."),
                sources=[{"kind": "reference", "detail": "no threshold row for this combination"}])

        stage = self.rt.risk.crop_stage(plot) if (self.rt and plot) else {}
        factor = (row.get("stage_factor") or {}).get(stage.get("stage") or "", 1.0)
        eff = round(row["etl"] * factor, 2)
        name = reference.problem_name(target)
        name_mr = reference.problem_name(target, "mr")
        text = (f"The economic threshold for {name} on {crop} is {row['etl']} {row['unit']}.")
        text_mr = (f"{crop} वरील {name_mr} ची आर्थिक नुकसान मर्यादा {row['etl']} {row['unit']} आहे.")
        if factor != 1.0 and stage.get("label"):
            text += (f" Your field is at {stage['label'].lower()}, which scales it to "
                     f"{eff} {row['unit']}.")
            text_mr += (f" तुमचे शेत सध्या {stage.get('label_mr', stage['label'])} अवस्थेत आहे, "
                        f"त्यामुळे ती {eff} {row['unit']} होते.")
        if row.get("alt"):
            text += f" An alternative field check: {row['alt']}."
        if row.get("persist_nights", 1) > 1:
            text += (f" It must hold for {row['persist_nights']} consecutive nights before it "
                     f"counts as crossed — one high night is weather, not a population.")
            text_mr += (f" ही मर्यादा {row['persist_nights']} रात्री सलग टिकावी लागते — "
                        f"एका रात्रीची जास्त संख्या म्हणजे प्रादुर्भाव नव्हे.")
        return Answer(
            intent="threshold", text=text, text_mr=text_mr,
            sources=[{"kind": "threshold", "detail": row.get("source"),
                      "status": row.get("status", "draft")}],
            data={"etl": row["etl"], "effective": eff, "unit": row["unit"],
                  "stage": stage.get("stage")})

    def _risk(self, q, plot, problem) -> Answer | None:
        if not plot or not self.rt:
            return None
        from . import forecast as fc_mod
        try:
            wx = self.rt.risk.weather_series(plot)
        except WeatherUnavailable as exc:
            return Answer(
                intent="risk_forecast",
                text=("I cannot answer that right now: weather data for your field could not "
                      f"be retrieved ({exc.reason}). PRAHARI does not substitute invented "
                      "weather, so there is no forecast to give you. Try again shortly."),
                text_mr=("सध्या हे सांगता येत नाही: तुमच्या शेतासाठी हवामान माहिती मिळाली नाही. "
                         "प्रहरी खोटी हवामान माहिती वापरत नाही, त्यामुळे अंदाज देता येत नाही."),
                sources=[{"kind": "weather", "detail": f"provider unavailable: {exc.reason}"}],
                grounded=True)
        stage = self.rt.risk.crop_stage(plot)
        since = self.rt.risk._since_spray_index(wx["days"], plot["id"])
        series = fc_mod.by_day(wx["days"], reference.problems_for_crop(plot["crop"]),
                               horizon=4, since_idx=since)
        head = fc_mod.headline(series, stage)
        days = " · ".join(f"{s['label']}: {s['level_label']}" for s in series)
        reasons = "\n".join(f"· {r}" for r in head["reasons"][:3])
        reasons_mr = "\n".join(f"· {r}" for r in head.get("reasons_mr", [])[:3])
        return Answer(
            intent="risk_forecast",
            text=f"{head['title']}\n\n{days}\n\n{reasons}",
            text_mr=f"{head.get('title_mr', head['title'])}\n\n{days}\n\n{reasons_mr}",
            sources=[
                {"kind": "weather", "detail": wx.get("source"),
                 "generated": wx.get("source_kind") == "generated",
                 "observed_through": wx.get("observed_through")},
                *[{"kind": "model", "detail": v["name"], "source": v["source"]}
                  for k, v in reference.MODEL_PROVENANCE.items()
                  if any(d.get("model") == k for s in series for d in s.get("drivers", []))],
            ],
            data={"forecast": series},
            actions=[{"do": "forecast", "label": "Open the forecast"}])

    def _field_status(self, q, plot, problem) -> Answer | None:
        if not plot or not self.rt:
            return None
        snap = self.db.one(
            "SELECT * FROM health_snapshots WHERE plot_id = :p ORDER BY day DESC LIMIT 1",
            {"p": plot["id"]})
        if not snap:
            return Answer(
                intent="field_status",
                text=(f"{plot['name']} has no health check recorded yet. Open the home screen "
                      f"once and PRAHARI will compute it from the weather at your field's "
                      f"coordinates and whatever you have counted."),
                text_mr=(f"{plot['name']} ची अजून आरोग्य तपासणी झालेली नाही. मुख्यपृष्ठ एकदा "
                         f"उघडा — प्रहरी तुमच्या शेतावरील हवामानावरून ते मोजेल."),
                sources=[{"kind": "field_record", "detail": "no snapshot yet"}])
        stage = self.rt.risk.crop_stage(plot)
        parts = [f"disease {round(snap['disease'])}", f"pest {round(snap['pest'])}",
                 f"weather {round(snap['weather'])}", f"nearby {round(snap['nearby'])}"]
        return Answer(
            intent="field_status",
            text=(f"{plot['name']} — {plot['crop']}, {plot['area_acre']} acres, currently at "
                  f"{(stage.get('label') or 'unknown stage').lower()}.\n\n"
                  f"Crop-health score {round(snap['score'])} out of 100, made of four penalties: "
                  + ", ".join(parts) + ".\n\nThat is a composite RISK indicator — not an "
                  "estimate of yield, and not a percentage of the crop."),
            text_mr=(f"{plot['name']} — {plot['crop']}, {plot['area_acre']} एकर, सध्या "
                     f"{stage.get('label_mr') or ''} अवस्थेत.\n\n"
                     f"पीक आरोग्य गुण {round(snap['score'])}/100. हा धोक्याचा निर्देशांक आहे — "
                     f"उत्पादनाचा अंदाज नाही."),
            sources=[{"kind": "field_record",
                      "detail": f"health snapshot for {snap['day']}"},
                     {"kind": "weather", "detail": snap.get("weather_source")}],
            data={"score": snap["score"], "day": snap["day"]},
            actions=[{"do": "home", "label": "Open the field"}])

    def _treatment(self, q, plot, problem) -> Answer | None:
        if not problem:
            return None
        ladder = reference.IPM.get(problem)
        name = reference.problem_name(problem)
        name_mr = reference.problem_name(problem, "mr")
        if not ladder:
            return Answer(
                intent="treatment",
                text=(f"PRAHARI does not carry an integrated management package for {name}, so "
                      f"I have nothing verified to give you. Your Krishi Sahayak or the nearest "
                      f"KVK will have the local recommendation."),
                text_mr=(f"{name_mr} साठी प्रहरीकडे व्यवस्थापन माहिती नाही. कृषी सहाय्यक किंवा "
                         f"कृषी विज्ञान केंद्राचा सल्ला घ्या."),
                sources=[{"kind": "reference", "detail": "no IPM ladder for this problem"}])

        cultural = ladder.get("cultural", [])
        bio = ladder.get("biological", [])
        crop = (plot or {}).get("crop")
        verified = chemicals.verified_claims(self.db, crop, problem) if crop else []

        text = (f"Integrated management for {name}, cheapest and safest rung first.\n\n"
                f"1 · Cultural — costs nothing:\n"
                + "\n".join(f"   · {c}" for c in cultural[:5]))
        text_mr = (f"{name_mr} चे एकात्मिक व्यवस्थापन — आधी स्वस्त व सुरक्षित उपाय.\n\n"
                   f"१ · मशागत — खर्च शून्य:\n"
                   + "\n".join(f"   · {c}" for c in cultural[:5]))
        if bio:
            text += ("\n\n2 · Biological and botanical:\n"
                     + "\n".join(f"   · {b['n']} — {b['d']}" for b in bio[:4]))
            text_mr += ("\n\n२ · जैविक व वनस्पतिजन्य:\n"
                        + "\n".join(f"   · {b['n']} — {b['d']}" for b in bio[:4]))
        text += ("\n\n3 · Chemical — only if a count crosses the economic threshold. "
                 + ("A verified label claim exists for this crop and problem, so PRAHARI can "
                    "show you a dose once the threshold is crossed."
                    if verified else
                    "PRAHARI has no VERIFIED label claim for this combination, so it will not "
                    "name a product. That is deliberate, not a gap to work around."))
        text_mr += ("\n\n३ · रासायनिक — फक्त मोजणीने आर्थिक मर्यादा ओलांडल्यावर. "
                    + ("तपासलेली शिफारस उपलब्ध आहे."
                       if verified else
                       "या संयोजनासाठी प्रहरीकडे तपासलेली शिफारस नाही, त्यामुळे औषधाचे नाव "
                       "सांगितले जाणार नाही."))
        return Answer(
            intent="treatment", text=text, text_mr=text_mr,
            sources=[{"kind": "ipm", "detail": f"PRAHARI IPM ladder for {name}"},
                     {"kind": "policy",
                      "detail": "Chemical rung opens only on a threshold crossing AND a "
                                "verified label claim"}],
            actions=[{"do": "decide", "target": problem, "label": "Should I spray?"}])

    def _organic(self, q, plot, problem) -> Answer | None:
        if not problem:
            # Answer generally, from the ladders the crop actually has.
            crop = (plot or {}).get("crop")
            pool = list(reference.problems_for_crop(crop)) + list(reference.pests_for_crop(crop)) \
                if crop else []
            pool = [p for p in pool if reference.IPM.get(p)]
            if not pool:
                return None
            problem = pool[0]
        ladder = reference.IPM.get(problem, {})
        bio = ladder.get("biological", [])
        cultural = ladder.get("cultural", [])
        if not bio and not cultural:
            return None
        name = reference.problem_name(problem)
        name_mr = reference.problem_name(problem, "mr")
        text = (f"Non-chemical management for {name}:\n\n"
                + "\n".join(f"· {c}" for c in cultural[:5])
                + ("\n\nBiological and botanical options:\n"
                   + "\n".join(f"· {b['n']} — {b['d']} (about ₹{b['cost']}/acre)"
                               for b in bio[:4]) if bio else "")
                + "\n\nThese work best BELOW the economic threshold, which is most of the time. "
                  "Once a population is well past threshold they hold it rather than clear it.")
        text_mr = (f"{name_mr} साठी रासायनिकाशिवाय उपाय:\n\n"
                   + "\n".join(f"· {c}" for c in cultural[:5])
                   + ("\n\nजैविक व वनस्पतिजन्य:\n"
                      + "\n".join(f"· {b['n']} — {b['d']} (सुमारे ₹{b['cost']}/एकर)"
                                  for b in bio[:4]) if bio else "")
                   + "\n\nमर्यादेखाली असताना हे उपाय सर्वात चांगले काम करतात.")
        return Answer(
            intent="organic", text=text, text_mr=text_mr,
            sources=[{"kind": "ipm", "detail": f"PRAHARI IPM ladder for {name}"}])

    def _safety(self, q, plot, problem) -> Answer | None:
        if not plot:
            return None
        from . import prescribe
        log = self.db.rows(
            "SELECT * FROM applications WHERE plot_id = :p AND kind = 'chemical'"
            " ORDER BY applied_on", {"p": plot["id"]})
        phi = prescribe.phi_status(log, plot["crop"], _today())
        if not log:
            return Answer(
                intent="safety",
                text=("No chemical application has been recorded on this field, so there is no "
                      "pre-harvest interval running and no harvest gate. If you have sprayed "
                      "something without recording it, record it — that is what makes the "
                      "harvest date reliable."),
                text_mr=("या शेतावर कोणतीही रासायनिक फवारणी नोंदवलेली नाही, त्यामुळे काढणीवर "
                         "कोणतेही बंधन नाही. फवारणी केली असेल तर नोंदवा — त्यामुळेच काढणीची तारीख "
                         "विश्वासार्ह राहते."),
                sources=[{"kind": "field_record", "detail": "no chemical applications recorded"}])
        last = log[-1]
        return Answer(
            intent="safety",
            text=(f"Your last recorded application was {last['product']} on "
                  f"{str(last['applied_on'])[:10]}, with a pre-harvest interval of "
                  f"{last['phi_days']} days. "
                  + (f"Harvest is gated until {str(last['clears_on'])[:10]} — harvesting before "
                     f"that makes the crop unsellable to any buyer who tests for residue."
                     if phi.get("blocked") else
                     "That interval has now passed, so harvest is clear as far as this "
                     "application goes.")
                  + "\n\nAlways re-read the label on the bottle. PRAHARI records what you told "
                    "it; the label is the legal document."),
            text_mr=(f"शेवटची नोंदवलेली फवारणी: {last['product']}, "
                     f"{str(last['applied_on'])[:10]} रोजी, प्रतीक्षा कालावधी "
                     f"{last['phi_days']} दिवस. "
                     + (f"{str(last['clears_on'])[:10]} पर्यंत काढणी करू नका."
                        if phi.get("blocked") else "प्रतीक्षा कालावधी संपला आहे.")
                     + "\n\nबाटलीवरील लेबल नेहमी वाचा — कायदेशीर कागद तेच आहे."),
            sources=[{"kind": "field_record",
                      "detail": f"application recorded on {str(last['applied_on'])[:10]}"}],
            data={"phi": phi})

    def _scouting(self, q, plot, problem) -> Answer | None:
        if not problem:
            return None
        p = reference.problem(problem)
        if not p:
            return None
        name, name_mr = p.get("name", problem), p.get("mr", "")
        bits = []
        bits_mr = []
        if p.get("scout"):
            bits.append(f"What to look for: {p['scout']}")
            bits_mr.append(f"काय पहावे: {p.get('mr_scout') or p['scout']}")
        if p.get("sci"):
            bits.append(f"Organism: {p['sci']}")
        if p.get("speed"):
            bits.append(f"How fast it moves: {p['speed']}")
        if p.get("trap"):
            bits.append(f"Trap: {p['trap']}")
            bits_mr.append(f"सापळा: {p['trap']}")
        model = p.get("model")
        if model and model in reference.MODEL_PROVENANCE:
            mp = reference.MODEL_PROVENANCE[model]
            bits.append(f"PRAHARI forecasts it with the {mp['name']}: {mp['rule']}")
        if not bits:
            return None
        return Answer(
            intent="scouting",
            text=f"{name}" + (f" ({name_mr})" if name_mr else "") + "\n\n" + "\n\n".join(bits),
            text_mr=(f"{name_mr or name}\n\n" + "\n\n".join(bits_mr or bits)),
            sources=([{"kind": "reference", "detail": "PRAHARI problem reference"}]
                     + ([{"kind": "model", "detail": reference.MODEL_PROVENANCE[model]["name"],
                          "source": reference.MODEL_PROVENANCE[model]["source"]}]
                        if model in reference.MODEL_PROVENANCE else [])))

    def _trap(self, q, plot, problem) -> Answer | None:
        if not plot:
            return None
        rows = self.db.rows(
            "SELECT tr.pest, t.counted_on, t.count FROM trap_observations t"
            " JOIN traps tr ON tr.id = t.trap_id WHERE t.plot_id = :p"
            " ORDER BY t.counted_on DESC, t.created_at DESC LIMIT 6", {"p": plot["id"]})
        if not rows:
            pests = [p for p in reference.pests_for_crop(plot["crop"])
                     if reference.threshold_for(p, plot["crop"])]
            if not pests:
                return None
            lines = []
            for pid in pests[:4]:
                p = reference.PESTS[pid]
                row = reference.threshold_for(pid, plot["crop"])
                lines.append(f"· {p['name']} — {p.get('trap', 'trap')}, "
                             f"threshold {row['etl']} {row['unit']}")
            return Answer(
                intent="trap",
                text=("No trap counts are recorded for this field yet. For "
                      f"{plot['crop']} PRAHARI can judge these:\n" + "\n".join(lines) +
                      "\n\nA trap count is the only evidence that can justify an intervention. "
                      "A photograph tells you what is there; the count tells you whether it "
                      "matters."),
                text_mr=("या शेतासाठी अजून सापळ्याची मोजणी नोंदवलेली नाही.\n" + "\n".join(lines) +
                         "\n\nउपाय योग्य आहे का हे फक्त सापळ्याची मोजणीच सांगू शकते."),
                sources=[{"kind": "threshold", "detail": "published ETL table"}],
                actions=[{"do": "traps", "label": "Set up a trap"}])
        latest = rows[0]
        row = reference.threshold_for(latest["pest"], plot["crop"])
        series = " → ".join(f"{r['count']:g}" for r in reversed(rows))
        return Answer(
            intent="trap",
            text=(f"Your most recent count is {latest['count']:g} for "
                  f"{reference.problem_name(latest['pest'])} on "
                  f"{str(latest['counted_on'])[:10]}."
                  + (f" The published threshold is {row['etl']} {row['unit']}." if row else "")
                  + f"\n\nThe recorded series, oldest first: {series}."
                  + "\n\nThree consecutive rises matter more than any single number — that is "
                    "how a population gets away from you."),
            text_mr=(f"शेवटची मोजणी {latest['count']:g} — "
                     f"{reference.problem_name(latest['pest'], 'mr')}, "
                     f"{str(latest['counted_on'])[:10]}."
                     + (f" प्रकाशित मर्यादा {row['etl']} {row['unit']}." if row else "")
                     + f"\n\nनोंदी: {series}."),
            sources=[{"kind": "field_record", "detail": "your recorded trap counts"},
                     {"kind": "threshold", "detail": (row or {}).get("source")}],
            data={"series": [r["count"] for r in reversed(rows)]})

    def _what_is_wrong(self, q, plot, problem) -> Answer | None:
        if not plot:
            return None
        dx = self.db.one(
            "SELECT d.*, o.observed_at FROM diagnoses d JOIN observations o ON o.id = d.observation_id"
            " WHERE d.plot_id = :p ORDER BY d.created_at DESC LIMIT 1", {"p": plot["id"]})
        if not dx:
            return Answer(
                intent="what_is_wrong",
                text=("Nothing has been scanned on this field yet, so I have nothing to go on. "
                      "Photograph an affected leaf — fill the frame with one leaf, in daylight, "
                      "and photograph the underside too if you can."),
                text_mr=("या शेतावर अजून कोणताही फोटो घेतलेला नाही. बाधित पानाचा फोटो काढा — "
                         "एकच पान चौकटीत भरा, उजेडात, आणि शक्य असल्यास पानाची खालची बाजूही."),
                sources=[{"kind": "field_record", "detail": "no observation on this field"}],
                actions=[{"do": "scan", "label": "Scan a leaf"}])
        if dx["abstained"]:
            return Answer(
                intent="what_is_wrong",
                text=(f"The last scan on {str(dx['observed_at'])[:10]} did not produce a "
                      f"confident answer. PRAHARI declined, and the reason it gave was "
                      f"'{dx['abstain_reason']}'.\n\n{dx['explain'] or ''}\n\n"
                      f"Sending it to an expert is the right next step — an agronomist sees "
                      f"the photograph, the weather at your field and its history."),
                text_mr=(f"{str(dx['observed_at'])[:10]} रोजीच्या तपासणीत खात्रीशीर उत्तर मिळाले "
                         f"नाही. तज्ज्ञांकडे पाठवणे हा योग्य पुढचा पर्याय आहे."),
                sources=[{"kind": "field_record", "detail": f"diagnosis {dx['id']}"}],
                actions=[{"do": "scan", "label": "Scan again"}])
        name = reference.problem_name(dx["confirmed"] or dx["top_problem"])
        confirmed = bool(dx["confirmed"])
        return Answer(
            intent="what_is_wrong",
            text=(f"The last scan, on {str(dx['observed_at'])[:10]}, "
                  + (f"was CONFIRMED by {dx['confirmed_by']} as {name}."
                     if confirmed else
                     f"pointed to {name} at {round((dx['top_posterior'] or 0)*100)}% "
                     f"confidence — proposed by PRAHARI, not confirmed by a human.")
                  + "\n\nOpen the observation to see the full differential, the supporting and "
                    "contradicting evidence, and the engine that produced it."),
            text_mr=(f"{str(dx['observed_at'])[:10]} रोजीच्या तपासणीत "
                     + (f"तज्ज्ञांनी {reference.problem_name(dx['confirmed'], 'mr')} निश्चित केले."
                        if confirmed else
                        f"{reference.problem_name(dx['top_problem'], 'mr')} ची शक्यता "
                        f"{round((dx['top_posterior'] or 0)*100)}% दिसली — प्रहरीचा अंदाज, "
                        f"तज्ज्ञांची खात्री नाही.")),
            sources=[{"kind": "field_record", "detail": f"diagnosis {dx['id']}",
                      "engine": dx["engine"], "model_version": dx["model_version"]}],
            data={"problem": dx["confirmed"] or dx["top_problem"], "confirmed": confirmed},
            actions=[{"do": "decide", "target": dx["confirmed"] or dx["top_problem"],
                      "label": "What should I do?"}])

    def _nearby(self, q, plot, problem) -> Answer | None:
        """"Are other farmers nearby seeing this?" (spec §21).

        Answered from AGGREGATED, AUTHORISED data only: the graded signal table
        and counts of posts. This handler cannot reach another farmer's fields,
        coordinates, phone number or diagnosis history — not because it chooses
        not to, but because the only thing it reads is a table of counts.

        It also refuses to inflate. Three worried people in a taluka is a
        possible cluster and gets said as one. The word "outbreak" is never
        produced here."""
        if not plot or not self.rt:
            return None
        from . import signals as signals_mod

        taluka = plot["taluka"]
        target = problem
        if not target:
            dx = self.db.one(
                "SELECT d.top_problem FROM diagnoses d JOIN observations o"
                " ON o.id = d.observation_id WHERE o.plot_id = :p AND d.abstained = 0"
                " AND d.top_problem IS NOT NULL ORDER BY d.created_at DESC LIMIT 1",
                {"p": plot["id"]})
            target = (dx or {}).get("top_problem")

        eng = self.rt.signals
        open_here = eng.open_signals([taluka])

        if not target and not open_here:
            return Answer(
                intent="nearby_community",
                text=(f"Nothing is clustering in {reference.taluka_name(taluka)} right now — no "
                      f"group of farmers there has reported the same problem often enough for "
                      f"PRAHARI to call it anything.\n\nThat is not the same as 'nothing is "
                      f"happening'. It means nobody has posted it. If you are seeing something, "
                      f"posting it is what turns one field into a signal."),
                text_mr=(f"{reference.taluka_name(taluka, 'mr')} मध्ये सध्या कोणताही समूह दिसत "
                         f"नाही — पुरेशा शेतकऱ्यांनी एकच समस्या नोंदवलेली नाही.\n\nयाचा अर्थ "
                         f"काहीच घडत नाही असा नाही — कोणी नोंदवलेले नाही. तुम्हाला काही दिसत "
                         f"असेल तर ते नोंदवा."),
                sources=[{"kind": "community_signal",
                          "detail": f"no open signal in {reference.taluka_name(taluka)}"}],
                actions=[{"do": "community_post", "label": "Post what you are seeing"}],
                data={"signals": [], "aggregate_only": True})

        if target:
            a = eng.assess(taluka, target, crop=plot.get("crop"), persist=False)
            c = a["counts"]
            name = a["problem_name"]
            if not a["grade"]:
                text = (f"Not enough to call it anything. In the last {a['window_days']} days "
                        f"{c['community_posts']} farmer post(s) in "
                        f"{a['taluka_name']} mention {name}, from {c['distinct_farmers']} "
                        f"different account(s) — PRAHARI needs "
                        f"{signals_mod.POST_FLOOR} posts from at least "
                        f"{signals_mod.AUTHOR_FLOOR} different farmers before it will use the "
                        f"word 'cluster'.\n\nSeparately, {c['diagnoses']} photograph(s) in this "
                        f"taluka were diagnosed as {name} in the same window.")
                text_mr = (f"{a['taluka_name']} मध्ये गेल्या {a['window_days']} दिवसांत "
                           f"{c['community_posts']} नोंदी आहेत — समूह म्हणण्यासाठी हे पुरेसे नाही.")
            else:
                text = (f"{a['label']} — {name} in {a['taluka_name']}.\n\n"
                        f"{c['distinct_farmers']} different farmers posted about it in the last "
                        f"{a['window_days']} days, across {c['distinct_villages']} village(s), "
                        f"and {c['same_problem_votes']} more marked 'I am seeing this too'. "
                        f"{c['diagnoses']} photograph(s) in the taluka were diagnosed as {name}, "
                        f"and there are {c['expert_confirmations']} expert confirmation(s).\n\n"
                        f"{a['means']}\n\n{signals_mod.NOT_AN_OUTBREAK}\n\n"
                        f"What it means for you: scout your own field this week. A signal is "
                        f"about a taluka; the spray decision is about your field, and it still "
                        f"needs a threshold count.")
                text_mr = (f"{a['label_mr']} — {a['problem_name_mr']}, {a['taluka_name']}.\n\n"
                           f"गेल्या {a['window_days']} दिवसांत {c['distinct_farmers']} "
                           f"शेतकऱ्यांनी ही समस्या नोंदवली आहे.\n\n{a['means_mr']}\n\n"
                           f"तुमच्यासाठी: या आठवड्यात स्वतःचे शेत तपासा. फवारणीचा निर्णय "
                           f"तुमच्या शेतातील मोजणीवरच घ्यावा लागेल.")
            return Answer(
                intent="nearby_community", text=text, text_mr=text_mr,
                sources=[{"kind": "community_signal",
                          "detail": f"{a['label']} · {a['taluka_name']} · {name}"},
                         {"kind": "method",
                          "detail": ("Aggregated counts of community posts, distinct posting "
                                     "accounts, villages, diagnoses and expert confirmations. "
                                     "No individual farmer, field or location is read or "
                                     "returned.")}],
                actions=[{"do": "community", "label": "Open the community"},
                         {"do": "scan", "label": "Scan your own field"}],
                data={"signal": {k: a[k] for k in ("grade", "label", "counts", "window_days",
                                                   "taluka_name", "problem_name")},
                      "aggregate_only": True})

        lines = [f"· {s['label']} — {s['problem_name']} ({s['community_posts_n']} posts from "
                 f"{s['distinct_authors']} farmers)" for s in open_here[:4]]
        return Answer(
            intent="nearby_community",
            text=(f"In {reference.taluka_name(taluka)} right now:\n\n" + "\n".join(lines)
                  + f"\n\n{signals_mod.NOT_AN_OUTBREAK}\n\nThese are counts. PRAHARI does not "
                    f"tell you which fields or which farmers."),
            text_mr=(f"{reference.taluka_name(taluka, 'mr')} मध्ये सध्या:\n\n"
                     + "\n".join(f"· {s['label_mr']} — {s['problem_name_mr']}"
                                  for s in open_here[:4])
                     + "\n\nही फक्त संख्या आहे. कोणते शेत किंवा कोणता शेतकरी हे प्रहरी सांगत नाही."),
            sources=[{"kind": "community_signal",
                      "detail": f"{len(open_here)} open signal(s) in "
                                f"{reference.taluka_name(taluka)}"}],
            actions=[{"do": "community", "label": "Open the community"}],
            data={"signals": open_here, "aggregate_only": True})

    # ── helpers ────────────────────────────────────────────────────────────
    def _latest_counted_pest(self, plot_id: str) -> str | None:
        row = self.db.one(
            "SELECT pest FROM threshold_checks WHERE plot_id = :p"
            " ORDER BY checked_at DESC, id DESC LIMIT 1", {"p": plot_id})
        return (row or {}).get("pest")

    def _refuse(self, intent: str) -> Answer:
        return Answer(
            intent=intent, text=REFUSAL["en"], text_mr=REFUSAL["mr"],
            grounded=False,
            sources=[],
            data={"scope": SCOPE["en"], "scope_mr": SCOPE["mr"]})


SUGGESTIONS = {
    "en": ["Should I spray?", "What is the risk this week?", "How is my field?",
           "What is the threshold for this pest?", "How do I control it without chemicals?",
           "When can I harvest?", "What should I look for when scouting?",
           "Are other farmers nearby seeing this?"],
    "mr": ["फवारणी करू का?", "या आठवड्यात धोका किती?", "माझे शेत कसे आहे?",
           "या किडीची मर्यादा किती?", "रासायनिकाशिवाय उपाय काय?",
           "काढणी कधी करू शकतो?", "तपासणी करताना काय पहावे?",
           "इतर शेतकऱ्यांना पण हेच दिसत आहे का?"],
}


# ── the context an optional language model is allowed to see ────────────────
_BOARD_FACT_KEYS = (
    "kind", "id", "name", "name_mr", "level", "fired", "detail",
    "etl", "etl_source", "unit", "damaging", "stage", "model_caveat",
    "no_model_note", "risk_unavailable",
)


def _board_fact(row: dict[str, Any]) -> dict[str, Any]:
    """One risk-board row, trimmed to what an answer could legitimately quote.

    The scouting prose and the full provenance blocks are dropped: they are
    long, they are already reachable through the scouting and threshold
    handlers, and every extra sentence in the bundle is another sentence a
    model can drift towards. What stays is the identification, the level, and
    the numbers — because `_numbers_agree` requires any number in the reply to
    appear here, so a fact omitted is a sentence the model may not write.
    """
    out = {k: row[k] for k in _BOARD_FACT_KEYS if k in row and row[k] is not None}
    prov = row.get("provenance") or {}
    if prov.get("name"):
        out["model"] = prov["name"]
        out["model_source"] = prov.get("source")
    return out


def field_facts(db: Database, rt, plot: dict[str, Any] | None,
                limit: int = 6) -> dict[str, Any]:
    """A compact, already-computed picture of THIS field.

    Assembled entirely from rows that exist. Nothing here is derived for the
    purpose of the assistant, and nothing is estimated to fill a gap — a field
    with no trap counts appears with no trap counts, which is what allows the
    model to be told, truthfully, that these facts are all there is.

    Kept small on purpose. A model handed everything answers from the largest
    number it can see; a model handed the field's current state answers about
    the field.
    """
    if not plot:
        return {"note": "The farmer has no field registered, so PRAHARI holds no field data."}

    out: dict[str, Any] = {
        "field": {
            "name": plot.get("name"), "crop": plot.get("crop"),
            "area_acre": plot.get("area_acre"), "taluka": plot.get("taluka"),
            "village": plot.get("village"), "sown_on": plot.get("sown_on"),
        },
    }
    stage = None
    if rt:
        # A stage needs a sowing date and a crop cycle. A field without one is
        # a real state, not an error, and the bundle simply carries no stage.
        with contextlib.suppress(Exception):
            stage = rt.risk.crop_stage(plot)
            out["crop_stage"] = stage

    snap = db.one("SELECT * FROM health_snapshots WHERE plot_id = :p "
                  "ORDER BY day DESC LIMIT 1", {"p": plot["id"]})
    if snap:
        out["crop_health"] = {
            "day": snap["day"], "score_out_of_100": round(snap["score"]),
            "penalties": {k: round(snap[k]) for k in ("disease", "pest", "weather", "nearby")
                          if snap.get(k) is not None},
            "meaning": ("A composite RISK indicator. It is not a yield estimate and not a "
                        "percentage of the crop affected."),
        }

    out["recent_diagnoses"] = db.rows(
        "SELECT top_problem, top_posterior, abstained, abstain_reason, created_at"
        "  FROM diagnoses WHERE plot_id = :p ORDER BY created_at DESC LIMIT :n",
        {"p": plot["id"], "n": limit})
    out["recent_trap_counts"] = db.rows(
        "SELECT t.pest, o.count, o.counted_on FROM trap_observations o"
        "  JOIN traps t ON t.id = o.trap_id WHERE t.plot_id = :p"
        "  ORDER BY o.counted_on DESC LIMIT :n",
        {"p": plot["id"], "n": limit})
    out["recent_threshold_checks"] = db.rows(
        "SELECT pest, count, etl_effective, band, chemical_authorised, checked_on"
        "  FROM threshold_checks WHERE plot_id = :p ORDER BY checked_on DESC LIMIT :n",
        {"p": plot["id"], "n": limit})
    out["recent_sprays"] = db.rows(
        "SELECT product, dose_text, applied_on FROM applications"
        "  WHERE plot_id = :p ORDER BY applied_on DESC LIMIT :n",
        {"p": plot["id"], "n": limit})
    out["open_followups"] = db.rows(
        "SELECT id, due_on, escalated FROM followups WHERE plot_id = :p"
        "  AND done_observation IS NULL AND outcome IS NULL ORDER BY due_on LIMIT :n",
        {"p": plot["id"], "n": limit})

    if rt and stage is not None:
        # `board` takes the crop stage as well. It was being called without it,
        # which raised TypeError on every single call — and the bare `except
        # Exception` here caught that and wrote the weather-unavailable note.
        # The board therefore never reached the model, not once, and the note
        # said the wrong reason. Catch ONLY the failure this line can honestly
        # attribute to weather; a programming error must surface as one.
        try:
            wx = rt.risk.weather_series(plot)
        except WeatherUnavailable as exc:
            # Weather is allowed to be unavailable and is never invented. The
            # model simply does not get a risk board, and cannot produce one.
            out["risk_board_note"] = (
                f"Weather is unavailable for this field right now ({exc.reason}), so PRAHARI "
                "has no risk board for it. Do not estimate one, and do not say conditions "
                "are unfavourable — that is not what an absent forecast means.")
        else:
            board, _fired = rt.risk.board(plot, wx, stage)
            out["risk_board"] = [_board_fact(b) for b in board]
            out["risk_board_weather"] = {
                "source": wx.get("source"),
                "observed_through": wx.get("observed_through"),
                "stale": bool(wx.get("stale")),
            }
    return out
