"""
PRAHARI · प्रहरी — the application
════════════════════════════════════════════════════════════════════════════
The one who keeps watch.

A crop-health early-warning and response platform for the Maharashtra State
Innovation Society problem statement. Not a photo classifier with a dashboard
around it: the loop is

    PREDICT → DETECT → VERIFY → ACT → MONITOR → LEARN

and every screen belongs to one of those six steps.

Routers, in the order of the argument:

    /api/auth           who you are, and what that lets you see
    /api/plots          the field, its crop cycle, its passport
    /api/risk           weather models fire days BEFORE a symptom exists
    /api/observations   the camera, and its right to refuse
    /api/traps          counts, because a diagnosis cannot authorise a spray
    /api/threshold      the economic gate — the only path to a chemical
    /api/recommendations  the IPM ladder, chemistry last and only if verified
    /api/followups      the re-scan that closes the loop
    /api/expert         a human decides the cases the model should not
    /api/officer        surveillance, and a week a scarce officer can work
    /api/notifications  with a delivery state that is not a guess
    /api/sync           the offline queue
    /api/agronomy       soil, water and weeds — the inputs upstream of disease
    /api/community      farmers reporting to each other, graded into signals
    /api/saathi         a grounded assistant that refuses rather than guesses
    /api/admin          verification of chemical reference data, and the audit
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings, get_settings
from .obs import configure_logging, new_request_id, request_id_var, user_id_var
from .ratelimit import RateLimiter
from .routers import (
    agronomy,
    auth,
    community,
    cropcalendar,
    decisions,
    demo,
    expert,
    followups,
    fpo,
    ledger,
    management,
    misc,
    observations,
    officer,
    plots,
    privacy,
    risk,
    saathi,
)
from .runtime import Runtime, set_runtime

log = logging.getLogger("prahari")

# Answer without the database: liveness, and readiness (which reports it as down).
_DB_FREE_PATHS = frozenset({"/api/health", "/api/ready"})

DESCRIPTION = """
**PRAHARI (प्रहरी)** — early detection and management of crop disease and pest infestation.

### What makes this different from a diagnosis app

* **PREDICT** — published infection models (Hutton, TOMCAST, Gubler-Thomas, 3-10) run on real
  weather for the field's own coordinates and fire *days before a symptom exists*.
* **DETECT** — a quality gate that REJECTS a bad photograph instead of diagnosing it, then a
  differential with confidence, supporting and contradicting evidence, and five distinct reasons
  the system may decline to answer at all.
* **VERIFY** — contextual questions when they can settle it; a human expert when they cannot.
* **ACT** — the economic threshold gate. Below it, *"do not spray"* is a decision object with
  evidence, a rupee value and a re-check date. A chemical is reachable only through a threshold
  crossing **and** a label claim that a named person has verified against the CIB&RC list.
* **MONITOR** — a scheduled re-scan compared with the first, reported as a direction, never as an
  invented severity percentage. Worse after treatment escalates to an officer, not to a second spray.
* **LEARN** — one expert confirmation moves one integer in that taluka's Dirichlet prior. Model
  retraining is a separate, versioned, evaluated act.

### Things this API will not do

It will not fabricate weather when the provider is down (`503 weather_unavailable`).
It will not present an unverified pesticide dose. It will not call a heuristic an AI model.
It will not call a cluster of photographs a confirmed outbreak.
"""

TAGS = [
    {"name": "auth", "description": "Registration, sessions and role-based access."},
    {"name": "fields", "description": "Field onboarding, crop cycles and the Field Health Passport."},
    {"name": "risk", "description": "PREDICT — weather-driven risk, forecast and crop-health score."},
    {"name": "observations", "description": "DETECT — the camera, the quality gate and the differential."},
    {"name": "traps", "description": "Pest trap monitoring and count trends."},
    {"name": "decisions", "description": "ACT — the economic threshold gate and the IPM ladder."},
    {"name": "follow-up", "description": "MONITOR — the re-scan that closes the loop."},
    {"name": "expert", "description": "VERIFY — the expert verification portal."},
    {"name": "officer", "description": "The agriculture officer's command centre."},
    {"name": "notifications", "description": "In-app, SMS and IVR, with honest delivery state."},
    {"name": "offline", "description": "The offline capture queue."},
    {"name": "agronomy", "description": ("Soil health, the irrigation water balance, and "
                                         "weed cover — the inputs upstream of disease.")},
    {"name": "community", "description": ("The farmer community, and the graded cluster signals "
                                          "it produces. Coarse geography by construction.")},
    {"name": "fpo", "description": ("Farmer producer organisations — counts across "
                                    "members who chose to join. Never a member's field.")},
    {"name": "assistant", "description": "PRAHARI Saathi — grounded answers, or an honest refusal."},
    {"name": "reference", "description": "Agronomic reference data and health checks."},
    {"name": "admin", "description": "Chemical reference verification and the audit trail."},
    {"name": "demo", "description": "Demo scenarios. Mounted only when DEMO_MODE=true."},
]


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    configure_logging()

    def bring_up(app: FastAPI, rt: Runtime, attempts: int = 1) -> bool:
        """Migrate, sync reference data and bootstrap the first administrator.

        A database that cannot be REACHED is not a configuration error, so it
        does not kill the process: the service comes up degraded, every data
        route answers 503 database_unavailable, and the next request after
        DB_RETRY_SECONDS tries again. Before this, an expired or unreachable
        database made uvicorn exit at startup and the whole site — including
        the static frontend — disappeared behind the host's generic error page.
        A schema error (bad SQL in a migration) is NOT caught here and still
        stops the start, because retrying it would never succeed."""
        st = app.state.db_state
        for i in range(attempts):
            st["last_try"] = time.monotonic()
            try:
                info = rt.startup()
                if s.demo_mode and s.auto_seed_demo:
                    from .seed_demo import seed
                    info["seed"] = seed(rt)
                # Independent of the demo seed, and allowed in production: the one
                # step that had no other way to happen. Creates nothing when it is
                # not configured, and nothing again once an administrator exists.
                from .seed_demo import bootstrap_admin
                info["admin_bootstrap"] = bootstrap_admin(rt)
                st.update(ready=True, error=None)
                log.info("ready", extra=info)
                return True
            except (OperationalError, InterfaceError) as exc:
                # The exception TYPE only: driver messages can carry a host name,
                # and nothing about the connection belongs in a log line.
                st.update(ready=False, error=type(exc).__name__)
                log.error("database unreachable — serving degraded",
                          extra={"attempt": i + 1, "error": type(exc).__name__})
                if i + 1 < attempts:
                    time.sleep(min(2 * (i + 1), 6))
        return False

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        rt = Runtime(s)
        set_runtime(rt)
        app.state.runtime = rt
        app.state.db_state = {"ready": False, "last_try": 0.0, "error": None}
        app.state.db_retry_lock = asyncio.Lock()
        bring_up(app, rt, attempts=max(1, s.db_startup_attempts))
        yield
        rt.db.dispose()
        set_runtime(None)

    app = FastAPI(
        title="PRAHARI",
        version=s.app_version,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        lifespan=lifespan,
        contact={"name": "PRAHARI", "url": "https://github.com/"},
        license_info={"name": "For evaluation — Smart India Hackathon 2026"},
    )

    # ── security middleware ────────────────────────────────────────────────
    if s.trusted_host_list != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=s.trusted_host_list)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Prahari-Signature"],
        max_age=600,
    )

    limiter = RateLimiter(s)

    async def _database_gate(request: Request, rid: str):
        """None when the request may proceed; a 503 when the database is down."""
        st = getattr(request.app.state, "db_state", None)
        if st is None or st["ready"]:
            return None
        path = request.url.path
        if not path.startswith("/api") or path in _DB_FREE_PATHS:
            return None
        if time.monotonic() - st["last_try"] >= s.db_retry_seconds:
            async with request.app.state.db_retry_lock:
                if not st["ready"] and time.monotonic() - st["last_try"] >= s.db_retry_seconds:
                    await run_in_threadpool(bring_up, request.app, request.app.state.runtime)
            if st["ready"]:
                return None
        return JSONResponse(
            status_code=503,
            content={"error": "database_unavailable",
                     "message": ("PRAHARI cannot reach its database right now. Nothing you "
                                 "saved is shown as if it were current. Try again shortly."),
                     "message_mr": ("PRAHARI ला सध्या डेटाबेसशी जोडता येत नाही. थोड्या वेळाने "
                                    "पुन्हा प्रयत्न करा."),
                     "retryable": True, "request_id": rid},
            headers={"X-Request-ID": rid, "Retry-After": str(int(s.db_retry_seconds))})

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or new_request_id()
        request_id_var.set(rid)
        user_id_var.set(None)
        t0 = time.perf_counter()

        blocked = limiter.check(request)
        if blocked is not None:
            return blocked

        unavailable = await _database_gate(request, rid)
        if unavailable is not None:
            return unavailable

        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"path": request.url.path})
            return JSONResponse(
                status_code=500,
                content={"error": "internal_error",
                         "message": "Something went wrong on our side. Try again shortly.",
                         "message_mr": "आमच्याकडे काहीतरी बिघडले. थोड्या वेळाने पुन्हा प्रयत्न करा.",
                         "retryable": True, "request_id": rid},
                headers={"X-Request-ID": rid})
        ms = round((time.perf_counter() - t0) * 1000)
        response.headers["X-Request-ID"] = rid
        _security_headers(response)
        if request.url.path.startswith("/api"):
            log.info("request", extra={"method": request.method, "path": request.url.path,
                                       "status": response.status_code, "ms": ms})
        return response

    # ── structured errors ──────────────────────────────────────────────────
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            body = detail
        else:
            body = {"error": _code_for(exc.status_code), "message": str(detail),
                    "retryable": exc.status_code in (429, 502, 503, 504)}
        body["request_id"] = request_id_var.get()
        headers = getattr(exc, "headers", None) or {}
        return JSONResponse(status_code=exc.status_code, content=body, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        problems = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"] if p not in ("body", "query"))
            problems.append({"field": loc, "message": err["msg"]})
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_request",
                     "message": ("Some of what you sent was not usable: "
                                 + "; ".join(f"{p['field']} — {p['message']}" for p in problems)),
                     "message_mr": "पाठवलेली काही माहिती योग्य नाही.",
                     "retryable": False, "problems": problems,
                     "request_id": request_id_var.get()})

    # ── routes ─────────────────────────────────────────────────────────────
    app.include_router(auth.router)
    app.include_router(plots.router)
    app.include_router(risk.router)
    app.include_router(cropcalendar.router)
    app.include_router(observations.router)
    app.include_router(traps_router())
    app.include_router(decisions.router)
    app.include_router(followups.router)
    app.include_router(expert.router)
    app.include_router(officer.router)
    app.include_router(agronomy.router)
    app.include_router(ledger.router)
    app.include_router(management.router)
    app.include_router(privacy.router)
    app.include_router(community.router)
    app.include_router(saathi.router)
    app.include_router(fpo.router)
    app.include_router(misc.notifications)
    app.include_router(misc.sync)
    app.include_router(misc.meta)
    app.include_router(misc.admin)
    if s.demo_mode:
        app.include_router(demo.router)
        log.warning("DEMO MODE IS ON — generated weather and demo endpoints are available")

    # ── media and the built frontend ───────────────────────────────────────
    if s.storage_provider == "local":
        media_dir = Path(s.storage_local_dir).resolve()
        media_dir.mkdir(parents=True, exist_ok=True)
        app.mount(s.storage_public_base, StaticFiles(directory=str(media_dir)), name="media")

    dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")

        # HEAD too: uptime monitors and some load balancers probe with HEAD, and
        # answering it 405 made a healthy site look down to them.
        @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith(("api/", "docs", "openapi.json", "media/")):
                return JSONResponse({"error": "not_found", "message": "No such endpoint."},
                                    status_code=404)
            candidate = dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


def traps_router():
    from .routers import traps
    return traps.router


def _security_headers(response) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy",
                                "geolocation=(self), camera=(self), microphone=(self)")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob: https:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "connect-src 'self' https:; frame-ancestors 'none'; base-uri 'self'")
    if get_settings().is_production:
        response.headers.setdefault("Strict-Transport-Security",
                                    "max-age=31536000; includeSubDomains")


def _code_for(status: int) -> str:
    return {400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found",
            405: "method_not_allowed", 409: "conflict", 413: "file_too_large",
            422: "invalid_request", 429: "rate_limited", 500: "internal_error",
            503: "service_unavailable"}.get(status, "error")


app = create_app()
