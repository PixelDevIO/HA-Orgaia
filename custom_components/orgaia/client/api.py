"""HTTP and WebSocket client for Orgaia's sync service, as packages/core/src/api.ts."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.parse import quote

import aiohttp

from ..protocol import PROTOCOL_VERSION
from ..protocol.crypto import Identity

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
# A clock this far from the service's is taken as wrong, and the service's time is used instead.
CLOCK_TOLERANCE_MS = 5 * 60 * 1000


class ApiError(Exception):
    """The service answered with an error: an HTTP status and a short code such as ``integration-needs-plan``."""

    def __init__(self, status: int, code: str, data: Any = None) -> None:
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code
        self.data = data


class Api:
    """A JSON client that signs in with the identity's key and keeps the session token."""

    def __init__(self, session: aiohttp.ClientSession, base: str, identity: Identity, device_id: str) -> None:
        self.base = base.rstrip("/")
        self.identity = identity
        self.device_id = device_id
        self._session = session
        self._token: str | None = None
        self._expires = 0.0
        self._lock = asyncio.Lock()
        # What to add to this machine's clock to get the service's time; 0 while the two agree.
        self.clock_offset = 0

    async def _raw(self, method: str, path: str, body: Any = None, token: str | None = None) -> Any:
        headers = {"x-device": self.device_id}
        if body is not None:
            headers["content-type"] = "application/json"
        if token:
            headers["authorization"] = f"Bearer {token}"
        data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode() if body is not None else None
        # Without a body aiohttp would still announce one (application/octet-stream), and the service
        # refuses that with 415: leaving a group never went through.
        skip = () if body is not None else ("Content-Type",)
        async with self._session.request(
            method, self.base + path, data=data, headers=headers, timeout=REQUEST_TIMEOUT, skip_auto_headers=skip
        ) as res:
            text = await res.text()
            try:
                parsed = json.loads(text) if text else None
            except ValueError:
                parsed = None
            if res.status >= 400:
                code = (
                    parsed.get("error")
                    if isinstance(parsed, dict) and isinstance(parsed.get("error"), str)
                    else "error"
                )
                raise ApiError(res.status, code, parsed)
            return parsed

    async def auth_token(self, force: bool = False) -> str:
        async with self._lock:
            if not force and self._token and self._expires - 60_000 > time.time() * 1000:
                return self._token
            challenge = await self._raw("POST", "/v1/auth/challenge", {"signPub": self.identity.sign_pub})
            nonce = challenge["nonce"]
            service_now = challenge.get("now")
            if isinstance(service_now, (int, float)) and not isinstance(service_now, bool):
                offset = int(service_now - time.time() * 1000)
                self.clock_offset = offset if abs(offset) > CLOCK_TOLERANCE_MS else 0
            body = {
                "signPub": self.identity.sign_pub,
                "boxPub": self.identity.box_pub,
                "boxSig": self.identity.box_sig,
                "nonce": nonce,
                "sig": self.identity.sign(("orgaia-auth:" + nonce).encode()),
                "deviceId": self.device_id,
                "protocol": PROTOCOL_VERSION,
            }
            res = await self._raw("POST", "/v1/auth/verify", body)
            self._token = res["token"]
            self._expires = float(res["expiresAt"])
            return self._token

    async def req(self, method: str, path: str, body: Any = None) -> Any:
        token = await self.auth_token()
        try:
            return await self._raw(method, path, body, token)
        except ApiError as err:
            if err.status != 401:
                raise
            return await self._raw(method, path, body, await self.auth_token(force=True))

    async def ws_connect(self) -> aiohttp.ClientWebSocketResponse:
        """Opens the live connection; it tells which group changed, never what."""
        token = await self.auth_token()
        url = ("ws" + self.base[4:] if self.base.startswith("http") else self.base) + "/v1/ws"
        ws = await self._session.ws_connect(url, heartbeat=55, timeout=aiohttp.ClientWSTimeout(ws_close=10))
        try:
            # The token goes in the first message, not in the address, so it ends up in no access log.
            await ws.send_json({"t": "auth", "token": token})
        except BaseException:
            await ws.close()
            raise
        return ws


def space_path(space_id: str) -> str:
    return "/v1/spaces/" + quote(space_id, safe="")
