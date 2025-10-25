"""Support for CAME scenarios - ASYNC VERSION.

Versione ottimizzata ASYNC da Stefano Paoletti
For more details: https://github.com/StefanoPaoletti/Came_Connect
"""
import asyncio
import logging
from typing import List

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_OFF, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .came_server import SecureCameManager
from .const import DOMAIN, CONF_MANAGER

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up CAME scenario entities."""
    manager = hass.data[DOMAIN][CONF_MANAGER]  # type: SecureCameManager
    
    # Initialize structure to track created scenario entities
    if "came_scenarios" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["came_scenarios"] = {}
    
    existing_scenario_entities = hass.data[DOMAIN]["came_scenarios"]
    
    def create_new_entities(scenarios):
        """Create new scenario entities for scenarios not yet registered."""
        _LOGGER.debug("Existing registered scenarios: %s", list(existing_scenario_entities.keys()))
        entities = []
        
        for scenario in scenarios:
            # Normalize user_defined key
            scenario["user_defined"] = scenario.get("user_defined", scenario.get("user-defined", 0))
            
            sid = scenario.get("id")
            if sid is None:
                _LOGGER.debug("Scenario without id ignored: %s", scenario)
                continue
            
            entity = existing_scenario_entities.get(sid)
            
            # If entity is not yet registered in Home Assistant, add it
            if entity is None or entity.hass is None:
                scenario_type = "user-defined" if scenario.get("user_defined", 0) == 1 else "static"
                _LOGGER.debug(
                    "Creating %s scenario id=%s name=%s",
                    scenario_type,
                    sid,
                    scenario.get("name")
                )
                entity = CameScenarioEntity(scenario, manager)
                existing_scenario_entities[sid] = entity
                entities.append(entity)
            else:
                _LOGGER.debug("Scenario id=%s already exists, skipping", sid)
        
        return entities
    
    # Create initial entities - ASYNC!
    try:
        # Use asyncio.to_thread for sync method
        scenarios = await asyncio.to_thread(manager.scenario_manager.get_scenarios)
        _LOGGER.info("Initial scenario setup: loaded %d scenarios", len(scenarios))
        entities = create_new_entities(scenarios)
        async_add_entities(entities)
    except Exception as exc:
        _LOGGER.error("Error loading initial scenarios: %s", exc, exc_info=True)
        return
    
    # Function that listens to refresh event to add new entities dynamically
    async def handle_refresh_scenarios():
        """Handle scenario refresh event - ASYNC."""
        _LOGGER.debug("Received came_scenarios_refreshed event, checking for new scenarios...")
        
        try:
            # ASYNC call
            scenarios = await asyncio.to_thread(manager.scenario_manager.get_scenarios)
            
            # Get existing and current IDs
            existing_ids = set(existing_scenario_entities.keys())
            current_ids = set(s["id"] for s in scenarios if s.get("id") is not None)
            
            # Remove obsolete entities
            removed_ids = existing_ids - current_ids
            registry = async_get_entity_registry(hass)
            
            for rid in removed_ids:
                entity = existing_scenario_entities.pop(rid, None)
                if entity is None:
                    continue
                
                entity_id = entity.entity_id
                
                # Remove entity from runtime if still active
                if entity.hass is not None:
                    await entity.async_remove()
                    _LOGGER.info("Scenario id=%s removed from runtime", rid)
                
                # Remove from registry (permanently)
                if registry.async_is_registered(entity_id):
                    registry.async_remove(entity_id)
                    _LOGGER.info("Scenario id=%s removed from registry", rid)
            
            # Find new entities to add
            new_entities = create_new_entities(scenarios)
            if new_entities:
                _LOGGER.info("Adding %d new scenarios", len(new_entities))
                async_add_entities(new_entities, update_before_add=True)
            
            # Update only entities that existed before refresh
            for scenario in scenarios:
                sid = scenario.get("id")
                if sid in existing_ids:
                    entity = existing_scenario_entities[sid]
                    old_name = entity._attr_name
                    entity._scenario = scenario
                    entity._attr_name = scenario.get("name", "Unknown Scenario")
                    entity._attr_unique_id = f"came_scenario_{sid}"
                    
                    if old_name != entity._attr_name:
                        _LOGGER.debug(
                            "Updated scenario id=%s: name from '%s' to '%s'",
                            sid,
                            old_name,
                            entity._attr_name
                        )
                    
                    if entity.hass is not None:
                        entity.async_write_ha_state()
        
        except Exception as exc:
            _LOGGER.error("Error handling scenario refresh: %s", exc, exc_info=True)
    
    # Register event listener
    async def _dispatcher_handler():
        """Dispatcher handler wrapper."""
        hass.async_create_task(handle_refresh_scenarios())
    
    async_dispatcher_connect(hass, "came_scenarios_refreshed", _dispatcher_handler)


class CameScenarioEntity(Scene):
    """Representation of a CAME scenario."""
    
    def __init__(self, scenario, manager: SecureCameManager):
        """Initialize CAME scenario entity."""
        self._manager = manager
        self._scenario = scenario
        self._attr_name = scenario.get("name", "Unknown Scenario")
        self._attr_unique_id = f"came_scenario_{scenario['id']}"
        self._unsub = None
        
        _LOGGER.debug(
            "Scenario entity initialized: id=%s, name=%s",
            scenario['id'],
            self._attr_name
        )
    
    async def async_activate(self, **kwargs):
        """Activate the scenario - ASYNC."""
        try:
            scenario_id = self._scenario["id"]
            _LOGGER.info("🎬 Activating scenario id=%s (%s)", scenario_id, self._attr_name)
            
            # ASYNC call
            await asyncio.to_thread(
                self._manager.scenario_manager.activate_scenario,
                scenario_id
            )
            
            self.async_write_ha_state()
            
            # After 2 seconds, send signal to refresh scenarios
            await asyncio.sleep(2)
            async_dispatcher_send(self.hass, "came_scenarios_refreshed")
            
            _LOGGER.debug("Scenario id=%s activated successfully", scenario_id)
            
        except Exception as exc:
            _LOGGER.error(
                "Error activating scenario id=%s (%s): %s",
                self._scenario["id"],
                self._attr_name,
                exc,
                exc_info=True
            )
            raise
    
    async def async_added_to_hass(self):
        """Connect entity to state updates."""
        def handle_update(scenario_id: int, new_data: dict):
            """Handle scenario update signal."""
            if scenario_id == self._scenario["id"]:
                _LOGGER.debug(
                    "Received update for scenario id=%s: %s",
                    scenario_id,
                    new_data
                )
                asyncio.run_coroutine_threadsafe(
                    self.update_state(new_data),
                    self.hass.loop
                )
        
        self._unsub = async_dispatcher_connect(
            self.hass,
            "came_scenario_update",
            handle_update
        )
    
    async def async_will_remove_from_hass(self):
        """Clean up dispatcher listener on removal."""
        if self._unsub:
            self._unsub()
            self._unsub = None
            _LOGGER.debug("Scenario id=%s unsubscribed from updates", self._scenario["id"])
    
    async def update_state(self, new_data: dict):
        """Update scenario state."""
        self._scenario.update(new_data)
        self.async_write_ha_state()
    
    @property
    def is_active(self):
        """Return True if scenario is active."""
        return self._scenario.get("scenario_status") == 2
    
    @property
    def available(self):
        """Return True if the scenario is available (even during transition)."""
        return self._scenario.get("scenario_status") is not None
    
    @property
    def state(self):
        """Return the current state of the scenario."""
        scenario_status = self._scenario.get("scenario_status")
        
        if scenario_status == 2:
            return STATE_ON
        elif scenario_status == 1:
            return "transition"
        elif scenario_status == 0:
            return STATE_OFF
        
        return STATE_UNAVAILABLE
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes for the scenario."""
        return {
            "id": self._scenario["id"],
            "status": self._scenario.get("status", 0),
            "scenario_status": self._scenario.get("scenario_status", 0),
            "user_defined": self._scenario.get("user-defined", 0),
        }
