"""Setup: paste an invitation link for Home Assistant from the Orgaia app, then an admin confirms it there."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import logging
import time
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig
from homeassistant.helpers.storage import Store
import voluptuous as vol

from .client.api import ApiError
from .client.engine import GroupEngine, JoinError
from .const import (
    CONF_DEVICE,
    CONF_JOIN,
    CONF_LINK,
    CONF_NAME,
    CONF_NODE,
    CONF_PERSONS,
    CONF_SEED,
    CONF_SERVER,
    CONF_SPACE,
    DEFAULT_MEMBER_NAME,
    DOMAIN,
    JOIN_POLL_SECONDS,
    JOIN_WAIT_SECONDS,
    STORAGE_VERSION,
)
from .coordinator import storage_key
from .protocol.crypto import fingerprint
from .protocol.invite import InviteCode, parse_invite

_LOGGER = logging.getLogger(__name__)


def _schema(name: str = DEFAULT_MEMBER_NAME) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_LINK): str, vol.Required(CONF_NAME, default=name): str})


class OrgaiaConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per group. Every entry has its own key, so groups never learn of each other."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OrgaiaOptionsFlow()

    def __init__(self) -> None:
        self._engine: GroupEngine | None = None
        self._code: InviteCode | None = None
        self._wait: asyncio.Task[str] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._request(user_input)
            if error is None:
                return await self.async_step_wait()
            errors["base"] = error
        return self.async_show_form(step_id="user", data_schema=_schema(), errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Home Assistant was removed from the group: it can join again with a new link."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._request(user_input)
            if error is None:
                return await self.async_step_wait()
            errors["base"] = error
        entry = self._get_reauth_entry()
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_schema(),
            errors=errors,
            description_placeholders={"group": entry.title},
        )

    async def _request(self, user_input: dict[str, Any]) -> str | None:
        """Sends the join request. Returns an error key, or None when it went out."""
        code = parse_invite(user_input[CONF_LINK])
        if code is None or not code.server.startswith(("https://", "http://")):
            return "invalid_link"
        name = (user_input.get(CONF_NAME) or "").strip() or DEFAULT_MEMBER_NAME
        engine = GroupEngine(async_get_clientsession(self.hass), GroupEngine.new_data(code.server))
        try:
            await engine.request_join(code, name)
        except JoinError as err:
            return err.reason
        except (aiohttp.ClientError, TimeoutError, ApiError):
            return "cannot_connect"
        self._engine, self._code, self._wait = engine, code, None
        return None

    async def _wait_for_admin(self) -> str:
        assert self._engine is not None
        deadline = time.monotonic() + JOIN_WAIT_SECONDS
        while time.monotonic() < deadline:
            try:
                state = await self._engine.check_join()
            except (aiohttp.ClientError, TimeoutError, ApiError) as err:
                _LOGGER.debug("Waiting for the admin: %s", err)
                state = "pending"
            if state != "pending":
                return state
            await asyncio.sleep(JOIN_POLL_SECONDS)
        return "timeout"

    async def async_step_wait(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._wait is None:
            self._wait = self.hass.async_create_task(self._wait_for_admin(), eager_start=False)
        if not self._wait.done():
            return self.async_show_progress(
                step_id="wait",
                progress_action="wait_for_admin",
                progress_task=self._wait,
                description_placeholders={
                    "group": (self._code and self._code.n) or "Orgaia",
                    "code": fingerprint(self._engine.identity.sign_pub) if self._engine else "",
                },
            )
        try:
            state = self._wait.result()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Waiting for the admin failed")
            state = "timeout"
        step = {"accepted": "finish", "rejected": "rejected"}.get(state, "timeout")
        return self.async_show_progress_done(next_step_id=step)

    async def async_step_rejected(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason="rejected")

    async def async_step_timeout(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason="timeout")

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        engine, code = self._engine, self._code
        assert engine is not None and code is not None and engine.space_id
        data = {
            CONF_SEED: engine.to_dict()["seed"],
            CONF_SERVER: engine.server,
            CONF_DEVICE: engine.device_id,
            CONF_NODE: engine.node,
            CONF_SPACE: engine.space_id,
            CONF_JOIN: engine.join,
        }
        await self.async_set_unique_id(engine.space_id)
        if self.source == "reauth":
            entry = self._get_reauth_entry()
            if entry.unique_id != engine.space_id:
                await self._leave(engine)
                return self.async_abort(reason="wrong_group")
            await Store(self.hass, STORAGE_VERSION, storage_key(entry.entry_id), private=True).async_remove()
            return self.async_update_reload_and_abort(entry, data=data)
        if self._async_current_entries() and any(e.unique_id == engine.space_id for e in self._async_current_entries()):
            # The new membership would only double the old one.
            await self._leave(engine)
            return self.async_abort(reason="already_configured")
        title = code.n
        try:
            await engine.sync()
            title = engine.view().name or title
        except (ApiError, aiohttp.ClientError, TimeoutError, JoinError) as err:
            _LOGGER.debug("First sync after joining failed, setup tries again: %s", err)
        return self.async_create_entry(title=title or "Orgaia", data=data)

    @staticmethod
    async def _leave(engine: GroupEngine) -> None:
        try:
            await engine.leave()
        except (ApiError, aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Leaving again failed: %s", err)


class OrgaiaOptionsFlow(OptionsFlow):
    """Which Home Assistant person each person of the group is. Same names are suggested."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        view = entry.runtime_data.data if getattr(entry, "runtime_data", None) else None
        if view is None:
            return self.async_abort(reason="not_loaded")
        # The form shows a field per person, labelled with the name (made unique if two share it).
        labels: dict[str, str] = {}
        for p in view.active_persons():
            label, n = p["name"], 2
            while label in labels:
                label, n = f"{p['name']} ({n})", n + 1
            labels[label] = p["id"]
        if not labels:
            return self.async_abort(reason="no_persons")
        if user_input is not None:
            mapping = {pid: user_input[label] for label, pid in labels.items() if user_input.get(label)}
            return self.async_create_entry(data={**entry.options, CONF_PERSONS: mapping})
        current = entry.options.get(CONF_PERSONS) or {}
        by_name = {
            (s.attributes.get("friendly_name") or s.name or "").strip().casefold(): s.entity_id
            for s in self.hass.states.async_all("person")
        }
        selector = EntitySelector(EntitySelectorConfig(domain="person"))
        schema: dict[Any, Any] = {}
        for label, pid in labels.items():
            name = view.person_by_id[pid]["name"]
            suggested = current.get(pid) or by_name.get(name.strip().casefold())
            schema[vol.Optional(label, description={"suggested_value": suggested} if suggested else None)] = selector
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
        )
