"""
PRAHARI · the service container
════════════════════════════════════════════════════════════════════════════
One place that builds the services, so every router asks for the same
instances and a test can build a whole application against a temporary
database with two lines.
"""
from __future__ import annotations

import logging
from typing import Any

from .config import Settings, get_settings
from .db import Database, get_db
from .notify import NotificationService
from .outbreak import OutbreakService
from .services.decisions import DecisionService
from .services.diagnosis import DiagnosisService
from .services.risk import RiskService
from .signals import SignalEngine
from .storage import Storage, build_storage
from .vision_service import VisionService, register_model_version
from .weather import WeatherService

log = logging.getLogger("prahari.runtime")


class Runtime:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.db: Database = get_db()
        self.storage: Storage = build_storage(self.settings)
        self.vision = VisionService(self.settings)
        self.weather = WeatherService(self.db, self.settings,
                                      demo_profile_fn=self._demo_profile)
        self.risk = RiskService(self.db, self.weather)
        self.diagnosis = DiagnosisService(self.db, self.vision)
        self.decisions = DecisionService(self.db)
        self.outbreak = OutbreakService(self.db)
        self.signals = SignalEngine(self.db)
        self.notify = NotificationService(self.db, self.settings)

    def _demo_profile(self) -> str:
        """Only ever consulted by the demo weather provider, which only exists
        when DEMO_MODE is on."""
        if not self.settings.demo_mode:
            return "monsoon"
        try:
            from . import scenarios
            row = self.db.one("SELECT scenario FROM demo_state WHERE id = 1")
            key = (row or {}).get("scenario", "emerging")
            return scenarios.SCENARIOS.get(key, {}).get("weather", "monsoon")
        except Exception:
            return "monsoon"

    def startup(self) -> dict[str, Any]:
        applied = []
        if self.settings.auto_migrate:
            applied = self.db.migrate()
        from . import chemicals
        synced = chemicals.sync_reference_claims(self.db)
        register_model_version(self.db, self.vision)
        log.info("prahari started",
                 extra={"env": self.settings.app_env, "demo": self.settings.demo_mode,
                        "migrations": applied, "claims": synced})
        return {"migrations": applied, "claims": synced}

    def health(self) -> dict[str, Any]:
        return {
            "database": self.db.health(),
            "weather": self.weather.health(),
            "vision": self.vision.health(),
            "storage": self.storage.health(),
            "notifications": self.notify.health(),
        }


_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        raise RuntimeError("runtime not initialised — build the app with create_app()")
    return _runtime


def set_runtime(rt: Runtime | None) -> None:
    global _runtime
    _runtime = rt
