"""Bounded HTTP requests with consistent failure semantics."""

import asyncio
import json
import time
from typing import Any

import aiohttp

from ..const import MAX_RESPONSE, REQUEST_TIMEOUT
from ..exceptions import (
    AuthenticationError,
    CannotConnect,
    CommandOutcomeUnknown,
    LifeSmartError,
    ProtocolError,
    RateLimited,
)


def require_success(payload: Any, *, auth: bool = False) -> dict:
    if not isinstance(payload, dict):
        raise ProtocolError("Expected an object response")
    code = payload.get("code")
    if type(code) is int and code == 0 or auth and code == "success":
        return payload
    if type(code) is int and code in (10004, 10005) or auth and code is not None:
        raise AuthenticationError("LifeSmart authentication rejected")
    if type(code) is not int:
        raise ProtocolError("Missing or invalid response code")
    raise LifeSmartError(f"LifeSmart API error {code}")


class HttpClient:
    def __init__(self, session: aiohttp.ClientSession, *, verify_ssl: bool = True):
        self.session = session
        self.verify_ssl = verify_ssl
        self._semaphore = asyncio.Semaphore(2)
        self._rate_until = 0.0

    async def request(
        self, url: str, body: dict, *, auth: bool = False, write: bool = False
    ) -> dict:
        if time.monotonic() < self._rate_until:
            raise RateLimited(self._rate_until - time.monotonic())
        try:
            async with self._semaphore, asyncio.timeout(REQUEST_TIMEOUT):
                async with self.session.post(
                    url, json=body, ssl=None if self.verify_ssl else False, allow_redirects=False
                ) as response:
                    if response.status in (401, 403):
                        raise AuthenticationError("HTTP authentication rejected")
                    if response.status == 429:
                        try:
                            delay = float(response.headers.get("Retry-After", "60"))
                        except ValueError:
                            delay = 60
                        error = RateLimited(delay)
                        self._rate_until = time.monotonic() + error.retry_after
                        raise error
                    if response.status != 200:
                        if write and response.status >= 500:
                            raise CommandOutcomeUnknown("Write acknowledgement unavailable")
                        raise CannotConnect(f"HTTP status {response.status}")
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        data.extend(chunk)
                        if len(data) > MAX_RESPONSE:
                            raise ProtocolError("Response exceeds size limit")
                    try:
                        payload = json.loads(data)
                    except (ValueError, UnicodeError) as err:
                        raise ProtocolError("Invalid JSON response") from err
                    return require_success(payload, auth=auth)
        except (TimeoutError, aiohttp.ClientError) as err:
            if write:
                raise CommandOutcomeUnknown("Write outcome unknown; refresh state") from err
            raise CannotConnect("LifeSmart connection failed") from err

    async def close(self):
        """The HTTP session belongs to Home Assistant, not this client."""
