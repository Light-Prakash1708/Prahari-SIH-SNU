"""
PRAHARI · the vision service
════════════════════════════════════════════════════════════════════════════
Two layers, and the distinction between them is the point.

  MEASUREMENT (vision.py, unchanged)
      Leaf segmentation and explicit symptom features — necrotic / chlorotic /
      powdery / dark fraction, lesion count, border sharpness, spread. Every
      number is inspectable and an agronomist can argue with it. This layer
      also runs the QUALITY GATE, and a photograph that fails the gate is never
      diagnosed by anything.

  CLASSIFICATION (this module)
      Whatever actually produces class probabilities:

        onnx      a fine-tuned model exported to ONNX, loaded locally
        api       a secure external inference endpoint
        none      no model is configured

Honesty rules that are enforced here, not documented and forgotten:

  · The symptom-feature engine is NEVER labelled AI, neural, or CNN. It is
    reported as `features` with a display name that says what it is.
  · When VISION_PROVIDER=none and ALLOW_FEATURE_ENGINE=false, the service
    reports `unavailable` and the API returns "AI model unavailable" rather
    than dressing heuristics up as inference.
  · Every diagnosis records the engine and model version that produced it, and
    the API returns both.
  · No accuracy figure is reported anywhere unless an evaluation actually
    produced it and wrote it into model_versions.metrics.
"""
from __future__ import annotations

import builtins
import io
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .clock import now_iso
from .config import Settings, get_settings

log = logging.getLogger("prahari.vision")


@dataclass
class ClassifierResult:
    """probs maps problem_id -> probability, or is None when no model ran."""
    probs: builtins.dict[str, float] | None
    engine: str                     # onnx | api | features | unavailable
    model_name: str
    model_version: str
    display: str                    # what the UI is allowed to call it
    is_neural: bool
    latency_ms: int = 0
    note: str = ""
    error: str | None = None
    metrics: builtins.dict[str, Any] | None = field(default=None)

    def dict(self) -> builtins.dict[str, Any]:
        return {
            "engine": self.engine, "model": self.model_name, "version": self.model_version,
            "display": self.display, "is_neural_model": self.is_neural,
            "latency_ms": self.latency_ms, "note": self.note, "error": self.error,
            "evaluation": self.metrics,
        }


class Classifier:
    engine = "unavailable"

    def ready(self) -> bool:
        return False

    def predict(self, image_bytes: bytes, crop: str,
                candidates: list[str]) -> ClassifierResult:
        raise NotImplementedError

    def info(self) -> dict[str, Any]:
        return {"engine": self.engine, "ready": self.ready()}


class NoModel(Classifier):
    engine = "unavailable"

    def __init__(self, reason: str):
        self.reason = reason

    def predict(self, image_bytes, crop, candidates):
        return ClassifierResult(
            probs=None, engine="unavailable", model_name="none", model_version="none",
            display="AI model unavailable", is_neural=False,
            note=self.reason,
            error="vision_model_unavailable")

    def info(self):
        return {"engine": "unavailable", "ready": False, "reason": self.reason}


class OnnxClassifier(Classifier):
    """A locally loaded ONNX model.

    Expected export contract (see ml/export_onnx.py):
      input   float32 [1, 3, H, W], ImageNet-normalised RGB
      output  float32 [1, C] logits
      labels  a JSON file listing the C class ids in output order, using the
              same problem ids as backend/data/problems.json

    Classes the model knows but this crop cannot have are dropped and the
    remaining mass renormalised, so a tomato photograph is never scored against
    a grape disease.
    """
    engine = "onnx"

    def __init__(self, settings: Settings):
        self.s = settings
        self.session = None
        self.labels: list[str] = []
        self.input_name = ""
        self.input_hw = (224, 224)
        self._lock = threading.Lock()
        self._error: str | None = None
        self._load()

    def _load(self) -> None:
        path = Path(self.s.vision_model_path or "")
        if not path.exists():
            self._error = f"VISION_MODEL_PATH does not exist: {path}"
            log.error("onnx model missing", extra={"path": str(path)})
            return
        try:
            import onnxruntime as ort
        except ImportError as exc:
            self._error = f"onnxruntime is not installed: {exc}"
            return
        try:
            so = ort.SessionOptions()
            so.log_severity_level = 3
            self.session = ort.InferenceSession(str(path), so,
                                                providers=["CPUExecutionProvider"])
            inp = self.session.get_inputs()[0]
            self.input_name = inp.name
            shape = inp.shape
            if len(shape) == 4 and isinstance(shape[2], int) and isinstance(shape[3], int):
                self.input_hw = (int(shape[2]), int(shape[3]))
            labels_path = Path(self.s.vision_model_labels or (path.parent / "labels.json"))
            if labels_path.exists():
                data = json.loads(labels_path.read_text(encoding="utf-8"))
                self.labels = data["labels"] if isinstance(data, dict) else list(data)
            else:
                self._error = f"labels file not found: {labels_path}"
                self.session = None
                return
            log.info("onnx vision model loaded",
                     extra={"path": str(path), "classes": len(self.labels),
                            "input": self.input_hw})
        except Exception as exc:                          # pragma: no cover - infra
            self._error = f"{type(exc).__name__}: {str(exc)[:200]}"
            self.session = None
            log.exception("onnx model failed to load")

    def ready(self) -> bool:
        return self.session is not None

    def predict(self, image_bytes, crop, candidates):
        import time
        if not self.ready():
            return ClassifierResult(None, "unavailable", "onnx", self.s.vision_model_version,
                                    "AI model unavailable", False,
                                    note=self._error or "model not loaded",
                                    error="vision_model_unavailable")
        import numpy as np
        from PIL import Image
        t0 = time.perf_counter()
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            side = min(img.size)
            img = img.crop(((img.width - side) // 2, (img.height - side) // 2,
                            (img.width + side) // 2, (img.height + side) // 2))
            img = img.resize((self.input_hw[1], self.input_hw[0]))
            arr = np.asarray(img, dtype=np.float32) / 255.0
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
            arr = (arr - mean) / std
            batch = np.transpose(arr, (2, 0, 1))[None, ...].astype(np.float32)
            with self._lock:
                out = self.session.run(None, {self.input_name: batch})[0]
            logits = np.asarray(out).reshape(-1).astype(np.float64)
            ex = np.exp(logits - logits.max())
            probs = ex / ex.sum()
        except Exception as exc:                          # pragma: no cover - infra
            return ClassifierResult(None, "unavailable", "onnx", self.s.vision_model_version,
                                    "AI model unavailable", False,
                                    note=f"inference failed: {type(exc).__name__}",
                                    error="vision_inference_failed")
        ms = round((time.perf_counter() - t0) * 1000)
        full = {lbl: float(p) for lbl, p in zip(self.labels, probs, strict=False)}
        return _restrict(full, candidates, engine="onnx", model_name="prahari-vision",
                         version=self.s.vision_model_version, ms=ms,
                         display=f"Prahari Vision {self.s.vision_model_version} (ONNX)",
                         is_neural=True)

    def info(self):
        return {"engine": "onnx", "ready": self.ready(), "error": self._error,
                "classes": len(self.labels), "input_hw": list(self.input_hw),
                "path": self.s.vision_model_path, "version": self.s.vision_model_version}


class ApiClassifier(Classifier):
    """A secure external inference endpoint.

    Contract: POST multipart {image, crop} with an Authorization bearer token,
    expecting {"probs": {problem_id: p, ...}, "model_version": "..."}.
    A non-200, a timeout or a malformed body is a failure, and a failure returns
    no probabilities — it never degrades into a guess.
    """
    engine = "api"

    def __init__(self, settings: Settings):
        self.s = settings

    def ready(self) -> bool:
        return bool(self.s.vision_api_url)

    def predict(self, image_bytes, crop, candidates):
        import time
        if not self.ready():
            return ClassifierResult(None, "unavailable", "api", "none",
                                    "AI model unavailable", False,
                                    note="VISION_API_URL is not set",
                                    error="vision_model_unavailable")
        try:
            import httpx
        except ImportError as exc:                        # pragma: no cover
            return ClassifierResult(None, "unavailable", "api", "none",
                                    "AI model unavailable", False,
                                    note=str(exc), error="vision_model_unavailable")
        t0 = time.perf_counter()
        headers = {}
        if self.s.vision_api_key:
            headers["Authorization"] = f"Bearer {self.s.vision_api_key}"
        try:
            r = httpx.post(self.s.vision_api_url, headers=headers,
                           files={"image": ("leaf.jpg", image_bytes, "image/jpeg")},
                           data={"crop": crop},
                           timeout=self.s.vision_timeout_seconds)
            r.raise_for_status()
            body = r.json()
            probs = {str(k): float(v) for k, v in (body.get("probs") or {}).items()}
            if not probs:
                raise ValueError("no probs in response")
            version = str(body.get("model_version") or self.s.vision_model_version)
        except Exception as exc:
            log.warning("vision api failed", extra={"error": str(exc)[:200]})
            return ClassifierResult(None, "unavailable", "api", self.s.vision_model_version,
                                    "AI model unavailable", False,
                                    note=f"{type(exc).__name__}: {str(exc)[:160]}",
                                    error="vision_inference_failed")
        ms = round((time.perf_counter() - t0) * 1000)
        return _restrict(probs, candidates, engine="api", model_name="remote-vision",
                         version=version, ms=ms,
                         display=f"Remote vision model {version}", is_neural=True)

    def info(self):
        return {"engine": "api", "ready": self.ready(), "url": self.s.vision_api_url,
                "version": self.s.vision_model_version}


class GeminiVisionClassifier(Classifier):
    """A general vision model, used as the classifier.

    What this is honest about, because the alternative is a lie a farmer acts
    on: Gemini is a real neural model, so `is_neural` is true and the UI may say
    so. But it was never trained on this crop, no evaluation has been run
    against a field-image test set, and so `metrics` stays empty and the
    existing caveat machinery prints "no accuracy claim is made".

    The model is never asked "what is wrong with this plant". It is handed
    PRAHARI's own closed list of problems for the crop and asked to score the
    photograph against each. That is the whole difference between a classifier
    and an oracle: the label space is ours, the ranking is its, and an id it
    invents scores nothing. Everything downstream — the taluka prior, the
    weather term, the margin, the abstention rule — runs exactly as it does for
    a locally loaded ONNX model.

    A failure returns no probabilities, never a guess. The service then falls
    back to the symptom-feature engine or abstains, which is the behaviour this
    instance had before a key existed.
    """
    engine = "gemini"

    def __init__(self, settings: Settings):
        self.s = settings

    def ready(self) -> bool:
        return bool(self.s.gemini_key)

    def predict(self, image_bytes, crop, candidates):
        import time
        if not self.ready():
            return ClassifierResult(
                None, "unavailable", "gemini", "none", "AI model unavailable", False,
                note=("VISION_PROVIDER=gemini but no GEMINI_API_KEY is set, so no vision "
                      "model is configured on this instance."),
                error="vision_model_unavailable")

        from . import llm as llm_mod
        from . import reference

        known = reference.problems_for_crop(crop)
        listing = [{"id": pid,
                    "name": p.get("name", pid),
                    "sci": p.get("sci"),
                    "scout": p.get("scout")}
                   for pid, p in known.items() if pid in candidates]

        t0 = time.perf_counter()
        verdict = llm_mod.vision_scores(key=self.s.gemini_key,
                                        model=self.s.gemini_vision_model,
                                        crop=crop, candidates=listing,
                                        image_bytes=image_bytes, settings=self.s)
        ms = round((time.perf_counter() - t0) * 1000)
        version = str(verdict.get("model") or self.s.gemini_vision_model)

        if not verdict.get("used"):
            log.warning("gemini vision did not produce a result",
                        extra={"reason": verdict.get("reason")})
            return ClassifierResult(
                None, "unavailable", "gemini-vision", version,
                "AI model unavailable", True, ms,
                note=str(verdict.get("reason") or "no result"),
                error="vision_inference_failed")

        return _restrict(
            verdict["scores"], candidates, engine="gemini",
            model_name="gemini-vision", version=version, ms=ms,
            display=f"Gemini vision ({version}) — general model, not trained on this crop",
            is_neural=True,
            note=("A general vision model scored the photograph against the problems PRAHARI "
                  "knows for this crop. These are match scores, not a trained classifier's "
                  "probabilities, and no evaluation has been run for this model on this crop — "
                  "so they rank the differential and no accuracy is claimed for them."
                  + (f" The model's note on the photograph: {verdict['quality']}"
                     if verdict.get("quality") else "")))

    def info(self):
        return {"engine": "gemini", "ready": self.ready(),
                "model": self.s.gemini_vision_model,
                "version": self.s.vision_model_version,
                "reason": (None if self.ready() else
                           "VISION_PROVIDER=gemini but GEMINI_API_KEY is not set")}


# A candidate the model never mentioned is not a candidate the model ruled out.
# The posterior downstream multiplies prior x image x weather, so a hard zero
# here would delete a problem from the differential no matter what the taluka
# history and the infection models say about it. It gets a floor instead — a
# hundredth of the lowest score the model did give, which is low enough to
# never win on its own and high enough that the other evidence can still speak.
_UNSCORED_FLOOR = 0.01


def _restrict(full: dict[str, float], candidates: list[str], *, engine: str,
              model_name: str, version: str, ms: int, display: str,
              is_neural: bool, note: str | None = None) -> ClassifierResult:
    """Map a model's output onto the problems PRAHARI knows for this crop.

    Two invariants, and the second one used to be assumed rather than enforced:
    a class the model emits that this crop cannot have is dropped, and EVERY
    candidate comes back with a value. The consumer of this result indexes the
    returned mapping by candidate id and multiplies — a missing key is a
    TypeError halfway through a diagnosis, which is a 500 on a farmer's scan.
    """
    kept = {k: float(v) for k, v in full.items() if k in candidates}
    scored = {k: v for k, v in kept.items() if v > 0}
    total = sum(scored.values())
    if total <= 0:
        return ClassifierResult(
            None, "unavailable", model_name, version, display, is_neural, ms,
            note=("The model produced no probability mass on any problem known for this crop. "
                  "That is an out-of-distribution signal, not a diagnosis."),
            error="vision_out_of_distribution")

    floor = min(scored.values()) * _UNSCORED_FLOOR
    raw = {pid: scored.get(pid, floor) for pid in candidates}
    denom = sum(raw.values())
    probs = {pid: v / denom for pid, v in raw.items()}

    missing = len(candidates) - len(scored)
    if note is None:
        dropped = round(1.0 - total, 4)
        note = (f"{len(kept)} of {len(full)} model classes are possible for this crop; "
                f"{dropped:.0%} of the model's probability mass fell outside them and was "
                f"dropped before renormalising.")
    if missing:
        note += (f" {missing} of {len(candidates)} problems for this crop were not scored by "
                 f"the model and were floored rather than eliminated.")
    return ClassifierResult(
        probs=probs, engine=engine, model_name=model_name, model_version=version,
        display=display, is_neural=is_neural, latency_ms=ms, note=note)


# ── the service ─────────────────────────────────────────────────────────────
class VisionService:
    """Runs the quality gate, then the configured classifier, and reports what
    ran. `classify` returning None means "no trained model produced this" — the
    diagnosis engine then either uses the symptom-feature likelihood (labelled
    as such) or abstains, depending on ALLOW_FEATURE_ENGINE."""

    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.classifier = self._build()

    def _build(self) -> Classifier:
        p = self.s.vision_provider
        if p == "onnx":
            return OnnxClassifier(self.s)
        if p == "api":
            return ApiClassifier(self.s)
        if p == "gemini":
            return GeminiVisionClassifier(self.s)
        return NoModel(
            "No trained vision model is configured (VISION_PROVIDER=none). "
            + ("PRAHARI is using its symptom-feature classifier, which measures the leaf and "
               "ranks candidates from those measurements. It is not a neural network and is "
               "not described as one."
               if self.s.allow_feature_engine else
               "Image diagnosis is disabled on this instance."))

    @property
    def neural_available(self) -> bool:
        return self.classifier.ready()

    @property
    def feature_engine_allowed(self) -> bool:
        return self.s.allow_feature_engine

    def analyse(self, image_bytes: bytes) -> dict[str, Any]:
        """Measurement + quality gate. Always runs; costs ~40 ms."""
        from . import vision
        return vision.analyse(image_bytes)

    def classify(self, image_bytes: bytes, crop: str,
                 candidates: list[str]) -> ClassifierResult:
        return self.classifier.predict(image_bytes, crop, candidates)

    def engine_descriptor(self, result: ClassifierResult) -> dict[str, Any]:
        """What the UI prints under a diagnosis. Never says 'AI' unless a
        trained model actually ran."""
        if result.probs is not None:
            return {
                "engine": result.engine,
                "label": result.display,
                "version": result.model_version,
                "is_neural_model": result.is_neural,
                "evaluated": bool(result.metrics),
                "evaluation": result.metrics,
                "caveat": (None if result.metrics else
                           "No evaluation metrics are recorded for this model version, so PRAHARI "
                           "makes no accuracy claim for it."),
            }
        return {
            "engine": "features",
            "label": "Symptom-feature classifier v1 (not a neural network)",
            "version": "features-v1",
            "is_neural_model": False,
            "evaluated": False,
            "evaluation": None,
            "caveat": ("This ranking comes from measured leaf features — necrotic, chlorotic and "
                       "powdery area, lesion count, border sharpness — combined with this taluka's "
                       "confirmed-case history and the weather models. No trained image model is "
                       "configured on this instance."),
            "model_unavailable_reason": result.note,
        }

    def health(self) -> dict[str, Any]:
        info = self.classifier.info()
        info["feature_engine_allowed"] = self.s.allow_feature_engine
        info["diagnosis_possible"] = bool(self.classifier.ready() or self.s.allow_feature_engine)
        return info


def register_model_version(db, service: VisionService) -> None:
    """Record which model this process is serving, so every diagnosis row can
    point at a version that exists in the database."""
    info = service.classifier.info()
    s = service.s
    if info.get("ready"):
        mid = f"vision:{s.vision_provider}:{s.vision_model_version}"
        name, provider, version = "prahari-vision", s.vision_provider, s.vision_model_version
        notes = "Loaded from " + str(info.get("path") or info.get("url"))
    else:
        mid = "vision:features:v1"
        name, provider, version = "symptom-feature-classifier", "features", "features-v1"
        notes = ("Deterministic leaf-feature likelihood. Not a neural network. No accuracy "
                 "claim is made because no evaluation has been run against a field-image test set.")
    if db.one("SELECT id FROM model_versions WHERE id=:id", {"id": mid}):
        return
    db.execute(
        "INSERT INTO model_versions (id, kind, name, version, provider, trained_on, eval_set,"
        " metrics, deployed_at, active, notes)"
        " VALUES (:id,'vision',:name,:v,:p,NULL,NULL,NULL,:at,1,:notes)",
        {"id": mid, "name": name, "v": version, "p": provider, "at": now_iso(), "notes": notes})


def active_model_id(service: VisionService) -> str:
    if service.classifier.ready():
        return f"vision:{service.s.vision_provider}:{service.s.vision_model_version}"
    return "vision:features:v1"
