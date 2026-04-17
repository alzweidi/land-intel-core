from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Request

from landintel.config import Settings
from landintel.domain.enums import AppRoleName

SESSION_HEADER_NAME = "x-landintel-session"
DEFAULT_SESSION_COOKIE_NAMES = ("__Host-landintel-session", "landintel-session")
_ROLE_RANK = {
    AppRoleName.ANALYST: 0,
    AppRoleName.REVIEWER: 1,
    AppRoleName.ADMIN: 2,
}


@dataclass(frozen=True, slots=True)
class RequestActor:
    role: AppRoleName
    authenticated: bool
    user_id: str | None = None
    user_email: str | None = None
    user_name: str | None = None
    session_token_present: bool = False
    session_error: str | None = None


def role_at_least(role: AppRoleName, minimum: AppRoleName) -> bool:
    return _ROLE_RANK[role] >= _ROLE_RANK[minimum]


def resolve_request_actor(*, request: Request, settings: Settings) -> RequestActor:
    token = _extract_session_token(request=request, settings=settings)
    if token is None:
        return RequestActor(role=AppRoleName.ANALYST, authenticated=False)

    payload = _decode_session_token(
        token=token,
        secret=settings.web_auth_session_secret,
    )
    if payload is None:
        return RequestActor(
            role=AppRoleName.ANALYST,
            authenticated=False,
            session_token_present=True,
            session_error="INVALID_OR_EXPIRED_SESSION",
        )

    user = payload.get("user")
    if not isinstance(user, dict):
        return RequestActor(
            role=AppRoleName.ANALYST,
            authenticated=False,
            session_token_present=True,
            session_error="INVALID_SESSION_USER",
        )

    role_value = user.get("role")
    try:
        role = AppRoleName(str(role_value).strip().lower())
    except ValueError:
        return RequestActor(
            role=AppRoleName.ANALYST,
            authenticated=False,
            session_token_present=True,
            session_error="INVALID_SESSION_ROLE",
        )

    return RequestActor(
        role=role,
        authenticated=True,
        user_id=_normalize_optional_text(user.get("id")),
        user_email=_normalize_optional_text(user.get("email")),
        user_name=_normalize_optional_text(user.get("name")),
        session_token_present=True,
    )


def resolve_request_actor_name(actor: RequestActor, fallback: str) -> str:
    if actor.user_name:
        return actor.user_name
    if actor.user_email:
        return actor.user_email
    if actor.user_id:
        return actor.user_id
    return fallback


def _extract_session_token(*, request: Request, settings: Settings) -> str | None:
    header_token = _normalize_optional_text(request.headers.get(SESSION_HEADER_NAME))
    if header_token is not None:
        return header_token

    cookie_names = [settings.web_auth_session_cookie_name, *DEFAULT_SESSION_COOKIE_NAMES]
    for cookie_name in cookie_names:
        cookie_token = _normalize_optional_text(request.cookies.get(cookie_name))
        if cookie_token is not None:
            return cookie_token
    return None


def _decode_session_token(*, token: str, secret: str) -> dict[str, Any] | None:
    payload_part, signature_part = _split_token(token)
    if payload_part is None or signature_part is None:
        return None

    expected_signature = _sign_payload(payload_part, secret)
    if not hmac.compare_digest(expected_signature, signature_part):
        return None

    try:
        payload = json.loads(_decode_base64url(payload_part).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    expires_at = _parse_datetime(payload.get("expiresAt"))
    if expires_at is None or datetime.now(UTC) >= expires_at:
        return None
    return payload


def _split_token(token: str) -> tuple[str | None, str | None]:
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None, None
    payload_part = parts[0].strip()
    signature_part = parts[1].strip()
    if not payload_part or not signature_part:
        return None, None
    return payload_part, signature_part


def _sign_payload(payload: str, secret: str) -> str:
    signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _encode_base64url(signature)


def _encode_base64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_base64url(payload: str) -> bytes:
    padded = payload + "=" * ((4 - len(payload) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
