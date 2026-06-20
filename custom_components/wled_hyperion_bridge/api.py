"""Async WLED JSON API client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp


class WLEDAPIError(Exception):
    """Base WLED API error."""


class WLEDConnectionError(WLEDAPIError):
    """Raised when WLED cannot be reached."""


class WLEDResponseError(WLEDAPIError):
    """Raised when WLED returns an invalid response."""


@dataclass(slots=True)
class WLEDClient:
    """Small async client for WLED's JSON state API."""

    session: aiohttp.ClientSession
    host: str
    port: int = 80
    request_timeout: float = 10.0

    @property
    def base_url(self) -> str:
        """Return the WLED HTTP base URL."""
        return f"http://{self.host}:{self.port}"

    async def async_get_state(self) -> dict[str, Any]:
        """Fetch WLED state from /json/state."""
        result = await self._request("GET", "/json/state")
        if not isinstance(result, dict):
            raise WLEDResponseError("WLED state response was not an object")
        return result

    async def async_set_state(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Post WLED state to /json/state."""
        result = await self._request("POST", "/json/state", json=payload)
        if result is None or isinstance(result, dict):
            return result
        raise WLEDResponseError("WLED state update response was not an object")

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Run one JSON HTTP request."""
        url = f"{self.base_url}{path}"
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)

        try:
            async with self.session.request(
                method, url, timeout=timeout, **kwargs
            ) as response:
                if response.status >= 400:
                    text = await response.text()
                    raise WLEDResponseError(
                        f"WLED returned HTTP {response.status}: {text[:160]}"
                    )

                if response.content_length == 0:
                    return None

                try:
                    return await response.json(content_type=None)
                except aiohttp.ContentTypeError as err:
                    raise WLEDResponseError("WLED did not return JSON") from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise WLEDConnectionError("Could not connect to WLED") from err
