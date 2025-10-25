"""CAME ETI/Domo digital input device (binary sensor).

Versione ottimizzata da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
"""
import logging
from typing import Optional

from .base import TYPE_DIGITALIN, CameDevice, DeviceState, StateType

_LOGGER = logging.getLogger(__name__)

# Binary Sensor states
BINARY_SENSOR_STATE_OFF = 0
BINARY_SENSOR_STATE_ON = 1


class CameDigitalIn(CameDevice):
    """CAME ETI/Domo digital input device class (binary sensor)."""

    def __init__(
        self,
        manager,
        device_info: DeviceState,
        device_class: Optional[str] = None,
    ):
        """Initialize digital input instance.
        
        Args:
            manager: CameManager instance
            device_info: Device information from CAME API
            device_class: Device class for Home Assistant (motion, door, window, etc)
        """
        super().__init__(
            manager, TYPE_DIGITALIN, device_info, device_class=device_class
        )

    def update(self):
        """Update device state from CAME device."""
        self._force_update("digitalin", "array")

    @property
    def is_on(self) -> bool:
        """Return True if digital input is active."""
        return self._device_info.get("status") == BINARY_SENSOR_STATE_ON

    @property
    def state(self) -> StateType:
        """Return the current device state (0=off, 1=on)."""
        return self._device_info.get("status")
