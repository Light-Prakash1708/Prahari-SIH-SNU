"""
PRAHARI · the farmer community — a surveillance instrument, not a feed
════════════════════════════════════════════════════════════════════════════
A farmer notices something odd on a leaf three days before it is diagnosable
from a photograph and two weeks before an officer walks that road. That
noticing is the earliest signal this system can possibly receive. Today it goes
into a WhatsApp group where nobody can count it.

This module is what happens when you treat that noticing as data:

    a farmer posts  →  neighbours reply "I have this too"  →  an expert answers
    →  the expert's verdict is recorded as a verdict, not as a popular comment
    →  several independent posts in one taluka become a POSSIBLE CLUSTER
    →  an officer goes and looks  →  a CONFIRMED FIELD SIGNAL

Three things this file refuses to do, and the refusals are structural:

1.  It never publishes a farm's position. `public_post()` builds its output
    from an ALLOWLIST of columns. Adding a private column to the table later
    cannot leak it, because a column that is not on the list is not emitted.
    village / taluka / district is the finest geography that exists here.

2.  It never calls community advice verified. `verification` starts at
    UNVERIFIED and the only thing that moves it is a row written by an
    identified expert account. No amount of agreement promotes a post.

3.  It never ranks by popularity. `rank()` scores relevance, crop match,
    location, expert verification and recency. `helpful_count` is displayed
    and contributes a tie-break of at most four points, because a feed that
    obeys likes will show a farmer the funniest post in the district rather
    than the disease two villages away.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import re
import uuid
from typing import Any

from . import reference, spatial
from .clock import days_ago, now_iso
from .clock import today as _today
from .db import Database, dumps, loads
from .errors import bad_request, conflict, forbidden, not_found, rate_limited

# ── the vocabulary ──────────────────────────────────────────────────────────
CATEGORIES: dict[str, dict[str, Any]] = {
    "disease": {"label": "Disease", "label_mr": "रोग", "icon": "🍂", "signal": True},
    "pest": {"label": "Pest", "label_mr": "कीड", "icon": "🐛", "signal": True},
    "crop_problem": {"label": "Crop problem", "label_mr": "पिकाची समस्या", "icon": "🌾",
                     "signal": True},
    "weather": {"label": "Weather damage", "label_mr": "हवामान नुकसान", "icon": "🌧",
                "signal": False},
    "cultivation": {"label": "Cultivation", "label_mr": "मशागत", "icon": "🚜", "signal": False},
    "success": {"label": "Success story", "label_mr": "यशोगाथा", "icon": "🌟", "signal": False},
    "question": {"label": "Question", "label_mr": "प्रश्न", "icon": "❓", "signal": False},
}

# A fixed symptom vocabulary, because free text cannot be counted. These are the
# words a farmer would use, not the words a pathologist would.
SYMPTOMS: dict[str, dict[str, str]] = {
    "yellowing": {"label": "Leaves turning yellow", "label_mr": "पाने पिवळी पडत आहेत"},
    "spots": {"label": "Spots on leaves", "label_mr": "पानांवर ठिपके"},
    "wilting": {"label": "Wilting / drooping", "label_mr": "मलूल होणे"},
    "white_powder": {"label": "White powder on leaves", "label_mr": "पानांवर पांढरी बुरशी"},
    "holes": {"label": "Holes in leaves", "label_mr": "पानांना छिद्रे"},
    "insects_seen": {"label": "Insects visible", "label_mr": "किडे दिसत आहेत"},
    "fruit_damage": {"label": "Damage on fruit / pod", "label_mr": "फळ किंवा शेंगेवर नुकसान"},
    "stem_damage": {"label": "Damage on stem", "label_mr": "खोडावर नुकसान"},
    "stunted": {"label": "Plants not growing", "label_mr": "वाढ खुंटली"},
    "spreading_fast": {"label": "Spreading fast", "label_mr": "झपाट्याने पसरत आहे"},
}

REPORT_REASONS: dict[str, dict[str, str]] = {
    "spam": {"label": "Spam or selling", "label_mr": "जाहिरात किंवा विक्री"},
    "misinformation": {"label": "Wrong information", "label_mr": "चुकीची माहिती"},
    "unsafe_advice": {"label": "Unsafe pesticide advice", "label_mr": "धोकादायक फवारणी सल्ला"},
    "abuse": {"label": "Abusive", "label_mr": "अपमानास्पद"},
    "off_topic": {"label": "Not about farming", "label_mr": "शेतीशी संबंधित नाही"},
    "other": {"label": "Something else", "label_mr": "इतर"},
}

VERIFICATION = {
    "UNVERIFIED": {
        "label": "Community advice — not verified",
        "label_mr": "शेतकऱ्यांचा सल्ला — तपासलेला नाही",
        "tone": "grey", "rank": 0,
    },
    "EXPERT_REVIEWED": {
        "label": "An expert has replied",
        "label_mr": "तज्ज्ञांनी उत्तर दिले आहे",
        "tone": "info", "rank": 1,
    },
    "CONFIRMED": {
        "label": "Expert confirmed",
        "label_mr": "तज्ज्ञांनी निश्चित केले",
        "tone": "green", "rank": 2,
    },
    "CORRECTED": {
        "label": "Expert corrected this",
        "label_mr": "तज्ज्ञांनी दुरुस्त केले",
        "tone": "amber", "rank": 2,
    },
}

UNVERIFIED_NOTICE = (
    "Replies from other farmers are experience, not a verified diagnosis. PRAHARI does not check "
    "them. Before you spray anything on this advice, run the threshold check on your own field.")
UNVERIFIED_NOTICE_MR = (
    "इतर शेतकऱ्यांची उत्तरे हा त्यांचा अनुभव आहे — तपासलेले निदान नाही. फवारणीपूर्वी स्वतःच्या "
    "शेतात आर्थिक नुकसान पातळी तपासा.")

# ── moderation limits ───────────────────────────────────────────────────────
POST_LIMIT_PER_HOUR = 6
COMMENT_LIMIT_PER_HOUR = 30
REPORTS_TO_FLAG = 3          # independent reports before the post is auto-flagged
REPORTS_TO_HIDE = 6

_LINK = re.compile(r"https?://|www\.", re.I)
_PHONE = re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{9}")
_SELLING = re.compile(
    r"\b(for sale|buy now|whatsapp me|dealer|wholesale|best rate|contact me|order now|"
    r"विक्रीसाठी|संपर्क करा|घाऊक)\b", re.I)

# A dose written as a number and a unit is the shape of a prescription. When one
# appears in a reply from someone who is not a verified expert, the reply gets a
# louder warning and an automatic moderation report — because "60 ml per pump"
# read by a farmer standing next to a sprayer is an instruction, whatever the
# person writing it intended.
_DOSE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ml|मिली|ग्रॅम|gm?|g|gram|grams|kg|लिटर|litre|liter|l)\b"
    r"|\b(?:per|प्रति)\s*(?:pump|पंप|acre|एकर|tank|टाकी|litre|लिटर)", re.I)


def advice_risk(text: str) -> dict[str, Any]:
    """Does this text read like a pesticide prescription?

    Deliberately generous about what counts. A false positive costs a warning
    banner; a false negative costs a farmer spraying an unverified dose."""
    body = text or ""
    dose = bool(_DOSE.search(body))
    named: list[str] = []
    low = body.lower()
    for claim in reference.CLAIMS:
        for token in filter(None, [claim.get("product"), claim.get("active_ingredient")]):
            head = str(token).split()[0].lower()
            if len(head) >= 6 and head in low and head not in named:
                named.append(head)
    return {
        "is_prescription": bool(dose and named) or bool(named and len(named) > 1),
        "mentions_dose": dose,
        "mentions_product": named[:4],
    }


def spam_signals(body: str, title: str = "") -> list[str]:
    text = f"{title} {body}"
    out = []
    if _LINK.search(text):
        out.append("contains_link")
    if _PHONE.search(text):
        out.append("contains_phone_number")
    if _SELLING.search(text):
        out.append("selling_language")
    letters = [c for c in text if c.isalpha() and c.isascii()]
    if len(letters) > 24 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        out.append("shouting")
    return out


def author_key(user_id: str) -> str:
    """A stable pseudonym for an author. The account id never leaves the server,
    so nothing in the community surface can be joined back to a user row by a
    client — but 'is this the same person who posted yesterday?' still works."""
    return "a" + hashlib.sha256(f"prahari-community:{user_id}".encode()).hexdigest()[:11]


# ── the privacy boundary ────────────────────────────────────────────────────
# An ALLOWLIST. Anything not named here is not published, including columns that
# do not exist yet. test_community_privacy.py asserts that plot_id, coordinates,
# phone numbers and account ids never appear in any community response.
PUBLIC_POST_FIELDS = (
    "id", "category", "crop", "crop_stage", "title", "body",
    "suspected_problem", "confirmed_problem", "verification", "status",
    "moderation_state", "village", "taluka", "district",
    "comment_count", "expert_count", "helpful_count", "same_problem_count",
    "observed_on", "created_at", "last_activity_at", "author_display", "author_role",
)

PRIVACY_STATEMENT = (
    "Community posts carry the village, taluka and district only. PRAHARI never publishes a "
    "field's coordinates, its area, its owner's phone number or account, or any part of that "
    "farmer's private scan history. What you see of another farmer's field is what they chose "
    "to attach to the post.")
PRIVACY_STATEMENT_MR = (
    "समुदायातील नोंदींमध्ये फक्त गाव, तालुका आणि जिल्हा दिसतो. शेताचे नेमके ठिकाण, क्षेत्र, "
    "फोन नंबर किंवा खासगी तपासणीचा इतिहास प्रहरी कधीही उघड करत नाही.")


class CommunityService:
    def __init__(self, db: Database):
        self.db = db

    # ── projection ─────────────────────────────────────────────────────────
    def public_post(self, row: dict[str, Any], viewer: dict[str, Any] | None = None,
                    *, with_body: bool = True) -> dict[str, Any]:
        out = {k: row.get(k) for k in PUBLIC_POST_FIELDS}
        if not with_body:
            out["body"] = (row.get("body") or "")[:180]
        out["symptoms"] = loads(row.get("symptoms"), []) or []
        out["symptom_labels"] = [SYMPTOMS[s]["label"] for s in out["symptoms"] if s in SYMPTOMS]
        out["symptom_labels_mr"] = [SYMPTOMS[s]["label_mr"] for s in out["symptoms"]
                                    if s in SYMPTOMS]
        out["category_meta"] = CATEGORIES.get(row.get("category"), {})
        out["verification_meta"] = VERIFICATION.get(row.get("verification") or "UNVERIFIED",
                                                    VERIFICATION["UNVERIFIED"])
        out["author_key"] = author_key(row["author_user_id"])
        out["taluka_name"] = reference.taluka_name(row.get("taluka") or "")
        # A village whose name IS the taluka name reads as a stutter ("Pimpalgaon
        # Baswant · Pimpalgaon Baswant"), so it is shown once.
        tname = reference.taluka_name(row.get("taluka") or "")
        village = row.get("village")
        out["place"] = tname if not village or village == tname else f"{village} · {tname}"
        out["problem_name"] = (reference.problem_name(row["confirmed_problem"] or
                                                      row["suspected_problem"])
                               if (row.get("confirmed_problem") or row.get("suspected_problem"))
                               else None)
        out["crop_label"] = (reference.CROPS.get(row.get("crop"), {}) or {}).get("name",
                                                                                row.get("crop"))
        out["images"] = [
            {"id": r["id"], "url": f"/api/community/images/{r['id']}"}
            for r in self.db.rows(
                "SELECT id FROM community_post_images WHERE post_id = :p ORDER BY created_at",
                {"p": row["id"]})]
        # The attached PRAHARI context was redacted when it was written. It is
        # re-read here, not rebuilt, so a change to _context() cannot widen what
        # an old post already published.
        out["context"] = loads(row.get("context"), None) if row.get("share_context") else None
        out["is_mine"] = bool(viewer and viewer["id"] == row["author_user_id"])
        out["days_ago"] = days_ago(row.get("created_at"))
        if row.get("verification") == "UNVERIFIED":
            out["notice"] = UNVERIFIED_NOTICE
            out["notice_mr"] = UNVERIFIED_NOTICE_MR
        return out

    def public_comment(self, row: dict[str, Any], viewer: dict[str, Any] | None = None
                       ) -> dict[str, Any]:
        risk = advice_risk(row.get("body") or "")
        return {
            "id": row["id"], "post_id": row["post_id"], "parent_id": row.get("parent_id"),
            "body": row["body"], "author_display": row["author_display"],
            "author_role": row["author_role"], "author_key": author_key(row["author_user_id"]),
            "is_expert": bool(row.get("is_expert")),
            "expert_response_id": row.get("expert_response_id"),
            "place": reference.taluka_name(row.get("taluka") or "") if row.get("taluka") else None,
            "helpful_count": row.get("helpful_count", 0),
            "status": row.get("status"),
            "created_at": row["created_at"], "days_ago": days_ago(row.get("created_at")),
            "is_mine": bool(viewer and viewer["id"] == row["author_user_id"]),
            # An unverified prescription is labelled at the point of reading, not
            # in a footnote at the bottom of the screen.
            "advice_warning": (
                None if row.get("is_expert") or not risk["is_prescription"] else {
                    "text": ("This reply names a pesticide and a dose. It has NOT been checked by "
                             "PRAHARI or by an expert. Do not spray on this advice — run the "
                             "threshold check on your own field first."),
                    "text_mr": ("या उत्तरात कीटकनाशक आणि मात्रा दिली आहे. ती प्रहरीने किंवा "
                                "तज्ज्ञांनी तपासलेली नाही. फवारणीपूर्वी स्वतःच्या शेतात पातळी तपासा."),
                }),
        }

    # ── writing a post ─────────────────────────────────────────────────────
    def create_post(self, user: dict[str, Any], farmer: dict[str, Any] | None,
                    data: dict[str, Any], plot: dict[str, Any] | None = None) -> dict[str, Any]:
        category = data.get("category")
        if category not in CATEGORIES:
            raise bad_request("unknown_category",
                              f"'{category}' is not a category PRAHARI understands.")
        bad = [s for s in (data.get("symptoms") or []) if s not in SYMPTOMS]
        if bad:
            raise bad_request("unknown_symptom",
                              f"PRAHARI does not have a symptom called '{bad[0]}'.")
        body = (data.get("body") or "").strip()
        title = (data.get("title") or "").strip()
        if len(body) < 10:
            raise bad_request("post_too_short",
                              "Describe what you are seeing in a sentence or two, so another "
                              "farmer can recognise it.",
                              "तुम्हाला काय दिसत आहे ते एक-दोन वाक्यांत लिहा.")

        ref = data.get("client_ref")
        if ref:
            dup = self.db.one(
                "SELECT * FROM community_posts WHERE author_user_id = :u AND client_ref = :c",
                {"u": user["id"], "c": ref})
            if dup:
                return {"post": self.public_post(dup, user), "duplicate": True}

        self._rate_limit("post", user["id"], POST_LIMIT_PER_HOUR,
                         "You have posted several times in the last hour.")

        taluka = (plot or {}).get("taluka") or (farmer or {}).get("taluka")
        village = (plot or {}).get("village") or (farmer or {}).get("village")
        if not taluka:
            raise bad_request(
                "no_location",
                "PRAHARI needs to know which taluka this is about before it can post it — "
                "register a field, or pick a taluka.",
                "ही नोंद कोणत्या तालुक्यातील आहे हे प्रहरीला माहीत असणे आवश्यक आहे.")
        if taluka not in reference.TALUKA_IDS:
            raise bad_request("unknown_taluka", f"'{taluka}' is not a taluka PRAHARI covers.")

        crop = (plot or {}).get("crop") or data.get("crop")
        suspected = data.get("suspected_problem") or None
        if suspected and not reference.problem(suspected):
            raise bad_request("unknown_problem", f"'{suspected}' is not a problem PRAHARI tracks.")

        share = bool(data.get("share_context")) and plot is not None
        context = self._context(plot, data) if share else None

        spam = spam_signals(body, title)
        moderation = "flagged" if len(spam) >= 2 else "ok"

        pid = "CP-" + uuid.uuid4().hex[:10].upper()
        stamp = now_iso()
        self.db.execute(
            "INSERT INTO community_posts (id, author_user_id, author_farmer_id, author_role,"
            " author_display, category, crop, crop_stage, title, body, symptoms,"
            " suspected_problem, village, taluka, district, plot_id, observation_id,"
            " diagnosis_id, share_context, context, verification, status, moderation_state,"
            " moderation_note, signal_eligible, observed_on, client_ref, created_at, updated_at,"
            " last_activity_at)"
            " VALUES (:id,:u,:f,:role,:disp,:cat,:crop,:stage,:title,:body,:sym,:susp,:vil,:tk,"
            " :dist,:plot,:obs,:dx,:share,:ctx,'UNVERIFIED','published',:mod,:modnote,:sig,"
            " :on,:ref,:now,:now,:now)",
            {"id": pid, "u": user["id"], "f": (farmer or {}).get("id"), "role": user["role"],
             "disp": self._display(user, farmer), "cat": category, "crop": crop,
             "stage": (context or {}).get("crop_stage"), "title": title or _headline(body),
             "body": body, "sym": dumps(data.get("symptoms") or []), "susp": suspected,
             "vil": village, "tk": taluka, "dist": "Nashik",
             "plot": (plot or {}).get("id"), "obs": data.get("observation_id"),
             "dx": data.get("diagnosis_id"),
             "share": 1 if share else 0, "ctx": dumps(context),
             "mod": moderation, "modnote": ", ".join(spam) or None,
             "sig": 1 if CATEGORIES[category]["signal"] else 0,
             "on": (data.get("observed_on") or _today().isoformat()),
             "ref": ref, "now": stamp})
        self._attach_topics(pid, category, crop, suspected, taluka)
        row = self.db.one("SELECT * FROM community_posts WHERE id = :id", {"id": pid})
        return {"post": self.public_post(row, user), "duplicate": False,
                "moderation": {"state": moderation, "signals": spam},
                "privacy": PRIVACY_STATEMENT}

    def _display(self, user: dict[str, Any], farmer: dict[str, Any] | None) -> str:
        name = (farmer or {}).get("name") or user.get("full_name") or "Farmer"
        return str(name)

    def _context(self, plot: dict[str, Any] | None, data: dict[str, Any]) -> dict[str, Any] | None:
        """The 'Use my field' attachment (spec §6), built ONCE, at write time,
        from an explicit list. The private record it is drawn from is never
        published — this is a summary a farmer could have typed themselves."""
        if not plot:
            return None
        from .runtime import get_runtime
        rt = get_runtime()
        stage = rt.risk.crop_stage(plot)
        ctx: dict[str, Any] = {
            "crop": plot.get("crop"),
            "crop_label": (reference.CROPS.get(plot.get("crop"), {}) or {}).get("name"),
            "crop_stage": stage.get("stage"),
            "crop_stage_label": stage.get("label"),
            "days_after_sowing": stage.get("days"),
            "taluka_name": reference.taluka_name(plot.get("taluka") or ""),
            "attached_by_farmer": True,
        }
        dxid = data.get("diagnosis_id")
        if dxid:
            dx = self.db.one(
                "SELECT top_problem, top_posterior, abstained, model_version, engine"
                " FROM diagnoses WHERE id = :d AND plot_id = :p",
                {"d": dxid, "p": plot["id"]})
            if dx:
                ctx["prahari_said"] = {
                    "problem": dx["top_problem"],
                    "problem_name": (reference.problem_name(dx["top_problem"])
                                     if dx["top_problem"] else None),
                    # A band, not a decimal. A posterior of 0.62 shown to a
                    # stranger reads as a measurement of their field.
                    "confidence": _band(dx["top_posterior"]),
                    "abstained": bool(dx["abstained"]),
                    "model_version": dx["model_version"],
                }
        try:
            wx = rt.risk.weather_series(plot)
            board, fired = rt.risk.board(plot, wx, stage)
            hits = [reference.problem_name(k) for k, v in (fired or {}).items() if v]
            ctx["weather_note"] = (
                f"Infection models firing in the last week: {', '.join(hits)}." if hits
                else "No infection model fired on this field's weather in the last week.")
            ctx["weather_source"] = wx.get("source")
        except Exception:
            ctx["weather_note"] = None
        return ctx

    # ── topics ─────────────────────────────────────────────────────────────
    def _attach_topics(self, post_id: str, category: str, crop: str | None,
                       problem: str | None, taluka: str) -> None:
        wanted = [("category", category, CATEGORIES[category]["label"],
                   CATEGORIES[category]["label_mr"])]
        if crop:
            meta = reference.CROPS.get(crop, {}) or {}
            wanted.append(("crop", crop, meta.get("name", crop), meta.get("mr")))
        if problem:
            wanted.append(("problem", problem, reference.problem_name(problem),
                           reference.problem_name(problem, "mr")))
        wanted.append(("taluka", taluka, reference.taluka_name(taluka),
                       reference.taluka_name(taluka, "mr")))
        for kind, ref_, label, label_mr in wanted:
            tid = f"{kind}:{ref_}"
            self.db.execute(
                "INSERT INTO community_topics (id, kind, ref, label, label_mr, post_count,"
                " created_at) VALUES (:id,:k,:r,:l,:lm,0,:now)"
                " ON CONFLICT (id) DO NOTHING",
                {"id": tid, "k": kind, "r": ref_, "l": label, "lm": label_mr, "now": now_iso()})
            self.db.execute(
                "INSERT INTO community_post_topics (post_id, topic_id) VALUES (:p,:t)"
                " ON CONFLICT (post_id, topic_id) DO NOTHING",
                {"p": post_id, "t": tid})
            self.db.execute(
                "UPDATE community_topics SET post_count = post_count + 1 WHERE id = :t",
                {"t": tid})

    def topics(self, user_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.db.rows(
            "SELECT * FROM community_topics WHERE post_count > 0"
            " ORDER BY post_count DESC, label LIMIT 40")
        followed = set()
        if user_id:
            followed = {r["topic_id"] for r in self.db.rows(
                "SELECT topic_id FROM community_topic_follows WHERE user_id = :u",
                {"u": user_id})}
        for r in rows:
            r["following"] = r["id"] in followed
        return rows

    def follow(self, user_id: str, topic_id: str, on: bool) -> dict[str, Any]:
        exists = self.db.one("SELECT id FROM community_topics WHERE id = :t", {"t": topic_id})
        if not exists:
            raise not_found("topic", topic_id)
        if on:
            self.db.execute(
                "INSERT INTO community_topic_follows (topic_id, user_id, created_at)"
                " VALUES (:t,:u,:now) ON CONFLICT (topic_id, user_id) DO NOTHING",
                {"t": topic_id, "u": user_id, "now": now_iso()})
        else:
            self.db.execute(
                "DELETE FROM community_topic_follows WHERE topic_id = :t AND user_id = :u",
                {"t": topic_id, "u": user_id})
        return {"topic_id": topic_id, "following": on}

    # ── the feed ───────────────────────────────────────────────────────────
    def feed(self, user: dict[str, Any], *, tab: str = "for_you", category: str | None = None,
             crop: str | None = None, taluka: str | None = None, q: str | None = None,
             limit: int = 30, offset: int = 0) -> dict[str, Any]:
        ctx = self.viewer_context(user)
        blocked = self._blocked(user["id"])

        sql = ("SELECT * FROM community_posts WHERE status = 'published'"
               " AND moderation_state <> 'blocked'")
        params: dict[str, Any] = {}
        if tab == "mine":
            sql += " AND author_user_id = :me"
            params["me"] = user["id"]
        elif tab == "nearby":
            near = ctx["near_talukas"] or ctx["talukas"]
            if not near:
                return {"tab": tab, "posts": [], "reason": "no_location",
                        "privacy": PRIVACY_STATEMENT}
            sql += " AND taluka IN (" + ",".join(f":t{i}" for i in range(len(near))) + ")"
            params.update({f"t{i}": t for i, t in enumerate(near)})
        elif tab == "experts":
            sql += " AND verification IN ('EXPERT_REVIEWED','CONFIRMED','CORRECTED')"
        elif tab == "saved":
            sql += (" AND id IN (SELECT target_id FROM community_reactions"
                    " WHERE user_id = :me AND kind = 'saved' AND target_type = 'post')")
            params["me"] = user["id"]
        if category:
            sql += " AND category = :cat"
            params["cat"] = category
        if crop:
            sql += " AND crop = :crop"
            params["crop"] = crop
        if taluka:
            sql += " AND taluka = :tk"
            params["tk"] = taluka
        if q:
            sql += (" AND (lower(title) LIKE :q OR lower(body) LIKE :q"
                    " OR lower(coalesce(suspected_problem,'')) LIKE :q"
                    " OR lower(coalesce(crop,'')) LIKE :q)")
            params["q"] = f"%{q.lower()}%"

        # A wide-but-bounded candidate set, ranked in Python. Ranking in SQL would
        # mean encoding "same crop as this viewer" as a CASE expression per
        # dialect, and the ranking is the part most likely to change.
        rows = self.db.rows(sql + " ORDER BY last_activity_at DESC LIMIT 400", params)
        rows = [r for r in rows if r["author_user_id"] not in blocked]

        scored = []
        for r in rows:
            score, why = self.rank(r, ctx) if tab in ("for_you", "nearby") else (
                _recency(r), [])
            scored.append((score, r, why))
        scored.sort(key=lambda x: (-x[0], str(x[1]["created_at"])[::-1]))
        page = scored[offset:offset + limit]

        posts = []
        for score, r, why in page:
            p = self.public_post(r, user, with_body=False)
            p["rank_score"] = round(score, 1)
            p["shown_because"] = why
            posts.append(p)
        return {
            "tab": tab, "posts": posts, "total": len(scored),
            "has_more": len(scored) > offset + limit,
            "viewer": {"talukas": ctx["talukas"], "crops": ctx["crops"]},
            "ranking": (
                "Ordered by relevance to your fields: your taluka and its neighbours, your crops, "
                "the problems those crops actually get, whether an expert has answered, and how "
                "recent it is. Popularity is not a ranking input — a reply marked helpful moves a "
                "post at most four points, as a tie-break."),
            "privacy": PRIVACY_STATEMENT, "privacy_mr": PRIVACY_STATEMENT_MR,
        }

    def viewer_context(self, user: dict[str, Any]) -> dict[str, Any]:
        """What this viewer's feed should be about — their talukas, their crops,
        the problems those crops get, and the topics they follow."""
        rows = self.db.rows(
            "SELECT p.taluka, p.crop FROM plots p JOIN farmers f ON f.id = p.farmer_id"
            " WHERE f.user_id = :u AND p.archived = 0", {"u": user["id"]})
        talukas = sorted({r["taluka"] for r in rows})
        crops = sorted({r["crop"] for r in rows})
        if not talukas:
            farmer = self.db.one("SELECT taluka FROM farmers WHERE user_id = :u",
                                 {"u": user["id"]})
            if farmer and farmer["taluka"]:
                talukas = [farmer["taluka"]]
        near = set(talukas)
        for t in talukas:
            here = reference.TALUKA_BY_ID.get(t)
            if not here:
                continue
            for other in reference.TALUKAS:
                if spatial.haversine(here, other) <= 25.0:
                    near.add(other["id"])
        problems: set[str] = set()
        for c in crops:
            problems |= set(reference.problems_for_crop(c).keys())
        followed = {r["topic_id"] for r in self.db.rows(
            "SELECT topic_id FROM community_topic_follows WHERE user_id = :u", {"u": user["id"]})}
        return {"talukas": talukas, "near_talukas": sorted(near), "crops": crops,
                "problems": problems, "followed": followed}

    def rank(self, post: dict[str, Any], ctx: dict[str, Any]) -> tuple[float, list[str]]:
        """Relevance, crop, location, expert verification, recency. Not likes.

        Every term returns a sentence, so the UI can show a farmer WHY a post is
        at the top of their feed — the same rule the diagnosis screen follows."""
        score = 0.0
        why: list[str] = []
        if post["taluka"] in ctx["talukas"]:
            score += 30
            why.append(f"In {reference.taluka_name(post['taluka'])}, where your field is")
        elif post["taluka"] in ctx["near_talukas"]:
            score += 14
            why.append(f"Near you — {reference.taluka_name(post['taluka'])}")
        if post.get("crop") and post["crop"] in ctx["crops"]:
            score += 26
            why.append(f"About {(reference.CROPS.get(post['crop'], {}) or {}).get('name', post['crop'])}, which you grow")
        prob = post.get("confirmed_problem") or post.get("suspected_problem")
        if prob and prob in ctx["problems"]:
            score += 16
            why.append(f"{reference.problem_name(prob)} affects a crop you grow")
        vmeta = VERIFICATION.get(post.get("verification") or "UNVERIFIED")
        if vmeta and vmeta["rank"] == 2:
            score += 22
            why.append("An expert has confirmed or corrected this")
        elif vmeta and vmeta["rank"] == 1:
            score += 11
            why.append("An expert has replied")
        if post.get("signal_eligible") and post.get("same_problem_count", 0) >= 2:
            score += 12
            why.append(f"{post['same_problem_count']} other farmers say they are seeing this too")
        for tid in ctx["followed"]:
            kind, _, ref_ = tid.partition(":")
            if ((kind == "crop" and post.get("crop") == ref_)
                    or (kind == "problem" and prob == ref_)
                    or (kind == "taluka" and post.get("taluka") == ref_)
                    or (kind == "category" and post.get("category") == ref_)):
                score += 9
                why.append("A topic you follow")
                break
        if post.get("category") in ("disease", "pest") and (post.get("comment_count") or 0) == 0:
            score += 7
            why.append("Nobody has answered this yet")
        score += _recency(post)
        # The only place popularity enters, and it is capped.
        score += min(4.0, (post.get("helpful_count") or 0) * 1.0)
        if post.get("moderation_state") == "flagged":
            score -= 40
        return score, why

    # ── one post, in full ──────────────────────────────────────────────────
    def post_detail(self, post_id: str, user: dict[str, Any]) -> dict[str, Any]:
        row = self.db.one("SELECT * FROM community_posts WHERE id = :id", {"id": post_id})
        if not row:
            raise not_found("post", post_id)
        if row["status"] == "removed" and row["author_user_id"] != user["id"] \
                and user["role"] not in ("admin", "officer"):
            raise not_found("post", post_id)
        blocked = self._blocked(user["id"])
        comments = [self.public_comment(c, user) for c in self.db.rows(
            "SELECT * FROM community_comments WHERE post_id = :p AND status = 'published'"
            " ORDER BY is_expert DESC, created_at", {"p": post_id})
            if c["author_user_id"] not in blocked]
        experts = self.db.rows(
            "SELECT * FROM community_expert_responses WHERE post_id = :p"
            " ORDER BY created_at DESC", {"p": post_id})
        for e in experts:
            e["verdict_name"] = (reference.problem_name(e["verdict_problem"])
                                 if e["verdict_problem"] else None)
            e["status_meta"] = VERIFICATION.get(e["status"], VERIFICATION["UNVERIFIED"])
        my = {r["kind"] for r in self.db.rows(
            "SELECT kind FROM community_reactions WHERE target_type='post' AND target_id=:t"
            " AND user_id=:u", {"t": post_id, "u": user["id"]})}
        return {
            "post": self.public_post(row, user),
            "comments": comments,
            "expert_responses": experts,
            "my_reactions": sorted(my),
            "similar": self.similar(row, user),
            "nearby_signal": self.post_signal(row),
            "privacy": PRIVACY_STATEMENT, "privacy_mr": PRIVACY_STATEMENT_MR,
        }

    def similar(self, post: dict[str, Any], user: dict[str, Any],
                limit: int = 5) -> list[dict[str, Any]]:
        """Similar cases (spec §20). Same crop and same suspected problem, or the
        same symptom set, in the district — most useful when an expert has
        already answered one of them."""
        rows = self.db.rows(
            "SELECT * FROM community_posts WHERE id <> :id AND status = 'published'"
            " AND moderation_state <> 'blocked' AND (crop = :crop OR :crop IS NULL)"
            " ORDER BY created_at DESC LIMIT 120",
            {"id": post["id"], "crop": post.get("crop")})
        mine = set(loads(post.get("symptoms"), []) or [])
        prob = post.get("confirmed_problem") or post.get("suspected_problem")
        out = []
        for r in rows:
            theirs = set(loads(r.get("symptoms"), []) or [])
            overlap = len(mine & theirs)
            rprob = r.get("confirmed_problem") or r.get("suspected_problem")
            sim = overlap * 2 + (5 if prob and rprob == prob else 0)
            sim += 3 if VERIFICATION.get(r["verification"], {}).get("rank") == 2 else 0
            if sim <= 0:
                continue
            p = self.public_post(r, user, with_body=False)
            p["similarity"] = sim
            p["similar_because"] = ([f"{overlap} of the same symptoms"] if overlap else []) + \
                                   ([f"also {reference.problem_name(rprob)}"] if prob and rprob == prob else [])
            out.append(p)
        out.sort(key=lambda p: -p["similarity"])
        return out[:limit]

    def post_signal(self, post: dict[str, Any]) -> dict[str, Any] | None:
        """The aggregate answer to "are others seeing this?", from the signal
        table — never by listing other farmers' posts back at them."""
        prob = post.get("confirmed_problem") or post.get("suspected_problem")
        if not prob or not post.get("signal_eligible"):
            return None
        row = self.db.one(
            "SELECT * FROM community_cluster_signals WHERE taluka = :t AND problem = :p"
            " AND state = 'open' ORDER BY updated_at DESC", {"t": post["taluka"], "p": prob})
        if not row:
            return None
        from .signals import GRADES
        return {"grade": row["grade"], **GRADES.get(row["grade"], {}),
                "taluka_name": reference.taluka_name(row["taluka"]),
                "problem_name": reference.problem_name(row["problem"]),
                "reports": row["community_posts_n"], "villages": row["distinct_villages"],
                "window_days": row["window_days"]}

    # ── replies ────────────────────────────────────────────────────────────
    def comment(self, user: dict[str, Any], post_id: str, body: str,
                parent_id: str | None = None) -> dict[str, Any]:
        post = self.db.one("SELECT * FROM community_posts WHERE id = :id", {"id": post_id})
        if not post or post["status"] != "published":
            raise not_found("post", post_id)
        body = (body or "").strip()
        if len(body) < 2:
            raise bad_request("comment_empty", "Write something before you send it.")
        self._rate_limit("comment", user["id"], COMMENT_LIMIT_PER_HOUR,
                         "You have replied a great many times in the last hour.")
        if parent_id and not self.db.one(
                "SELECT id FROM community_comments WHERE id = :c AND post_id = :p",
                {"c": parent_id, "p": post_id}):
            raise not_found("comment", parent_id)

        expert = self.db.one("SELECT * FROM experts WHERE user_id = :u", {"u": user["id"]})
        farmer = self.db.one("SELECT * FROM farmers WHERE user_id = :u", {"u": user["id"]})
        cid = "CC-" + uuid.uuid4().hex[:10].upper()
        stamp = now_iso()
        self.db.execute(
            "INSERT INTO community_comments (id, post_id, parent_id, author_user_id, author_role,"
            " author_display, taluka, body, is_expert, status, created_at)"
            " VALUES (:id,:p,:par,:u,:role,:disp,:tk,:body,:ex,'published',:now)",
            {"id": cid, "p": post_id, "par": parent_id, "u": user["id"], "role": user["role"],
             "disp": self._display(user, farmer), "tk": (farmer or {}).get("taluka"),
             "body": body, "ex": 1 if expert else 0, "now": stamp})
        self.db.execute(
            "UPDATE community_posts SET comment_count = comment_count + 1,"
            " last_activity_at = :now, updated_at = :now WHERE id = :p",
            {"p": post_id, "now": stamp})

        # An unverified prescription raises a moderation report automatically, so
        # an expert is asked to correct it rather than a farmer having to notice.
        risk = advice_risk(body)
        if risk["is_prescription"] and not expert:
            self._auto_report("comment", cid, post_id, "unsafe_advice",
                              f"Automatic: names {', '.join(risk['mentions_product'])} with a dose, "
                              f"from an account that is not a verified expert.")
        row = self.db.one("SELECT * FROM community_comments WHERE id = :id", {"id": cid})
        return {"comment": self.public_comment(row, user),
                "advice_flagged": bool(risk["is_prescription"] and not expert)}

    def react(self, user: dict[str, Any], target_type: str, target_id: str, kind: str,
              on: bool = True) -> dict[str, Any]:
        if target_type not in ("post", "comment"):
            raise bad_request("bad_target", "Reactions attach to a post or a comment.")
        if kind not in ("helpful", "same_problem", "thanks", "saved"):
            raise bad_request("bad_reaction", f"'{kind}' is not a reaction PRAHARI records.")
        table = "community_posts" if target_type == "post" else "community_comments"
        row = self.db.one(f"SELECT * FROM {table} WHERE id = :id", {"id": target_id})
        if not row:
            raise not_found(target_type, target_id)
        if kind == "same_problem" and target_type != "post":
            raise bad_request("bad_reaction", "'I have this too' belongs on a post.")
        if kind == "same_problem" and row["author_user_id"] == user["id"]:
            raise bad_request("own_post",
                              "You wrote this one — the count is of OTHER farmers seeing it.")
        farmer = self.db.one("SELECT taluka FROM farmers WHERE user_id = :u", {"u": user["id"]})
        if on:
            self.db.execute(
                "INSERT INTO community_reactions (target_type, target_id, user_id, kind, taluka,"
                " created_at) VALUES (:tt,:ti,:u,:k,:tk,:now)"
                " ON CONFLICT (target_type, target_id, user_id, kind) DO NOTHING",
                {"tt": target_type, "ti": target_id, "u": user["id"], "k": kind,
                 "tk": (farmer or {}).get("taluka"), "now": now_iso()})
        else:
            self.db.execute(
                "DELETE FROM community_reactions WHERE target_type=:tt AND target_id=:ti"
                " AND user_id=:u AND kind=:k",
                {"tt": target_type, "ti": target_id, "u": user["id"], "k": kind})
        self._recount(target_type, target_id)
        fresh = self.db.one(f"SELECT * FROM {table} WHERE id = :id", {"id": target_id})
        return {"target_type": target_type, "target_id": target_id, "kind": kind, "on": on,
                "helpful_count": fresh.get("helpful_count", 0),
                "same_problem_count": fresh.get("same_problem_count", 0)}

    def _recount(self, target_type: str, target_id: str) -> None:
        def n(kind: str) -> int:
            return int(self.db.scalar(
                "SELECT COUNT(*) FROM community_reactions WHERE target_type=:tt"
                " AND target_id=:ti AND kind=:k",
                {"tt": target_type, "ti": target_id, "k": kind}) or 0)
        if target_type == "post":
            self.db.execute(
                "UPDATE community_posts SET helpful_count=:h, same_problem_count=:s"
                " WHERE id=:id", {"h": n("helpful"), "s": n("same_problem"), "id": target_id})
        else:
            self.db.execute("UPDATE community_comments SET helpful_count=:h WHERE id=:id",
                            {"h": n("helpful"), "id": target_id})

    def saved(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.db.rows(
            "SELECT p.* FROM community_posts p JOIN community_reactions r"
            " ON r.target_id = p.id AND r.target_type='post' AND r.kind='saved'"
            " WHERE r.user_id = :u ORDER BY r.created_at DESC", {"u": user["id"]})
        return [self.public_post(r, user, with_body=False) for r in rows]

    # ── the expert's verdict ───────────────────────────────────────────────
    def expert_respond(self, user: dict[str, Any], expert: dict[str, Any], post_id: str,
                       data: dict[str, Any]) -> dict[str, Any]:
        post = self.db.one("SELECT * FROM community_posts WHERE id = :id", {"id": post_id})
        if not post:
            raise not_found("post", post_id)
        status = (data.get("status") or "").upper()
        if status not in ("EXPERT_REVIEWED", "CONFIRMED", "CORRECTED"):
            raise bad_request(
                "bad_status",
                "An expert response is EXPERT_REVIEWED, CONFIRMED or CORRECTED. "
                "UNVERIFIED is where a post starts — it is not something an expert can assert.")
        verdict = data.get("verdict_problem") or None
        if status in ("CONFIRMED", "CORRECTED") and not verdict:
            raise bad_request(
                "verdict_required",
                "Confirming or correcting a post means naming the problem you are confirming "
                "or correcting it to.")
        if verdict and not reference.problem(verdict):
            raise bad_request("unknown_problem", f"'{verdict}' is not a problem PRAHARI tracks.")
        body = (data.get("body") or "").strip()
        if len(body) < 10:
            raise bad_request("response_too_short",
                              "Say what you are seeing and what the farmer should do next.")

        rid = "CE-" + uuid.uuid4().hex[:10].upper()
        stamp = now_iso()
        # The response is also a comment, so it appears in the thread where the
        # farmer is reading — with the badge, not merely in a separate panel.
        cid = "CC-" + uuid.uuid4().hex[:10].upper()
        self.db.execute(
            "INSERT INTO community_comments (id, post_id, author_user_id, author_role,"
            " author_display, body, is_expert, expert_response_id, status, created_at)"
            " VALUES (:id,:p,:u,'expert',:disp,:body,1,:rid,'published',:now)",
            {"id": cid, "p": post_id, "u": user["id"],
             "disp": expert.get("name") or user.get("full_name"), "body": body,
             "rid": rid, "now": stamp})
        self.db.execute(
            "INSERT INTO community_expert_responses (id, post_id, expert_id, expert_user_id,"
            " expert_name, institution, status, verdict_problem, corrects, confidence, body,"
            " advice_kind, comment_id, created_at)"
            " VALUES (:id,:p,:e,:u,:name,:inst,:st,:v,:corr,:conf,:body,:kind,:cid,:now)",
            {"id": rid, "p": post_id, "e": expert.get("id"), "u": user["id"],
             "name": expert.get("name") or user.get("full_name"),
             "inst": expert.get("institution"), "st": status, "v": verdict,
             "corr": post.get("suspected_problem") if status == "CORRECTED" else None,
             "conf": data.get("confidence") or "moderate", "body": body,
             "kind": data.get("advice_kind") or "ipm", "cid": cid, "now": stamp})

        # The post's verification only ever moves UP the ladder, and only here.
        current = VERIFICATION.get(post["verification"], VERIFICATION["UNVERIFIED"])["rank"]
        new = VERIFICATION[status]["rank"]
        verification = status if new >= current else post["verification"]
        self.db.execute(
            "UPDATE community_posts SET verification = :v, confirmed_problem = :cp,"
            " expert_count = expert_count + 1, comment_count = comment_count + 1,"
            " last_activity_at = :now, updated_at = :now WHERE id = :id",
            {"v": verification,
             "cp": verdict if status in ("CONFIRMED", "CORRECTED") else post["confirmed_problem"],
             "now": stamp, "id": post_id})

        # An expert confirmation is evidence. It goes to the signal engine and,
        # when the post came from a real field, to that taluka's prior — the same
        # learning step an expert case makes, through the same door.
        if status == "CONFIRMED" and verdict and post.get("crop"):
            from .runtime import get_runtime
            get_runtime().diagnosis.bump_prior(post["taluka"], post["crop"], verdict)
        row = self.db.one("SELECT * FROM community_expert_responses WHERE id = :id", {"id": rid})
        return {"expert_response": row, "verification": verification,
                "post": self.public_post(
                    self.db.one("SELECT * FROM community_posts WHERE id=:i", {"i": post_id}),
                    user)}

    # ── moderation ─────────────────────────────────────────────────────────
    def report(self, user: dict[str, Any], target_type: str, target_id: str, reason: str,
               note: str | None = None) -> dict[str, Any]:
        if reason not in REPORT_REASONS:
            raise bad_request("bad_reason", f"'{reason}' is not a reason PRAHARI records.")
        if target_type not in ("post", "comment"):
            raise bad_request("bad_target", "You can report a post or a comment.")
        table = "community_posts" if target_type == "post" else "community_comments"
        row = self.db.one(f"SELECT * FROM {table} WHERE id = :id", {"id": target_id})
        if not row:
            raise not_found(target_type, target_id)
        if row["author_user_id"] == user["id"]:
            raise bad_request("own_content", "You cannot report your own post.")
        dup = self.db.one(
            "SELECT id FROM community_reports WHERE target_type=:tt AND target_id=:ti"
            " AND reporter_user_id=:u", {"tt": target_type, "ti": target_id, "u": user["id"]})
        if dup:
            raise conflict("already_reported",
                           "You have already reported this. A moderator will look at it.")
        post_id = target_id if target_type == "post" else row["post_id"]
        rid = "CR-" + uuid.uuid4().hex[:10].upper()
        self.db.execute(
            "INSERT INTO community_reports (id, target_type, target_id, post_id,"
            " reporter_user_id, reason, note, state, created_at)"
            " VALUES (:id,:tt,:ti,:p,:u,:r,:n,'open',:now)",
            {"id": rid, "tt": target_type, "ti": target_id, "p": post_id, "u": user["id"],
             "r": reason, "n": (note or "")[:600] or None, "now": now_iso()})
        return self._apply_report_thresholds(target_type, target_id, rid)

    def _auto_report(self, target_type: str, target_id: str, post_id: str, reason: str,
                     note: str) -> None:
        self.db.execute(
            "INSERT INTO community_reports (id, target_type, target_id, post_id,"
            " reporter_user_id, reason, note, state, created_at)"
            " SELECT :id,:tt,:ti,:p,u.id,:r,:n,'open',:now FROM users u"
            " WHERE u.role = 'admin' ORDER BY u.created_at LIMIT 1",
            {"id": "CR-" + uuid.uuid4().hex[:10].upper(), "tt": target_type, "ti": target_id,
             "p": post_id, "r": reason, "n": note, "now": now_iso()})

    def _apply_report_thresholds(self, target_type: str, target_id: str,
                                 report_id: str) -> dict[str, Any]:
        n = int(self.db.scalar(
            "SELECT COUNT(DISTINCT reporter_user_id) FROM community_reports"
            " WHERE target_type=:tt AND target_id=:ti AND state='open'",
            {"tt": target_type, "ti": target_id}) or 0)
        table = "community_posts" if target_type == "post" else "community_comments"
        self.db.execute(f"UPDATE {table} SET report_count = :n WHERE id = :id",
                        {"n": n, "id": target_id})
        action = "none"
        if target_type == "post":
            if n >= REPORTS_TO_HIDE:
                self.db.execute(
                    "UPDATE community_posts SET moderation_state='blocked', status='hidden',"
                    " moderation_note='Hidden after repeated reports — awaiting review'"
                    " WHERE id=:id", {"id": target_id})
                action = "hidden"
            elif n >= REPORTS_TO_FLAG:
                self.db.execute(
                    "UPDATE community_posts SET moderation_state='flagged' WHERE id=:id",
                    {"id": target_id})
                action = "flagged"
        elif n >= REPORTS_TO_FLAG:
            self.db.execute("UPDATE community_comments SET status='hidden' WHERE id=:id",
                            {"id": target_id})
            action = "hidden"
        return {"report_id": report_id, "reports": n, "action": action,
                "message": ("Thank you. PRAHARI does not remove a post because one person "
                            "disagrees with it — a moderator will read this.")}

    def moderation_queue(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.rows(
            "SELECT r.*, p.title, p.taluka, p.category FROM community_reports r"
            " LEFT JOIN community_posts p ON p.id = r.post_id"
            " WHERE r.state = 'open' ORDER BY r.created_at DESC LIMIT :n", {"n": limit})
        for r in rows:
            r["reason_meta"] = REPORT_REASONS.get(r["reason"], {})
        return rows

    def moderate(self, admin: dict[str, Any], report_id: str, action: str,
                 note: str | None = None) -> dict[str, Any]:
        rep = self.db.one("SELECT * FROM community_reports WHERE id = :id", {"id": report_id})
        if not rep:
            raise not_found("report", report_id)
        if action not in ("dismiss", "hide", "remove", "request_expert_correction"):
            raise bad_request("bad_action", f"'{action}' is not a moderation action.")
        table = "community_posts" if rep["target_type"] == "post" else "community_comments"
        if action == "hide":
            self.db.execute(f"UPDATE {table} SET status='hidden' WHERE id=:id",
                            {"id": rep["target_id"]})
        elif action == "remove":
            self.db.execute(f"UPDATE {table} SET status='removed' WHERE id=:id",
                            {"id": rep["target_id"]})
        elif action == "dismiss" and rep["target_type"] == "post":
            self.db.execute(
                "UPDATE community_posts SET moderation_state='ok', status='published'"
                " WHERE id=:id", {"id": rep["target_id"]})
        self.db.execute(
            "UPDATE community_reports SET state=:st, action=:a, reviewed_by=:u, reviewed_at=:now"
            " WHERE id=:id",
            {"st": "dismissed" if action == "dismiss" else "actioned", "a": action,
             "u": admin["id"], "now": now_iso(), "id": report_id})
        return {"report_id": report_id, "action": action, "note": note}

    def block(self, user: dict[str, Any], post_id: str, on: bool = True) -> dict[str, Any]:
        """Blocking is by post, never by account id — a client never learns who
        it blocked beyond 'the person who wrote that'."""
        post = self.db.one("SELECT author_user_id FROM community_posts WHERE id = :id",
                           {"id": post_id})
        if not post:
            raise not_found("post", post_id)
        if post["author_user_id"] == user["id"]:
            raise bad_request("own_content", "You cannot block yourself.")
        if on:
            self.db.execute(
                "INSERT INTO community_blocks (user_id, blocked_id, created_at)"
                " VALUES (:u,:b,:now) ON CONFLICT (user_id, blocked_id) DO NOTHING",
                {"u": user["id"], "b": post["author_user_id"], "now": now_iso()})
        else:
            self.db.execute(
                "DELETE FROM community_blocks WHERE user_id=:u AND blocked_id=:b",
                {"u": user["id"], "b": post["author_user_id"]})
        return {"blocked": on}

    def _blocked(self, user_id: str) -> set[str]:
        return {r["blocked_id"] for r in self.db.rows(
            "SELECT blocked_id FROM community_blocks WHERE user_id = :u", {"u": user_id})}

    def delete_own(self, user: dict[str, Any], post_id: str) -> dict[str, Any]:
        post = self.db.one("SELECT * FROM community_posts WHERE id = :id", {"id": post_id})
        if not post:
            raise not_found("post", post_id)
        if post["author_user_id"] != user["id"] and user["role"] != "admin":
            raise forbidden("this post")
        self.db.execute(
            "UPDATE community_posts SET status='removed', updated_at=:now WHERE id=:id",
            {"now": now_iso(), "id": post_id})
        return {"deleted": True, "id": post_id,
                "note": ("The post is withdrawn. Any cluster signal it already contributed to "
                         "keeps its count — surveillance evidence is not retracted by deleting "
                         "the message, but your text is no longer shown.")}

    def _rate_limit(self, kind: str, user_id: str, limit: int, human: str) -> None:
        table = "community_posts" if kind == "post" else "community_comments"
        since = (_today() - dt.timedelta(days=1)).isoformat()
        rows = self.db.rows(
            f"SELECT created_at FROM {table} WHERE author_user_id = :u AND created_at >= :since",
            {"u": user_id, "since": since})
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
        recent = 0
        for r in rows:
            try:
                ts = dt.datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts >= cutoff:
                recent += 1
        if recent >= limit:
            raise rate_limited(900)


def _headline(body: str) -> str:
    """A post with no title gets one from its first sentence, cut on a word
    boundary. "…same grey spreading patche" reads like a bug, because it is."""
    first = re.split(r"(?<=[.!?।])\s", body.strip())[0]
    if len(first) <= 64:
        return first
    cut = first[:64].rsplit(" ", 1)[0]
    return cut + "…"


def _band(p: float | None) -> str:
    if p is None:
        return "unknown"
    return "high" if p >= 0.7 else "moderate" if p >= 0.45 else "low"


def _recency(post: dict[str, Any]) -> float:
    age = days_ago(post.get("last_activity_at") or post.get("created_at"))
    if age is None:
        return 0.0
    return 25.0 * math.exp(-max(0, age) / 5.0)
