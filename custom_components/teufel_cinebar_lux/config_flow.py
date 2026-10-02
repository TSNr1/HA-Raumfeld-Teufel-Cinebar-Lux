"""Einrichtung: Host eingeben, Cinebar automatisch finden."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .definitions import CINEBAR_LUX_TYPE, CONF_HOST, CONF_NAME, CONF_PLAYER, DOMAIN
from .hub import async_list_players


class CinebarConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host = ""
        self._players: dict[str, dict] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = user_input[CONF_HOST].strip()
            try:
                self._players = await async_list_players(async_get_clientsession(self.hass), self._host)
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                if not self._players:
                    errors["base"] = "no_players"
                else:
                    cinebars = {u: p for u, p in self._players.items() if p["type"] == CINEBAR_LUX_TYPE}
                    if len(cinebars) == 1:
                        return await self._create(next(iter(cinebars)))
                    return await self.async_step_player()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST, default=self._host): str}),
            errors=errors,
        )

    async def async_step_player(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return await self._create(user_input[CONF_PLAYER])
        options = {u: p["name"] for u, p in self._players.items()}
        return self.async_show_form(
            step_id="player",
            data_schema=vol.Schema({vol.Required(CONF_PLAYER): vol.In(options)}),
        )

    async def _create(self, player_uuid: str) -> ConfigFlowResult:
        await self.async_set_unique_id(player_uuid)
        self._abort_if_unique_id_configured()
        name = self._players[player_uuid]["name"]
        return self.async_create_entry(
            title=name,
            data={CONF_HOST: self._host, CONF_PLAYER: player_uuid, CONF_NAME: name},
        )
