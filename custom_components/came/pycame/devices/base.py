"""CAME ETI/Domo abstract devices base class.

Versione ottimizzata da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union

from ..exceptions import ETIDomoUnmanagedDeviceError
from ..models import Floor, Room

_LOGGER = logging.getLogger(__name__)


# Device type IDs
TYPE_LIGHT = 0
TYPE_THERMOSTAT = 2
TYPE_ANALOG_SENSOR = -1
TYPE_GENERIC_RELAY = 11
TYPE_OPENING = 1
TYPE_ENERGY_SENSOR = -2  # energy measurement
TYPE_DIGITALIN = 14

# Device type mapping
TYPES = {
    # Internal types
    -2: "Energy Sensor",
    -1: "Analog Sensor",
    0: "Light",
    1: "Opening",
    2: "Thermostat",
    3: "Page",
    4: "Scenario",
    5: "Camera",
    6: "Security Panel",
    7: "Security Area",
    8: "Security Scenario",
    9: "Security Input",
    10: "Security output",
    11: "Generic relay",
    12: "Generic text",  # currently disabled
    13: "Sound zone",
    14: "Digital input",  # technical alarm
}

StateType = Union[None, str, int, float]
DeviceState = Dict[str, Any]


class CameDevice(ABC):
    """Abstract base class for CAME ETI/Domo devices."""

    @abstractmethod
    def __init__(
        self,
        manager,
        type_id: int,
        device_info: DeviceState,
        device_class: Optional[str] = "",
    ):
        """Initialize device instance."""
        self._manager = manager
        self._type_id = type_id
        self._device_info = device_info

        self._device_class = device_class if device_class != "" else self.type.lower()

    def _sanitize_for_entity_id(self, text: str) -> str:
        """Sanitize text for use in entity_id.
        
        Converts to lowercase and replaces spaces/special chars with underscores.
        Example: "Living Room" -> "living_room"
        """
        if not text:
            return ""
        # Convert to lowercase
        text = text.lower()
        # Replace spaces and special characters with underscores
        text = re.sub(r'[^a-z0-9]+', '_', text)
        # Remove leading/trailing underscores
        text = text.strip('_')
        return text

    @property
    def unique_id(self) -> str:
        """Return the unique ID of device.
        
        OTTIMIZZATO v3: Uses sanitized name + act_id for clean, human-readable IDs
        
        Instead of: 0-4e019f322148a8106d1a89245dc675a2fec6ca4e
        Now: salotto_123 (name + act_id)
        
        The domain (climate/light/etc) already identifies the type, so we don't need type_id.
        
        NOTE: If you rename the device in CAME, the unique_id changes.
        This is a known limitation of the CAME protocol.
        """
        act_id = self.act_id or 0
        name_part = self._sanitize_for_entity_id(self.name)
        
        # Limit name part to 20 chars to keep ID reasonable
        if len(name_part) > 20:
            name_part = name_part[:20]
        
        # Format: name_actid
        # Example: salotto_123 instead of 0_salotto_123
        # Result: climate.salotto_123 (much cleaner!)
        return f"{name_part}_{act_id}"

    @property
    def type_id(self) -> int:
        """Return the type ID of device."""
        return self._type_id

    @property
    def type(self) -> str:
        """Return the type of device."""
        return TYPES.get(self._type_id, f"Unknown ({self._type_id})")

    @property
    def name(self) -> Optional[str]:
        """Return the name of device."""
        return self._device_info.get("name")

    @property
    def act_id(self) -> Optional[int]:
        """Return the action ID for device."""
        return self._device_info.get("act_id")

    def _check_act_id(self):
        """Check for act ID availability."""
        if not self.act_id:
            raise ETIDomoUnmanagedDeviceError()

    @property
    def floor_id(self) -> Optional[int]:
        """Return the device's floor ID."""
        return self._device_info.get("floor_ind")

    @property
    def floor(self) -> Optional[Floor]:
        """Return the device's floor instance."""
        for floor in self._manager.get_all_floors():
            if floor.id == self.floor_id:
                return floor

        return Floor(id=self.floor_id, name=f"Floor #{self.floor_id}")

    @property
    def room_id(self) -> Optional[int]:
        """Return the device's room ID."""
        return self._device_info.get("room_ind")

    @property
    def room(self) -> Optional[Room]:
        """Return the device's room instance."""
        for room in self._manager.get_all_rooms():
            if room.id == self.room_id:
                return room

        return Room(
            id=self.room_id, name=f"Room #{self.room_id}", floor_id=self.floor_id
        )

    @property
    def available(self) -> bool:
        """Return True if device is available."""
        return self._manager.connected

    @property
    def state(self) -> StateType:
        """Return the current device state."""
        return self._device_info.get("status")

    def update_state(self, state: DeviceState) -> bool:
        """Update device state.
        
        Args:
            state: New device state from CAME
            
        Returns:
            True if state was actually updated (changed), False otherwise
        """
        if state.get("act_id") != self.act_id:
            return False

        # Remove cmd_name from state if present
        if state.get("cmd_name"):
            state.pop("cmd_name")

        # Log only changed fields
        changed_fields = {}
        for key, value in state.items():
            if self._device_info.get(key) != value:
                changed_fields[key] = value
        
        if changed_fields:
            _LOGGER.debug(
                "State update for %s '%s' (act_id=%s): %s",
                self.type.lower(),
                self.name,
                self.act_id,
                changed_fields,
            )

        self._device_info = state

        return bool(changed_fields)

    def _force_update(self, cmd_base: str, field: str = "array"):
        """Force update device state from CAME device.
        
        Args:
            cmd_base: Base command name (e.g., "light", "thermo")
            field: Response field containing device data
        """
        self._check_act_id()

        cmd = {
            "cmd_name": f"{cmd_base}_list_req",
            "topologic_scope": "act",
            "value": self.act_id,
        }
        
        _LOGGER.debug(
            "Force update for %s '%s' (act_id=%s)",
            self.type.lower(),
            self.name,
            self.act_id
        )
        
        response = self._manager.application_request(cmd, f"{cmd_base}_list_resp")
        res = response.get(field, [])
        
        if not isinstance(res, list):
            res = [res]
        
        for device_info in res:  # type: DeviceState
            if device_info.get("act_id") == self.act_id:
                self.update_state(device_info)
                return
        
        _LOGGER.warning(
            "Force update failed for %s '%s' - device not found in response",
            self.type.lower(),
            self.name
        )

    @abstractmethod
    def update(self):
        """Update device state.
        
        This method must be implemented by subclasses.
        """
        raise NotImplementedError

    @property
    def device_class(self) -> Optional[str]:
        """Return the class of this device."""
        return self._device_class
