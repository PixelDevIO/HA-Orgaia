"""Changes made from Home Assistant entities, always in the name of the person the user is."""

from __future__ import annotations

import time

from homeassistant.components.websocket_api import current_connection
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .board import person_of_user
from .client.engine import WriteError
from .const import CONF_VOICE_PERSON, DOMAIN
from .entity import OrgaiaEntity
from .protocol.actions import Change

# A context a service call set on the entity just before calling it. One that is older was left over
# from an earlier call; a voice assistant calls the entity without setting one.
FRESH_CONTEXT = 2.0


def fail(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders)


class Writer(OrgaiaEntity):
    """Finds out who is calling and writes in their name. Nothing is written anonymously."""

    def _caller(self) -> tuple[str | None, bool]:
        """The person behind this call, and whether a user was known at all. The context is used up."""
        context, at = self._context, self._context_set
        self._context, self._context_set = None, None
        user = context.user_id if context and at and time.time() - at <= FRESH_CONTEXT else None
        if user:
            return person_of_user(self.hass, self.coordinator.config_entry, user), True
        # The calendar panel and Assist in the browser call the entity straight from the user's
        # connection, without a context: the connection still tells who it is.
        connection = current_connection.get()
        if connection is not None and connection.user is not None:
            return person_of_user(self.hass, self.coordinator.config_entry, connection.user.id), False
        return None, False

    def _person(self, adding_article: bool = False) -> str:
        """The person to write as. Only adding an article may fall back to the voice assistant's person."""
        person, known = self._caller()
        if person:
            return person
        if not known and adding_article:
            voice = self.coordinator.config_entry.options.get(CONF_VOICE_PERSON)
            p = self.coordinator.data.person_by_id.get(voice or "")
            if p and not p["removed"]:
                return p["id"]
        raise fail("who_are_you" if known else "no_user")

    async def _write(self, changes: list[Change], person: str) -> None:
        if not changes:
            return
        try:
            await self.coordinator.write(changes, person)
        except WriteError as err:
            entry = self.coordinator.config_entry
            if err.reason == "read_only":
                raise fail("read_only", group=entry.title) from err
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=f"write_{err.reason}",
                translation_placeholders={"group": entry.title},
            ) from err
