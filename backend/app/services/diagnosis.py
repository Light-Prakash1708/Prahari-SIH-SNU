"""
PRAHARI · the diagnosis service
════════════════════════════════════════════════════════════════════════════
DETECT, and the camera's right to refuse.

Order of operations, and it is not negotiable:

    1. QUALITY GATE   a photograph that fails is REJECTED, not diagnosed.
                      No candidate list is returned underneath an abstention
                      for a quality failure — questions cannot fix a blurred
                      photograph and offering them implies they can.
    2. CLASSIFY       whatever is configured: an ONNX model, a remote inference
                      API, or the symptom-feature likelihood. The engine that
                      ran is recorded on the row and returned to the client.
    3. COMBINE        posterior ∝ prior(taluka) × image × weather-model
    4. ABSTAIN        five separate reasons, each with its own explanation.

Nothing here converts a heuristic into "95% AI confidence". If no trained model
is configured and the feature engine is disabled, the answer is
"AI model unavailable" and the observation still gets stored, still reaches an
expert, and still contributes to surveillance.
"""
from __future__ import annotations

import uuid
from typing import Any

from .. import diagnose, loop, reference
from ..clock import now_iso
from ..db import Database, bit, dumps
from ..vision_service import VisionService


class DiagnosisService:
    def __init__(self, db: Database, vision: VisionService):
        self.db = db
        self.vision = vision

    # ── the taluka prior ───────────────────────────────────────────────────
    def prior(self, taluka: str, crop: str) -> dict[str, Any]:
        candidates = list(reference.problems_for_crop(crop).keys())
        rows = self.db.rows(
            "SELECT problem, alpha FROM priors WHERE taluka = :t AND crop = :c",
            {"t": taluka, "c": crop})
        counts = {r["problem"]: r["alpha"] - 1.0 for r in rows}
        out = diagnose.dirichlet_prior({k: int(v) for k, v in counts.items()}, candidates)
        out["confirmed_cases"] = int(sum(max(0.0, v) for v in counts.values()))
        out["note"] = (
            "Each candidate starts at α = 1 — a uniform prior that assumes nothing. Every "
            "EXPERT-CONFIRMED case in this taluka adds exactly 1. No gradient, no retraining, "
            "and an agriculture officer can audit it by counting confirmed cases.")
        return out

    def bump_prior(self, taluka: str, crop: str, problem: str) -> dict[str, Any]:
        row = self.db.one(
            "SELECT alpha FROM priors WHERE taluka=:t AND crop=:c AND problem=:p",
            {"t": taluka, "c": crop, "p": problem})
        if row:
            self.db.execute(
                "UPDATE priors SET alpha = alpha + 1, updated_at = :now"
                " WHERE taluka=:t AND crop=:c AND problem=:p",
                {"now": now_iso(), "t": taluka, "c": crop, "p": problem})
            alpha = row["alpha"] + 1
        else:
            self.db.execute(
                "INSERT INTO priors (taluka, crop, problem, alpha, updated_at)"
                " VALUES (:t,:c,:p,2.0,:now)",
                {"t": taluka, "c": crop, "p": problem, "now": now_iso()})
            alpha = 2.0
        return {"taluka": taluka, "crop": crop, "problem": problem, "alpha": alpha}

    # ── the diagnosis ──────────────────────────────────────────────────────
    def run(self, *, observation: dict[str, Any], plot: dict[str, Any],
            image_bytes: bytes, features: dict[str, Any],
            fired: dict[str, bool], weather_meta: dict[str, Any]) -> dict[str, Any]:
        crop = plot["crop"]
        taluka = plot["taluka"]
        candidates = list(reference.problems_for_crop(crop).keys())

        # 0 · a crop with no image reference set at all
        if not reference.crop_has_vision_reference(crop):
            return self._store(
                observation, plot,
                {"abstain": True, "reason": "crop-not-covered", "ranked": [],
                 "explain": (
                     "No open field-realistic image dataset exists for this crop in India, so "
                     "PRAHARI has no image reference set for it. Rather than ship a classifier "
                     "that has never seen a real photograph of this crop, the camera abstains and "
                     "the weather and threshold engines carry the advisory. That is a finding "
                     "about Indian open agricultural data, not a gap being hidden."),
                 "engine": "unavailable"},
                engine_desc={"engine": "unavailable", "label": "No image reference set for this crop",
                             "version": "n/a", "is_neural_model": False, "evaluated": False},
                prior={}, weather_meta=weather_meta, questions=[])

        # 1 · the quality gate — before anything else looks at the picture
        quality = features["quality"]
        if not quality["ok"]:
            return self._store(
                observation, plot,
                {"abstain": True, "reason": "photo-quality", "ranked": [],
                 "explain": " ".join(f["msg"] for f in quality["failures"]),
                 "explain_mr": " ".join(f.get("mr", "") for f in quality["failures"]).strip(),
                 "engine": "quality-gate"},
                engine_desc={"engine": "quality-gate",
                             "label": "Image quality gate",
                             "version": "v1", "is_neural_model": False, "evaluated": False,
                             "caveat": ("A photograph that fails the gate is never diagnosed. "
                                        "No candidate list is shown, because a differential drawn "
                                        "from an unreadable image is worse than none.")},
                prior={}, weather_meta=weather_meta, questions=[], quality=quality)

        # 2 · classify
        result = self.vision.classify(image_bytes, crop, candidates)
        engine_desc = self.vision.engine_descriptor(result)

        if result.probs is None and not self.vision.feature_engine_allowed:
            return self._store(
                observation, plot,
                {"abstain": True, "reason": "model-unavailable", "ranked": [],
                 "explain": ("AI model unavailable. No trained image model is configured on this "
                             "instance and the symptom-feature engine is switched off, so PRAHARI "
                             "will not offer an image-based diagnosis. Your observation has been "
                             "recorded and can be sent to an expert."),
                 "engine": "unavailable"},
                engine_desc=engine_desc, prior={}, weather_meta=weather_meta,
                questions=[], quality=quality)

        prior = self.prior(taluka, crop)
        dx = diagnose.diagnose(features, crop, prior["p"],
                               reference.problems_for_crop(crop), fired, result.probs)
        dx["engine"] = result.engine if result.probs is not None else "features"

        questions = ([] if dx.get("reason") in ("photo-quality", "unfamiliar-pattern",
                                                "crop-not-covered", "model-unavailable")
                     else loop.pick_questions(dx["ranked"], dx["reason"]) if dx["ranked"] else [])
        return self._store(observation, plot, dx, engine_desc=engine_desc, prior=prior,
                           weather_meta=weather_meta, questions=questions, quality=quality,
                           model_version=result.model_version)

    # ── persistence ────────────────────────────────────────────────────────
    def _store(self, observation, plot, dx, *, engine_desc, prior, weather_meta,
               questions, quality: dict[str, Any] | None = None,
               model_version: str | None = None) -> dict[str, Any]:
        did = "D-" + uuid.uuid4().hex[:12].upper()
        ranked = dx.get("ranked") or []
        top = ranked[0] if ranked and not dx.get("abstain") else None
        evidence = self._evidence(dx, quality)
        self.db.execute(
            "INSERT INTO diagnoses (id, observation_id, plot_id, crop, engine, model_version,"
            " top_problem, top_posterior, margin, abstained, abstain_reason, explain, evidence,"
            " prior_used, weather_used, created_at)"
            " VALUES (:id,:obs,:plot,:crop,:eng,:mv,:tp,:post,:margin,:abs,:reason,:explain,"
            " :ev,:prior,:wx,:now)",
            {"id": did, "obs": observation["id"], "plot": plot["id"], "crop": plot["crop"],
             "eng": engine_desc["engine"],
             "mv": model_version or engine_desc.get("version"),
             "tp": top["id"] if top else None,
             "post": top["posterior"] if top else None,
             "margin": dx.get("margin"),
             "abs": bit(dx.get("abstain")), "reason": dx.get("reason"),
             "explain": dx.get("explain"), "ev": dumps(evidence),
             "prior": dumps(prior), "wx": dumps(weather_meta), "now": now_iso()})

        for i, r in enumerate(ranked):
            support, against = self._support(r, dx)
            self.db.execute(
                "INSERT INTO diagnosis_candidates (diagnosis_id, rank, problem, posterior, prior,"
                " image_fit, weather_factor, supporting, contradicting)"
                " VALUES (:d,:r,:p,:post,:prior,:img,:wx,:sup,:con)",
                {"d": did, "r": i + 1, "p": r["id"], "post": r["posterior"],
                 "prior": r.get("prior"), "img": r.get("image"), "wx": r.get("weather"),
                 "sup": dumps(support), "con": dumps(against)})

        return {
            "diagnosis_id": did,
            "abstain": bool(dx.get("abstain")),
            "reason": dx.get("reason"),
            "explain": dx.get("explain"),
            "explain_mr": dx.get("explain_mr"),
            "engine": engine_desc,
            "differential": self._differential(ranked, dx),
            "top": (self._candidate_view(ranked[0], dx) if top else None),
            "margin": dx.get("margin"),
            "floors": dx.get("floors"),
            "prior": prior,
            "questions": questions,
            "quality": quality,
            "evidence": evidence,
        }

    def _differential(self, ranked: list[dict], dx: dict[str, Any]) -> list[dict[str, Any]]:
        """Always a differential, never a single answer. Shown even when the
        engine abstains for ambiguity — the farmer deserves to see WHAT it is
        torn between — but never under a quality failure."""
        if dx.get("reason") in ("photo-quality", "crop-not-covered", "model-unavailable"):
            return []
        return [self._candidate_view(r, dx) for r in ranked[:3]]

    def _candidate_view(self, r: dict, dx: dict[str, Any]) -> dict[str, Any]:
        support, against = self._support(r, dx)
        p = reference.problem(r["id"]) or {}
        return {
            "id": r["id"], "name": r.get("name") or p.get("name"),
            "name_mr": r.get("name_mr") or p.get("mr"), "em": r.get("em") or p.get("em"),
            "sci": r.get("sci") or p.get("sci"),
            "confidence": round(r["posterior"], 4),
            "confidence_pct": round(r["posterior"] * 100),
            "prior": r.get("prior"), "image_fit": r.get("image"),
            "weather_factor": r.get("weather"),
            "supporting": support, "contradicting": against,
        }

    def _support(self, r: dict, dx: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """Plain-language evidence for and against, derived from the same three
        terms the posterior was built from. No new facts are introduced here.

        Bilingual, because this is the part of the screen a Marathi-reading
        farmer is most likely to actually weigh. The Marathi is written
        alongside the English, not machine-translated at request time."""
        sup, con = [], []
        img, prior, wx = r.get("image") or 0, r.get("prior") or 0, r.get("weather") or 1.0
        floor = dx.get("ood_floor", 0.12)
        if img >= max(0.28, floor * 2.0):
            sup.append({
                "en": f"the measured leaf features fit this pattern well ({img*100:.0f}% fit)",
                "mr": f"पानावर मोजलेली लक्षणे या रोगाशी चांगली जुळतात ({img*100:.0f}%)"})
        elif img < floor:
            con.append({
                "en": (f"the measured leaf features do not fit this pattern ({img*100:.1f}% fit, "
                       f"below the {floor*100:.0f}% floor)"),
                "mr": (f"पानावर मोजलेली लक्षणे या रोगाशी जुळत नाहीत ({img*100:.1f}%, "
                       f"किमान {floor*100:.0f}% हवे)")})
        if wx > 1.2:
            sup.append({
                "en": "this problem's published infection model has fired on current weather",
                "mr": "सध्याच्या हवामानावर या रोगाचे प्रकाशित संसर्ग मॉडेल सक्रिय झाले आहे"})
        elif wx < 0.9:
            con.append({
                "en": "this problem's infection model has not fired on current weather",
                "mr": "सध्याच्या हवामानावर या रोगाचे संसर्ग मॉडेल सक्रिय झालेले नाही"})
        if prior > 0.3:
            sup.append({
                "en": (f"expert-confirmed cases of this problem in this taluka raise its prior "
                       f"to {prior*100:.0f}%"),
                "mr": (f"या तालुक्यात तज्ज्ञांनी निश्चित केलेल्या प्रकरणांमुळे याची शक्यता "
                       f"{prior*100:.0f}% पर्यंत वाढते")})
        return sup, con

    def _evidence(self, dx: dict[str, Any], quality: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "top_fit": dx.get("top_fit"), "best_fit": dx.get("best_fit"),
            "best_fitting": dx.get("best_fitting"), "ood_floor": dx.get("ood_floor"),
            "quality_checks": (quality or {}).get("checks"),
        }

    # ── contextual questions ───────────────────────────────────────────────
    def answer(self, diagnosis_id: str, answers: dict[str, str]) -> dict[str, Any]:
        dx = self.db.one("SELECT * FROM diagnoses WHERE id = :id", {"id": diagnosis_id})
        if not dx:
            return {}
        if dx["abstain_reason"] in ("photo-quality", "crop-not-covered", "model-unavailable"):
            # A quality failure cannot be talked out of. This is the safety rule
            # from the abstention design, enforced rather than described.
            return {
                "blocked": True,
                "reason": dx["abstain_reason"],
                "message": ("The photograph itself is the blocker, so answering questions cannot "
                            "produce a diagnosis. Take the picture again following the guidance, "
                            "or send the case to an expert."),
                "message_mr": ("अडचण फोटोमध्येच आहे, त्यामुळे प्रश्नांची उत्तरे दिल्याने निदान होणार नाही. "
                               "पुन्हा फोटो काढा किंवा तज्ज्ञांकडे पाठवा."),
            }
        rows = self.db.rows(
            "SELECT * FROM diagnosis_candidates WHERE diagnosis_id = :d ORDER BY rank",
            {"d": diagnosis_id})
        ranked = [{"id": r["problem"], "posterior": r["posterior"],
                   "prior": r["prior"], "image": r["image_fit"], "weather": r["weather_factor"],
                   "name": reference.problem_name(r["problem"]),
                   "name_mr": reference.problem_name(r["problem"], "mr"),
                   "em": (reference.problem(r["problem"]) or {}).get("em")}
                  for r in rows]
        if not ranked:
            return {}
        out = loop.apply_answers(ranked, answers)
        stamp = now_iso()
        for qid, val in (answers or {}).items():
            q = loop.QUESTION_BY_ID.get(qid)
            if not q:
                continue
            opt = next((o for o in q["options"] if o["v"] == val), None)
            self.db.execute(
                "INSERT INTO diagnosis_context (diagnosis_id, question_id, question, answer,"
                " answer_label, effect, answered_at)"
                " VALUES (:d,:qid,:q,:a,:al,:e,:now)",
                {"d": diagnosis_id, "qid": qid, "q": q["q"], "a": val,
                 "al": (opt or {}).get("t"),
                 "e": dumps((opt or {}).get("boost")), "now": stamp})

        new_top = out["ranked"][0]
        decisive = (new_top["posterior"] >= diagnose.POSTERIOR_FLOOR and
                    new_top["posterior"] - out["ranked"][1]["posterior"] >= diagnose.MARGIN_FLOOR
                    if len(out["ranked"]) > 1 else new_top["posterior"] >= diagnose.POSTERIOR_FLOOR)
        if decisive:
            self.db.execute(
                "UPDATE diagnoses SET abstained = 0, abstain_reason = NULL, top_problem = :p,"
                " top_posterior = :post, explain = :ex WHERE id = :id",
                {"p": new_top["id"], "post": new_top["posterior"],
                 "ex": ("Settled by the farmer's answers to contextual questions, which re-weighted "
                        "the candidates the image had already ranked."),
                 "id": diagnosis_id})
        for i, r in enumerate(out["ranked"]):
            self.db.execute(
                "UPDATE diagnosis_candidates SET rank = :r, posterior = :p"
                " WHERE diagnosis_id = :d AND problem = :prob",
                {"r": i + 1, "p": r["posterior"], "d": diagnosis_id, "prob": r["id"]})
        return {
            "blocked": False,
            "decisive": decisive,
            "shifted": out["shifted"],
            "moves": out["moves"],
            "differential": [self._candidate_view(r, {"ood_floor": diagnose.OOD_FLOOR})
                             for r in out["ranked"][:3]],
            "top": self._candidate_view(out["ranked"][0], {"ood_floor": diagnose.OOD_FLOOR}),
            "note": ("Answers re-weight candidates the image already ranked. They can never "
                     "introduce a candidate the photograph did not see, and they can never lift "
                     "confidence past the same 99% cap the diagnosis itself respects."),
        }

    # ── follow-up comparison ───────────────────────────────────────────────
    def compare(self, before_features: dict[str, Any],
                after_features: dict[str, Any]) -> dict[str, Any]:
        out = loop.compare_scans(before_features, after_features)
        out["severity_percentages"] = None
        out["why_no_percentage"] = (
            "These are two hand-held photographs of different leaves in different light. The "
            "DIRECTION of change survives that; a percentage does not. PRAHARI reports direction "
            "and says so rather than inventing '38% → 21%'.")
        return out
