"""Support for the CAME covers (openings like garage doors, shutters, etc.).

Versione ottimizzata da Stefano Paoletti
For more details: https://github.com/StefanoPaoletti/Came_Connect
"""
import logging
from typing import List

from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.components.cover import (
    ENTITY_ID_FORMAT,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .pycame.came_manager import CameManager
from .pycame.devices import CameDevice
from .pycame.devices.came_opening import OPENING_STATE_OPEN
from .const import CONF_MANAGER, CONF_PENDING, DOMAIN, SIGNAL_DISCOVERY_NEW
from .entity import CameEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities
):
    """Set up CAME openings devices dynamically through discovery."""
    
    async def async_discover_sensor(dev_ids):
        """Discover and add a discovered CAME openings devices."""
        if not dev_ids:
            return
        
        _LOGGER.debug("Discovering %d new cover(s)", len(dev_ids))
        entities = await hass.async_add_executor_job(_setup_entities, hass, dev_ids)
        
        if entities:
            _LOGGER.info("Adding %d cover entit(ies)", len(entities))
            async_add_entities(entities)
    
    async_dispatcher_connect(
        hass, SIGNAL_DISCOVERY_NEW.format(COVER_DOMAIN), async_discover_sensor
    )
    
    devices_ids = hass.data[DOMAIN][CONF_PENDING].pop(COVER_DOMAIN, [])
    await async_discover_sensor(devices_ids)


def _setup_entities(hass, dev_ids: List[str]):
    """Set up CAME opening device."""
    manager = hass.data[DOMAIN][CONF_MANAGER]  # type: CameManager
    entities = []
    
    for dev_id in dev_ids:
        device = manager.get_device_by_id(dev_id)
        if device is None:
            _LOGGER.warning("Cover device with ID %s not found", dev_id)
            continue
        
        try:
            entities.append(CameCoverEntity(device))
            _LOGGER.debug("Created cover entity for device %s", dev_id)
        except Exception as exc:
            _LOGGER.error("Error setting up cover %s: %s", dev_id, exc)
    
    return entities


class CameCoverEntity(CameEntity, CoverEntity):
    """CAME opening device entity (cover)."""
    
    def __init__(self, device: CameDevice):
        """Init CAME opening device entity."""
        super().__init__(device)
        self.entity_id = ENTITY_ID_FORMAT.format(self.unique_id)
        
        # Determina le funzionalità supportate
        self._attr_supported_features = (
            CoverEntityFeature.OPEN 
            | CoverEntityFeature.CLOSE 
            | CoverEntityFeature.STOP
        )
        
        # Aggiungi supporto position se disponibile
        if hasattr(device, 'current_position'):
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION
            _LOGGER.debug("Cover %s supports position control", self.entity_id)
        
        _LOGGER.debug(
            "Cover %s initialized with features: %s",
            self.entity_id,
            self._attr_supported_features
        )
    
    @property
    def is_open(self):
        """Return true if cover is open."""
        is_open = self._device.state == OPENING_STATE_OPEN
        _LOGGER.debug("Cover %s is_open: %s (state=%s)", self.entity_id, is_open, self._device.state)
        return is_open
    
    @property
    def is_closed(self):
        """Return true if cover is closed."""
        # Inverso di is_open
        return not self.is_open
    
    @property
    def current_cover_position(self):
        """Return current position of cover (0 closed, 100 open)."""
        if hasattr(self._device, 'current_position'):
            position = self._device.current_position
            _LOGGER.debug("Cover %s current position: %s", self.entity_id, position)
            return position
        return None
    
    def open_cover(self, **kwargs):
        """Open the cover."""
        try:
            _LOGGER.info("🔼 Opening cover %s", self.entity_id)
            self._device.open()
        except Exception as exc:
            _LOGGER.error("Error opening cover %s: %s", self.entity_id, exc)
    
    def close_cover(self, **kwargs):
        """Close the cover."""
        try:
            _LOGGER.info("🔽 Closing cover %s", self.entity_id)
            self._device.close()
        except Exception as exc:
            _LOGGER.error("Error closing cover %s: %s", self.entity_id, exc)
    
    def stop_cover(self, **kwargs):
        """Stop the cover."""
        try:
            _LOGGER.info("⏸️ Stopping cover %s", self.entity_id)
            self._device.stop()
        except Exception as exc:
            _LOGGER.error("Error stopping cover %s: %s", self.entity_id, exc)
    
    def set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        if not hasattr(self._device, 'set_position'):
            _LOGGER.warning("Cover %s does not support position control", self.entity_id)
            return
        
        try:
            position = kwargs.get('position')
            _LOGGER.info("📍 Setting cover %s to position %s%%", self.entity_id, position)
            self._device.set_position(position)
        except Exception as exc:
            _LOGGER.error("Error setting cover position %s: %s", self.entity_id, exc)
