"""
PRAHARI · notifications
════════════════════════════════════════════════════════════════════════════
    NotificationService
        ├── InAppChannel     a row the app reads. Always available.
        ├── SmsChannel       none | log | http  (credentials from env)
        ├── EmailChannel     none | log | smtp
        └── IvrChannel       script generated and stored; dialling is a
                             deployment integration, and the state says so

The rule: a delivery row records what the PROVIDER said, not what we hoped.

  queued     accepted for sending
  sent       the provider accepted it
  delivered  the provider confirmed handset delivery (only a provider callback
             can set this — nothing in this file ever does)
  failed     the provider rejected it, with the error kept
  skipped    no provider is configured, or the farmer has not opted in

"sent" is not "delivered". An SMS gateway returning 200 means it accepted the
message, and claiming more than that is the kind of number that makes a whole
dashboard untrustworthy.
"""
from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

from .clock import now_iso, today
from .config import Settings, get_settings
from .db import Database

log = logging.getLogger("prahari.notify")

GSM_SINGLE, GSM_MULTI = 160, 153
UNICODE_SINGLE, UNICODE_MULTI = 70, 67


def segments(text: str) -> int:
    unicode_ = any(ord(c) > 127 for c in text)
    single, multi = (UNICODE_SINGLE, UNICODE_MULTI) if unicode_ else (GSM_SINGLE, GSM_MULTI)
    if len(text) <= single:
        return 1
    return -(-len(text) // multi)


class Channel(ABC):
    name = "abstract"

    @abstractmethod
    def send(self, address: str, subject: str, body: str) -> dict[str, Any]:
        """Returns {'state','provider','provider_ref','error'}. Never raises."""

    def configured(self) -> bool:
        return True


class InAppChannel(Channel):
    name = "inapp"

    def send(self, address, subject, body):
        # The notification row IS the delivery. It exists before this is called.
        return {"state": "delivered", "provider": "prahari", "provider_ref": None,
                "error": None}


class NullChannel(Channel):
    def __init__(self, name: str, reason: str):
        self.name, self.reason = name, reason

    def configured(self):
        return False

    def send(self, address, subject, body):
        return {"state": "skipped", "provider": "none", "provider_ref": None,
                "error": self.reason}


class LogChannel(Channel):
    """Writes the exact payload to the log and records `sent`. Used in
    development so the message content is reviewable without a gateway
    contract — and it never claims delivery."""

    def __init__(self, name: str):
        self.name = name

    def send(self, address, subject, body):
        log.info("notification (log channel)",
                 extra={"channel": self.name, "to": address, "subject": subject,
                        "body": body})
        return {"state": "sent", "provider": f"log:{self.name}", "provider_ref": None,
                "error": "Logged locally. No real gateway is configured, so delivery is unknown."}


class HttpSmsChannel(Channel):
    """A generic HTTP SMS gateway. Most Indian providers (and the government's
    own bulk SMS rails) accept a POST of this shape; the exact field names are
    provider-specific and belong in a deployment adapter."""
    name = "sms"

    def __init__(self, s: Settings):
        self.s = s

    def configured(self):
        return bool(self.s.sms_api_url and self.s.sms_api_key)

    def send(self, address, subject, body):
        if not self.configured():
            return {"state": "skipped", "provider": "none", "provider_ref": None,
                    "error": "SMS_API_URL / SMS_API_KEY are not configured."}
        try:
            import httpx
            r = httpx.post(self.s.sms_api_url, timeout=15,
                           headers={"Authorization": f"Bearer {self.s.sms_api_key}"},
                           json={"to": address, "sender": self.s.sms_sender_id,
                                 "message": body})
            r.raise_for_status()
            ref = None
            try:
                ref = str((r.json() or {}).get("id") or (r.json() or {}).get("message_id") or "")
            except Exception:
                ref = None
            return {"state": "sent", "provider": "http-sms", "provider_ref": ref,
                    "error": None}
        except Exception as exc:
            return {"state": "failed", "provider": "http-sms", "provider_ref": None,
                    "error": f"{type(exc).__name__}: {str(exc)[:160]}"}


class SmtpEmailChannel(Channel):
    name = "email"

    def __init__(self, s: Settings):
        self.s = s

    def configured(self):
        return bool(self.s.smtp_host and self.s.smtp_from)

    def send(self, address, subject, body):
        if not self.configured():
            return {"state": "skipped", "provider": "none", "provider_ref": None,
                    "error": "SMTP_HOST / SMTP_FROM are not configured."}
        import smtplib
        from email.message import EmailMessage
        try:
            msg = EmailMessage()
            msg["From"] = self.s.smtp_from
            msg["To"] = address
            msg["Subject"] = subject
            msg.set_content(body)
            with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=20) as srv:
                srv.starttls()
                if self.s.smtp_user:
                    srv.login(self.s.smtp_user, self.s.smtp_password or "")
                srv.send_message(msg)
            return {"state": "sent", "provider": "smtp", "provider_ref": None, "error": None}
        except Exception as exc:
            return {"state": "failed", "provider": "smtp", "provider_ref": None,
                    "error": f"{type(exc).__name__}: {str(exc)[:160]}"}


class NotificationService:
    def __init__(self, db: Database, settings: Settings | None = None):
        self.db = db
        self.s = settings or get_settings()
        self.inapp = InAppChannel()
        self.sms = self._sms()
        self.email = self._email()

    def _sms(self) -> Channel:
        p = self.s.sms_provider
        if p == "http":
            return HttpSmsChannel(self.s)
        if p == "log":
            return LogChannel("sms")
        return NullChannel("sms", "No SMS gateway is configured (SMS_PROVIDER is not configured).")

    def _email(self) -> Channel:
        p = self.s.email_provider
        if p == "smtp":
            return SmtpEmailChannel(self.s)
        if p == "log":
            return LogChannel("email")
        return NullChannel("email", "No mail transport is configured (EMAIL_PROVIDER is not configured).")

    # ── the call sites use this ────────────────────────────────────────────
    def push(self, *, user_id: str | None, plot_id: str | None, kind: str,
             title: str, body: str, severity: str = "watch",
             title_mr: str | None = None, body_mr: str | None = None,
             at: str | None = None, channels: list[str] | None = None,
             sms_text: str | None = None, address: str | None = None,
             lang: str = "mr") -> str:
        nid = "N-" + uuid.uuid4().hex[:12]
        stamp = now_iso()
        self.db.execute(
            "INSERT INTO notifications (id, user_id, plot_id, at, kind, severity, title,"
            " title_mr, body, body_mr, created_at)"
            " VALUES (:id,:uid,:pid,:at,:kind,:sev,:t,:tmr,:b,:bmr,:now)",
            {"id": nid, "uid": user_id, "pid": plot_id, "at": at or today().isoformat(),
             "kind": kind, "sev": severity, "t": title, "tmr": title_mr, "b": body,
             "bmr": body_mr, "now": stamp})
        self._record(nid, "inapp", address=None, body=title, result=self.inapp.send("", title, body))

        for ch in (channels or []):
            if ch == "sms":
                text = sms_text or _sms_text(title_mr if lang == "mr" else title,
                                             body_mr if lang == "mr" else body)
                self._record(nid, "sms", address, text,
                             self.sms.send(address or "", title, text) if address
                             else {"state": "skipped", "provider": "none", "provider_ref": None,
                                   "error": "No phone number on file for this farmer."},
                             segments_=segments(text))
            elif ch == "email":
                self._record(nid, "email", address, body,
                             self.email.send(address or "", title, body) if address
                             else {"state": "skipped", "provider": "none", "provider_ref": None,
                                   "error": "No email address on file."})
            elif ch == "ivr":
                script = body_mr or body
                self._record(nid, "ivr", address, script,
                             {"state": "queued", "provider": "none", "provider_ref": None,
                              "error": ("IVR script generated and stored. Dialling requires a "
                                        "telephony integration, which is not configured.")})
        return nid

    def _record(self, nid: str, channel: str, address: str | None, body: str,
                result: dict[str, Any], segments_: int | None = None) -> None:
        stamp = now_iso()
        self.db.execute(
            "INSERT INTO notification_deliveries (notification_id, channel, address, state,"
            " provider, provider_ref, error, body, segments, queued_at, updated_at)"
            " VALUES (:n,:c,:a,:s,:p,:r,:e,:b,:seg,:q,:u)",
            {"n": nid, "c": channel, "a": address, "s": result["state"],
             "p": result.get("provider"), "r": result.get("provider_ref"),
             "e": result.get("error"), "b": body, "seg": segments_,
             "q": stamp, "u": stamp})

    def mark_delivered(self, notification_id: str, channel: str, provider_ref: str = "") -> int:
        """Called by a provider webhook. Nothing else may set 'delivered' on an
        external channel."""
        return self.db.execute(
            "UPDATE notification_deliveries SET state='delivered', provider_ref=:r, updated_at=:u"
            " WHERE notification_id=:n AND channel=:c AND state IN ('queued','sent')",
            {"r": provider_ref, "u": now_iso(), "n": notification_id, "c": channel})

    def health(self) -> dict[str, Any]:
        return {
            "inapp": {"configured": True},
            "sms": {"provider": self.s.sms_provider, "configured": self.sms.configured()},
            "email": {"provider": self.s.email_provider, "configured": self.email.configured()},
            "note": ("A delivery is reported as 'sent' when a gateway accepts it. Only a provider "
                     "callback to /api/webhooks/delivery can move it to 'delivered'."),
        }


def _sms_text(title: str, body: str) -> str:
    text = f"PRAHARI: {title}. {body}".strip()
    return text[:320]
