"""CAME ETI/Domo energy sensor device (power and energy monitoring).

Versione ottimizzata da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
"""
import logging
from typing import Optional

from ..exceptions import ETIDomoUnmanagedDeviceError
from .base import TYPE_ENERGY_SENSOR, CameDevice, DeviceState, StateType

_LOGGER = logging.getLogger(__name__)


class CameEnergySensor(CameDevice):
    """CAME ETI/Domo energy sensor device class (monitors power consumption/production)."""

    def __init__(
        self,
        manager,
        device_info: DeviceState,
        update_cmd_base: str = "meters",
        update_src_field: str = "array",
        device_class: Optional[str] = None,
    ):
        """Initialize energy sensor instance.
        
        Args:
            manager: CameManager instance
            device_info: Device information from CAME API
            update_cmd_base: Base command for updates (default: "meters")
            update_src_field: Response field name (default: "array")
            device_class: Device class for Home Assistant
        """
        super().__init__(
            manager, TYPE_ENERGY_SENSOR, device_info, device_class=device_class
        )
        self._update_cmd_base = update_cmd_base
        self._update_src_field = update_src_field

    def update(self):
        """Update device state from CAME device."""
        try:
            self._force_update(self._update_cmd_base, self._update_src_field)
        except ETIDomoUnmanagedDeviceError:
            # Some energy sensors may not support force update
            _LOGGER.debug(
                "Energy sensor '%s' does not support force update",
                self.name
            )
            pass

    def push_update(self, state: DeviceState):
        """Update from CAME ETI/Domo push data.
        
        This method is called when the energy polling in __init__.py
        receives new data for this sensor.
        
        Args:
            state: New state data from CAME
        """
        if self._device_info.get("id") != state.get("id"):
            return
        
        updated = self.update_state(state)
        
        # If this sensor has a reference to its HA entity, update it
        if updated and hasattr(self, "hass_entity"):
            self.hass_entity.async_write_ha_state()

    @property
    def state(self) -> StateType:
        """Return the current instantaneous power in Watts."""
        return self._device_info.get("instant_power")

    @property
    def unit_of_measurement(self) -> Optional[str]:
        """Return the unit of measurement (typically W for power)."""
        return self._device_info.get("unit") or "W"

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes for the energy sensor.
        
        Returns:
            Dictionary with additional energy statistics and metadata
        """
        return {
            "produced": self._device_info.get("produced"),
            "last_24h_avg": self._device_info.get("last_24h_avg"),
            "last_month_avg": self._device_info.get("last_month_avg"),
            "energy_unit": self._device_info.get("energy_unit"),
        }
