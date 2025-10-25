"""Support for the CAME analog sensors."""

import logging
from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    ENTITY_ID_FORMAT,
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
    RestoreEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import PRESSURE_UNITS, TEMPERATURE_UNITS

from .pycame.came_manager import CameManager
from .pycame.devices import CameDevice
from .pycame.devices.came_energy_sensor import CameEnergySensor
from .const import CONF_MANAGER, CONF_PENDING, DOMAIN, SIGNAL_DISCOVERY_NEW
from .entity import CameEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities
):
    """Set up CAME analog sensors dynamically through discovery."""

    async def async_discover_sensor(dev_ids):
        """Discover and add a discovered CAME sensor."""
        if not dev_ids:
            return
        entities = await hass.async_add_executor_job(_setup_entities, hass, dev_ids)
        async_add_entities(entities)

    async_dispatcher_connect(
        hass, SIGNAL_DISCOVERY_NEW.format(SENSOR_DOMAIN), async_discover_sensor
    )

    devices_ids = hass.data[DOMAIN][CONF_PENDING].pop(SENSOR_DOMAIN, [])
    await async_discover_sensor(devices_ids)

def _setup_entities(hass, dev_ids):
    """Set up CAME analog sensor device."""
    manager = hass.data[DOMAIN][CONF_MANAGER]
    entities = []
    for dev_id in dev_ids:
        device = manager.get_device_by_id(dev_id)
        if device is None:
            continue
        if isinstance(device, CameEnergySensor):
            produced = 0
            extra = device.extra_state_attributes
            if isinstance(extra, dict):
                produced = extra.get("produced", 0)

            power_sensor = CameEnergySensorEntity(device)
            energy_sensor = CameEnergyTotalSensorEntity(power_sensor, produced=produced)
            entities.append(power_sensor)
            entities.append(energy_sensor)
        else:
            entities.append(CameSensorEntity(device))
    return entities

class CameSensorEntity(CameEntity, SensorEntity):
    """CAME analog sensor device entity."""

    def __init__(self, device: CameDevice):
        """Init CAME analog sensor device entity."""
        super().__init__(device)
        self.entity_id = ENTITY_ID_FORMAT.format(self.unique_id)
        self._attr_state_class = SensorStateClass.MEASUREMENT

        if self._device.unit_of_measurement == "%":
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE
        elif self._device.unit_of_measurement in TEMPERATURE_UNITS:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = self._device.unit_of_measurement
        elif self._device.unit_of_measurement in PRESSURE_UNITS:
            self._attr_device_class = SensorDeviceClass.PRESSURE
            self._attr_native_unit_of_measurement = self._device.unit_of_measurement
        else:
            self._attr_device_class = self._device.device_class
            self._attr_native_unit_of_measurement = self._device.unit_of_measurement

        self._attr_unit_of_measurement = self._device.unit_of_measurement

    @property
    def state(self) -> StateType:
        """Return the state of the entity."""
        return self._device.state

class CameEnergySensorEntity(CameEntity, SensorEntity):
    """CAME energy sensor device entity."""

    _attr_should_poll = True

    def __init__(self, device: CameDevice):
        """Init CAME energy sensor device entity."""
        super().__init__(device)
        device.hass_entity = self
        self.entity_id = ENTITY_ID_FORMAT.format(self.unique_id)
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = "W"

    def update(self):
        """Update the energy sensor entity."""
        self._device.update()

    @property
    def native_value(self) -> StateType:
        """Return the current power."""
        state = self._device.state
        if isinstance(state, dict):
            return state.get("produced")
        return state

    @property
    def extra_state_attributes(self):
        """Return the extra attributes."""
        return self._device.extra_state_attributes or {}

class CameEnergyTotalSensorEntity(CameEntity, RestoreEntity, SensorEntity):
    """Sensor that integrates power to compute energy."""

    _attr_should_poll = True

    def __init__(self, source_entity: CameEnergySensorEntity, produced: int = 0):
        super().__init__(source_entity._device)
        self._source_entity = source_entity
        self._produced = produced

        if produced == 1:
            self._attr_name = f"{source_entity.name} Energia prodotta"
            self._attr_unique_id = f"{source_entity.unique_id}_energy_produced"
        else:
            self._attr_name = f"{source_entity.name} Energia consumata"
            self._attr_unique_id = f"{source_entity.unique_id}_energy_consumed"

        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = "kWh"
        self._last_time = None
        self._energy_total = 0.0

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()
        
        last_state = await self.async_get_last_state()
        
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                self._energy_total = float(last_state.state)
                _LOGGER.info(
                    "Restored energy for %s: %.3f kWh",
                    self.entity_id,
                    self._energy_total
                )
            except (ValueError, TypeError):
                _LOGGER.warning("Could not restore energy for %s", self.entity_id)
                self._energy_total = 0.0
        else:
            _LOGGER.info("No previous state for %s, starting from 0 kWh", self.entity_id)

    def update(self):
        """Update energy calculation."""
        now = dt_util.utcnow()
        power = self._source_entity.native_value
        
        if self._last_time is not None and isinstance(power, (int, float)):
            elapsed_hours = (now - self._last_time).total_seconds() / 3600
            energy_increment = (power * elapsed_hours) / 1000
            self._energy_total += energy_increment
            
            if energy_increment > 0.0001:
                _LOGGER.debug(
                    "Energy %s: +%.4f kWh (power=%dW, dt=%.1fs) -> %.3f kWh",
                    self.entity_id,
                    energy_increment,
                    int(power),
                    (now - self._last_time).total_seconds(),
                    self._energy_total
                )
        
        self._last_time = now

    @property
    def native_value(self):
        """Return total energy in kWh."""
        return round(self._energy_total, 3)
