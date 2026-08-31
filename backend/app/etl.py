"""
PRAHARI · the economic threshold gate
════════════════════════════════════════════════════════════════════════════
This is the module the whole product is built around, and it is the only path
by which a chemical recommendation can be reached.

Diagnosis tells you WHAT. Only a threshold tells you WHETHER IT IS WORTH
DOING ANYTHING. Below the Economic Threshold Level a spray costs more than the
damage it prevents AND removes the natural enemies that were holding the
population down — so "do not spray" is a real recommendation with a real saving,
not an absence of one.

Why this matters more than a better classifier: an independent evaluation of
India's National Pest Surveillance System across 30 districts of Odisha
(n = 1,422, Indian Journal of Extension Education) found 79% of farmers were
RECEIVING advisories but only 49.11% acted on them — and compliance fell to 10%
for yellow stem borer at high severity, because the recommendation cost more
than the farmer had. Compliance falls as the problem gets worse. Detection was
never the bottleneck.

The threshold is also stage-dependent. The same count means different things at
different crop stages, and a threshold quoted without a stage is agronomically
meaningless — so `stage_factor` scales it.
"""
from __future__ import annotations

from typing import Any

# What one application actually costs an acre in Maharashtra: product plus
# labour plus the sprayer. Used to put a rupee number on "do not spray".
SPRAY_COST_PER_ACRE = 1450.0

BANDS = {
    "monitor": {
        "title": "Below threshold — do not spray",
        "title_mr": "मर्यादेखाली — फवारणी करू नका",
        "action": "monitor",
        "why": ("At {pct}% of the economic threshold a spray costs more than the damage it prevents, "
                "and it kills the natural enemies holding the population down. Re-count in five days."),
        "why_mr": ("आर्थिक नुकसान मर्यादेच्या {pct}% वर. आत्ता फवारणी केल्यास खर्च नुकसानापेक्षा जास्त "
                   "होईल आणि मित्रकीटक मरतील. पाच दिवसांनी पुन्हा मोजा."),
        "chemical": False,
    },
    "act-nonchemical": {
        "title": "Approaching threshold — act, but not with chemistry",
        "title_mr": "मर्यादेजवळ — उपाय करा, पण रासायनिक नको",
        "action": "cultural+bio",
        "why": ("At {pct}% of threshold. Cultural and biological control still work at this density "
                "and will hold the population below threshold at a fraction of the cost."),
        "why_mr": ("मर्यादेच्या {pct}% वर. या घनतेवर मशागत व जैविक उपाय पुरेसे आहेत आणि खर्च खूप कमी येतो."),
        "chemical": False,
    },
    "chemical": {
        "title": "Threshold crossed — a chemical application is justified",
        "title_mr": "मर्यादा ओलांडली — रासायनिक फवारणी योग्य",
        "action": "chemical",
        "why": ("At {pct}% of threshold the expected damage now exceeds the cost of control. "
                "Spray once, spray correctly, and re-count in five days."),
        "why_mr": ("मर्यादेच्या {pct}% वर. अपेक्षित नुकसान आता नियंत्रण खर्चापेक्षा जास्त आहे. "
                   "एकदाच योग्य फवारणी करा आणि पाच दिवसांनी पुन्हा मोजा."),
        "chemical": True,
    },
    "urgent": {
        "title": "Well past threshold — treat now",
        "title_mr": "मर्यादेच्या खूप पुढे — त्वरित उपाय करा",
        "action": "chemical",
        "why": ("At {pct}% of threshold, damage is accumulating daily. Treat now, and review why "
                "monitoring missed the build-up."),
        "why_mr": ("मर्यादेच्या {pct}% वर. रोज नुकसान वाढत आहे. आत्ता उपाय करा."),
        "chemical": True,
    },
}


def decide(row: dict[str, Any], count: float, stage: str | None,
           crop_value: dict[str, float] | None = None,
           area_acre: float = 1.0) -> dict[str, Any]:
    """row is one entry from thresholds.json. Returns the decision plus the
    arithmetic behind it, because a farmer who is told not to spray deserves to
    see what that decision saved."""
    base = float(row["etl"])
    factor = float((row.get("stage_factor") or {}).get(stage or "", 1.0))
    effective = base * factor
    ratio = count / effective if effective else 0.0

    band = ("monitor" if ratio < 0.5 else
            "act-nonchemical" if ratio < 1.0 else
            "chemical" if ratio < 1.6 else "urgent")
    b = BANDS[band]
    pct = round(ratio * 100)

    # What the decision is worth, in rupees. Damage avoided uses a linear
    # approximation of yield loss against threshold — deliberately simple and
    # deliberately labelled as an approximation, because a precise-looking
    # number here would be invented.
    spray_cost = SPRAY_COST_PER_ACRE * area_acre
    econ = None
    if crop_value:
        yield_kg = crop_value.get("yield_kg_per_acre", 0) * area_acre
        price = crop_value.get("price_per_kg", 0)
        gross = yield_kg * price
        loss_fraction = max(0.0, min(0.35, (ratio - 0.4) * 0.14))
        damage_avoided = gross * loss_fraction
        econ = {
            "crop_gross_value": round(gross),
            "spray_cost": round(spray_cost),
            "estimated_damage_avoided": round(damage_avoided),
            "net_of_spraying": round(damage_avoided - spray_cost),
            "worth_it": damage_avoided > spray_cost,
            "note": ("Damage avoided is a linear approximation against the threshold, not a "
                     "calibrated yield-loss model. It is shown to make the trade-off visible, "
                     "not to be quoted as a forecast."),
        }

    return {
        "pest": row["pest"], "crop": row["crop"],
        "count": count, "unit": row["unit"],
        "etl_base": base, "stage": stage, "stage_factor": factor,
        "etl_effective": round(effective, 2),
        "ratio": round(ratio, 3), "percent_of_threshold": pct,
        "band": band, "action": b["action"],
        "title": b["title"], "title_mr": b["title_mr"],
        "why": b["why"].format(pct=pct), "why_mr": b["why_mr"].format(pct=pct),
        "chemical_authorised": b["chemical"],
        "persist_nights": row.get("persist_nights", 1),
        "alt_threshold": row.get("alt"),
        "source": row.get("source"), "source_status": row.get("status", "draft"),
        "economics": econ,
        "saving_if_not_sprayed": None if b["chemical"] else round(spray_cost),
    }


def ledger(checks: list) -> dict[str, Any]:
    """The "sprays avoided" number, and the honest statement of what it is
    compared against.

    The counterfactual is the prophylactic calendar most growers actually run —
    a cover spray every seven days regardless of pressure. Each threshold check
    that returned below-threshold is one application the calendar would have made
    and this system did not. This is deliberately the WEAKEST available claim: a
    stronger one would need a paired untreated plot over a season, and we have
    not run one."""
    if not checks:
        return {"calendar": 0, "actual": 0, "avoided": 0, "saved": 0,
                "baseline": "7-day prophylactic calendar", "season_days": 0}
    # `days_ago` is NULL when a timestamp will not parse. Treat that as zero rather
    # than propagating it — a ledger that cannot be drawn is worse than one that
    # under-counts, and the underlying data bug shows up as a short season.
    days = max(abs(c.get("days_ago") or 0) for c in checks) or 42
    calendar = max(1, int(days // 7))
    actual = sum(1 for c in checks if c.get("acted"))
    avoided = max(0, calendar - actual)
    return {
        "calendar": calendar, "actual": actual, "avoided": avoided,
        "saved": round(avoided * SPRAY_COST_PER_ACRE),
        "litres_not_applied": round(avoided * 0.55, 1),
        "season_days": days,
        "baseline": ("A 7-day prophylactic cover spray through the season, whatever the trap says — "
                     "what most growers actually run."),
        "caveat": ("This compares against a routine calendar, not a controlled trial against an "
                   "untreated plot. A real reduction figure needs a season of paired plots, and that "
                   "is the first thing a deployment should fund rather than claim."),
    }
