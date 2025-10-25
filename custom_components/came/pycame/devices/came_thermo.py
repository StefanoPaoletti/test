"""CAME ETI/Domo thermoregulation device implementation.

Versione ottimizzata da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
"""

import logging
from typing import Optional

from .base import TYPE_THERMOSTAT, CameDevice, DeviceState

_LOGGER = logging.getLogger(__name__)

# Thermoregulation device states
THERMO_STATE_OFF = 0
THERMO_STATE_ON = 1

# Thermoregulation device modes
THERMO_MODE_OFF = 0
THERMO_MODE_MANUAL = 1
THERMO_MODE_AUTO = 2
THERMO_MODE_JOLLY = 3

# Thermoregulation device seasons
THERMO_SEASON_OFF = "plant_off"
THERMO_SEASON_WINTER = "winter"
THERMO_SEASON_SUMMER = "summer"

# Thermoregulation device dehumidifier states
THERMO_DEHUMIDIFIER_OFF = 0
THERMO_DEHUMIDIFIER_ON = 1

# Thermoregulation device fan speeds
THERMO_FAN_SPEED_OFF = 0
THERMO_FAN_SPEED_SLOW = 1
THERMO_FAN_SPEED_MEDIUM = 2
THERMO_FAN_SPEED_FAST = 3
THERMO_FAN_SPEED_AUTO = 4


class CameThermo(CameDevice):
    """CAME ETI/Domo thermoregulation device class."""

    def __init__(self, manager, device_info: DeviceState):
        """Initialize CAME thermostat device."""
        super().__init__(manager, TYPE_THERMOSTAT, device_info)

    @property
    def mode(self) -> Optional[int]:
        """Get current thermostat mode."""
        return self._device_info.get("mode")

    @property
    def season(self) -> Optional[str]:
        """Get current season mode (winter/summer)."""
        return self._device_info.get("season")

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature in °C."""
        temp = self._device_info.get("temp", self._device_info.get("temp_dec"))
        return temp / 10 if temp is not None else None

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the target temperature in °C."""
        temp = self._device_info.get("set_point")
        return temp / 10 if temp is not None else None

    @property
    def support_target_temperature(self) -> bool:
        """Return True if device can change target temperature."""
        return True

    @property
    def dehumidifier_state(self) -> Optional[int]:
        """Return the state of dehumidifier."""
        dehumidifier = self._device_info.get("dehumidifier", {})
        return dehumidifier.get("enabled")

    @property
    def target_humidity(self) -> Optional[int]:
        """Return the target humidity level."""
        dehumidifier = self._device_info.get("dehumidifier", {})
        return dehumidifier.get("setpoint")

    @property
    def support_target_humidity(self) -> bool:
        """Return True if device can change target humidity."""
        return self.target_humidity is not None

    @property
    def fan_speed(self) -> Optional[int]:
        """Get current fan speed (0-4)."""
        return self._device_info.get("fan_speed")

    @property
    def support_fan_speed(self) -> bool:
        """Return True if device can change fan speed."""
        return self.fan_speed is not None

    @property
    def fan_mode(self) -> Optional[str]:
        """Return current fan mode as string (LOW/MEDIUM/HIGH/AUTO)."""
        speed = self.fan_speed
        if speed == THERMO_FAN_SPEED_SLOW:
            return "LOW"
        elif speed == THERMO_FAN_SPEED_MEDIUM:
            return "MEDIUM"
        elif speed == THERMO_FAN_SPEED_FAST:
            return "HIGH"
        elif speed == THERMO_FAN_SPEED_AUTO or speed == THERMO_FAN_SPEED_OFF:
            # When OFF, fan is disabled but displayed as AUTO
            return "AUTO"
        return "AUTO"  # Safe fallback

    def update(self):
        """Update device state from CAME device."""
        self._force_update("thermo")

    def zone_config(
        self,
        mode: int = None,
        temperature: float = None,
        season: str = None,
        fan_speed: int = None,
    ):
        """Change thermostat configuration.
        
        Args:
            mode: Thermostat mode (0=off, 1=manual, 2=auto, 3=jolly)
            temperature: Target temperature in °C
            season: Season mode (plant_off/winter/summer)
            fan_speed: Fan speed (0-4)
        """
        if mode is None and temperature is None and season is None and fan_speed is None:
            raise ValueError("At least one parameter is required")

        self._check_act_id()

        cmd = {
            "cmd_name": "thermo_zone_config_req",
            "act_id": self.act_id,
            "mode": mode if mode is not None else self._device_info.get("mode"),
            "set_point": (
                int(temperature * 10)
                if temperature is not None
                else self._device_info.get("set_point")
            ),
            "extended_infos": 0,
        }
        
        if season is not None:
            cmd["extended_infos"] = 1
            cmd["season"] = season
        
        if fan_speed is not None:
            cmd["extended_infos"] = 1
            cmd["fan_speed"] = fan_speed

        # Log changes
        log_params = {}
        for key in ["mode", "set_point", "season", "fan_speed"]:
            if key in cmd:
                log_params[key] = cmd[key]

        if mode is not None:
            log_params["mode"] = int(cmd["mode"] != THERMO_MODE_OFF)

        _LOGGER.debug(
            "Setting new config for thermostat '%s': %s",
            self.name,
            log_params
        )

        self._manager.application_request(cmd)

    def set_target_temperature(self, temp: float) -> None:
        """Set target temperature in °C."""
        _LOGGER.debug("Setting target temperature for %s: %.1f°C", self.name, temp)
        self.zone_config(temperature=temp)

    def set_fan_speed(self, speed: str) -> None:
        """Set fan coil speed.
        
        Args:
            speed: Fan speed string (LOW/MEDIUM/HIGH/AUTO)
        """
        speed_map = {
            "LOW": THERMO_FAN_SPEED_SLOW,
            "MEDIUM": THERMO_FAN_SPEED_MEDIUM,
            "HIGH": THERMO_FAN_SPEED_FAST,
            "AUTO": THERMO_FAN_SPEED_AUTO,
        }
        
        if speed not in speed_map:
            _LOGGER.warning(
                "Invalid fan speed for %s: %s (valid: LOW/MEDIUM/HIGH/AUTO)",
                self.name,
                speed
            )
            return

        _LOGGER.info("Setting fan speed for %s: %s", self.name, speed)
        
        try:
            self.zone_config(fan_speed=speed_map[speed])
        except Exception as exc:
            _LOGGER.error(
                "Error setting fan speed for %s: %s",
                self.name,
                exc
            )
