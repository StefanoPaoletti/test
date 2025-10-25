"""Support for the CAME digital inputs (binary sensors).

Versione ottimizzata da Stefano Paoletti
For more details: https://github.com/StefanoPaoletti/Came_Connect
"""
import logging
from typing import List

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.binary_sensor import (
    ENTITY_ID_FORMAT,
    BinarySensorEntity
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .pycame.came_manager import CameManager
from .pycame.devices import CameDevice
from .pycame.devices.came_digitalin import BINARY_SENSOR_STATE_OFF
from .const import CONF_MANAGER, CONF_PENDING, DOMAIN, SIGNAL_DISCOVERY_NEW
from .entity import CameEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities
):
    """Set up CAME digital input devices dynamically through discovery."""
    
    async def async_discover_sensor(dev_ids):
        """Discover and add a discovered CAME digital input devices."""
        if not dev_ids:
            return
        
        _LOGGER.debug("Discovering %d new binary sensor(s)", len(dev_ids))
        entities = await hass.async_add_executor_job(_setup_entities, hass, dev_ids)
        
        if entities:
            _LOGGER.info("Adding %d binary sensor entit(ies)", len(entities))
            async_add_entities(entities)
    
    async_dispatcher_connect(
        hass, SIGNAL_DISCOVERY_NEW.format(BINARY_SENSOR_DOMAIN), async_discover_sensor
    )
    
    devices_ids = hass.data[DOMAIN][CONF_PENDING].pop(BINARY_SENSOR_DOMAIN, [])
    await async_discover_sensor(devices_ids)


def _setup_entities(hass, dev_ids: List[str]):
    """Set up CAME digital input device."""
    manager = hass.data[DOMAIN][CONF_MANAGER]  # type: CameManager
    entities = []
    
    for dev_id in dev_ids:
        device = manager.get_device_by_id(dev_id)
        if device is None:
            _LOGGER.warning("Binary sensor device with ID %s not found", dev_id)
            continue
        
        try:
            entities.append(CameDigitalInEntity(device))
            _LOGGER.debug("Created binary sensor for device %s", dev_id)
        except Exception as exc:
            _LOGGER.error("Error setting up binary sensor %s: %s", dev_id, exc)
    
    return entities


class CameDigitalInEntity(CameEntity, BinarySensorEntity):
    """CAME digital input device entity (binary sensor)."""
    
    def __init__(self, device: CameDevice):
        """Init CAME digital input device entity."""
        super().__init__(device)
        self.entity_id = ENTITY_ID_FORMAT.format(self.unique_id)
        
        _LOGGER.debug(
            "Binary sensor %s initialized (device_class=%s)",
            self.entity_id,
            getattr(device, 'device_class', 'none')
        )
    
    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        # NOTA: La logica sembra invertita nel codice originale
        # Verifica se questo è corretto per il tuo sistema CAME
        state = self._device.state
        result = state == BINARY_SENSOR_STATE_OFF
        
        _LOGGER.debug(
            "Binary sensor %s: state=%s, is_on=%s",
            self.entity_id,
            state,
            result
        )
        
        return result
    
    @property
    def device_class(self):
        """Return the device class of the binary sensor."""
        # Ritorna la device class se disponibile dal dispositivo CAME
        return getattr(self._device, 'device_class', None)

