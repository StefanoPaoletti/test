"""Support for the CAME climate devices (thermostats and fan coils).

Versione ottimizzata da Stefano Paoletti
For more details: https://github.com/StefanoPaoletti/Came_Connect
"""

import logging
from typing import Optional

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.climate import (
    ENTITY_ID_FORMAT,
    HVACMode,
    ClimateEntity,
    ClimateEntityFeature,
)
from homeassistant.components.climate.const import HVACAction
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_TENTHS,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .pycame.came_manager import CameManager
from .pycame.devices import CameDevice
from .pycame.devices.came_thermo import (
    THERMO_DEHUMIDIFIER_ON,
    THERMO_FAN_SPEED_AUTO,
    THERMO_FAN_SPEED_FAST,
    THERMO_FAN_SPEED_MEDIUM,
    THERMO_FAN_SPEED_SLOW,
    THERMO_MODE_AUTO,
    THERMO_MODE_JOLLY,
    THERMO_MODE_MANUAL,
    THERMO_MODE_OFF,
    THERMO_SEASON_OFF,
    THERMO_SEASON_SUMMER,
    THERMO_SEASON_WINTER,
)

from .const import CONF_MANAGER, CONF_PENDING, DOMAIN, SIGNAL_DISCOVERY_NEW
from .entity import CameEntity

_LOGGER = logging.getLogger(__name__)

CAME_MODE_TO_HA = {
    THERMO_MODE_OFF: HVACMode.OFF,
    THERMO_MODE_AUTO: HVACMode.AUTO,
    THERMO_MODE_JOLLY: HVACMode.AUTO,
}

CAME_SEASON_TO_HA = {
    THERMO_SEASON_OFF: HVACMode.OFF,
    THERMO_SEASON_WINTER: HVACMode.HEAT,
    THERMO_SEASON_SUMMER: HVACMode.COOL,
}


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities
):
    """Set up CAME climate devices dynamically through discovery."""
    
    async def async_discover_sensor(dev_ids):
        """Discover and add CAME climate devices."""
        if not dev_ids:
            return
        
        _LOGGER.debug("Discovering %d new climate device(s)", len(dev_ids))
        entities = await hass.async_add_executor_job(_setup_entities, hass, dev_ids)
        
        if entities:
            _LOGGER.info("Adding %d climate entit(ies)", len(entities))
            async_add_entities(entities)

    async_dispatcher_connect(
        hass, SIGNAL_DISCOVERY_NEW.format(CLIMATE_DOMAIN), async_discover_sensor
    )

    devices_ids = hass.data[DOMAIN][CONF_PENDING].pop(CLIMATE_DOMAIN, [])
    await async_discover_sensor(devices_ids)


def _setup_entities(hass, dev_ids):
    """Set up CAME climate entities."""
    manager = hass.data[DOMAIN][CONF_MANAGER]  # type: CameManager
    entities = []
    
    for dev_id in dev_ids:
        device = manager.get_device_by_id(dev_id)
        if device is None:
            _LOGGER.warning("Climate device with ID %s not found", dev_id)
            continue

        try:
            if getattr(device, "support_fan_speed", False):
                _LOGGER.info(
                    "💨 Fan coil rilevato: %s → CameFancoilClimateEntity",
                    device.name,
                )
                entities.append(CameFancoilClimateEntity(device))
            else:
                _LOGGER.info(
                    "🌡️ Termostato rilevato: %s → CameClimateEntity", 
                    device.name
                )
                entities.append(CameClimateEntity(device))
        except Exception as exc:
            _LOGGER.error("Error setting up climate device %s: %s", dev_id, exc)
    
    return entities


class CameClimateEntity(CameEntity, ClimateEntity):
    """CAME climate entity (thermostat)."""
    
    def __init__(self, device: CameDevice):
        """Initialize CAME climate entity."""
        super().__init__(device)
        self.entity_id = ENTITY_ID_FORMAT.format(self.unique_id)

        # Determina le funzionalità supportate
        self._attr_supported_features = (
            (
                ClimateEntityFeature.TARGET_TEMPERATURE
                if device.support_target_temperature
                else 0
            )
            | (
                ClimateEntityFeature.TARGET_HUMIDITY
                if device.support_target_humidity
                else 0
            )
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

        self._attr_target_temperature_step = PRECISION_TENTHS
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        
        _LOGGER.debug(
            "Climate entity %s initialized with features: %s",
            self.entity_id,
            self._attr_supported_features
        )

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._device.current_temperature

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the target temperature."""
        return self._device.target_temperature

    @property
    def target_humidity(self) -> Optional[int]:
        """Return the target humidity."""
        return self._device.target_humidity

    @property
    def hvac_mode(self):
        """Return current HVAC mode set by user (not current action)."""
        if self._device.mode in CAME_MODE_TO_HA:
            return CAME_MODE_TO_HA[self._device.mode]
        if self._device.dehumidifier_state == THERMO_DEHUMIDIFIER_ON:
            return HVACMode.DRY
        return CAME_SEASON_TO_HA.get(self._device.season, HVACMode.OFF)

    @property
    def hvac_action(self) -> Optional[HVACAction]:
        """Return the current running HVAC operation for thermostats."""
        _LOGGER.debug(
            "🛠️ HVAC Action - %s: state=%s, mode=%s, season=%s",
            self.entity_id,
            self._device.state,
            self._device.mode,
            self._device.season,
        )

        if self._device.mode == THERMO_MODE_OFF:
            return HVACAction.OFF

        if self._device.state == 1:
            if self._device.season == THERMO_SEASON_WINTER:
                return HVACAction.HEATING
            elif self._device.season == THERMO_SEASON_SUMMER:
                return HVACAction.COOLING
            return HVACAction.HEATING  # fallback

        return HVACAction.IDLE

    @property
    def hvac_modes(self):
        """Return the list of available HVAC modes."""
        ops = [HVACMode.OFF, HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL]
        if self._device.support_target_humidity:
            ops.append(HVACMode.DRY)
        return ops

    def set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if ATTR_TEMPERATURE in kwargs:
            try:
                temp = kwargs[ATTR_TEMPERATURE]
                _LOGGER.debug("Setting temperature for %s to %s°C", self.entity_id, temp)
                self._device.set_target_temperature(temp)
            except Exception as exc:
                _LOGGER.error("Error setting temperature for %s: %s", self.entity_id, exc)

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new HVAC mode."""
        try:
            _LOGGER.debug("Setting HVAC mode for %s to %s", self.entity_id, hvac_mode)
            
            if hvac_mode == HVACMode.OFF:
                self._device.zone_config(mode=THERMO_MODE_OFF)
            elif hvac_mode == HVACMode.HEAT:
                self._device.zone_config(
                    mode=THERMO_MODE_MANUAL, season=THERMO_SEASON_WINTER
                )
            elif hvac_mode == HVACMode.COOL:
                self._device.zone_config(
                    mode=THERMO_MODE_MANUAL, season=THERMO_SEASON_SUMMER
                )
            elif hvac_mode == HVACMode.AUTO:
                self._device.zone_config(mode=THERMO_MODE_AUTO)
            else:
                _LOGGER.warning("Unknown HVAC mode %s, defaulting to AUTO", hvac_mode)
                self._device.zone_config(mode=THERMO_MODE_AUTO)
        except Exception as exc:
            _LOGGER.error("Error setting HVAC mode for %s: %s", self.entity_id, exc)


class CameFancoilClimateEntity(CameClimateEntity):
    """CAME fan coil climate entity with fan speed control."""
    
    def __init__(self, device: CameDevice):
        """Initialize CAME fan coil entity."""
        super().__init__(device)
        self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
        self._attr_fan_modes = ["auto", "low", "medium", "high"]
        
        _LOGGER.info(
            "🎛️ Fan coil %s: modalità disponibili %s", 
            device.name, 
            self._attr_fan_modes
        )

    @property
    def hvac_action(self) -> Optional[HVACAction]:
        """Return the current running HVAC action for fan coil."""
        if self._device.mode == THERMO_MODE_OFF:
            return HVACAction.OFF
        
        if self._device.fan_speed in [
            THERMO_FAN_SPEED_SLOW,
            THERMO_FAN_SPEED_MEDIUM,
            THERMO_FAN_SPEED_FAST,
            THERMO_FAN_SPEED_AUTO,
        ]:
            return HVACAction.FAN
        
        return HVACAction.IDLE

    @property
    def fan_mode(self) -> Optional[str]:
        """Return the current fan mode."""
        # Legge la velocità attuale dal dispositivo
        fan_mode = getattr(self._device, "fan_mode", None)
        if fan_mode is not None:
            # Normalizza in minuscolo per Home Assistant
            return fan_mode.lower()
        return None

    def set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        try:
            _LOGGER.info("🔁 Cambio velocità ventilatore %s: %s", self.entity_id, fan_mode)
            
            if fan_mode not in self._attr_fan_modes:
                _LOGGER.warning("🚫 Modalità ventilatore non valida: %s", fan_mode)
                return
            
            if not hasattr(self._device, "set_fan_speed"):
                _LOGGER.warning(
                    "⛔ Il dispositivo %s NON supporta set_fan_speed", 
                    self._device.name
                )
                return
            
            # Invia al dispositivo il fan_mode in MAIUSCOLO (CAME usa MAIUSCOLO)
            self._device.set_fan_speed(fan_mode.upper())
            
        except Exception as exc:
            _LOGGER.error("Error setting fan mode for %s: %s", self.entity_id, exc)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode asynchronously."""
        _LOGGER.debug("🔁 [ASYNC] Cambio velocità ventilatore %s: %s", self.entity_id, fan_mode)
        await self.hass.async_add_executor_job(self.set_fan_mode, fan_mode)
        self.async_write_ha_state()
