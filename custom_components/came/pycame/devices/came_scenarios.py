"""CAME ETI/Domo scenario device and manager implementation.

Versione ottimizzata da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
"""

import logging

from .base import CameDevice
from ..exceptions import ETIDomoError
from homeassistant.helpers.dispatcher import async_dispatcher_send

_LOGGER = logging.getLogger(__name__)


class ScenarioDevice(CameDevice):
    """Logical representation of CAME scenarios."""

    def __init__(self, manager):
        """Initialize scenario device."""
        super().__init__(
            manager,
            device_info={"act_id": -1, "name": "Scenarios"},
            type_id=4
        )
        self._name = "Scenarios"
        _LOGGER.debug("ScenarioDevice initialized with type: %s", self.type)

    @property
    def name(self):
        """Return device name."""
        return self._name

    @property
    def device_type(self):
        """Return device type."""
        return "scenarios"

    @property
    def available_scenarios(self):
        """Return list of available scenarios."""
        return self._manager.get_scenarios()

    def activate(self, scenario_id: int):
        """Activate a scenario."""
        self._manager.activate_scenario(scenario_id)

    def update(self, data: dict) -> bool:
        """Update device state (scenarios don't have state)."""
        return False


class ScenarioManager:
    """Manager for CAME scenarios."""

    def __init__(self, manager):
        """Initialize scenario manager."""
        self._manager = manager
        self._scenarios = []

    def get_scenarios(self):
        """Retrieve list of scenarios from CAME system."""
        scenarios = self._manager.application_request(
            {"cmd_name": "scenarios_list_req"}, 
            "scenarios_list_resp"
        ).get("array", [])
        
        _LOGGER.debug("Retrieved %d scenario(s) from CAME", len(scenarios))
        return scenarios

    def activate_scenario(self, scenario_id: int):
        """Activate an existing scenario.
        
        Args:
            scenario_id: ID of the scenario to activate
        """
        try:
            _LOGGER.debug("Activating scenario id=%d", scenario_id)
            self._manager.application_request(
                {"cmd_name": "scenario_activation_req", "id": scenario_id},
                resp_command=None
            )
        except ETIDomoError as e:
            # CAME returns 'generic_reply' instead of expected response
            if "Actual 'generic_reply'" in str(e):
                _LOGGER.warning(
                    "Scenario activation returned generic reply (may still have worked): %s",
                    str(e)
                )
            else:
                raise

    def create_scenario(self, name: str):
        """Start recording a new scenario.
        
        Args:
            name: Name for the new scenario
        """
        _LOGGER.debug("Starting scenario recording: %s", name)
        self._manager.application_request(
            {"cmd_name": "scenario_registration_start", "name": name},
            resp_command="scenario_registration_start_ack"
        )

    def delete_scenario(self, scenario_id: int):
        """Delete a scenario.
        
        Args:
            scenario_id: ID of the scenario to delete
        """
        _LOGGER.info("Deleting scenario id=%d", scenario_id)
        self._manager.application_request(
            {"cmd_name": "scenario_delete_req", "id": scenario_id},
            resp_command="scenario_delete_resp"
        )

    def refresh_scenarios(self):
        """Refresh scenario list from CAME device."""
        _LOGGER.debug("Refreshing scenario list from CAME")
        self._scenarios = self.get_scenarios()
        _LOGGER.debug(
            "Scenario list refreshed: %d scenario(s) available",
            len(self._scenarios)
        )

    def handle_update(self, hass, device_info: dict):
        """Handle scenario-related updates from CAME device.
        
        Args:
            hass: Home Assistant instance
            device_info: Update data from CAME
        """
        cmd_name = device_info.get("cmd_name")
        
        if cmd_name == "scenario_status_ind":
            # Scenario status changed
            scenario_id = device_info.get("id")
            _LOGGER.debug(
                "Scenario status update: id=%s, data=%s",
                scenario_id,
                device_info
            )
            hass.add_job(
                async_dispatcher_send,
                hass,
                "came_scenario_update",
                scenario_id,
                device_info,
            )
            
        elif cmd_name == "scenario_user_ind" and device_info.get("action") in ("add", "create"):
            # New user scenario added
            _LOGGER.info(
                "New user scenario detected (action=%s), refreshing list",
                device_info.get("action")
            )
            self.refresh_scenarios()
            hass.add_job(
                async_dispatcher_send,
                hass,
                "came_scenarios_refreshed"
            )
