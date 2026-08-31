"""
PRAHARI · structured errors
════════════════════════════════════════════════════════════════════════════
A farmer standing in a field gets a sentence, not a stack trace. A client gets
a machine-readable code and an honest `retryable` flag so it knows whether to
offer a retry button or a different action.

    {"error": "weather_unavailable",
     "message": "Weather data could not be retrieved for this field.",
     "message_mr": "...", "retryable": true}
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class PrahariError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str,
                 message_mr: str | None = None, retryable: bool = False,
                 detail: dict[str, Any] | None = None):
        payload = {"error": code, "message": message, "retryable": retryable}
        if message_mr:
            payload["message_mr"] = message_mr
        if detail:
            payload["detail"] = detail
        super().__init__(status_code=status_code, detail=payload)
        self.code = code


def not_found(entity: str, entity_id: str = "") -> PrahariError:
    return PrahariError(404, f"{entity}_not_found",
                        f"That {entity.replace('_', ' ')} does not exist"
                        + (f" ({entity_id})." if entity_id else "."),
                        message_mr="ही नोंद सापडली नाही.")


def forbidden(what: str = "this record") -> PrahariError:
    return PrahariError(403, "forbidden",
                        f"You are not authorised to access {what}.",
                        message_mr="तुम्हाला ही माहिती पाहण्याची परवानगी नाही.")


def unauthorized(message: str = "Sign in to continue.") -> PrahariError:
    return PrahariError(401, "unauthenticated", message,
                        message_mr="कृपया प्रथम साइन इन करा.")


def bad_request(code: str, message: str, message_mr: str | None = None,
                detail: dict[str, Any] | None = None) -> PrahariError:
    return PrahariError(400, code, message, message_mr, retryable=False, detail=detail)


def conflict(code: str, message: str, message_mr: str | None = None) -> PrahariError:
    return PrahariError(409, code, message, message_mr)


def unavailable(code: str, message: str, message_mr: str | None = None,
                detail: dict[str, Any] | None = None) -> PrahariError:
    """503 with retryable=true. Used wherever an external dependency failed —
    and never accompanied by substitute data."""
    return PrahariError(503, code, message, message_mr, retryable=True, detail=detail)


def too_large(limit_bytes: int) -> PrahariError:
    return PrahariError(413, "file_too_large",
                        f"That file is larger than the {limit_bytes // 1_000_000} MB limit.",
                        message_mr="फाइल खूप मोठी आहे.")


def rate_limited(retry_after: int) -> PrahariError:
    return PrahariError(429, "rate_limited",
                        f"Too many requests. Try again in {retry_after} seconds.",
                        message_mr="खूप विनंत्या. थोड्या वेळाने पुन्हा प्रयत्न करा.",
                        retryable=True)
