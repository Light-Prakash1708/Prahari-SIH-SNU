"""
PRAHARI · the advisory that actually reaches a farmer
════════════════════════════════════════════════════════════════════════════
The screen is not the product. Extension in India reaches about 6.8% of
farmers; the ones who most need a blight warning are the least likely to be
holding a smartphone when it fires. So every advisory is generated in three
forms at once:

  app   the full card, with the reasoning
  sms   140 GSM-7 characters, one segment, no splitting — and Marathi in
        Devanagari is UCS-2, which is 70 characters, so Marathi SMS is
        transliterated to Latin script rather than truncated. This is a real
        constraint that most Indian agri apps get wrong.
  ivr   a script for the voice line, in short spoken sentences with the number
        first, because a farmer listening to a call cannot scroll back.

The rule that governs all three: SAY THE ACTION FIRST. A farmer who hangs up
after four seconds should already know whether to spray.
"""
from __future__ import annotations

from typing import Any

# GSM-7 single segment. Concatenated SMS drops to 153 chars/segment and costs
# per segment, so 140 is the number that matters.
GSM_SINGLE = 140
UCS2_SINGLE = 70

_TRANSLIT = {
    "उशिरा येणारा करपा": "ushira yenara karpa", "लवकर येणारा करपा": "lavkar yenara karpa",
    "केवडा": "kevda", "भुरी": "bhuri", "जांभळा करपा": "jambhla karpa",
    "नागअळी (टुटा)": "Tuta", "घाटे अळी": "ghate ali", "फुलकिडे": "phulkide",
    "पांढरी माशी": "pandhri mashi", "लष्करी अळी": "lashkari ali",
    "गुलाबी बोंडअळी": "gulabi bondali", "पानावरील करपा": "panavaril karpa",
    "नत्राची कमतरता": "natrachi kamtarta", "रोग आढळला नाही": "rog nahi",
    "खोडमाशी / गर्डल बीटल": "girdle beetle",
}

L10N = {
    "mr": {"alert": "Suchana", "spray": "Favarni kara", "dont": "Favarni NAKO",
           "wait": "divas thamba", "call": "Salla 1800-180-1551",
           "risk_high": "dhoka JAST", "risk_low": "dhoka kami"},
    "hi": {"alert": "Suchna", "spray": "Chidkav karein", "dont": "Chidkav NA karein",
           "wait": "din rukein", "call": "Salah 1800-180-1551",
           "risk_high": "khatra ADHIK", "risk_low": "khatra kam"},
    "en": {"alert": "Alert", "spray": "SPRAY", "dont": "DO NOT SPRAY",
           "wait": "days", "call": "Advice 1800-180-1551",
           "risk_high": "risk HIGH", "risk_low": "risk low"},
}


def _latin(name_mr: str, name_en: str) -> str:
    return _TRANSLIT.get(name_mr, name_en)


def sms(lang: str, problem_name_en: str, problem_name_mr: str,
        act: bool, product: str | None, dose_line: str | None,
        phi_days: int, village: str = "") -> dict[str, Any]:
    t = L10N.get(lang, L10N["en"])
    name = _latin(problem_name_mr, problem_name_en) if lang != "en" else problem_name_en
    head = f"PRAHARI {t['alert']}: {name}"
    if act and product:
        # Product name first, dose second, waiting period third. Nothing else
        # fits, and nothing else changes what the farmer does in the next hour.
        body = f" - {t['spray']}: {product.split()[0]} {dose_line or ''}. PHI {phi_days}d."
    else:
        body = f" - {t['dont']}. {t['risk_low']}."
    text = (head + body + f" {t['call']}").strip()
    if len(text) > GSM_SINGLE:
        text = text[:GSM_SINGLE - 1].rstrip() + "."
    non_ascii = any(ord(c) > 127 for c in text)
    limit = UCS2_SINGLE if non_ascii else GSM_SINGLE
    return {
        "text": text, "chars": len(text), "encoding": "UCS-2" if non_ascii else "GSM-7",
        "limit": limit, "segments": max(1, -(-len(text) // limit)),
        "fits_one_segment": len(text) <= limit,
        "note": ("Marathi in Devanagari forces UCS-2, which halves the segment to 70 characters — "
                 "so the Marathi SMS is transliterated to Latin script. Farmers read it fine; "
                 "a truncated Devanagari message they do not."),
    }


def ivr(lang: str, problem_name_mr: str, problem_name_en: str, act: bool,
        product: str | None, dose_line: str | None, phi_days: int,
        why_short: str) -> dict[str, Any]:
    """A spoken script. Action in the first sentence, always."""
    name = problem_name_mr if lang == "mr" else problem_name_en
    if lang == "mr":
        lines = ([f"नमस्कार. तुमच्या शेतात {name} चा धोका आहे."] +
                 ([f"आज फवारणी करा. {product}, {dose_line}.",
                   f"फवारणीनंतर {phi_days} दिवस काढणी करू नका."] if act else
                  ["आज फवारणी करू नका. अजून गरज नाही.",
                   "पाच दिवसांनी पुन्हा मोजा."]) +
                 [why_short, "अधिक माहितीसाठी एक दाबा. कृषी सहाय्यकाशी बोलण्यासाठी दोन दाबा."])
    else:
        lines = ([f"Namaskar. Your field is at risk of {name}."] +
                 ([f"Spray today. {product}, {dose_line}.",
                   f"Do not harvest for {phi_days} days after spraying."] if act else
                  ["Do not spray today. It is not needed yet.",
                   "Count again in five days."]) +
                 [why_short, "Press 1 to hear this again. Press 2 to speak to the Krishi Sahayak."])
    return {"lines": lines, "seconds": round(sum(len(line) for line in lines) / 13.5),
            "note": ("Read at roughly 13.5 characters per second. Anything past 45 seconds is "
                     "hung up on — that is the real length limit, not a character count.")}


def build(lang: str, problem: dict[str, Any], decision: dict[str, Any],
          prescription: dict[str, Any] | None, model_reason: str) -> dict[str, Any]:
    act = bool(decision and decision.get("chemical_authorised"))
    product = prescription["product"] if prescription else None
    dose_line = prescription["dose"]["per_tank"] if prescription else None
    dose_txt = (f"{dose_line} {prescription['dose']['per_tank_unit']}/"
                f"{prescription['dose']['tank_litres']}L") if prescription else None
    phi = prescription["phi_days"] if prescription else 0
    short = (model_reason[:90] + "…") if len(model_reason) > 90 else model_reason
    return {
        "lang": lang,
        "sms": sms(lang, problem["name"], problem.get("mr", problem["name"]),
                   act, product, dose_txt, phi),
        "ivr": ivr(lang, problem.get("mr", problem["name"]), problem["name"],
                   act, product, dose_txt, phi, short),
        "app_headline": (f"{problem['name']} — spray justified" if act
                         else f"{problem['name']} — do not spray yet"),
    }
