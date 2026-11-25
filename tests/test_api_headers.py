"""What goes over the wire: a request without a body announces none, or the service refuses it (415)."""

from __future__ import annotations

import aiohttp
from aiohttp import web

from custom_components.orgaia.client.api import Api
from custom_components.orgaia.protocol.crypto import Identity


async def test_a_request_without_body_has_no_content_type(socket_enabled) -> None:
    seen: list[dict[str, str]] = []

    async def handler(request: web.Request) -> web.Response:
        seen.append({"method": request.method, "type": request.headers.get("Content-Type", "")})
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
    try:
        async with aiohttp.ClientSession() as session:
            api = Api(session, f"http://127.0.0.1:{port}", Identity.create(), "dev1")
            await api._raw("POST", "/v1/spaces/s/leave")  # noqa: SLF001
            await api._raw("DELETE", "/v1/invites/i/join")  # noqa: SLF001
            await api._raw("POST", "/v1/auth/challenge", {"signPub": "x"})  # noqa: SLF001
    finally:
        await runner.cleanup()
    assert seen == [
        {"method": "POST", "type": ""},
        {"method": "DELETE", "type": ""},
        {"method": "POST", "type": "application/json"},
    ]
