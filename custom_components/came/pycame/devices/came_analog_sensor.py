"""CAME ETI/Domo analog sensor device.

Versione ottimizzata da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
"""
import logging
from typing import Optional

from .base import TYPE_ANALOG_SENSOR, CameDevice, DeviceState, StateType

_LOGGER = logging.getLogger(__name__)


class CameAnalogSensor(CameDevice):
    """CAME ETI/Domo analog sensor device class (temperature, humidity, pressure)."""

    def __init__(
        self,
        manager,
        device_info: DeviceState,
        update_cmd_base: str = "thermo",
        update_src_field: str = "array",
        device_class: Optional[str] = None,
    ):
        """Initialize analog sensor instance.
        
        Args:
            manager: CameManager instance
            device_info: Device information from CAME API
            update_cmd_base: Base command for updates (default: "thermo")
            update_src_field: Response field name (default: "array")
            device_class: Device class override (temperature, humidity, pressure)
        """
        super().__init__(
            manager, TYPE_ANALOG_SENSOR, device_info, device_class=device_class
        )
        self._update_cmd_base = update_cmd_base
        self._update_src_field = update_src_field

    def update(self):
        """Update device state from CAME device."""
        self._force_update(self._update_cmd_base, self._update_src_field)

    @property
    def state(self) -> StateType:
        """Return the current sensor value."""
        return self._device_info.get("value")

    @property
    def unit_of_measurement(self) -> Optional[str]:
        """Return the unit of measurement of this sensor (°C, %, hPa, etc)."""
        return self._device_info.get("unit")
