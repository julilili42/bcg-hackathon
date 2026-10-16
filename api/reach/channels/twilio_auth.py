"""Twilio request signature validation (HMAC-SHA1 over URL + sorted form params)."""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Mapping

from fastapi import HTTPException, Request

from reach.settings import Settings


def compute_signature(auth_token: str, url: str, params: Mapping[str, str]) -> str:
    payload = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def public_url(request: Request, settings: Settings) -> str:
    """The URL Twilio actually called, reconstructed behind a tunnel or proxy."""
    path = request.url.path
    query = f"?{request.url.query}" if request.url.query else ""
    if settings.public_base_url:
        return f"{settings.public_base_url}{path}{query}"
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}{path}{query}"


def public_base(request: Request, settings: Settings) -> str:
    url = public_url(request, settings)
    return url.split("/api/")[0]


async def twilio_form(request: Request) -> dict[str, str]:
    """FastAPI dependency: parse the form and enforce the signature when TWILIO_VALIDATE is on."""
    settings: Settings = request.app.state.settings
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    if settings.twilio_validate:
        if not settings.twilio_auth_token:
            raise HTTPException(status_code=503, detail="TWILIO_AUTH_TOKEN missing while TWILIO_VALIDATE=1")
        expected = compute_signature(settings.twilio_auth_token, public_url(request, settings), params)
        provided = request.headers.get("x-twilio-signature", "")
        if not hmac.compare_digest(expected, provided):
            raise HTTPException(status_code=403, detail="invalid Twilio signature")
    return params
