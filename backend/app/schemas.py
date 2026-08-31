"""
PRAHARI · request and response schemas
════════════════════════════════════════════════════════════════════════════
Typed at the edge. The prototype accepted bare form fields and dicts, which
meant a malformed latitude reached the risk engine before anything noticed.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

PHONE_RE = re.compile(r"^(\+91)?[6-9]\d{9}$")
Role = Literal["farmer", "officer", "expert", "admin"]
Lang = Literal["mr", "hi", "en"]


class ErrorBody(BaseModel):
    error: str
    message: str
    message_mr: str | None = None
    retryable: bool = False
    detail: dict[str, Any] | None = None


# ── auth ────────────────────────────────────────────────────────────────────
class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    role: Role = "farmer"
    email: EmailStr | None = None
    phone: str | None = None
    lang: Lang = "mr"
    # farmer profile
    taluka: str | None = None
    village: str | None = Field(default=None, max_length=120)
    full_name_mr: str | None = Field(default=None, max_length=120)
    agristack_id: str | None = Field(default=None, max_length=64)
    literacy: Literal["reads", "voice_only"] = "reads"
    # officer / expert profile
    institution: str | None = Field(default=None, max_length=160)
    specialism: str | None = Field(default=None, max_length=160)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        if v is None or v == "":
            return None
        v = v.replace(" ", "").replace("-", "")
        if not PHONE_RE.match(v):
            raise ValueError("Enter a 10-digit Indian mobile number.")
        return v[-10:]

    @model_validator(mode="after")
    def _identity(self):
        if not self.email and not self.phone:
            raise ValueError("Provide an email address or a mobile number.")
        if self.role == "farmer" and not self.taluka:
            raise ValueError("A farmer registration needs a taluka.")
        return self


class LoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=160,
                            description="Email address or 10-digit mobile number")
    password: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    role: Role
    user_id: str


class PasswordResetRequestIn(BaseModel):
    identifier: str


class PasswordResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=200)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class MeOut(BaseModel):
    user: dict[str, Any]
    profile: dict[str, Any] | None = None
    scopes: list[str] = []


# ── fields ──────────────────────────────────────────────────────────────────
class PlotIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    crop: str
    variety: str | None = Field(default=None, max_length=80)
    area_acre: float = Field(gt=0, le=1000)
    sown_on: dt.date
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    location_source: Literal["gps", "map", "manual"] = "manual"
    taluka: str | None = None
    village: str | None = Field(default=None, max_length=120)
    soil: str | None = Field(default=None, max_length=60)
    irrigation: str | None = Field(default=None, max_length=60)
    tank_litres: int = Field(default=15, ge=5, le=200)
    expected_harvest: dt.date | None = None
    boundary: dict[str, Any] | None = Field(
        default=None, description="GeoJSON Polygon. Area derived from it is approximate.")

    @model_validator(mode="after")
    def _location(self):
        if self.location_source in ("gps", "map") and (self.lat is None or self.lng is None):
            raise ValueError("GPS or map placement needs both latitude and longitude.")
        # No location rule here on purpose.
        #
        # This validator rejected a field that carried neither coordinates nor
        # a taluka, which made "Add field" fail with a 422 whenever the farmer
        # left the taluka on its default — the option the form itself labels
        # "Use my account taluka". The router already resolves a location, in
        # order: a drawn boundary's centroid, an explicit taluka, the nearest
        # taluka to the coordinates, and finally the farmer's OWN taluka from
        # their account. It cannot see the farmer from in here, so a schema
        # that guesses on its behalf can only be wrong in one direction.
        #
        # Nothing is loosened: a field still ends up with a real taluka or the
        # router raises `unknown_taluka`. The check simply moved to the place
        # that has the farmer in hand.
        if self.sown_on > dt.date.today() + dt.timedelta(days=1):
            raise ValueError("The sowing date cannot be in the future.")
        if self.sown_on < dt.date.today() - dt.timedelta(days=730):
            raise ValueError("That sowing date is more than two seasons ago.")
        return self


class PlotPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    variety: str | None = None
    area_acre: float | None = Field(default=None, gt=0, le=1000)
    soil: str | None = None
    irrigation: str | None = None
    tank_litres: int | None = Field(default=None, ge=5, le=200)
    expected_harvest: dt.date | None = None
    archived: bool | None = None


class CropCycleIn(BaseModel):
    crop: str
    variety: str | None = None
    sown_on: dt.date
    end_previous: bool = True


# ── observations ────────────────────────────────────────────────────────────
class ObservationMeta(BaseModel):
    plot_id: str
    kind: Literal["leaf", "trap", "symptom", "followup"] = "leaf"
    notes: str | None = Field(default=None, max_length=1000)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    observed_at: dt.datetime | None = None
    client_ref: str | None = Field(
        default=None, max_length=64,
        description="Idempotency key from the offline queue. Re-sending the same key "
                    "returns the original observation instead of creating a duplicate.")
    image_role: Literal["whole_plant", "affected", "closeup", "underside", "stem", "trap"] = "affected"


class AnswersIn(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict, max_length=12)


class ExpertRequestIn(BaseModel):
    reason: str | None = Field(default=None, max_length=600)
    urgency: Literal["normal", "urgent"] = "normal"


# ── traps ───────────────────────────────────────────────────────────────────
class TrapIn(BaseModel):
    plot_id: str
    pest: str
    trap_type: Literal["pheromone", "sticky_yellow", "sticky_blue", "light"] = "pheromone"
    installed_on: dt.date | None = None


class TrapCountIn(BaseModel):
    count: float = Field(ge=0, le=10000)
    counted_on: dt.date | None = None
    nights: int = Field(default=1, ge=1, le=14)


# ── decisions ───────────────────────────────────────────────────────────────
class ThresholdIn(BaseModel):
    plot_id: str
    pest: str
    count: float = Field(ge=0, le=10000)
    trap_obs_id: str | None = None


class ApplyIn(BaseModel):
    plot_id: str
    target: str
    kind: Literal["cultural", "mechanical", "biological", "chemical"] = "chemical"
    product: str = Field(min_length=1, max_length=160)
    claim_id: str | None = None
    moa_group: str | None = None
    dose_text: str | None = Field(default=None, max_length=300)
    phi_days: int = Field(default=0, ge=0, le=120)
    applied_on: dt.date | None = None
    check_id: int | None = None
    decision_id: str | None = None


# ── expert ──────────────────────────────────────────────────────────────────
class ExpertReviewIn(BaseModel):
    action: Literal["confirm", "reject", "change", "request_info", "field_visit", "mark_urgent"]
    verdict: str | None = None
    confidence: Literal["low", "moderate", "high"] | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _needs_verdict(self):
        if self.action in ("confirm", "change") and not self.verdict:
            raise ValueError("Confirming or changing a diagnosis needs a verdict.")
        return self


# ── officer ─────────────────────────────────────────────────────────────────
class AssignIn(BaseModel):
    observation_id: str | None = None
    case_id: str | None = None
    officer_id: str | None = None
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    due_in_days: int = Field(default=2, ge=0, le=30)


class AssignmentCloseIn(BaseModel):
    status: Literal["visited", "confirmed", "rejected", "escalated"]
    finding: str | None = Field(default=None, max_length=2000)
    confirmed_problem: str | None = None


# ── admin ───────────────────────────────────────────────────────────────────
class VerifyClaimIn(BaseModel):
    source: str = Field(min_length=8, max_length=400,
                        description="The exact CIB&RC / PPQS citation for this label claim.")
    source_url: str | None = None
    expires_on: dt.date | None = None


class ClaimStatusIn(BaseModel):
    status: Literal["draft", "verified", "expired", "revoked"]
    note: str | None = None


# ── offline sync ────────────────────────────────────────────────────────────
class SyncItem(BaseModel):
    client_ref: str = Field(min_length=6, max_length=64)
    kind: Literal["threshold", "trap_count", "application", "note"]
    plot_id: str
    payload: dict[str, Any]
    captured_at: dt.datetime


class SyncIn(BaseModel):
    items: list[SyncItem] = Field(default_factory=list, max_length=100)


# ── community ───────────────────────────────────────────────────────────────
# The public shape of a post is deliberately narrow. There is no latitude, no
# longitude, no plot_id and no phone field to fill in — a client cannot ask for
# what the schema has no room for.
CommunityCategory = Literal["disease", "pest", "crop_problem", "weather",
                            "cultivation", "success", "question"]
ExpertStatus = Literal["EXPERT_REVIEWED", "CONFIRMED", "CORRECTED"]
ReactionKind = Literal["helpful", "same_problem", "thanks", "saved"]
ReportReason = Literal["spam", "misinformation", "unsafe_advice", "abuse", "off_topic", "other"]


class CommunityPostIn(BaseModel):
    category: CommunityCategory
    title: str = Field(default="", max_length=140)
    body: str = Field(min_length=10, max_length=4000)
    crop: str | None = Field(default=None, max_length=40)
    plot_id: str | None = None
    symptoms: list[str] = Field(default_factory=list, max_length=10)
    suspected_problem: str | None = Field(default=None, max_length=60)
    observation_id: str | None = None
    diagnosis_id: str | None = None
    share_context: bool = False
    observed_on: dt.date | None = None
    taluka: str | None = Field(default=None, max_length=40)
    client_ref: str | None = Field(default=None, max_length=64)


class CommunityCommentIn(BaseModel):
    body: str = Field(min_length=2, max_length=2000)
    parent_id: str | None = None


class CommunityReactionIn(BaseModel):
    kind: ReactionKind
    on: bool = True
    target_type: Literal["post", "comment"] = "post"


class CommunityReportIn(BaseModel):
    target_type: Literal["post", "comment"] = "post"
    reason: ReportReason
    note: str | None = Field(default=None, max_length=600)


class CommunityExpertResponseIn(BaseModel):
    status: ExpertStatus
    body: str = Field(min_length=10, max_length=4000)
    verdict_problem: str | None = Field(default=None, max_length=60)
    confidence: Literal["low", "moderate", "high"] = "moderate"
    advice_kind: Literal["ipm", "cultural", "scouting", "refer_officer", "no_action"] = "ipm"


class CommunityModerateIn(BaseModel):
    action: Literal["dismiss", "hide", "remove", "request_expert_correction"]
    note: str | None = Field(default=None, max_length=600)


class SignalConfirmIn(BaseModel):
    confirmed: bool
    note: str = Field(min_length=4, max_length=600)


# ── soil, water and weeds ───────────────────────────────────────────────────
class SoilSelfTestIn(BaseModel):
    plot_id: str
    answers: dict[str, int]
    tested_on: dt.date | None = None


class SoilLabIn(BaseModel):
    """Every value is optional and NONE MEANS UNMEASURED. A missing potassium
    figure must never become a zero — zero is a reading, and a very alarming
    one."""
    plot_id: str
    organic_carbon_pct: float | None = Field(default=None, ge=0, le=10)
    nitrogen_kg_ha: float | None = Field(default=None, ge=0, le=5000)
    phosphorus_kg_ha: float | None = Field(default=None, ge=0, le=1000)
    potassium_kg_ha: float | None = Field(default=None, ge=0, le=5000)
    ph: float | None = Field(default=None, ge=2, le=12)
    lab_name: str | None = Field(default=None, max_length=120)
    report_ref: str | None = Field(default=None, max_length=60)
    tested_on: dt.date | None = None


class FollowupOutcomeIn(BaseModel):
    """A self-reported follow-up outcome.

    `unmeasurable` exists so a farmer can close a loop honestly when there is
    nothing left to judge — the crop was harvested, the leaf dropped. Forcing a
    better/same/worse answer in that case manufactures data.
    """
    outcome: Literal["better", "same", "worse", "unmeasurable"]
    note: str | None = Field(default=None, max_length=300)


class FarmEntryIn(BaseModel):
    """One line in the farm money ledger.

    `direction` splits expense from income so the dashboard can show the
    difference; `client_ref` makes a re-send from the offline queue idempotent
    rather than double-counting a season's costs.
    """
    plot_id: str
    direction: Literal["expense", "income"] = "expense"
    category: str = Field(max_length=40)
    title: str = Field(min_length=1, max_length=120)
    amount_inr: float = Field(gt=0, le=100_000_000)
    quantity: float | None = Field(default=None, ge=0, le=1_000_000)
    unit: str | None = Field(default=None, max_length=20)
    spent_on: dt.date | None = None
    note: str | None = Field(default=None, max_length=300)
    client_ref: str | None = Field(default=None, max_length=64)


class FarmEntryPatch(BaseModel):
    category: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    amount_inr: float | None = Field(default=None, gt=0, le=100_000_000)
    quantity: float | None = Field(default=None, ge=0, le=1_000_000)
    unit: str | None = Field(default=None, max_length=20)
    spent_on: dt.date | None = None
    note: str | None = Field(default=None, max_length=300)


class IrrigationIn(BaseModel):
    applied_on: dt.date | None = None
    method: str | None = Field(default=None, max_length=30)
    mm_applied: float | None = Field(default=None, ge=0, le=500)
    hours: float | None = Field(default=None, ge=0, le=48)
    note: str | None = Field(default=None, max_length=300)


# ── privacy: deleting your own records ──────────────────────────────────────
#
# `community_mode` is a genuine choice rather than a setting. A post three
# neighbours corroborated is at once the farmer's writing and the evidence
# behind a regional signal, so the account holder decides which matters more to
# them and the screen states the consequence of each. There is no default in
# the UI; the default here exists only so a malformed request removes rather
# than silently retains.
class DeleteRecordsIn(BaseModel):
    categories: list[str] = Field(min_length=1, max_length=12)
    password: str = Field(min_length=1, max_length=200)
    confirm: str = Field(min_length=1, max_length=40)
    community_mode: Literal["delete", "anonymise"] = "delete"


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    confirm: str = Field(min_length=1, max_length=40)
    community_mode: Literal["delete", "anonymise"] = "delete"
    reason: str | None = Field(default=None, max_length=300)
