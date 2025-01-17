""" Implement the Select entities of this implementation """
from __future__ import annotations
import logging
from home_connect_async import Appliance, HomeConnect, HomeConnectError, Events
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .common import EntityBase, EntityManager
from .const import DEVICE_ICON_MAP, DOMAIN, SPECIAL_ENTITIES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass:HomeAssistant , config_entry:ConfigType, async_add_entities:AddEntitiesCallback) -> None:
    """Add Selects for passed config_entry in HA."""
    homeconnect:HomeConnect = hass.data[DOMAIN]['homeconnect']
    entity_manager = EntityManager(async_add_entities)

    def add_appliance(appliance:Appliance) -> None:
        if appliance.available_programs:
            device = ProgramSelect(appliance)
            entity_manager.add(device)

        if appliance.available_programs:
            for program in appliance.available_programs.values():
                if program.options:
                    for option in program.options.values():
                        if option.key not in SPECIAL_ENTITIES['ignore'] and option.allowedvalues and len(option.allowedvalues)>1:
                            device = OptionSelect(appliance, option.key)
                            entity_manager.add(device)

        for setting in appliance.settings.values():
            if setting.key not in SPECIAL_ENTITIES['ignore'] and setting.allowedvalues and len(setting.allowedvalues)>1:
                device = SettingsSelect(appliance, setting.key)
                entity_manager.add(device)

        entity_manager.register()

    def remove_appliance(appliance:Appliance) -> None:
        entity_manager.remove_appliance(appliance)

    homeconnect.register_callback(add_appliance, [Events.PAIRED, Events.PROGRAM_SELECTED])
    homeconnect.register_callback(remove_appliance, Events.DEPAIRED)
    for appliance in homeconnect.appliances.values():
        add_appliance(appliance)

class ProgramSelect(EntityBase, SelectEntity):
    """ Selection of available programs """

    @property
    def unique_id(self) -> str:
        return f'{self.haId}_programs'

    @property
    def name_ext(self) -> str:
        return "Programs"

    @property
    def icon(self) -> str:
        if self._appliance.type in DEVICE_ICON_MAP:
            return DEVICE_ICON_MAP[self._appliance.type]
        return None

    @property
    def device_class(self) -> str:
        return f"{DOMAIN}__programs"

    @property
    def available(self) -> bool:
        return super().available \
            and self._appliance.available_programs \
            and not self._appliance.active_program \
            and  (
                "BSH.Common.Status.RemoteControlActive" not in self._appliance.status or
                self._appliance.status["BSH.Common.Status.RemoteControlActive"]
            )

    @property
    def options(self) -> list[str]:
        """Return a set of selectable options."""
        if self._appliance.available_programs:
            return list(self._appliance.available_programs.keys())
        return []

    @property
    def current_option(self) -> str:
        """Return the selected entity option to represent the entity state."""
        if self._appliance.selected_program:
            key = self._appliance.selected_program.key
            if  key in self._appliance.available_programs:
                # The API sometimes returns programs which are not one of the avilable programs so we ignore it
                return key
        return None

    async def async_select_option(self, option: str) -> None:
        try:
            await self._appliance.async_select_program(key=option)
        except HomeConnectError as ex:
            if ex.error_description:
                raise HomeAssistantError(f"Failed to set the selected program: {ex.error_description} ({ex.code} - {self._key}={option})")
            else:
                raise HomeAssistantError(f"Failed to set the selected program ({ex.code} - {self._key}={option})")

    async def async_on_update(self, appliance:Appliance, key:str, value) -> None:
        self.async_write_ha_state()


class OptionSelect(EntityBase, SelectEntity):
    """ Selection of program options """
    @property
    def device_class(self) -> str:
        return f"{DOMAIN}__options"

    @property
    def name_ext(self) -> str|None:
        if self._appliance.available_programs:
            for program in self._appliance.available_programs.values():
                if program.options and self._key in program.options and program.options[self._key].name:
                    return program.options[self._key].name
        return None

    @property
    def icon(self) -> str:
        return self._conf.get('icon', 'mdi:office-building-cog')

    @property
    def available(self) -> bool:
        return self.program_option_available

    @property
    def options(self) -> list[str]:
        """Return a set of selectable options."""
        if self.program_option_available:
            selected_program_key = self._appliance.selected_program.key
            available_program = self._appliance.available_programs.get(selected_program_key)
            if available_program:
                option = available_program.options.get(self._key)
                if option:
                    #_LOGGER.info("Allowed values for %s : %s", self._key, str(option.allowedvalues))
                    vals = option.allowedvalues.copy()
                    vals.append('')
                    return vals
        #_LOGGER.info("Allowed values for %s : %s", self._key, None)
        return []

    @property
    def current_option(self) -> str:
        """Return the selected entity option to represent the entity state."""
        # if self._appliance.selected_program.options[self._key].value not in self.options:
        #     _LOGGER.debug("The current option is not in the list of available options")
        if self.program_option_available:
            if self._appliance.selected_program.options[self._key].value == '':
                _LOGGER.error("Returning empty option value for %s", self._key)
            #_LOGGER.info("Current value for %s : %s", self._key, self._appliance.selected_program.options[self._key].value)
            return self._appliance.selected_program.options[self._key].value
        else:
            #_LOGGER.info("Current value for %s : %s", self._key, None)
            return None

    async def async_select_option(self, option: str) -> None:
        try:
            await self._appliance.async_set_option(self._key, option)
        except HomeConnectError as ex:
            if ex.error_description:
                raise HomeAssistantError(f"Failed to set the selected option: {ex.error_description} ({ex.code})")
            else:
                raise HomeAssistantError(f"Failed to set the selected option: ({ex.code})")

    async def async_on_update(self, appliance:Appliance, key:str, value) -> None:
        self.async_write_ha_state()


class SettingsSelect(EntityBase, SelectEntity):
    """ Selection of settings """
    @property
    def device_class(self) -> str:
        return f"{DOMAIN}__settings"

    @property
    def name_ext(self) -> str|None:
        if self._key in self._appliance.settings and self._appliance.settings[self._key].name:
            return self._appliance.settings[self._key].name
        return None

    @property
    def icon(self) -> str:
        return self._conf.get('icon', 'mdi:tune')

    @property
    def available(self) -> bool:
        return super().available \
        and (
            "BSH.Common.Status.RemoteControlActive" not in self._appliance.status or
            self._appliance.status["BSH.Common.Status.RemoteControlActive"]
        )

    @property
    def options(self) -> list[str]:
        """Return a set of selectable options."""
        try:
            return self._appliance.settings[self._key].allowedvalues
        except Exception as ex:
            pass
        return []

    @property
    def current_option(self) -> str:
        """Return the selected entity option to represent the entity state."""
        return self._appliance.settings[self._key].value

    async def async_select_option(self, option: str) -> None:
        try:
            await self._appliance.async_apply_setting(self._key, option)
        except HomeConnectError as ex:
            if ex.error_description:
                raise HomeAssistantError(f"Failed to apply the setting: {ex.error_description} ({ex.code})")
            else:
                raise HomeAssistantError(f"Failed to apply the setting: ({ex.code})")


    async def async_on_update(self, appliance:Appliance, key:str, value) -> None:
        self.async_write_ha_state()
