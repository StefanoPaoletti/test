"""Support for the CAME lights (on/off, dimmable, RGB) - ASYNC VERSION.

Versione ottimizzata ASYNC da Stefano Paoletti
For more details: https://github.com/StefanoPaoletti/Came_Connect
"""
import logging
from typing import List

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_HS_COLOR
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.light import ENTITY_ID_FORMAT, LightEntity

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .came_server import SecureCameManager
from .pycame.devices import CameDevice
from .pycame.devices.came_light import LIGHT_STATE_ON

from .const import CONF_MANAGER, CONF_PENDING, DOMAIN, SIGNAL_DISCOVERY_NEW, SIGNAL_UPDATE_ENTITY
from .entity import CameEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities
):
    """Set up CAME light devices dynamically through discovery."""

    async def async_discover_sensor(dev_ids):
        """Discover and add a discovered CAME light devices."""
        if not dev_ids:
            return

        _LOGGER.debug("Discovering %d new light(s)", len(dev_ids))
        entities = _setup_entities(hass, dev_ids)
        
        if entities:
            _LOGGER.info("Adding %d light entit(ies)", len(entities))
            async_add_entities(entities)

    async_dispatcher_connect(
        hass, SIGNAL_DISCOVERY_NEW.format(LIGHT_DOMAIN), async_discover_sensor
    )

    devices_ids = hass.data[DOMAIN][CONF_PENDING].pop(LIGHT_DOMAIN, [])
    await async_discover_sensor(devices_ids)


def _setup_entities(hass, dev_ids: List[str]):
    """Set up CAME light device."""
    manager = hass.data[DOMAIN][CONF_MANAGER]  # type: SecureCameManager
    entities = []
    
    for dev_id in dev_ids:
        device = manager.get_device_by_id(dev_id)
        if device is None:
            _LOGGER.warning("Light device with ID %s not found", dev_id)
            continue
        
        try:
            entities.append(CameLightEntity(device))
            _LOGGER.debug("Created light entity for device %s", dev_id)
        except Exception as exc:
            _LOGGER.error("Error setting up light %s: %s", dev_id, exc)
    
    return entities


class CameLightEntity(CameEntity, LightEntity):
    """CAME light device entity with full async support."""

    def __init__(self, device: CameDevice):
        """Init CAME light device entity."""
        super().__init__(device)
        self.entity_id = ENTITY_ID_FORMAT.format(self.unique_id)
        
        # Pending brightness for smooth operation
        self._pending_brightness = None

        # Determine supported features
        support_brightness = getattr(self._device, 'support_brightness', False)
        support_color = getattr(self._device, 'support_color', False)

        _LOGGER.debug(
            "Initializing light %s - brightness: %s, color: %s",
            self.entity_id,
            support_brightness,
            support_color
        )

        # Define supported_color_modes (required by modern HA)
        if support_color:
            self._attr_supported_color_modes = {"hs"}
        elif support_brightness:
            self._attr_supported_color_modes = {"brightness"}
        else:
            self._attr_supported_color_modes = {"onoff"}

        _LOGGER.debug(
            "Light %s color modes: %s",
            self.entity_id,
            self._attr_supported_color_modes
        )

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._device.state == LIGHT_STATE_ON

    @property
    def brightness(self):
        """Return the brightness of the light (0-255)."""
        if not hasattr(self._device, 'brightness') or not getattr(self._device, 'support_brightness', False):
            return None
        
        # Convert from 0-100 (CAME) to 0-255 (Home Assistant)
        brightness_pct = self._device.brightness
        if brightness_pct is not None:
            return round(brightness_pct * 255 / 100)
        return None

    @property
    def hs_color(self):
        """Return the hs_color of the light."""
        if not hasattr(self._device, 'hs_color') or not getattr(self._device, 'support_color', False):
            return None
        
        hs = self._device.hs_color
        if hs is not None:
            return tuple(hs)
        return None
    
    @property
    def color_mode(self):
        """Return the current color mode of the light."""
        if getattr(self._device, 'support_color', False):
            return "hs"
        elif getattr(self._device, 'support_brightness', False):
            return "brightness"
        else:
            return "onoff"

    async def async_turn_on(self, **kwargs):
        """Turn on or control the light - FULLY ASYNC."""
        try:
            _LOGGER.debug(
                "⚡ ASYNC turn on light %s - brightness: %s, hs_color: %s",
                self.entity_id,
                kwargs.get(ATTR_BRIGHTNESS),
                kwargs.get(ATTR_HS_COLOR)
            )

            brightness_pct = None
            if ATTR_BRIGHTNESS in kwargs and hasattr(self._device, 'async_set_brightness'):
                # Convert from 0-255 (HA) to 0-100 (CAME)
                brightness_pct = round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
            
            hs_color = kwargs.get(ATTR_HS_COLOR)

            # Handle brightness with pending logic for CAME devices
            if self._device.state == LIGHT_STATE_ON:
                # Light already on → apply brightness and color immediately
                if brightness_pct is not None:
                    await self._device.async_set_brightness(brightness_pct)
                    _LOGGER.debug(
                        "Light %s already ON, applied brightness %s%%",
                        self.entity_id,
                        brightness_pct
                    )
                
                if hs_color is not None and hasattr(self._device, 'async_set_hs_color'):
                    await self._device.async_set_hs_color(hs_color)
                    _LOGGER.debug(
                        "Light %s applied color HS: %s",
                        self.entity_id,
                        hs_color
                    )
            else:
                # Light off → turn on first, apply brightness on next update
                self._pending_brightness = brightness_pct
                await self._device.async_turn_on()
                _LOGGER.debug(
                    "Light %s turning ON, pending brightness: %s%%",
                    self.entity_id,
                    brightness_pct
                )

            # Update UI immediately for responsiveness
            self.async_write_ha_state()
            
        except Exception as exc:
            _LOGGER.error("Error turning on light %s: %s", self.entity_id, exc)

    async def async_turn_off(self, **kwargs):
        """Turn off the light - FULLY ASYNC."""
        try:
            _LOGGER.debug("⚡ ASYNC turn off light %s", self.entity_id)
            self._pending_brightness = None  # Cancel pending
            await self._device.async_turn_off()
            
            # Update UI immediately
            self.async_write_ha_state()
            
        except Exception as exc:
            _LOGGER.error("Error turning off light %s: %s", self.entity_id, exc)

    async def async_added_to_hass(self):
        """Register update listener when entity is added to hass."""
        await super().async_added_to_hass()
        
        # CRITICO: Ascolta il segnale SIGNAL_UPDATE_ENTITY
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE_ENTITY,
                self._handle_coordinator_update
            )
        )
        _LOGGER.debug("✅ Light %s registered update listener", self.entity_id)

    async def _handle_coordinator_update(self):
        """Handle update signal from coordinator."""
        _LOGGER.debug("🔄 Light %s received update signal", self.entity_id)
        
        # Apply pending brightness if needed
        if self._pending_brightness is not None and self._device.state == LIGHT_STATE_ON:
            _LOGGER.debug(
                "Light %s confirmed ON, applying pending brightness %s%%",
                self.entity_id,
                self._pending_brightness
            )
            try:
                await self._device.async_set_brightness(self._pending_brightness)
            except Exception as exc:
                _LOGGER.error("Error applying pending brightness: %s", exc)
            finally:
                self._pending_brightness = None
        
        # Update state in UI
        self.async_write_ha_state()
        _LOGGER.debug("✅ Light %s state updated in UI", self.entity_id)
