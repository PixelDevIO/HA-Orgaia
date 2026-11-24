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
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.storage import Store
import voluptuous as vol

from .client.api import ApiError
from .client.engine import GroupEngine, JoinError
from .const import (
    COMPLETED_DAYS,
    CONF_COMPLETED_DAYS,
    CONF_DASHBOARD,
    CONF_DASHBOARD_SECTIONS,
    CONF_DASHBOARD_STYLE,
    CONF_DEVICE,
    CONF_JOIN,
    CONF_LINK,
    CONF_LISTS,
    CONF_NAME,
    CONF_NODE,
    CONF_PERSON_DEVICES,
    CONF_PERSONS,
    CONF_SEED,
    CONF_SERVER,
    CONF_SPACE,
    CONF_VOICE_PERSON,
    DASHBOARD_DEFAULT_SECTIONS,
    DASHBOARD_SECTIONS,
    DASHBOARD_STYLES,
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


def _schema() -> vol.Schema:
    """The link is all the setup asks for; Home Assistant is called just that in the group."""
    return vol.Schema({vol.Required(CONF_LINK): str})


def _person_labels(view: Any) -> dict[str, str]:
    """A field per person, labelled with the name (made unique if two share it)."""
    labels: dict[str, str] = {}
    for p in view.active_persons():
        label, n = p["name"], 2
        while label in labels:
            label, n = f"{p['name']} ({n})", n + 1
        labels[label] = p["id"]
    return labels


def _persons_schema(hass: Any, view: Any, labels: dict[str, str], current: Mapping[str, str]) -> vol.Schema:
    """Who is who, with the Home Assistant person of the same name suggested."""
    by_name = {
        (s.attributes.get("friendly_name") or s.name or "").strip().casefold(): s.entity_id
        for s in hass.states.async_all("person")
    }
    selector = EntitySelector(EntitySelectorConfig(domain="person"))
    schema: dict[Any, Any] = {}
    for label, pid in labels.items():
        name = view.person_by_id[pid]["name"]
        suggested = current.get(pid) or by_name.get(name.strip().casefold())
        schema[vol.Optional(label, description={"suggested_value": suggested} if suggested else None)] = selector
    return vol.Schema(schema)


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
        self._title = "Orgaia"
        self._data: dict[str, Any] = {}
        self._labels: dict[str, str] = {}

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

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Joins the same group again with a new link and a new key, keeping entities and automations.

        For when the key should change (a backup got into the wrong hands) or the old membership is in
        doubt. The old membership is left once the new one stands.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._request(user_input)
            if error is None:
                return await self.async_step_wait()
            errors["base"] = error
        entry = self._get_reconfigure_entry()
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(),
            errors=errors,
            description_placeholders={"group": entry.title},
        )

    async def _request(self, user_input: dict[str, Any]) -> str | None:
        """Sends the join request. Returns an error key, or None when it went out."""
        code = parse_invite(user_input[CONF_LINK])
        if code is None or not code.server.startswith(("https://", "http://")):
            return "invalid_link"
        # Older dialogs and scripts may still send a name; the form no longer asks for one.
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
        # Nobody answered: the request is taken back, so the same invitation works for another try and
        # no admin accepts a Home Assistant that has stopped waiting.
        if self._engine is not None:
            await self._engine.withdraw_join()
        return self.async_abort(reason="timeout")

    @callback
    def async_remove(self) -> None:
        """The dialog was closed while waiting: the request is taken back as well."""
        engine = self._engine
        if engine is not None and not engine.space_id and engine.join:
            if self._wait is not None and not self._wait.done():
                self._wait.cancel()
            self.hass.async_create_task(engine.withdraw_join(), eager_start=False)

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
        if self.source in ("reauth", "reconfigure"):
            entry = self._get_reauth_entry() if self.source == "reauth" else self._get_reconfigure_entry()
            if entry.unique_id != engine.space_id:
                await self._leave(engine)
                return self.async_abort(reason="wrong_group")
            old = getattr(entry, "runtime_data", None)
            if self.source == "reconfigure" and old is not None:
                # The old key leaves the group, so the admins see one Home Assistant, not two.
                await self._leave(old.engine)
            await Store(self.hass, STORAGE_VERSION, storage_key(entry.entry_id), private=True).async_remove()
            return self.async_update_reload_and_abort(entry, data=data)
        if self._async_current_entries() and any(e.unique_id == engine.space_id for e in self._async_current_entries()):
            # The new membership would only double the old one.
            await self._leave(engine)
            return self.async_abort(reason="already_configured")
        title = code.n
        view = None
        try:
            await engine.sync()
            view = engine.view()
            title = view.name or title
        except (ApiError, aiohttp.ClientError, TimeoutError, JoinError) as err:
            _LOGGER.debug("First sync after joining failed, setup tries again: %s", err)
        self._title, self._data = title or "Orgaia", data
        # Who is who belongs to the setup: without it the card cannot tell who ticked something off.
        if view is not None and self.hass.states.async_all("person"):
            self._labels = _person_labels(view)
        return await self.async_step_ready()

    async def async_step_ready(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Connected. What is left is one look: who is who, and whether the dashboard should stand in the sidebar."""
        assert self._engine is not None
        if user_input is not None:
            persons = {pid: user_input[label] for label, pid in self._labels.items() if user_input.get(label)}
            options: dict[str, Any] = {CONF_DASHBOARD: bool(user_input.get(CONF_DASHBOARD, True))}
            if persons:
                options[CONF_PERSONS] = persons
            return self.async_create_entry(
                title=self._title, data=self._data, options=options, description_placeholders={"group": self._title}
            )
        fields = dict(_persons_schema(self.hass, self._engine.view(), self._labels, {}).schema) if self._labels else {}
        fields[vol.Optional(CONF_DASHBOARD, default=True)] = BooleanSelector()
        return self.async_show_form(
            step_id="ready", data_schema=vol.Schema(fields), description_placeholders={"group": self._title}
        )

    @staticmethod
    async def _leave(engine: GroupEngine) -> None:
        try:
            await engine.leave()
        except (ApiError, aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Leaving again failed: %s", err)


class OrgaiaOptionsFlow(OptionsFlow):
    """People (which Home Assistant person each one is) and settings (voice, lists, devices, ticks)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        if not getattr(entry, "runtime_data", None):
            return self.async_abort(reason="not_loaded")
        return self.async_show_menu(step_id="init", menu_options=["persons", "settings"])

    async def async_step_persons(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        view = entry.runtime_data.data
        labels = _person_labels(view)
        if not labels:
            return self.async_abort(reason="no_persons")
        if user_input is not None:
            mapping = {pid: user_input[label] for label, pid in labels.items() if user_input.get(label)}
            return self.async_create_entry(data={**entry.options, CONF_PERSONS: mapping})
        current = entry.options.get(CONF_PERSONS) or {}
        return self.async_show_form(step_id="persons", data_schema=_persons_schema(self.hass, view, labels, current))

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        view = entry.runtime_data.data
        if user_input is not None:
            options = {**entry.options}
            voice = user_input.get(CONF_VOICE_PERSON) or ""
            options[CONF_VOICE_PERSON] = voice if voice != NOBODY else None
            options[CONF_LISTS] = list(user_input.get(CONF_LISTS) or [])
            options[CONF_PERSON_DEVICES] = bool(user_input.get(CONF_PERSON_DEVICES, True))
            options[CONF_COMPLETED_DAYS] = int(user_input.get(CONF_COMPLETED_DAYS, COMPLETED_DAYS))
            options[CONF_DASHBOARD] = bool(user_input.get(CONF_DASHBOARD, False))
            style = user_input.get(CONF_DASHBOARD_STYLE)
            options[CONF_DASHBOARD_STYLE] = style if style in DASHBOARD_STYLES else DASHBOARD_STYLES[0]
            chosen = user_input.get(CONF_DASHBOARD_SECTIONS) or []
            options[CONF_DASHBOARD_SECTIONS] = [s for s in DASHBOARD_SECTIONS if s in chosen] or list(
                DASHBOARD_DEFAULT_SECTIONS
            )
            return self.async_create_entry(data=options)
        persons = [SelectOptionDict(value=NOBODY, label="—")] + [
            SelectOptionDict(value=p["id"], label=p["name"]) for p in view.active_persons()
        ]
        lists = [
            SelectOptionDict(value=lst["id"], label=lst["name"])
            for lst in view.lists
            if lst["type"] in ("tasks", "shopping", "timetable")
        ]
        schema = {
            vol.Optional(CONF_VOICE_PERSON, default=entry.options.get(CONF_VOICE_PERSON) or NOBODY): SelectSelector(
                SelectSelectorConfig(options=persons, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_LISTS, default=entry.options.get(CONF_LISTS) or []): SelectSelector(
                SelectSelectorConfig(options=lists, multiple=True, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_PERSON_DEVICES, default=entry.options.get(CONF_PERSON_DEVICES, True)): BooleanSelector(),
            vol.Optional(
                CONF_COMPLETED_DAYS, default=entry.options.get(CONF_COMPLETED_DAYS, COMPLETED_DAYS)
            ): NumberSelector(NumberSelectorConfig(min=0, max=60, step=1, mode=NumberSelectorMode.BOX)),
            vol.Optional(CONF_DASHBOARD, default=bool(entry.options.get(CONF_DASHBOARD, False))): BooleanSelector(),
            vol.Optional(
                CONF_DASHBOARD_STYLE, default=entry.options.get(CONF_DASHBOARD_STYLE) or DASHBOARD_STYLES[0]
            ): SelectSelector(
                SelectSelectorConfig(
                    options=DASHBOARD_STYLES, translation_key=CONF_DASHBOARD_STYLE, mode=SelectSelectorMode.LIST
                )
            ),
            vol.Optional(
                CONF_DASHBOARD_SECTIONS,
                default=entry.options.get(CONF_DASHBOARD_SECTIONS) or list(DASHBOARD_DEFAULT_SECTIONS),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=DASHBOARD_SECTIONS,
                    translation_key=CONF_DASHBOARD_SECTIONS,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        }
        return self.async_show_form(step_id="settings", data_schema=vol.Schema(schema))


# Chosen in the settings when no person should add articles by voice.
NOBODY = "-"
