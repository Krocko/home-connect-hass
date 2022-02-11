""" Implement the Sensor entities of this implementation """
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import logging
from home_connect_async import Appliance, HomeConnect, Events
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .common import EntityBase, EntityManager
from .const import DEVICE_ICON_MAP, DOMAIN, SPECIAL_ENTITIES, HOME_CONNECT_DEVICE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass:HomeAssistant , config_entry:ConfigType, async_add_entities:AddEntitiesCallback) -> None:
    """ Add sensors for passed config_entry in HA """
    #auth = hass.data[DOMAIN][config_entry.entry_id]
    homeconnect:HomeConnect = hass.data[DOMAIN]['homeconnect']
    entity_manager = EntityManager()

    def add_appliance(appliance:Appliance) -> None:
        new_entities = []
        if appliance.available_programs and appliance.selected_program:
            device = SelectedProgramSensor(appliance)
            new_entities.append(device)

        if appliance.selected_program:
            for option in appliance.selected_program.options.values():
                if not isinstance(option.value, bool):
                    device = ProgramOptionSensor(appliance, option.key, SPECIAL_ENTITIES['options'].get(option.key, {}))
                    new_entities.append(device)

            if appliance.active_program:
                for option in appliance.active_program.options.values():
                    if option.key not in appliance.selected_program.options and not isinstance(option.value, bool):
                        device = ActivityOptionSensor(appliance, option.key, SPECIAL_ENTITIES['options'].get(option.key, {}))
                        new_entities.append(device)

        for (key, value) in appliance.status.items():
            device = None
            if key in SPECIAL_ENTITIES['status']:
                conf = SPECIAL_ENTITIES['status'][key]
                if conf['type'] == 'sensor':
                    device = StatusSensor(appliance, key, conf)
            else:
                conf = {}
                if not isinstance(value, bool): # should be a binary sensor if it has a boolean value
                    if 'temperature' in key.lower():
                        conf['class'] = 'temperature'
                    device = StatusSensor(appliance, key, conf)
            if device:
                new_entities.append(device)

        # for (key, conf) in SPECIAL_ENTITIES['activity_options'].items():
        #     if appliance.type in conf['appliances'] and conf['type']=='sensor':
        #         device = ActivityOptionSensor(appliance, key, conf)
        #         new_entities.append(device)

        if len(new_entities)>0:
            entity_manager.register_entities(new_entities, async_add_entities)

    def remove_appliance(appliance:Appliance) -> None:
        entity_manager.remove_appliance(appliance)


    # First add the global home connect satus sensor
    async_add_entities([HomeConnectStatusSensor(homeconnect)])

    # Subscribe for events and register the existing appliances
    homeconnect.register_callback(add_appliance, [Events.PAIRED, Events.PROGRAM_STARTED])
    homeconnect.register_callback(remove_appliance, Events.DEPAIRED)
    for appliance in homeconnect.appliances.values():
        add_appliance(appliance)



class SelectedProgramSensor(EntityBase, SensorEntity):
    """ Selected program sensor """
    @property
    def unique_id(self) -> str:
        return f'{self.haId}_selected_program'

    @property
    def name(self) -> str:
        return f"{self._appliance.brand} {self._appliance.type} - Selected Program"

    @property
    def icon(self) -> str:
        if self._appliance.type in DEVICE_ICON_MAP:
            return DEVICE_ICON_MAP[self._appliance.type]
        return None

    @property
    def device_class(self) -> str:
        return f"{DOMAIN}__programs"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._appliance.selected_program.key if self._appliance.selected_program else None

    async def async_on_update(self, appliance:Appliance, key:str, value) -> None:
        self.async_write_ha_state()

    # async def async_start_program(self) -> bool:
    #     return await self._appliance.async_start_program()

    # async def async_select_program(self, program, options=None, **kwargs) -> bool:
    #     return await self._appliance.async_select_program(key=program, options=options)


class ProgramOptionSensor(EntityBase, SensorEntity):
    """ Special active program sensor """
    @property
    def device_class(self) -> str:
        if "class" in self._conf:
            return self._conf["class"]
        return f"{DOMAIN}__options"

    @property
    def icon(self) -> str:
        return self._conf.get('icon', 'mdi:office-building-cog')

    @property
    def name(self) -> str:
        if self._appliance.selected_program and (self._key in self._appliance.selected_program.options):
            name = self._appliance.selected_program.options[self._key].name
            if name:
                return f"{self._appliance.brand} {self._appliance.type} - {name}"
        return super().name

    @property
    def available(self) -> bool:
        return (self._key in self._appliance.selected_program.options) and super().available

    @property
    def internal_unit(self) -> str | None:
        """ Get the original unit before manipulations """
        if "unit" in self._conf:
            return self._conf["unit"]
        if self._appliance.active_program and (self._key in  self._appliance.active_program.options):
            return self._appliance.active_program.options[self._key].unit
        if self._appliance.selected_program and (self._key in  self._appliance.selected_program.options):
            return self._appliance.selected_program.options[self._key].unit
        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        unit = self.internal_unit
        if unit=="gram":
            return "kg"
        return unit

    @property
    def native_value(self):
        """Return the state of the sensor."""

        program = self._appliance.active_program if self._appliance.active_program else self._appliance.selected_program
        if program is None:
            return None

        if self._key not in program.options:
            _LOGGER.debug("Option key %s is missing from program", self._key)
            return None

        option = program.options[self._key]

        if self.device_class == "timestamp":
            return  datetime.now(timezone.utc).astimezone() + timedelta(seconds=option.value)
        if "timespan" in self.device_class:
            m, s = divmod(option.value, 60)
            h, m = divmod(m, 60)
            return f"{h}:{m:02d}"
        if self.internal_unit=="gram":
            return round(option.value/1000, 1)
        if option.displayvalue:
            return option.displayvalue
        if isinstance(option.value, str):
            if option.value.endswith(".Off"):
                return "Off"
            if option.value.endswith(".On"):
                return "On"
        return option.value

    async def async_on_update(self, appliance:Appliance, key:str, value) -> None:
        self.async_write_ha_state()


class ActivityOptionSensor(ProgramOptionSensor):
    """ Special active program sensor """

    @property
    def available(self) -> bool:
        return self._appliance.active_program and self._key in self._appliance.active_program.options


class StatusSensor(EntityBase, SensorEntity):
    """ Status sensor """
    @property
    def device_class(self) -> str:
        return f"{DOMAIN}__status"

    @property
    def icon(self) -> str:
        return self._conf.get('icon', 'mdi:gauge-full')

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._appliance.status.get(self._key)

    async def async_on_update(self, appliance:Appliance, key:str, value) -> None:
        self.async_write_ha_state()


class HomeConnectStatusSensor(SensorEntity):
    """ Global Home Connect status sensor """
    should_poll = True

    def __init__(self, homeconnect:HomeConnect) -> None:
        self._homeconnect = homeconnect

    @property
    def device_info(self):
        """Return information to link this entity with the correct device."""
        return HOME_CONNECT_DEVICE

    @property
    def unique_id(self) -> str:
        return "homeconnect_status"

    @property
    def name(self) -> str:
        return "Home Connect Status"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return self._homeconnect.status.name
