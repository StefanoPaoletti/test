"""CAME ETI/Domo opening device (covers/shutters/doors).

Versione ottimizzata da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
"""
import logging
from typing import Optional

from .base import TYPE_OPENING, CameDevice, DeviceState
from ..exceptions import ETIDomoUnmanagedDeviceError

_LOGGER = logging.getLogger(__name__)

# Opening states
OPENING_STATE_STOP = 0
OPENING_STATE_OPEN = 1
OPENING_STATE_CLOSE = 2
# wanted_status: 0=stop, 1=open, 2=close, 3=slat open, 4=slat close


class CameOpening(CameDevice):
    """CAME ETI/Domo opening device class (shutters, doors, gates)."""

    def __init__(self, manager, device_info: DeviceState):
        """Initialize CAME opening device."""
        super().__init__(manager, TYPE_OPENING, device_info)

    @property
    def act_id(self) -> Optional[int]:
        """Return the action ID for opening device.
        
        Note: Opens use 'open_act_id' instead of standard 'act_id'
        """
        return self._device_info.get("open_act_id")

    def _check_act_id(self):
        """Check for act ID availability."""
        if not self.act_id:
            raise ETIDomoUnmanagedDeviceError()

    def opening(self, state: int = None):
        """Switch opening to new state.
        
        Args:
            state: Desired state (0=stop, 1=open, 2=close)
        """
        if state is None:
            raise ValueError("State parameter is required")

        self._check_act_id()

        cmd = {
            "cmd_name": "opening_move_req",
            "act_id": self.act_id,
            "wanted_status": state if state is not None else self.state,
        }
        
        state_names = {0: "STOP", 1: "OPEN", 2: "CLOSE"}
        state_name = state_names.get(state, f"UNKNOWN({state})")
        
        _LOGGER.debug(
            "Setting opening '%s' to state %s (wanted_status=%d)",
            self.name,
            state_name,
            state
        )

        self._manager.application_request(cmd)

    def open(self):
        """Open the cover/shutter/door."""
        _LOGGER.debug("Opening '%s'", self.name)
        self.opening(OPENING_STATE_OPEN)

    def close(self):
        """Close the cover/shutter/door."""
        _LOGGER.debug("Closing '%s'", self.name)
        self.opening(OPENING_STATE_CLOSE)

    def stop(self):
        """Stop the cover/shutter/door movement."""
        _LOGGER.debug("Stopping '%s'", self.name)
        self.opening(OPENING_STATE_STOP)

    def update(self):
        """Update device state from CAME device."""
        self._force_update("opening")
