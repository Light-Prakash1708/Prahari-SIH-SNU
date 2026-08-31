"""
PRAHARI · the signal engine
════════════════════════════════════════════════════════════════════════════
Where the community stops being a conversation and becomes surveillance.

The engine reads five independent evidence streams for one (taluka, problem)
pair inside a window:

    1. community posts        farmers describing the same thing
    2. same-problem votes     "I am seeing this too", from OTHER accounts
    3. PRAHARI diagnoses      a photograph, a model, a posterior
    4. expert responses       a named expert confirming
    5. traps and officers     a count over the economic threshold, a visit

and grades what it finds:

    possible_cluster        several INDEPENDENT farmers in one taluka saying
                            the same thing. Independent means distinct accounts
                            — one farmer posting four times is one farmer.
    corroborated_signal     the above, PLUS at least one piece of evidence that
                            is not conversation: a diagnosis, a trap count over
                            threshold, or an expert confirmation.
    confirmed_field_signal  an officer went and looked, and said yes.

The word "outbreak" does not appear in any grade, and never will. That word
belongs to outbreak_events, which requires expert-confirmed DIAGNOSES, and it
moves budgets and triggers state advisories. Three people worried about the
same yellow leaf is a lead, not an outbreak, and a system that cannot tell the
difference will be believed exactly once.

The alert this engine sends to nearby farmers says "three fields in your taluka"
and never says whose. See alert() — it addresses farmers by their OWN plots and
carries no identity from the posts at all.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from . import reference
from .clock import now_iso
from .clock import today as _today
from .db import Database, dumps

GRADES: dict[str, dict[str, Any]] = {
    "possible_cluster": {
        "label": "Possible cluster",
        "label_mr": "संभाव्य समूह",
        "tone": "info", "rank": 1,
        "means": ("Several different farmers in this taluka have described the same problem. "
                  "Nobody has verified any of them yet."),
        "means_mr": ("या तालुक्यातील अनेक वेगवेगळ्या शेतकऱ्यांनी हीच समस्या नोंदवली आहे. "
                     "अजून कोणीही तपासणी केलेली नाही."),
    },
    "corroborated_signal": {
        "label": "Corroborated signal",
        "label_mr": "पुष्टी मिळालेला संकेत",
        "tone": "warn", "rank": 2,
        "means": ("The reports are backed by evidence that is not conversation — a PRAHARI "
                  "diagnosis, a trap count over the economic threshold, or an expert's verdict."),
        "means_mr": ("या नोंदींना संभाषणाबाहेरचा पुरावा आहे — प्रहरीचे निदान, पातळीवरील सापळा "
                     "मोजणी, किंवा तज्ज्ञांचा निर्णय."),
    },
    "confirmed_field_signal": {
        "label": "Confirmed field signal",
        "label_mr": "पडताळणी झालेला संकेत",
        "tone": "bad", "rank": 3,
        "means": "An agriculture officer inspected a field and confirmed it on the ground.",
        "means_mr": "कृषी अधिकाऱ्याने शेतात जाऊन प्रत्यक्ष खात्री केली आहे.",
    },
}

WINDOW_DAYS = 14
POST_FLOOR = 3          # posts describing the same thing
AUTHOR_FLOOR = 2        # distinct accounts — one farmer posting thrice is one farmer
VILLAGE_FLOOR = 1

NOT_AN_OUTBREAK = (
    "This is a SIGNAL, not an outbreak. PRAHARI grades what farmers report separately from what "
    "has been verified: an outbreak declaration needs expert-confirmed diagnoses and lives in the "
    "surveillance panel, not here.")


class SignalEngine:
    def __init__(self, db: Database):
        self.db = db

    # ── evidence ───────────────────────────────────────────────────────────
    def _posts(self, taluka: str, problem: str, crop: str | None,
               days: int) -> list[dict[str, Any]]:
        since = (_today() - dt.timedelta(days=days)).isoformat()
        sql = ("SELECT id, author_user_id, village, crop, category, observed_on,"
               " suspected_problem, confirmed_problem, same_problem_count, verification, created_at"
               " FROM community_posts WHERE status = 'published' AND signal_eligible = 1"
               " AND moderation_state <> 'blocked' AND taluka = :t"
               " AND substr(created_at,1,10) >= :since"
               " AND (suspected_problem = :p OR confirmed_problem = :p)")
        params: dict[str, Any] = {"t": taluka, "p": problem, "since": since}
        if crop:
            sql += " AND crop = :crop"
            params["crop"] = crop
        return self.db.rows(sql + " ORDER BY created_at", params)

    def _votes(self, post_ids: list[str], authors: set[str]) -> int:
        """"I have this too", counted only from accounts that did not write the
        posts. A ring of one farmer agreeing with themselves is not evidence."""
        if not post_ids:
            return 0
        keys = {f"p{i}": pid for i, pid in enumerate(post_ids)}
        rows = self.db.rows(
            "SELECT DISTINCT user_id FROM community_reactions WHERE kind = 'same_problem'"
            " AND target_type = 'post' AND target_id IN ("
            + ",".join(f":{k}" for k in keys) + ")", keys)
        return len({r["user_id"] for r in rows} - authors)

    def _diagnoses(self, taluka: str, problem: str, crop: str | None, days: int) -> int:
        since = (_today() - dt.timedelta(days=days)).isoformat()
        sql = ("SELECT COUNT(*) FROM observations o JOIN diagnoses d ON d.observation_id = o.id"
               " WHERE o.taluka = :t AND substr(o.observed_at,1,10) >= :since"
               " AND o.status <> 'rejected' AND d.abstained = 0"
               " AND (d.top_problem = :p OR d.confirmed = :p)")
        params: dict[str, Any] = {"t": taluka, "p": problem, "since": since}
        if crop:
            sql += " AND o.crop = :crop"
            params["crop"] = crop
        return int(self.db.scalar(sql, params) or 0)

    def _expert_confirmations(self, post_ids: list[str], taluka: str, problem: str,
                              days: int) -> int:
        n = 0
        if post_ids:
            keys = {f"p{i}": pid for i, pid in enumerate(post_ids)}
            n += int(self.db.scalar(
                "SELECT COUNT(*) FROM community_expert_responses WHERE status = 'CONFIRMED'"
                " AND verdict_problem = :prob AND post_id IN ("
                + ",".join(f":{k}" for k in keys) + ")", {**keys, "prob": problem}) or 0)
        since = (_today() - dt.timedelta(days=days)).isoformat()
        n += int(self.db.scalar(
            "SELECT COUNT(*) FROM expert_cases WHERE taluka = :t AND verdict = :p"
            " AND status = 'verified' AND substr(submitted_at,1,10) >= :since",
            {"t": taluka, "p": problem, "since": since}) or 0)
        return n

    def _trap_signals(self, taluka: str, problem: str, days: int) -> int:
        """A trap count that crossed the economic threshold is hard evidence for a
        PEST. For a disease there is no trap, and this term is simply zero — it
        is not filled in with something else."""
        if problem not in reference.PESTS:
            return 0
        since = (_today() - dt.timedelta(days=days)).isoformat()
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM threshold_checks tc JOIN plots p ON p.id = tc.plot_id"
            " WHERE p.taluka = :t AND tc.pest = :p AND tc.checked_on >= :since"
            " AND tc.chemical_authorised = 1",
            {"t": taluka, "p": problem, "since": since}) or 0)

    def _officer_confirmations(self, taluka: str, problem: str, days: int) -> int:
        since = (_today() - dt.timedelta(days=days)).isoformat()
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM assignments a WHERE a.taluka = :t AND a.status = 'closed'"
            " AND lower(coalesce(a.finding,'')) LIKE :like"
            " AND substr(a.assigned_at,1,10) >= :since",
            {"t": taluka, "like": f"%{reference.problem_name(problem).lower()}%",
             "since": since}) or 0)

    # ── the assessment ─────────────────────────────────────────────────────
    def assess(self, taluka: str, problem: str, *, crop: str | None = None,
               days: int = WINDOW_DAYS, persist: bool = True) -> dict[str, Any]:
        posts = self._posts(taluka, problem, crop, days)
        authors = {p["author_user_id"] for p in posts}
        villages = {p["village"] for p in posts if p["village"]}
        votes = self._votes([p["id"] for p in posts], authors)
        diagnoses = self._diagnoses(taluka, problem, crop, days)
        confirmations = self._expert_confirmations([p["id"] for p in posts], taluka, problem, days)
        traps = self._trap_signals(taluka, problem, days)
        officers = self._officer_confirmations(taluka, problem, days)

        existing = self.db.one(
            "SELECT * FROM community_cluster_signals WHERE taluka=:t AND problem=:p"
            " AND crop=:c AND state='open'",
            {"t": taluka, "p": problem, "c": crop or ""})

        evidence: list[dict[str, Any]] = []
        grade: str | None = None

        corroborating = len(posts) + votes
        if len(posts) >= POST_FLOOR and len(authors) >= AUTHOR_FLOOR:
            grade = "possible_cluster"
            evidence.append({
                "stream": "community",
                "detail": (f"{len(posts)} posts from {len(authors)} different farmers in "
                           f"{len(villages) or 1} village(s) over {days} days "
                           f"(floor: {POST_FLOOR} posts from {AUTHOR_FLOOR} farmers)")})
            if votes:
                evidence.append({"stream": "corroboration",
                                 "detail": f"{votes} other farmer(s) marked 'I am seeing this too'"})
        else:
            evidence.append({
                "stream": "community",
                "detail": (f"{len(posts)} post(s) from {len(authors)} farmer(s) — below the "
                           f"{POST_FLOOR}-post, {AUTHOR_FLOOR}-farmer floor. PRAHARI does not "
                           f"call this a cluster.")})

        hard = []
        if diagnoses:
            hard.append({"stream": "diagnosis",
                         "detail": f"{diagnoses} PRAHARI diagnosis(es) of {reference.problem_name(problem)} "
                                   f"in this taluka in the same window"})
        if confirmations:
            hard.append({"stream": "expert",
                         "detail": f"{confirmations} expert confirmation(s)"})
        if traps:
            hard.append({"stream": "trap",
                         "detail": f"{traps} trap count(s) over the economic threshold"})
        if grade and hard:
            grade = "corroborated_signal"
            evidence.extend(hard)
        elif grade:
            evidence.append({"stream": "corroboration",
                             "detail": ("No diagnosis, trap count or expert verdict backs these "
                                        "reports yet — so this stays a possible cluster.")})

        officer_confirmed = bool(existing and existing["confirmed_at"]) or officers > 0
        if grade and officer_confirmed:
            grade = "confirmed_field_signal"
            evidence.append({
                "stream": "officer",
                "detail": (existing.get("officer_note") if existing and existing.get("officer_note")
                           else f"{officers} closed field visit(s) recording this problem")})

        out = {
            "taluka": taluka, "taluka_name": reference.taluka_name(taluka),
            "district": "Nashik",
            "problem": problem, "problem_name": reference.problem_name(problem),
            "problem_name_mr": reference.problem_name(problem, "mr"),
            "crop": crop, "window_days": days,
            "grade": grade, **(GRADES.get(grade) if grade else
                               {"label": "No cluster", "label_mr": "समूह नाही",
                                "tone": "grey", "rank": 0,
                                "means": "Not enough independent reports to call this anything.",
                                "means_mr": "पुरेशा स्वतंत्र नोंदी नाहीत."}),
            "counts": {
                "community_posts": len(posts), "distinct_farmers": len(authors),
                "distinct_villages": len(villages), "same_problem_votes": votes,
                "diagnoses": diagnoses, "expert_confirmations": confirmations,
                "trap_signals": traps, "officer_confirmations": officers,
                "corroborating_voices": corroborating,
            },
            "evidence": evidence,
            "what_this_is_not": NOT_AN_OUTBREAK,
            "privacy": ("This count is an aggregate. PRAHARI does not tell you which fields, which "
                        "farmers, or where — only how many, and in which taluka."),
            "recommended_action": _action(grade),
        }
        if persist and grade:
            out["id"] = self._persist(out, existing)
        elif persist and existing and not grade:
            self.db.execute(
                "UPDATE community_cluster_signals SET state='closed', updated_at=:now"
                " WHERE id=:id", {"now": now_iso(), "id": existing["id"]})
        return out

    def _persist(self, a: dict[str, Any], existing: dict[str, Any] | None) -> str:
        stamp = now_iso()
        day = _today().isoformat()
        c = a["counts"]
        params = {
            "n": c["community_posts"], "au": c["distinct_farmers"],
            "vi": c["distinct_villages"], "vo": c["same_problem_votes"],
            "dx": c["diagnoses"], "ec": c["expert_confirmations"],
            "tr": c["trap_signals"], "oc": c["officer_confirmations"],
            "grade": a["grade"], "ev": dumps(a["evidence"]), "win": a["window_days"],
            "now": stamp,
        }
        if existing:
            self.db.execute(
                "UPDATE community_cluster_signals SET grade=:grade, community_posts_n=:n,"
                " distinct_authors=:au, distinct_villages=:vi, same_problem_votes=:vo,"
                " diagnoses_n=:dx, expert_confirmations=:ec, trap_signals=:tr,"
                " officer_confirmations=:oc, evidence=:ev, window_days=:win,"
                " last_seen_on=:day, updated_at=:now WHERE id=:id",
                {**params, "day": day, "id": existing["id"]})
            return existing["id"]
        sid = "CS-" + uuid.uuid4().hex[:10].upper()
        self.db.execute(
            "INSERT INTO community_cluster_signals (id, taluka, district, crop, problem, grade,"
            " community_posts_n, distinct_authors, distinct_villages, same_problem_votes,"
            " diagnoses_n, expert_confirmations, trap_signals, officer_confirmations, evidence,"
            " window_days, state, first_seen_on, last_seen_on, created_at, updated_at)"
            " VALUES (:id,:t,'Nashik',:crop,:p,:grade,:n,:au,:vi,:vo,:dx,:ec,:tr,:oc,:ev,:win,"
            " 'open',:day,:day,:now,:now)",
            {**params, "id": sid, "t": a["taluka"], "crop": a["crop"] or "",
             "p": a["problem"], "day": day})
        return sid

    # ── sweeping the district ──────────────────────────────────────────────
    def sweep(self, *, days: int = WINDOW_DAYS,
              talukas: list[str] | None = None) -> list[dict[str, Any]]:
        """Recompute every (taluka, problem) pair that has any community activity.
        Cheap because the candidate set comes from the posts themselves rather
        than from the cross product of talukas and problems."""
        since = (_today() - dt.timedelta(days=days)).isoformat()
        pairs = self.db.rows(
            "SELECT taluka, coalesce(confirmed_problem, suspected_problem) AS problem,"
            " coalesce(crop,'') AS crop, COUNT(*) AS n FROM community_posts"
            " WHERE status='published' AND signal_eligible = 1 AND substr(created_at,1,10) >= :s"
            " AND coalesce(confirmed_problem, suspected_problem) IS NOT NULL"
            " GROUP BY taluka, coalesce(confirmed_problem, suspected_problem), coalesce(crop,'')",
            {"s": since})
        out = []
        for p in pairs:
            if talukas is not None and p["taluka"] not in talukas:
                continue
            a = self.assess(p["taluka"], p["problem"], crop=p["crop"] or None, days=days)
            if a["grade"]:
                out.append(a)
        out.sort(key=lambda x: (-x["rank"], -x["counts"]["community_posts"]))
        return out

    def open_signals(self, talukas: list[str] | None = None) -> list[dict[str, Any]]:
        rows = self.db.rows(
            "SELECT * FROM community_cluster_signals WHERE state = 'open'"
            " ORDER BY updated_at DESC")
        out = []
        for r in rows:
            if talukas is not None and r["taluka"] not in talukas:
                continue
            r["taluka_name"] = reference.taluka_name(r["taluka"])
            r["problem_name"] = reference.problem_name(r["problem"])
            r["problem_name_mr"] = reference.problem_name(r["problem"], "mr")
            r.update({k: v for k, v in GRADES.get(r["grade"], {}).items() if k != "rank"})
            r["rank"] = GRADES.get(r["grade"], {}).get("rank", 0)
            r["what_this_is_not"] = NOT_AN_OUTBREAK
            out.append(r)
        out.sort(key=lambda x: (-x["rank"], str(x["updated_at"])), reverse=False)
        return sorted(out, key=lambda x: -x["rank"])

    # ── the officer's verdict ──────────────────────────────────────────────
    def officer_confirm(self, signal_id: str, officer_user: dict[str, Any], *,
                        confirmed: bool, note: str) -> dict[str, Any]:
        row = self.db.one("SELECT * FROM community_cluster_signals WHERE id = :id",
                          {"id": signal_id})
        if row is None:
            from .errors import not_found
            raise not_found("signal", signal_id)
        stamp = now_iso()
        if confirmed:
            self.db.execute(
                "UPDATE community_cluster_signals SET grade='confirmed_field_signal',"
                " confirmed_by=:u, confirmed_at=:now, officer_note=:n,"
                " officer_confirmations = officer_confirmations + 1, updated_at=:now"
                " WHERE id=:id",
                {"u": officer_user["id"], "now": stamp, "n": note[:600], "id": signal_id})
        else:
            self.db.execute(
                "UPDATE community_cluster_signals SET state='dismissed', officer_note=:n,"
                " confirmed_by=:u, updated_at=:now WHERE id=:id",
                {"n": note[:600], "u": officer_user["id"], "now": stamp, "id": signal_id})
        return {"signal_id": signal_id, "confirmed": confirmed, "note": note,
                "grade": "confirmed_field_signal" if confirmed else "dismissed",
                "effect": ("Farmers in this taluka growing this crop will be told that a field "
                           "signal has been confirmed. They are not told whose fields."
                           if confirmed else
                           "The signal is closed. The posts stay; the cluster claim does not.")}

    # ── telling nearby farmers, without telling them who ───────────────────
    def alert(self, signal: dict[str, Any]) -> dict[str, Any]:
        """Spec §14. The message is built from COUNTS. It carries no post id, no
        village at house level, no name — a farmer learns that three fields in
        their taluka have this, not which three."""
        from .runtime import get_runtime
        rt = get_runtime()
        row = self.db.one("SELECT * FROM community_cluster_signals WHERE id = :id",
                          {"id": signal.get("id")}) if signal.get("id") else None
        if row and row["alerted_at"] and row["grade"] != "confirmed_field_signal":
            return {"sent": 0, "reason": "already_alerted"}
        if (GRADES.get(signal["grade"], {}).get("rank", 0)) < 2:
            return {"sent": 0, "reason": "below_alert_threshold",
                    "note": ("A possible cluster is not alerted to a whole taluka. Farmers are "
                             "warned when something outside the conversation corroborates it.")}
        crop = signal.get("crop")
        sql = ("SELECT DISTINCT f.user_id, p.id AS plot_id FROM plots p"
               " JOIN farmers f ON f.id = p.farmer_id"
               " WHERE p.taluka = :t AND p.archived = 0")
        params: dict[str, Any] = {"t": signal["taluka"]}
        if crop:
            sql += " AND p.crop = :c"
            params["c"] = crop
        targets = self.db.rows(sql, params)
        name = signal["problem_name"]
        title = f"{signal['label']} — {name} in {signal['taluka_name']}"
        body = (f"{signal['counts']['distinct_farmers']} different farmers in "
                f"{signal['taluka_name']} have reported {name} in the last "
                f"{signal['window_days']} days, and {_hard_phrase(signal)}. "
                f"Scout your own field this week before you decide anything. "
                f"PRAHARI does not say which fields these are.")
        sent = 0
        for t in targets:
            rt.notify.push(user_id=t["user_id"], plot_id=t["plot_id"],
                           kind="community_signal",
                           severity="rising" if signal["rank"] == 2 else "high",
                           title=title, body=body,
                           title_mr=f"{signal['label_mr']} — {signal['problem_name_mr']}",
                           body_mr=(f"{signal['taluka_name']} मध्ये गेल्या {signal['window_days']} "
                                    f"दिवसांत {signal['counts']['distinct_farmers']} शेतकऱ्यांनी "
                                    f"{signal['problem_name_mr']} नोंदवले आहे. या आठवड्यात "
                                    f"स्वतःचे शेत तपासा."))
            sent += 1
        if row:
            self.db.execute(
                "UPDATE community_cluster_signals SET alerted_at = :now WHERE id = :id",
                {"now": now_iso(), "id": row["id"]})
        return {"sent": sent, "title": title, "body": body,
                "privacy": "Recipients are chosen by their OWN field's taluka and crop. "
                           "No identity from the reporting posts is used or disclosed."}


def _hard_phrase(signal: dict[str, Any]) -> str:
    c = signal["counts"]
    bits = []
    if c["diagnoses"]:
        bits.append(f"{c['diagnoses']} photograph(s) diagnosed by PRAHARI")
    if c["expert_confirmations"]:
        bits.append(f"{c['expert_confirmations']} expert confirmation(s)")
    if c["trap_signals"]:
        bits.append(f"{c['trap_signals']} trap count(s) over the threshold")
    if c["officer_confirmations"]:
        bits.append("an officer has confirmed it in a field")
    return " and ".join(bits) if bits else "it has not been corroborated yet"


def _action(grade: str | None) -> str:
    return {
        None: "Nothing to act on. Routine scouting.",
        "possible_cluster": ("Ask an officer to look at two of these fields, or ask an expert to "
                             "answer the posts. Until someone does, this is a conversation."),
        "corroborated_signal": ("Warn farmers in this taluka to scout. Do NOT issue a spray "
                                "advisory — a signal is not a threshold crossing, and the "
                                "threshold is per field."),
        "confirmed_field_signal": ("Brief the Krishi Sahayaks for this taluka, raise scouting "
                                   "frequency in neighbouring talukas, and check whether the "
                                   "surveillance panel now has enough confirmed diagnoses to "
                                   "open a graded outbreak event."),
    }[grade]
