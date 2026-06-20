"""Tests for the WLED JSON API client."""

from __future__ import annotations

from typing import Any

import aiohttp
import pytest
from aiohttp import web

from custom_components.wled_hyperion_bridge.api import WLEDClient, WLEDResponseError


@pytest.fixture
async def wled_server(aiohttp_server: Any) -> Any:
    """Create a fake WLED server."""
    calls: list[dict[str, Any]] = []

    async def get_state(request: web.Request) -> web.Response:
        return web.json_response(
            {
                "on": True,
                "bri": 100,
                "lor": 2,
                "seg": [{"id": 0, "fx": 0, "pal": 0, "col": [[255, 255, 255]]}],
            }
        )

    async def post_state(request: web.Request) -> web.Response:
        payload = await request.json()
        calls.append(payload)
        return web.json_response({"success": True})

    app = web.Application()
    app["calls"] = calls
    app.router.add_get("/json/state", get_state)
    app.router.add_post("/json/state", post_state)
    return await aiohttp_server(app)


@pytest.fixture
async def client_session() -> aiohttp.ClientSession:
    """Create an aiohttp client session."""
    async with aiohttp.ClientSession() as session:
        yield session


async def test_client_gets_wled_state(
    wled_server: Any, client_session: aiohttp.ClientSession
) -> None:
    """Client reads /json/state."""
    client = WLEDClient(
        session=client_session,
        host=wled_server.host,
        port=wled_server.port,
    )

    state = await client.async_get_state()

    assert state["bri"] == 100
    assert state["lor"] == 2


async def test_client_posts_wled_state(
    wled_server: Any, client_session: aiohttp.ClientSession
) -> None:
    """Client writes /json/state."""
    client = WLEDClient(
        session=client_session,
        host=wled_server.host,
        port=wled_server.port,
    )

    result = await client.async_set_state({"lor": 0})

    assert result == {"success": True}
    assert wled_server.app["calls"] == [{"lor": 0}]


async def test_client_raises_on_http_error(
    aiohttp_server: Any, client_session: aiohttp.ClientSession
) -> None:
    """Client surfaces WLED HTTP errors."""

    async def get_state(request: web.Request) -> web.Response:
        return web.Response(status=500, text="boom")

    app = web.Application()
    app.router.add_get("/json/state", get_state)
    server = await aiohttp_server(app)
    client = WLEDClient(session=client_session, host=server.host, port=server.port)

    with pytest.raises(WLEDResponseError):
        await client.async_get_state()
