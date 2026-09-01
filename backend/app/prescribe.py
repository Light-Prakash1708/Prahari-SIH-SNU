"""
PRAHARI · the prescription
════════════════════════════════════════════════════════════════════════════
Four rules are ENFORCED here rather than printed as advice. Every one of them
exists because of a documented failure.

  1  LABEL CLAIM.  India registers a pesticide against a specific crop AND a
     specific pest. In October 2017, 21 farmers died in Yavatmal district. The
     Centre for Science and Environment's root-cause finding was that state
     agriculture university advisories "do not adhere to the pesticides that the
     Central Insecticides Board has registered" — off-label recommendation, from
     the official system. Nothing reaches a farmer here unless it is in the
     label-claim table for that exact crop and target.

  2  STATE BAN.  Section 27 of the Insecticides Act lets a state prohibit sale,
     distribution or use in the public interest. Maharashtra used it in
     September 2018 for a 60-day ban on five formulations. A recommendation must
     therefore be able to go stale overnight, so the restricted list is data,
     read at request time, never compiled in.

  3  RESISTANCE ROTATION.  IRAC and FRAC both say: never follow a mode-of-action
     group with itself, and cap each group at two applications per season. Pink
     bollworm broke Bt cotton in Maharashtra by exactly this route. The engine
     reads the spray log and blocks the repeat.

  4  PRE-HARVEST INTERVAL.  A logged application sets the earliest date the crop
     may be harvested. If the PHI outruns the days to harvest the product is
     removed, because using it makes the crop unsellable to any buyer who tests
     residue — and the export pack-houses do test.

And one thing no Indian app ships: THE DOSE IN THE FARMER'S OWN UNITS.
"1.8 ml/L" is not actionable. "27 ml in your 15-litre knapsack, 8 tanks for your
0.4 hectares, buy the 250 ml bottle" is arithmetic, and it is the difference
between a correct label and a correct spray.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

# Common knapsack sizes in Maharashtra. The farmer picks one; everything else
# is derived.
TANK_SIZES = [15, 16, 20]
BOTTLE_SIZES_ML = [50, 100, 250, 500, 1000]
BOTTLE_SIZES_G = [50, 100, 250, 500, 1000]

TOXICITY = {
    "red":    {"label": "Extremely toxic", "mr": "अत्यंत विषारी", "rank": 4,
               "ppe": "Full cover: rubber gloves, boots, apron, face shield and a cartridge respirator. Never spray alone."},
    "yellow": {"label": "Highly toxic", "mr": "अति विषारी", "rank": 3,
               "ppe": "Gloves, boots, full sleeves, goggles and a respirator. Do not spray against the wind."},
    "blue":   {"label": "Moderately toxic", "mr": "मध्यम विषारी", "rank": 2,
               "ppe": "Gloves, boots, full sleeves and a cloth mask. Wash with soap immediately after."},
    "green":  {"label": "Slightly toxic", "mr": "सौम्य विषारी", "rank": 1,
               "ppe": "Gloves and full sleeves. Wash hands and face before eating or smoking."},
}


def _bottle_for(amount: float, unit: str) -> dict[str, Any]:
    sizes = BOTTLE_SIZES_ML if unit.startswith("ml") else BOTTLE_SIZES_G
    for s in sizes:
        if amount <= s:
            return {"size": s, "unit": "ml" if unit.startswith("ml") else "g", "count": 1}
    n = int(amount // sizes[-1]) + (1 if amount % sizes[-1] else 0)
    return {"size": sizes[-1], "unit": "ml" if unit.startswith("ml") else "g", "count": n}


def dose_arithmetic(claim: dict[str, Any], area_acre: float, tank_litres: int) -> dict[str, Any]:
    """The whole point. Turn a label rate into tanks, millilitres and a bottle."""
    water_total = claim["water_l_per_acre"] * area_acre
    tanks = water_total / tank_litres
    per_tank = claim["dose"] * tank_litres
    total = claim["dose"] * water_total
    unit = claim["unit"].split("/")[0]              # 'ml' or 'g'
    bottle = _bottle_for(total, unit)
    return {
        "label_rate": f"{claim['dose']} {claim['unit']}",
        "tank_litres": tank_litres,
        "per_tank": round(per_tank, 1), "per_tank_unit": unit,
        "tanks_needed": round(tanks, 1), "tanks_whole": int(tanks) + (1 if tanks % 1 else 0),
        "water_litres": round(water_total),
        "total_product": round(total, 1), "total_unit": unit,
        "buy": bottle,
        "plain": (f"{round(per_tank,1)} {unit} in your {tank_litres} L knapsack. "
                  f"{int(tanks)+(1 if tanks%1 else 0)} tanks covers {area_acre} acre"
                  f"{'s' if area_acre != 1 else ''}. Total {round(total,1)} {unit} — "
                  f"buy {bottle['count']} × {bottle['size']} {bottle['unit']}."),
        "plain_mr": (f"{round(per_tank,1)} {unit} प्रति {tank_litres} लिटर पंप. "
                     f"{int(tanks)+(1 if tanks%1 else 0)} पंप = {area_acre} एकर. "
                     f"एकूण {round(total,1)} {unit}."),
    }


def phi_status(spray_log: list[dict[str, Any]], crop: str,
               today: dt.date | None = None) -> dict[str, Any]:
    """The harvest gate. Reads the log, returns the earliest safe harvest date."""
    today = today or dt.date.today()
    rel = [s for s in spray_log if s.get("crop") == crop and s.get("phi_days") is not None]
    if not rel:
        return {"clear": True, "days_left": 0, "until": None, "last": None,
                "msg": "No chemical applied to this crop. Residue-safe for immediate harvest.",
                "msg_mr": "या पिकावर रसायन वापरलेले नाही. काढणी सुरक्षित."}
    worst, worst_clear = None, None
    for s in rel:
        applied = dt.date.fromisoformat(s["applied_on"])
        clears = applied + dt.timedelta(days=int(s["phi_days"]))
        if worst_clear is None or clears > worst_clear:
            worst, worst_clear = s, clears
    days_left = (worst_clear - today).days
    if days_left <= 0:
        return {"clear": True, "days_left": 0, "until": worst_clear.isoformat(), "last": worst,
                "msg": (f"Pre-harvest interval satisfied — {worst['product']} applied "
                        f"{worst['applied_on']}, PHI {worst['phi_days']} days. "
                        f"This lot may be declared residue-cleared."),
                "msg_mr": "प्रतीक्षा कालावधी पूर्ण. काढणी सुरक्षित."}
    return {"clear": False, "days_left": days_left, "until": worst_clear.isoformat(), "last": worst,
            "msg": (f"Harvest blocked for {days_left} more day{'s' if days_left != 1 else ''}. "
                    f"{worst['product']} has a {worst['phi_days']}-day pre-harvest interval; "
                    f"earliest safe harvest is {worst_clear.isoformat()}."),
            "msg_mr": (f"आणखी {days_left} दिवस काढणी करू नका. {worst['product']} चा प्रतीक्षा कालावधी "
                       f"{worst['phi_days']} दिवस. सुरक्षित तारीख {worst_clear.isoformat()}.")}


def screen(claims: list[dict[str, Any]], restricted: list[dict[str, Any]],
           spray_log: list[dict[str, Any]], crop: str, target: str,
           area_acre: float = 1.0, tank_litres: int = 15,
           days_to_harvest: int | None = None, flowering: bool = False,
           strict: bool = True) -> dict[str, Any]:
    """Returns every label-claimed option for this crop and target, each either
    allowed or blocked with the reason. Blocked options are RETURNED, not hidden —
    a farmer who is told "not this one, and here is why" learns something; a
    farmer shown a shorter list learns nothing."""
    banned = {r["product"]: r for r in restricted}
    log = [s for s in spray_log if s.get("crop") == crop]
    log.sort(key=lambda s: s["applied_on"])
    last_moa = log[-1]["moa_group"] if log else None
    moa_counts: dict[str, int] = {}
    for s in log:
        if s.get("moa_group"):
            moa_counts[s["moa_group"]] = moa_counts.get(s["moa_group"], 0) + 1

    rows = []
    for c in claims:
        if c["crop"] != crop or c["target"] != target:
            continue
        blocks, warns = [], []

        if c["product"] in banned:
            blocks.append({"rule": "state-ban",
                           "msg": (f"Restricted in Maharashtra. {banned[c['product']]['reason']} "
                                   f"This product cannot be recommended here.")})
        if strict and c.get("status") != "cited":
            warns.append({"rule": "verification",
                          "msg": ("This label claim is marked DRAFT and has not yet been verified "
                                  "against the CIB&RC 'Major Uses of Pesticides' list. Prototype only.")})
        if last_moa and c["moa"] == last_moa:
            blocks.append({"rule": "resistance",
                           "msg": (f"Same mode-of-action group ({c['moa']}) as your last application. "
                                   f"Rotating is the difference between this product working next "
                                   f"season and not.")})
        if moa_counts.get(c["moa"], 0) >= 2:
            blocks.append({"rule": "resistance",
                           "msg": f"Group {c['moa']} has already been used twice this season — the IRAC/FRAC cap."})
        if days_to_harvest is not None and c["phi"] > days_to_harvest:
            blocks.append({"rule": "phi",
                           "msg": (f"Pre-harvest interval is {c['phi']} days but harvest is in "
                                   f"{days_to_harvest}. Using this makes the crop unsellable to any "
                                   f"buyer who tests residue.")})
        if c["bee"] == "high" and flowering:
            warns.append({"rule": "pollinator",
                          "msg": "Highly toxic to bees and the crop is flowering. Spray only after 6 pm."})

        tox = TOXICITY[c["toxicity"]]
        if tox["rank"] >= 3:
            warns.append({"rule": "toxicity",
                          "msg": f"{tox['label']} ({c['toxicity']} triangle). {tox['ppe']}"})

        rows.append({
            "product": c["product"], "moa": c["moa"], "target": target, "crop": crop,
            "toxicity": c["toxicity"], "toxicity_label": tox["label"],
            "toxicity_label_mr": tox["mr"], "ppe": tox["ppe"],
            "phi_days": c["phi"], "reentry_hours": c["reentry_h"],
            "bee": c["bee"], "cost_per_acre": c["cost_acre"],
            "status": c.get("status", "draft"), "note": c.get("note"),
            "dose": dose_arithmetic(c, area_acre, tank_litres),
            "blocked": bool(blocks), "blocks": blocks, "warnings": warns,
            # Prefer allowed, then lower toxicity, then shorter PHI, then cheaper.
            "_rank": (1 if blocks else 0, tox["rank"], c["phi"], c["cost_acre"]),
        })

    rows.sort(key=lambda r: r["_rank"])
    for r in rows:
        r.pop("_rank", None)
    allowed = [r for r in rows if not r["blocked"]]
    return {
        "options": rows,
        "allowed_count": len(allowed),
        "blocked_count": len(rows) - len(allowed),
        "recommended": allowed[0] if allowed else None,
        "last_moa_used": last_moa,
        "moa_history": moa_counts,
        "verification_banner": ("Label claims in this build are marked DRAFT. Every row must be "
                                "verified against the CIB&RC 'Major Uses of Pesticides' list before "
                                "any real advisory is issued. This is a prototype."),
        "no_option_msg": (
            "Every label-claimed option for this crop and pest is blocked — by a state restriction, "
            "by the resistance rotation, or by the pre-harvest interval. That is a real answer, not a "
            "gap: refer this case to the block extension officer or the nearest KVK." if not allowed else None),
    }


def ladder(ipm: dict[str, Any], target: str, chemical_authorised: bool,
           prescription: dict[str, Any] | None,
           scout: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Cheapest rung first, always. The chemical rung is withheld until the
    threshold gate authorises it — and when it is withheld, the app says so
    rather than leaving an empty section that looks like an oversight.

    `scout` adds the rung that was missing: MONITORING. It was absent because
    the IPM tables describe interventions and monitoring is not one, which left
    the ladder unable to express the thing PRAHARI recommends most often — keep
    walking the field. Its content is the problem's own published scouting text
    and the decision's own re-check interval; nothing here is composed prose.

    Rungs with no entries in the knowledge base are omitted rather than filled.
    A mechanical rung invented for a pest whose tables have none would be the
    app making up agronomy, which is the one thing it must never do.
    """
    lad = ipm.get(target, {"cultural": [], "biological": []})
    steps = []
    if scout and scout.get("items"):
        steps.append({
            "rung": 0, "key": "monitor", "cost": 0,
            "title": "Keep looking — this is the rung most seasons stay on",
            "title_mr": "पाहणी चालू ठेवा — बहुतेक हंगाम इथेच थांबतात",
            "items": list(scout["items"]),
            "recheck_on": scout.get("recheck_on"),
        })
    steps += [
        {"rung": 1, "key": "cultural", "cost": 0,
         "title": "Do these first — they cost nothing",
         "title_mr": "आधी हे करा — खर्च शून्य",
         "items": [{"text": t} for t in lad.get("cultural", [])]},
        {"rung": 2, "key": "biological", "cost": None,
         "title": "Biological and botanical",
         "title_mr": "जैविक व वनस्पतिजन्य",
         "items": [{"text": f"{b['n']} — {b['d']}", "cost": b["cost"]}
                   for b in lad.get("biological", [])]},
    ]
    if chemical_authorised:
        # The threshold decides whether rung 3 opens. Whether we happen to have
        # already screened a product is a separate question — an earlier version
        # conflated the two and printed "chemical NOT justified" directly beneath
        # a verdict saying "treat now", on the same screen.
        items = ([{"text": f"{prescription['product']} ({prescription['moa']})",
                   "cost": prescription["cost_per_acre"]}] if prescription else
                 [{"text": ("The threshold is crossed, so a chemical application is justified. "
                            "The screened list below shows which products are legal for this crop "
                            "and pest, and which are blocked.")}])
        steps.append({"rung": 3, "key": "chemical",
                      "cost": prescription["cost_per_acre"] if prescription else None,
                      "title": "Chemical — justified now",
                      "title_mr": "रासायनिक — आता योग्य",
                      "items": items})
    else:
        steps.append({"rung": 3, "key": "chemical", "cost": None,
                      "title": "Chemical — NOT justified yet",
                      "title_mr": "रासायनिक — अजून गरज नाही",
                      "items": [{"text": ("Nothing is offered here because the economic threshold has "
                                          "not been crossed. This is not an oversight.")}],
                      "withheld": True})
    return steps
