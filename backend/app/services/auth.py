"""Optional API-key authentication.

When ``ALLIN1_API_KEY`` is set, every API route (except ``/api/health``, which
hosting platforms poll) requires that key. When it is *not* set, the app
behaves exactly as before: open, which is what you want on a laptop or a home
LAN, and never what you want on a public URL.

The key may be presented in three ways, because the browser needs all three:

* ``X-API-Key: <key>``              — used by ``fetch`` calls
* ``Authorization: Bearer <key>``   — the conventional REST way, for scripts
* ``?key=<key>``                    — required by ``EventSource`` (which cannot
  send custom headers) and by plain ``<a download>`` links. Note that query
  strings can end up in proxy/access logs, so the header forms are preferred.
"""

from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import Settings

API_KEY_HEADER = "X-API-Key"
QUERY_PARAM = "key"

# Reachable without a key so uptime checks and the PWA's pre-login probe work.
PUBLIC_PATHS = frozenset({"/api/health"})

# Interactive docs are handy, but they enumerate the API on a public host.
PROTECTED_EXACT_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})


def path_requires_auth(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return False
    if path.startswith("/api/"):
        return True
    return path in PROTECTED_EXACT_PATHS


def extract_presented_key(request: Request) -> str | None:
    header_key = request.headers.get(API_KEY_HEADER)
    if header_key:
        return header_key.strip()

    authorization = request.headers.get("authorization", "")
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        return credentials.strip()

    query_key = request.query_params.get(QUERY_PARAM)
    if query_key:
        return query_key.strip()

    return None


def keys_match(presented: str | None, expected: str | None) -> bool:
    if not presented or not expected:
        return False
    return secrets.compare_digest(presented, expected)


def is_authorized(request: Request, settings: Settings) -> bool:
    if not settings.api_key:
        return True
    return keys_match(extract_presented_key(request), settings.api_key)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Rejects unauthenticated requests whenever an API key is configured."""

    async def dispatch(self, request: Request, call_next):
        settings: Settings = request.app.state.settings

        if (
            not settings.api_key
            or request.method == "OPTIONS"  # CORS preflight carries no credentials
            or not path_requires_auth(request.url.path)
            or is_authorized(request, settings)
        ):
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={
                "error_code": "unauthorized",
                "message": "An API key is required. Provide it via the "
                f"'{API_KEY_HEADER}' header, an 'Authorization: Bearer' header, "
                f"or a '?{QUERY_PARAM}=' query parameter.",
                "auth_required": True,
            },
        )
