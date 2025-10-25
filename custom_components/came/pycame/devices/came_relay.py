"""CAME ETI/Domo relay device implementation.

Versione ottimizzata da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
"""

import logging

from .base import TYPE_GENERIC_RELAY, CameDevice, DeviceState

_LOGGER = logging.getLogger(__name__)

# Relay states
GENERIC_RELAY_STATE_OFF = 0
GENERIC_RELAY_STATE_ON = 1


class CameRelay(CameDevice):
    """CAME ETI/Domo relay device class."""

    def __init__(self, manager, device_info: DeviceState):
        """Initialize CAME relay device."""
        super().__init__(manager, TYPE_GENERIC_RELAY, device_info)

    def switch(self, state: int = None):
        """Switch relay to new state."""
        if state is None:
            raise ValueError("State parameter is required")

        self._check_act_id()

        cmd = {
            "cmd_name": "relay_activation_req",
            "act_id": self.act_id,
            "wanted_status": state,
        }

        _LOGGER.debug(
            "Setting new state for relay '%s': status=%d",
            self.name,
            state
        )

        self._manager.application_request(cmd)

    def turn_off(self):
        """Turn off relay."""
        _LOGGER.debug("Turning off relay %s", self.name)
        self.switch(GENERIC_RELAY_STATE_OFF)

    def turn_on(self):
        """Turn on relay."""
        _LOGGER.debug("Turning on relay %s", self.name)
        self.switch(GENERIC_RELAY_STATE_ON)

    def update(self):
        """Update device state from CAME device."""
        self._force_update("relay")
