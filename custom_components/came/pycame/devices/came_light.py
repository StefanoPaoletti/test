"""CAME ETI/Domo light device implementation.

Versione ottimizzata da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
"""

import colorsys
import logging
from typing import List

from .base import TYPE_LIGHT, CameDevice, DeviceState

_LOGGER = logging.getLogger(__name__)

# Light types
LIGHT_TYPE_STEP_STEP = "STEP_STEP"
LIGHT_TYPE_DIMMER = "DIMMER"
LIGHT_TYPE_RGB = "RGB"

# Light states
LIGHT_STATE_OFF = 0
LIGHT_STATE_ON = 1
LIGHT_STATE_AUTO = 4


class CameLight(CameDevice):
    """CAME ETI/Domo light device class."""

    def __init__(self, manager, device_info: DeviceState):
        """Initialize CAME light device."""
        super().__init__(manager, TYPE_LIGHT, device_info)

    @property
    def light_type(self) -> str:
        """Get light type (STEP_STEP, DIMMER, or RGB)."""
        return self._device_info.get("type")

    @property
    def support_color(self) -> bool:
        """Return True if light supports color as HS values."""
        return self.light_type.upper() == LIGHT_TYPE_RGB

    @property
    def rgb_color(self) -> List[int]:
        """Return the RGB color of the light."""
        perc = int(self._device_info.get("perc", 100) * 255 / 100)
        return self._device_info.get("rgb", [perc, perc, perc])

    @property
    def _hsv_color(self) -> List[int]:
        """Return the HSV color of the light."""
        rgb = self.rgb_color
        hsv = colorsys.rgb_to_hsv(rgb[0], rgb[1], rgb[2])
        return [round(hsv[0] * 360), round(hsv[1] * 100), round(hsv[2] * 100 / 255)]

    @property
    def hs_color(self) -> List[int]:
        """Return the HS color of the light."""
        return self._hsv_color[0:2]

    def set_rgb_color(self, rgb: List[int]):
        """Set RGB color of light (values 0-255)."""
        if not self.support_color:
            _LOGGER.debug("Light %s does not support color", self.name)
            return

        # Clamp RGB values to 0-255
        rgb = [max(0, min(255, val)) for val in rgb]

        _LOGGER.debug("Setting RGB color for %s: %s", self.name, rgb)
        self.switch(rgb=rgb)

    def set_hs_color(self, hs: List[float]):
        """Set HS color of light (H: 0-360, S: 0-100)."""
        if not self.support_color:
            _LOGGER.debug("Light %s does not support color", self.name)
            return

        # Clamp HS values
        hs = [max(0, min(360, hs[0])), max(0, min(100, hs[1]))]

        if self.support_color:
            hsv = self._hsv_color
            rgb = list(
                map(
                    int,
                    colorsys.hsv_to_rgb(
                        hs[0] / 360, hs[1] / 100, hsv[2] * 255 / 100
                    ),
                )
            )
            _LOGGER.debug("Setting HS color for %s: HS=%s -> RGB=%s", self.name, hs, rgb)
            self.switch(rgb=rgb)

    @property
    def support_brightness(self) -> bool:
        """Return True if light supports brightness control."""
        return self.light_type in (LIGHT_TYPE_DIMMER, LIGHT_TYPE_RGB)

    @property
    def brightness(self) -> int:
        """Get light brightness in percents (0-100)."""
        if self.support_color:
            return self._hsv_color[2]

        return self._device_info.get("perc", 100)

    def set_brightness(self, brightness: int):
        """Set light brightness in percents (0-100)."""
        if not self.support_brightness:
            _LOGGER.debug("Light %s does not support brightness", self.name)
            return

        # Clamp brightness to 0-100
        brightness = max(0, min(100, brightness))

        _LOGGER.debug("Setting brightness for %s: %d%%", self.name, brightness)

        if self.support_color:
            hsv = self._hsv_color
            rgb = list(
                map(
                    int,
                    colorsys.hsv_to_rgb(
                        hsv[0] / 360, hsv[1] / 100, brightness * 255 / 100
                    ),
                )
            )
            self.switch(rgb=rgb)
        else:
            self.switch(brightness=brightness)

    def switch(self, state: int = None, brightness: int = None, rgb: List[int] = None):
        """Switch light to new state."""
        if state is None and brightness is None and rgb is None:
            raise ValueError("At least one parameter is required")

        self._check_act_id()

        cmd = {
            "cmd_name": "light_switch_req",
            "act_id": self.act_id,
            "wanted_status": state if state is not None else self.state,
        }
        
        log_params = {}
        if state is not None:
            log_params["status"] = cmd["wanted_status"]
        if brightness is not None:
            log_params["perc"] = cmd["perc"] = brightness
        if rgb is not None:
            log_params["rgb"] = cmd["rgb"] = rgb[0:3]

        _LOGGER.debug("Setting new state for light '%s': %s", self.name, log_params)

        self._manager.application_request(cmd)

    def turn_off(self):
        """Turn off light."""
        _LOGGER.debug("Turning off light %s", self.name)
        self.switch(LIGHT_STATE_OFF)

    def turn_on(self):
        """Turn on light."""
        _LOGGER.debug("Turning on light %s", self.name)
        self.switch(LIGHT_STATE_ON)

    def turn_auto(self):
        """Switch light to automatic mode."""
        _LOGGER.debug("Switching light %s to AUTO mode", self.name)
        self.switch(LIGHT_STATE_AUTO)

    def update(self):
        """Update device state from CAME device."""
        self._force_update("light")
