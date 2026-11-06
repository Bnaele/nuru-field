"""Database access and authentication.

The backend connects to Supabase with `SUPABASE_SERVICE_KEY`, which bypasses Row
Level Security. That makes every query responsible for its own scoping, so every
read and write below filters on `user_id` explicitly — RLS in `schema.sql` is a
second line of defence, not the only one.

The service key never leaves the server. The browser only ever holds the anon
key.
"""

from __future__ import annotations

from fastapi import Header, HTTPException
from supabase import Client, create_client

from config import SUPABASE_SERVICE_KEY, SUPABASE_URL

_client: Client | None = None

_NOT_CONFIGURED = (
    "The database is not configured. Add SUPABASE_URL and SUPABASE_SERVICE_KEY to "
    "backend/.env, then restart the API. See backend/.env.example."
)


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def get_supabase() -> Client:
    """Lazy singleton, so the app starts and serves keyless endpoints without a DB."""
    global _client
    if _client is None:
        if not is_configured():
            raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


async def get_current_user(authorization: str | None = Header(default=None)):
    """Resolve the caller from their Supabase access token.

    Verification is delegated to Supabase rather than decoding the JWT locally,
    so a revoked session stops working immediately.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Sign in to use this feature.",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to use this feature.")

    try:
        response = get_supabase().auth.get_user(token)
    except HTTPException:
        raise
    except Exception as error:  # network, malformed token, expired session
        raise HTTPException(
            status_code=401,
            detail="Your session has expired. Please sign in again.",
        ) from error

    if not response or not response.user:
        raise HTTPException(
            status_code=401,
            detail="Your session has expired. Please sign in again.",
        )
    return response.user
