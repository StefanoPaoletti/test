"""Support for the CAME lights (on/off, dimmable, RGB).

Versione ottimizzata da Stefano Paoletti
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

from .pycame.came_manager import CameManager
from .pycame.devices import CameDevice
from .pycame.devices.came_light import LIGHT_STATE_ON

from .const import CONF_MANAGER, CONF_PENDING, DOMAIN, SIGNAL_DISCOVERY_NEW
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
        entities = await hass.async_add_executor_job(_setup_entities, hass, dev_ids)
        
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
    manager = hass.data[DOMAIN][CONF_MANAGER]  # type: CameManager
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
    """CAME light device entity."""

    def __init__(self, device: CameDevice):
        """Init CAME light device entity."""
        super().__init__(device)
        self.entity_id = ENTITY_ID_FORMAT.format(self.unique_id)
        
        # OTTIMIZZATO: Inizializza pending_brightness in __init__
        self._pending_brightness = None

        # Determina le funzionalità supportate dal dispositivo
        support_brightness = getattr(self._device, 'support_brightness', False)
        support_color = getattr(self._device, 'support_color', False)

        _LOGGER.debug(
            "Initializing light %s - brightness: %s, color: %s",
            self.entity_id,
            support_brightness,
            support_color
        )

        # Definisci i supported_color_modes (richiesto da HA moderno)
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
        # Verifica se il dispositivo supporta la luminosità
        if not hasattr(self._device, 'brightness') or not getattr(self._device, 'support_brightness', False):
            return None
        
        # Converti da 0-100 (CAME) a 0-255 (Home Assistant)
        brightness_pct = self._device.brightness
        if brightness_pct is not None:
            return round(brightness_pct * 255 / 100)
        return None

    @property
    def hs_color(self):
        """Return the hs_color of the light."""
        # Verifica se il dispositivo supporta il colore
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

    def turn_on(self, **kwargs):
        """Turn on or control the light."""
        try:
            _LOGGER.debug(
                "💡 Turn on light %s - brightness: %s, hs_color: %s",
                self.entity_id,
                kwargs.get(ATTR_BRIGHTNESS),
                kwargs.get(ATTR_HS_COLOR)
            )

            brightness_pct = None
            if ATTR_BRIGHTNESS in kwargs and hasattr(self._device, 'set_brightness'):
                # Converti da 0-255 (HA) a 0-100 (CAME)
                brightness_pct = round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
            
            hs_color = kwargs.get(ATTR_HS_COLOR)

            # Gestione brightness con logica pending per dispositivi CAME
            if self._device.state == LIGHT_STATE_ON:
                # Luce già accesa → applica subito brightness e colore
                if brightness_pct is not None:
                    self._device.set_brightness(brightness_pct)
                    _LOGGER.debug(
                        "Light %s already ON, applying brightness %s%%",
                        self.entity_id,
                        brightness_pct
                    )
                
                if hs_color is not None and hasattr(self._device, 'set_hs_color'):
                    self._device.set_hs_color(hs_color)
                    _LOGGER.debug(
                        "Light %s applying color HS: %s",
                        self.entity_id,
                        hs_color
                    )
            else:
                # Luce spenta → prima accendi, poi applica brightness al prossimo update
                self._pending_brightness = brightness_pct
                self._device.turn_on()
                _LOGGER.debug(
                    "Light %s turning ON, pending brightness: %s%%",
                    self.entity_id,
                    brightness_pct
                )

            # Aggiorna subito l'UI per reattività
            self.schedule_update_ha_state()
            
        except Exception as exc:
            _LOGGER.error("Error turning on light %s: %s", self.entity_id, exc)

    def turn_off(self, **kwargs):
        """Turn off the light."""
        try:
            _LOGGER.debug("💡 Turn off light %s", self.entity_id)
            self._pending_brightness = None  # Cancella pending
            self._device.turn_off()
        except Exception as exc:
            _LOGGER.error("Error turning off light %s: %s", self.entity_id, exc)

    def update(self):
        """Update the entity state and apply pending brightness if needed."""
        try:
            # Se c'è un brightness pending e la luce è ora accesa, applicalo
            if self._pending_brightness is not None and self._device.state == LIGHT_STATE_ON:
                _LOGGER.debug(
                    "Light %s confirmed ON, applying pending brightness %s%%",
                    self.entity_id,
                    self._pending_brightness
                )
                self._device.set_brightness(self._pending_brightness)
                self._pending_brightness = None
        except Exception as exc:
            _LOGGER.error("Error updating light %s: %s", self.entity_id, exc)
