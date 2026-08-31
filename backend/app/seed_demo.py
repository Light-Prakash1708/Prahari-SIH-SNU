"""
PRAHARI · demo seed
════════════════════════════════════════════════════════════════════════════
Builds a demonstration district: farmers with real accounts, fields with real
coordinates, an officer, an expert and an admin — then a plausible surveillance
history written THROUGH THE REAL ENGINES rather than typed into fixtures.

Runs only when DEMO_MODE=true and AUTO_SEED_DEMO=true. config.py refuses both
in production, so a deployed instance cannot seed itself.

Every credential below is a demo credential and is printed to the log on
startup. Nothing here is a real person or a real farm.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import logging
import random
import uuid
from typing import Any

from . import accounts, reference
from .clock import now_iso
from .clock import today as _today
from .db import Database
from .schemas import RegisterIn

log = logging.getLogger("prahari.seed")

DEMO_PASSWORD = "prahari-demo-2026"

FARMERS = [
    {"name": "Rajesh Pawar", "mr": "राजेश पवार", "phone": "9000000001",
     "taluka": "pimpalgaon", "village": "Pimpalgaon Baswant",
     "plots": [{"name": "Tomato block 1", "crop": "tomato", "acre": 1.6, "sown": 62,
                "lat": 20.1712, "lng": 73.9855}]},
    {"name": "Sunita Deshmukh", "mr": "सुनीता देशमुख", "phone": "9000000002",
     "taluka": "niphad", "village": "Niphad",
     "plots": [{"name": "Grape plot A", "crop": "grape", "acre": 2.4, "sown": 110,
                "lat": 20.0821, "lng": 74.1109},
               {"name": "Onion west", "crop": "onion", "acre": 1.1, "sown": 48,
                "lat": 20.0855, "lng": 74.1180}]},
    {"name": "Ganesh Wagh", "mr": "गणेश वाघ", "phone": "9000000003",
     "taluka": "dindori", "village": "Dindori",
     "plots": [{"name": "Soybean north", "crop": "soybean", "acre": 3.2, "sown": 55,
                "lat": 20.2015, "lng": 73.8340}]},
    {"name": "Kavita Jadhav", "mr": "कविता जाधव", "phone": "9000000004",
     "taluka": "chandvad", "village": "Chandwad",
     "plots": [{"name": "Cotton east", "crop": "cotton", "acre": 4.0, "sown": 70,
                "lat": 20.3300, "lng": 74.2450}]},
    {"name": "Anil Shinde", "mr": "अनिल शिंदे", "phone": "9000000005",
     "taluka": "pimpalgaon", "village": "Ozar",
     "plots": [{"name": "Tomato block 2", "crop": "tomato", "acre": 2.0, "sown": 58,
                "lat": 20.1540, "lng": 73.9310}]},
    # Three more tomato growers around Pimpalgaon and one in Niphad. A cluster
    # needs INDEPENDENT reporters — with two accounts in a taluka the signal
    # engine can never reach its floor, and a demo that cannot reach its own
    # threshold teaches the wrong lesson about the threshold.
    {"name": "Manda Bhoir", "mr": "मंदा भोईर", "phone": "9000000006",
     "taluka": "pimpalgaon", "village": "Karanjgaon",
     "plots": [{"name": "Tomato patch", "crop": "tomato", "acre": 1.2, "sown": 60,
                "lat": 20.1901, "lng": 74.0102}]},
    {"name": "Sopan Gaikwad", "mr": "सोपान गायकवाड", "phone": "9000000007",
     "taluka": "pimpalgaon", "village": "Pimpalgaon Baswant",
     "plots": [{"name": "Tomato low block", "crop": "tomato", "acre": 0.9, "sown": 66,
                "lat": 20.1620, "lng": 73.9740}]},
    {"name": "Lata Borse", "mr": "लता बोरसे", "phone": "9000000008",
     "taluka": "niphad", "village": "Lasalgaon",
     "plots": [{"name": "Onion east", "crop": "onion", "acre": 2.2, "sown": 52,
                "lat": 20.1430, "lng": 74.2380}]},
    {"name": "Dattatray More", "mr": "दत्तात्रय मोरे", "phone": "9000000009",
     "taluka": "dindori", "village": "Vani",
     "plots": [{"name": "Maize block", "crop": "maize", "acre": 2.8, "sown": 44,
                "lat": 20.2740, "lng": 73.8890}]},
]


def seed(rt) -> dict[str, Any]:
    db: Database = rt.db
    if db.scalar("SELECT COUNT(*) FROM users"):
        return {"skipped": "database already has users"}
    day = _today()
    rng = random.Random(20260827)
    created = {"farmers": [], "plots": [], "officer": None, "expert": None, "admin": None}

    accounts.register(db, RegisterIn(
        full_name="District Administrator", password=DEMO_PASSWORD, role="admin",
        email="admin@prahari.demo", lang="en", taluka="niphad"), allow_privileged=True)
    created["admin"] = "admin@prahari.demo"

    officer = accounts.register(db, RegisterIn(
        full_name="Krishi Sahayak — Nashik", password=DEMO_PASSWORD, role="officer",
        email="officer@prahari.demo", lang="mr", taluka="niphad"), allow_privileged=True)
    created["officer"] = "officer@prahari.demo"
    for t in reference.TALUKA_IDS:
        accounts.grant_scope(db, officer["profile"]["id"], t)

    accounts.register(db, RegisterIn(
        full_name="Dr. A. Kulkarni", password=DEMO_PASSWORD, role="expert",
        email="expert@prahari.demo", lang="en", taluka="niphad",
        institution="KVK Nashik", specialism="Plant pathology"), allow_privileged=True)
    created["expert"] = "expert@prahari.demo"

    from .routers.plots import _polygon_area_acres  # noqa: F401  (shape reference)

    for f in FARMERS:
        reg = accounts.register(db, RegisterIn(
            full_name=f["name"], full_name_mr=f["mr"], password=DEMO_PASSWORD,
            role="farmer", phone=f["phone"], lang="mr", taluka=f["taluka"],
            village=f["village"]))
        created["farmers"].append(f["phone"])
        farmer_id = reg["profile"]["id"]
        for p in f["plots"]:
            pid = "P-" + uuid.uuid4().hex[:10].upper()
            sown = (day - dt.timedelta(days=p["sown"])).isoformat()
            stamp = now_iso()
            db.execute(
                "INSERT INTO plots (id, farmer_id, name, crop, variety, area_acre, area_source,"
                " sown_on, lat, lng, location_source, taluka, village, soil, irrigation,"
                " tank_litres, archived, created_at, updated_at)"
                " VALUES (:id,:f,:n,:crop,NULL,:a,'declared',:sown,:lat,:lng,'gps',:tk,:vil,"
                " 'medium black','drip',15,0,:now,:now)",
                {"id": pid, "f": farmer_id, "n": p["name"], "crop": p["crop"], "a": p["acre"],
                 "sown": sown, "lat": p["lat"], "lng": p["lng"], "tk": f["taluka"],
                 "vil": f["village"], "now": stamp})
            db.execute(
                "INSERT INTO crop_cycles (id, plot_id, crop, sown_on, created_at)"
                " VALUES (:id,:p,:crop,:sown,:now)",
                {"id": "C-" + uuid.uuid4().hex[:10].upper(), "p": pid, "crop": p["crop"],
                 "sown": sown, "now": stamp})
            db.execute(
                "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, created_at)"
                " VALUES (:p,:at,'field','info',:t,:d,:now)",
                {"p": pid, "at": sown[:10], "t": f"Field registered — {p['crop']}",
                 "d": f"{p['acre']} acres in {reference.taluka_name(f['taluka'])}.",
                 "now": stamp})
            created["plots"].append(pid)

    _surveillance_history(db, rt, rng, day)
    _community_history(db, rt, day)

    log.warning(
        "DEMO DATA SEEDED — every account below uses the password %r. "
        "Farmers: %s · Officer: %s · Expert: %s · Admin: %s",
        DEMO_PASSWORD, ", ".join(created["farmers"]), created["officer"],
        created["expert"], created["admin"])
    return created


def _surveillance_history(db: Database, rt, rng, day: dt.date) -> None:
    """A late-blight cluster building over three weeks across neighbouring
    talukas, written as observation + diagnosis rows so the officer console and
    the Gi* statistic have something real to compute over.

    These rows carry `source = 'app'` and abstained = 0 with an explicit
    `engine = 'seed'` marker on the diagnosis, so nothing in the audit views can
    mistake them for model output.
    """
    spread = [("pimpalgaon", 21), ("niphad", 16), ("dindori", 11), ("chandvad", 6)]
    plots = db.rows("SELECT * FROM plots ORDER BY taluka")
    by_taluka: dict[str, list[dict[str, Any]]] = {}
    for p in plots:
        by_taluka.setdefault(p["taluka"], []).append(p)

    n = 0
    for taluka, first_offset in spread:
        pool = by_taluka.get(taluka) or []
        if not pool:
            continue
        for k in range(rng.randint(3, 6)):
            plot = rng.choice(pool)
            problems = [q for q in reference.problems_for_crop(plot["crop"])
                        if q not in ("healthy", "nitrogen_deficiency")]
            if not problems:
                # Cotton, pigeonpea and sugarcane carry no image reference set —
                # the camera abstains on them by design, so there is nothing to seed.
                continue
            problem = "late_blight" if "late_blight" in problems else problems[0]
            offset = first_offset - rng.randint(0, first_offset)
            at = (day - dt.timedelta(days=offset))
            stamp = at.isoformat() + "T08:00:00Z"
            oid = "O-" + uuid.uuid4().hex[:10].upper()
            db.execute(
                "INSERT INTO observations (id, plot_id, farmer_id, kind, taluka, crop, crop_stage,"
                " observed_at, source, status, created_at)"
                " VALUES (:id,:p,:f,'leaf',:tk,:crop,:cs,:at,'app',:st,:now)",
                {"id": oid, "p": plot["id"], "f": plot["farmer_id"], "tk": taluka,
                 "crop": plot["crop"],
                 "cs": reference.crop_stage(plot["crop"], plot["sown_on"], at).get("stage"),
                 "at": stamp, "st": "confirmed" if k < 2 else "open", "now": now_iso()})
            did = "D-" + uuid.uuid4().hex[:10].upper()
            post = round(rng.uniform(0.52, 0.86), 3)
            db.execute(
                "INSERT INTO diagnoses (id, observation_id, plot_id, crop, engine, model_version,"
                " top_problem, top_posterior, margin, abstained, explain, created_at)"
                " VALUES (:id,:o,:p,:crop,'seed','demo-history',:prob,:post,:m,0,:ex,:now)",
                {"id": did, "o": oid, "p": plot["id"], "crop": plot["crop"], "prob": problem,
                 "post": post, "m": round(post - 0.3, 3),
                 "ex": ("Seeded demonstration history. engine='seed' marks this row as fixture "
                        "data, not model output — the audit views separate it."),
                 "now": now_iso()})
            if k < 2:
                db.execute(
                    "UPDATE diagnoses SET confirmed = :prob, confirmed_by = 'Dr. A. Kulkarni',"
                    " confirmed_at = :at WHERE id = :id",
                    {"prob": problem, "at": now_iso(), "id": did})
                rt.diagnosis.bump_prior(taluka, plot["crop"], problem)
            db.execute(
                "INSERT INTO field_events (plot_id, at, kind, severity, title, detail, ref, created_at)"
                " VALUES (:p,:at,'scan','rising',:t,:d,:ref,:now)",
                {"p": plot["id"], "at": at.isoformat(),
                 "t": f"Leaf scanned — {reference.problem_name(problem)}",
                 "d": f"{round(post*100)}% posterior.", "ref": oid, "now": now_iso()})
            n += 1
    log.info("seeded surveillance history", extra={"observations": n})


def _community_history(db: Database, rt, day: dt.date) -> None:
    """A community that is already mid-conversation on the day of the demo.

    Written through the REAL service — CommunityService.create_post, .comment,
    .react, .expert_respond — so the seeded feed obeys every rule the live one
    does: the same privacy projection, the same rate limits, the same
    verification ladder. A fixture written straight into the tables would be
    the one place in the system where a post could carry a plot id.
    """
    from .community import CommunityService
    from .signals import SignalEngine

    svc = CommunityService(db)

    def who(phone: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
        user = db.one("SELECT * FROM users WHERE phone = :p", {"p": phone})
        farmer = db.one("SELECT * FROM farmers WHERE user_id = :u", {"u": user["id"]})
        plot = db.one("SELECT * FROM plots WHERE farmer_id = :f ORDER BY created_at",
                      {"f": farmer["id"]})
        return dict(user), dict(farmer), dict(plot) if plot else None

    # ── the late-blight thread: three independent tomato growers ───────────
    script = [
        ("9000000001", "disease", "late_blight", ["spots", "spreading_fast"], 5,
         "Two days back I saw grey wet patches on the lower leaves of the tomato. After "
         "yesterday's rain they have grown and there is white fuzz underneath in the morning. "
         "Is this the करपा?"),
        ("9000000005", "disease", "late_blight", ["spots", "spreading_fast", "fruit_damage"], 3,
         "Same thing in my block at Ozar. Started on two rows near the water channel, now it is "
         "on maybe twenty plants. Some fruit has a hard brown patch also."),
        ("9000000007", "disease", "late_blight", ["spots"], 1,
         "Mine also has these grey patches since morning. Only a few plants at the low end of "
         "the block where water stands. Should I spray or wait?"),
    ]
    post_ids: list[str] = []
    for phone, category, problem, symptoms, days_ago_, body in script:
        user, farmer, plot = who(phone)
        out = svc.create_post(user, farmer, {
            "category": category, "body": body, "symptoms": symptoms,
            "suspected_problem": problem, "share_context": True,
            "observed_on": (day - dt.timedelta(days=days_ago_)).isoformat(),
        }, plot)
        pid = out["post"]["id"]
        post_ids.append(pid)
        # backdate so the feed is not four posts all stamped "today"
        stamp = (day - dt.timedelta(days=days_ago_)).isoformat() + "T07:30:00.000Z"
        db.execute("UPDATE community_posts SET created_at=:s, last_activity_at=:s WHERE id=:i",
                   {"s": stamp, "i": pid})

    # neighbours corroborating — the cheapest and most valuable signal there is
    for phone in ("9000000005", "9000000006", "9000000007"):
        user, _f, _p = who(phone)
        for pid in post_ids:
            post = db.one("SELECT author_user_id FROM community_posts WHERE id=:i", {"i": pid})
            if post["author_user_id"] == user["id"]:
                continue
            # A rate limit or a duplicate reaction is fine here; the seed is
            # allowed to be partial, it is not allowed to abort startup.
            with contextlib.suppress(Exception):               # pragma: no cover - seed only
                svc.react(user, "post", pid, "same_problem", True)

    # a farmer-to-farmer reply, and one that names a dose so the misinformation
    # path has something real to catch on the demo screen
    user, _f, _p = who("9000000006")
    svc.comment(user, post_ids[0],
                "Ours started the same way last year after the September rain. Removing the "
                "affected leaves early and not irrigating in the evening helped more than "
                "anything else.")
    user, _f, _p = who("9000000005")
    svc.comment(user, post_ids[0],
                "Dealer told me to put Mancozeb 45 gram per pump immediately. I did it last week.")

    # ── the expert's verdict — the only thing that changes verification ────
    expert_user = db.one("SELECT * FROM users WHERE email = 'expert@prahari.demo'")
    expert = db.one("SELECT * FROM experts WHERE user_id = :u", {"u": expert_user["id"]})
    if expert_user and expert:
        svc.expert_respond(dict(expert_user), dict(expert), post_ids[0], {
            "status": "CONFIRMED", "verdict_problem": "late_blight", "confidence": "high",
            "advice_kind": "ipm",
            "body": ("This is late blight (Phytophthora infestans). The white fringe on the "
                     "underside in the morning is the giveaway — early blight gives concentric "
                     "rings and no fringe.\n\nFirst: stop evening irrigation and remove the "
                     "affected leaves into a bag, not onto the field bund. Then check the "
                     "forecast — the Hutton criteria have been firing on this taluka's weather "
                     "all week, so the pressure is real.\n\nDo not spray on a neighbour's dose. "
                     "Open the recommendation screen on your own field; PRAHARI will only show "
                     "you a product whose label claim someone has verified."),
        })

    # ── an unanswered question, so the expert inbox is not empty ───────────
    user, farmer, plot = who("9000000008")
    svc.create_post(user, farmer, {
        "category": "pest", "body": (
            "Silvery streaks on the onion leaf tips and the tips are curling. I can see very "
            "small insects when I split a leaf. Is this thrips, and at what count should I "
            "start worrying?"),
        "symptoms": ["insects_seen", "stunted"], "suspected_problem": "thrips",
        "share_context": True,
    }, plot)

    # ── a result worth sharing, which is what keeps people reading ─────────
    user, farmer, plot = who("9000000003")
    svc.create_post(user, farmer, {
        "category": "success", "body": (
            "Counted the trap for three weeks instead of spraying on a schedule. Crossed the "
            "threshold only once, so I sprayed once instead of four times. Saved about "
            "₹4,200 an acre and the pod damage looks the same as last year."),
        "symptoms": [], "share_context": False,
    }, plot)

    user, farmer, plot = who("9000000009")
    svc.create_post(user, farmer, {
        "category": "question", "body": (
            "Maize is at the whorl stage and I am seeing window-pane damage on the young "
            "leaves. Is it worth putting out pheromone traps now or is it too late in the "
            "season to bother?"),
        "symptoms": ["holes"], "suspected_problem": "faw", "share_context": True,
    }, plot)

    # ── compute the signals the officer console will open on ───────────────
    SignalEngine(db).sweep()
    log.info("seeded community", extra={"posts": db.scalar(
        "SELECT COUNT(*) FROM community_posts")})
