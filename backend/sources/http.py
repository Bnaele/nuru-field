"""Shared HTTP helper.

One place to set timeouts, the User-Agent, retry behaviour and error translation,
so no individual source module has to remember them. Every failure becomes an
`UpstreamError` carrying a message that is safe to show a grower.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from config import HTTP_USER_AGENT

# Provider names as a grower would recognise them. A 429 from a data provider is
# the one failure where the culprit is worth naming: "Open-Meteo is rate-limiting
# us" tells the user to try again, while "that data source" reads like the app is
# broken. Deployed instances share their egress IP with other tenants, so being
# throttled says nothing about this field or this app.
_PROVIDER_NAMES = (
    ("open-meteo.com", "Open-Meteo, the weather service"),
    ("nominatim.openstreetmap.org", "OpenStreetMap's place lookup"),
    ("isric.org", "SoilGrids, the soil service"),
    ("joburgmarket.co.za", "Joburg Market"),
)


def _provider_label(url: str) -> str:
    for fragment, name in _PROVIDER_NAMES:
        if fragment in url:
            return name
    return "that data source"


class UpstreamError(RuntimeError):
    """A data provider failed in a way the user should be told about."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def get_text(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 20.0,
    retries: int = 2,
    headers: dict[str, str] | None = None,
    accept: str = "text/html,application/xhtml+xml",
    unavailable_message: str = "That data source is temporarily unavailable.",
) -> str:
    """GET a document as text, retrying transient failures.

    Retries cover connection errors, timeouts, 429 and 5xx. A 4xx other than 429
    is a request problem, so it fails immediately rather than hammering the
    provider with a request that will never succeed.
    """
    request_headers = {"User-Agent": HTTP_USER_AGENT, "Accept": accept}
    if headers:
        request_headers.update(headers)

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, params=params, headers=request_headers)

            if response.status_code == 429:
                last_error = UpstreamError(
                    f"{_provider_label(url)} is rate-limiting us right now. "
                    "Please try again shortly.",
                    status_code=503,
                )
                await asyncio.sleep(1.5 * (attempt + 1))
                continue

            if response.status_code >= 500:
                last_error = UpstreamError(unavailable_message, status_code=502)
                await asyncio.sleep(1.0 * (attempt + 1))
                continue

            if response.status_code >= 400:
                raise UpstreamError(
                    unavailable_message,
                    status_code=502,
                )

            return response.text

        except (httpx.TimeoutException, httpx.TransportError) as error:
            last_error = UpstreamError(unavailable_message, status_code=502)
            last_error.__cause__ = error
            await asyncio.sleep(1.0 * (attempt + 1))

    assert last_error is not None
    raise last_error


async def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 20.0,
    retries: int = 2,
    headers: dict[str, str] | None = None,
    unavailable_message: str = "That data source is temporarily unavailable.",
) -> Any:
    """GET and decode a JSON document."""
    body = await get_text(
        url,
        params=params,
        timeout=timeout,
        retries=retries,
        headers=headers,
        accept="application/json",
        unavailable_message=unavailable_message,
    )
    try:
        return json.loads(body)
    except ValueError as error:
        raise UpstreamError(unavailable_message, status_code=502) from error
