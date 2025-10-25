"""
The CAME Integration Component - Optimized by Stefano Paoletti

Based on original work by Den901
For more details: https://github.com/StefanoPaoletti/Came_Connect

Security Enhanced: Credentials encrypted in memory using Fernet
Performance Enhanced: Full async implementation with aiohttp
"""
import asyncio
import logging
import threading
from typing import List

from homeassistant.components.climate import DOMAIN as CLIMATE
from homeassistant.components.cover import DOMAIN as COVER
from homeassistant.components.light import DOMAIN as LIGHT
from homeassistant.components.sensor import DOMAIN as SENSOR
from homeassistant.components.scene import DOMAIN as SCENE
from homeassistant.components.switch import DOMAIN as SWITCH
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .came_server import SecureCameManager
from .pycame.devices import CameDevice
from .pycame.exceptions import ETIDomoConnectionError, ETIDomoConnectionTimeoutError
from .pycame.devices.base import TYPE_ENERGY_SENSOR

from .const import (
    CONF_ENTRY_IS_SETUP,
    CONF_MANAGER,
    CONF_PENDING,
    DOMAIN,
    SERVICE_FORCE_UPDATE,
    SERVICE_PULL_DEVICES,
    SIGNAL_DELETE_ENTITY,
    SIGNAL_DISCOVERY_NEW,
    SIGNAL_UPDATE_ENTITY,
    STARTUP_MESSAGE,
)

_LOGGER = logging.getLogger(__name__)

CAME_TYPE_TO_HA = {
    "Light": LIGHT,
    "Thermostat": CLIMATE,
    "Analog Sensor": SENSOR,
    "Generic relay": SWITCH,
    "Digital input": BINARY_SENSOR,
    "Energy Sensor": SENSOR,
    "Scenario": SCENE,
    "Opening": COVER,
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI with full async support."""
    # Print startup message
    if DOMAIN not in hass.data:
        _LOGGER.info(STARTUP_MESSAGE)
        hass.data[DOMAIN] = {}

    config = entry.data.copy()
    config.update(entry.options)

    # Create SecureCameManager with encrypted credentials and async support
    manager = SecureCameManager(
        config.get(CONF_HOST),
        config.get(CONF_USERNAME, "admin"),
        config.get(CONF_PASSWORD, "admin"),
        hass=hass
    )
    _LOGGER.info("🔒 Secure CAME manager initialized (encrypted credentials + async)")

    # ASYNC initial update with DELAYS to prevent "Too many sessions"
    async def initial_update():
        """Sequential initial update with delays between calls."""
        _LOGGER.debug("Starting sequential initial update...")
        
        # Step 1: Get floors
        _LOGGER.debug("⏳ Step 1/3: Getting floors...")
        await manager.get_all_floors()
        await asyncio.sleep(1.0)  # ← DELAY 1 secondo
        
        # Step 2: Get rooms
        _LOGGER.debug("⏳ Step 2/3: Getting rooms...")
        await manager.get_all_rooms()
        await asyncio.sleep(1.0)  # ← DELAY 1 secondo
        
        # Step 3: Get devices
        _LOGGER.debug("⏳ Step 3/3: Getting devices...")
        devices = await manager.get_all_devices()
        
        _LOGGER.info("✅ Sequential initial update completed")
        return devices

    try:
        devices = await initial_update()
        _LOGGER.info("✅ Initial device discovery completed (%d devices)", len(devices) if devices else 0)
    except ETIDomoConnectionTimeoutError as exc:
        raise ConfigEntryNotReady from exc

    # Create stop event for tasks
    stop_event = threading.Event()

    # ASYNC listener task (replaces thread)
    async def _came_async_listener(hass: HomeAssistant, manager: SecureCameManager, stop_event: threading.Event):
        """Async task that listens for device status updates."""
        _LOGGER.warning("🎧 Starting async listener task - LISTENING FOR UPDATES")
        try:
            while not stop_event.is_set():
                try:
                    update_result = await manager.status_update()
                    if update_result:
                        _LOGGER.warning("🔄 STATUS UPDATE RECEIVED! Sending signal to all entities...")
                        async_dispatcher_send(hass, SIGNAL_UPDATE_ENTITY)
                        _LOGGER.warning("📡 Signal SIGNAL_UPDATE_ENTITY sent to all entities")
                except ETIDomoConnectionError:
                    _LOGGER.warning("⚠️ Server offline, will reconnect...")
                    await asyncio.sleep(2)
                except Exception as exc:
                    _LOGGER.error("❌ Error in async listener: %s", exc, exc_info=True)
                    await asyncio.sleep(2)
                
                # Polling interval: 2 seconds
                await asyncio.sleep(2)
                
        except asyncio.CancelledError:
            _LOGGER.warning("🛑 Async listener task cancelled")
            raise

    # Initialize data storage
    hass.data[DOMAIN] = {
        CONF_MANAGER: manager,
        CONF_ENTITIES: {},
        CONF_ENTRY_IS_SETUP: set(),
        CONF_PENDING: {},
        "stop_event": stop_event,
        "listener_task": None,
        "energy_polling_task": None,
        "keep_alive_task": None,
    }

    hass.data[DOMAIN]["came_scenario_manager"] = manager.scenario_manager

    # Start async listener task
    hass.data[DOMAIN]["listener_task"] = hass.async_create_task(
        _came_async_listener(hass, manager, stop_event)
    )

    # ASYNC energy polling
    async def async_energy_polling(hass: HomeAssistant, manager: SecureCameManager, stop_event: threading.Event):
        """Async polling for energy data."""
        _LOGGER.debug("Starting async energy polling")
        try:
            while not stop_event.is_set():
                try:
                    # DIRECT ASYNC CALL - no executor!
                    response = await asyncio.wait_for(
                        manager.application_request(
                            {"cmd_name": "meters_list_req"},
                            "meters_list_resp",
                        ),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    _LOGGER.warning("Timeout requesting energy data")
                    response = None
                except Exception as exc:
                    _LOGGER.warning("Error requesting energy data: %s", exc)
                    response = None

                if response:
                    meter_updates = response.get("array", [])
                    if isinstance(meter_updates, list) and manager._devices:
                        for d in meter_updates:
                            for dev in manager._devices:
                                if dev.type_id == TYPE_ENERGY_SENSOR and d.get("act_id") == dev.act_id:
                                    if hasattr(dev, "push_update"):
                                        dev.push_update(d)
                                        async_dispatcher_send(hass, SIGNAL_UPDATE_ENTITY)
                
                await asyncio.sleep(10)
                
        except asyncio.CancelledError:
            _LOGGER.debug("Energy polling task cancelled")
            raise
        except Exception as e:
            _LOGGER.error("Critical error in energy polling: %s", e)

    # NEW: ASYNC keep-alive task
    async def async_keep_alive(hass: HomeAssistant, manager: SecureCameManager, stop_event: threading.Event):
        """Keep session alive with periodic keep-alive requests."""
        _LOGGER.debug("Starting async keep-alive task")
        try:
            while not stop_event.is_set():
                await asyncio.sleep(600)  # Every 10 minutes
                if not stop_event.is_set():
                    try:
                        await manager.keep_alive()
                        _LOGGER.debug("Keep-alive sent successfully")
                    except Exception as exc:
                        _LOGGER.warning("Keep-alive error: %s", exc)
        except asyncio.CancelledError:
            _LOGGER.debug("Keep-alive task cancelled")
            raise

    # Load devices into Home Assistant platforms
    async def async_load_devices(devices: List[CameDevice]):
        """Load new devices."""
        dev_types = {}
        for device in devices:
            if (
                device.type in CAME_TYPE_TO_HA
                and device.unique_id not in hass.data[DOMAIN][CONF_ENTITIES]
            ):
                ha_type = CAME_TYPE_TO_HA[device.type]
                dev_types.setdefault(ha_type, [])
                dev_types[ha_type].append(device.unique_id)
                hass.data[DOMAIN][CONF_ENTITIES][device.unique_id] = None
        
        _LOGGER.info("Detected device types for HA platforms: %s", list(dev_types.keys()))
        
        for ha_type, dev_ids in dev_types.items():
            config_entries_key = f"{ha_type}.{DOMAIN}"
            if config_entries_key not in hass.data[DOMAIN][CONF_ENTRY_IS_SETUP]:
                hass.data[DOMAIN][CONF_PENDING][ha_type] = dev_ids
                _LOGGER.debug("Starting setup for HA entities: %s", ha_type)
                await hass.config_entries.async_forward_entry_setups(entry, [ha_type])
                hass.data[DOMAIN][CONF_ENTRY_IS_SETUP].add(config_entries_key)
            else:
                async_dispatcher_send(
                    hass, SIGNAL_DISCOVERY_NEW.format(ha_type), dev_ids
                )

    await async_load_devices(devices)

    # Service: Update devices list
    async def async_update_devices(event_time):
        """Pull new devices list from server - ASYNC."""
        _LOGGER.debug("Updating devices list")

        # DIRECT ASYNC CALL - no executor!
        devices = await manager.get_all_devices()
        await async_load_devices(devices)

        # Delete devices that no longer exist
        newlist_ids = []
        for device in devices:
            newlist_ids.append(device.unique_id)
        for dev_id in list(hass.data[DOMAIN][CONF_ENTITIES]):
            if dev_id not in newlist_ids:
                async_dispatcher_send(hass, SIGNAL_DELETE_ENTITY, dev_id)
                hass.data[DOMAIN][CONF_ENTITIES].pop(dev_id)

    hass.services.async_register(DOMAIN, SERVICE_PULL_DEVICES, async_update_devices)

    # Service: Force update all entities
    async def async_force_update(call):
        """Force all devices to pull data."""
        _LOGGER.warning("🔄 FORCE UPDATE service called - sending update signal")
        async_dispatcher_send(hass, SIGNAL_UPDATE_ENTITY)

    hass.services.async_register(DOMAIN, SERVICE_FORCE_UPDATE, async_force_update)

    # Service: Refresh scenarios
    async def async_refresh_scenarios_service(call):
        """Refresh scenarios list - ASYNC."""
        _LOGGER.debug("refresh_scenarios service called")
        scenario_manager = hass.data[DOMAIN]["came_scenario_manager"]
        
        # DIRECT ASYNC CALL
        await scenario_manager.async_get_scenarios()
        
        _LOGGER.debug("refresh_scenarios completed, sending event")
        async_dispatcher_send(hass, "came_scenarios_refreshed")

    hass.services.async_register(DOMAIN, "refresh_scenarios", async_refresh_scenarios_service)

    # Start all async tasks when Home Assistant starts
    async def start_tasks(_):
        """Start all background tasks."""
        await asyncio.sleep(5)
        
        _LOGGER.warning("🚀 Starting background tasks (energy + keep-alive)")
        
        # Energy polling task
        hass.data[DOMAIN]["energy_polling_task"] = hass.async_create_task(
            async_energy_polling(hass, manager, stop_event)
        )
        
        # Keep-alive task (NEW!)
        hass.data[DOMAIN]["keep_alive_task"] = hass.async_create_task(
            async_keep_alive(hass, manager, stop_event)
        )
        
        _LOGGER.warning("✅ All background tasks started successfully")

    hass.bus.async_listen_once("homeassistant_started", start_tasks)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload the CAME integration - FULLY ASYNC."""
    _LOGGER.info("Starting CAME integration unload")
    
    # Cancel all async tasks
    for task_name in ["energy_polling_task", "keep_alive_task", "listener_task"]:
        task = hass.data[DOMAIN].get(task_name)
        if task and not task.done():
            _LOGGER.debug("Cancelling %s", task_name)
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                _LOGGER.debug("%s cancelled successfully", task_name)
    
    # Set stop event
    stop_event = hass.data[DOMAIN].get("stop_event")
    if stop_event:
        stop_event.set()
    
    # Unload all platforms
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(
                    entry, platform.split(".", 1)[0]
                )
                for platform in hass.data[DOMAIN][CONF_ENTRY_IS_SETUP]
            ]
        )
    )
    
    if unload_ok:
        # Cleanup encrypted credentials and close session
        manager = hass.data[DOMAIN].get(CONF_MANAGER)
        if manager:
            _LOGGER.debug("Securely clearing encrypted credentials and closing session")
            try:
                manager.cleanup()
                await manager.close()  # Close aiohttp session
                _LOGGER.info("✅ Credentials cleared and session closed")
            except Exception as exc:
                _LOGGER.error("Error during cleanup: %s", exc)
        
        # Remove services
        hass.services.async_remove(DOMAIN, SERVICE_FORCE_UPDATE)
        hass.services.async_remove(DOMAIN, SERVICE_PULL_DEVICES)
        hass.services.async_remove(DOMAIN, "refresh_scenarios")
        
        # Remove data
        hass.data.pop(DOMAIN)
        
        _LOGGER.info("✅ CAME integration unloaded successfully")
    
    return unload_ok
