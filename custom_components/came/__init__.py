"""
The CAME Integration Component - Optimized by Stefano Paoletti

Based on original work by Den901
For more details: https://github.com/StefanoPaoletti/Came_Connect

Security Enhanced: Credentials are now encrypted in memory using Fernet encryption
"""
import asyncio
import logging
import threading
from time import sleep
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
from homeassistant.helpers.dispatcher import async_dispatcher_send, dispatcher_send

from .came_server import SecureCameManager  # ← MODIFICATO: era CameManager
from .pycame.devices import CameDevice
from .pycame.exceptions import ETIDomoConnectionError, ETIDomoConnectionTimeoutError
from .pycame.devices.base import TYPE_ENERGY_SENSOR

from .const import (
    CONF_CAME_LISTENER,
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
    """Set up this integration using UI."""
    # Print startup message
    if DOMAIN not in hass.data:
        _LOGGER.info(STARTUP_MESSAGE)
        hass.data[DOMAIN] = {}

    config = entry.data.copy()
    config.update(entry.options)

    # MODIFICATO: Usa SecureCameManager invece di CameManager
    # Le credenziali vengono automaticamente cifrate in memoria
    manager = SecureCameManager(
        config.get(CONF_HOST),
        config.get(CONF_USERNAME, "admin"),
        config.get(CONF_PASSWORD, "admin"),
        hass=hass
    )
    _LOGGER.debug("Secure CAME manager initialized with encrypted credentials")

    def initial_update():
        manager.get_all_floors()
        manager.get_all_rooms()
        return manager.get_all_devices()

    try:
        devices = await hass.async_add_executor_job(initial_update)
    except ETIDomoConnectionTimeoutError as exc:
        raise ConfigEntryNotReady from exc

    # Crea evento di stop per thread e polling
    stop_event = threading.Event()

    def _came_update_listener(hass: HomeAssistant, manager: SecureCameManager, stop_event: threading.Event):
        """Thread che ascolta gli aggiornamenti dei dispositivi in loop."""
        while not stop_event.is_set():
            try:
                if manager.status_update():
                    _LOGGER.debug("Received devices status update.")
                    dispatcher_send(hass, SIGNAL_UPDATE_ENTITY)
            except ETIDomoConnectionError:
                _LOGGER.debug("Server goes offline. Reconnecting...")
            except Exception as exc:
                _LOGGER.error("Error in listener thread: %s", exc)
            sleep(1)
        _LOGGER.debug("Listener thread stopped")

    thread = threading.Thread(
        target=_came_update_listener, args=(hass, manager, stop_event), daemon=False
    )

    hass.data[DOMAIN] = {
        CONF_MANAGER: manager,
        CONF_ENTITIES: {},
        CONF_ENTRY_IS_SETUP: set(),
        CONF_PENDING: {},
        CONF_CAME_LISTENER: thread,
        "stop_event": stop_event,
        "energy_polling_task": None,
    }

    hass.data[DOMAIN]["came_scenario_manager"] = manager.scenario_manager

    thread.start()

    async def async_energy_polling(hass: HomeAssistant, manager: SecureCameManager, stop_event: threading.Event):
        """Polling async per i dati energia."""
        try:
            while not stop_event.is_set():
                try:
                    response = await asyncio.wait_for(
                        hass.async_add_executor_job(
                            manager.application_request,
                            {"cmd_name": "meters_list_req"},
                            "meters_list_resp",
                        ),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    _LOGGER.warning("Timeout durante richiesta dati energia")
                    response = None
                except Exception as exc:
                    _LOGGER.warning("Errore durante richiesta dati energia: %s", exc)
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
            _LOGGER.debug("Polling energia cancellato")
            raise
        except Exception as e:
            _LOGGER.error("Errore critico nel polling energia: %s", e)

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

    async def async_update_devices(event_time):
        """Pull new devices list from server."""
        _LOGGER.debug("Update devices")

        devices = await hass.async_add_executor_job(manager.get_all_devices)
        await async_load_devices(devices)

        # Delete not exist device
        newlist_ids = []
        for device in devices:
            newlist_ids.append(device.unique_id)
        for dev_id in list(hass.data[DOMAIN][CONF_ENTITIES]):
            if dev_id not in newlist_ids:
                async_dispatcher_send(hass, SIGNAL_DELETE_ENTITY, dev_id)
                hass.data[DOMAIN][CONF_ENTITIES].pop(dev_id)

    hass.services.async_register(DOMAIN, SERVICE_PULL_DEVICES, async_update_devices)

    async def async_force_update(call):
        """Force all devices to pull data."""
        async_dispatcher_send(hass, SIGNAL_UPDATE_ENTITY)

    hass.services.async_register(DOMAIN, SERVICE_FORCE_UPDATE, async_force_update)

    # Avvia polling energia async
    async def start_energy_polling(_):
        await asyncio.sleep(5)
        hass.data[DOMAIN]["energy_polling_task"] = hass.async_create_task(
            async_energy_polling(hass, manager, stop_event)
        )

    hass.bus.async_listen_once("homeassistant_started", start_energy_polling)
    
    async def async_refresh_scenarios_service(call):
        _LOGGER.debug("refresh_scenarios service called")
        scenario_manager = hass.data[DOMAIN]["came_scenario_manager"]
        await hass.async_add_executor_job(scenario_manager.refresh_scenarios)
        _LOGGER.debug("refresh_scenarios completed, sending event 'came_scenarios_refreshed'")
        dispatcher_send(hass, "came_scenarios_refreshed")

    hass.services.async_register(DOMAIN, "refresh_scenarios", async_refresh_scenarios_service)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unloading the CAME platforms - FIXED WITH TIMEOUT."""
    _LOGGER.info("Starting CAME integration unload")
    
    # Ferma il polling energia
    energy_task = hass.data[DOMAIN].get("energy_polling_task")
    if energy_task and not energy_task.done():
        energy_task.cancel()
        try:
            await asyncio.wait_for(energy_task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _LOGGER.debug("Energy polling task cancelled")
    
    # Ferma il listener thread
    stop_event = hass.data[DOMAIN].get("stop_event")
    if stop_event:
        stop_event.set()
    
    thread = hass.data[DOMAIN].get(CONF_CAME_LISTENER)
    if thread and thread.is_alive():
        # FIX CRITICO: Timeout di 5 secondi per evitare blocchi infiniti
        thread.join(timeout=5.0)
        if thread.is_alive():
            _LOGGER.warning("Thread did not stop within timeout, forcing cleanup")
    
    # Unload platforms
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
        # AGGIUNTO: Cleanup delle credenziali cifrate PRIMA di rimuovere i servizi
        manager = hass.data[DOMAIN].get(CONF_MANAGER)
        if manager:
            _LOGGER.debug("Securely clearing encrypted credentials from memory")
            try:
                manager.cleanup()
                _LOGGER.info("Encrypted credentials cleared successfully")
            except Exception as exc:
                _LOGGER.error("Error clearing credentials: %s", exc)
        
        hass.services.async_remove(DOMAIN, SERVICE_FORCE_UPDATE)
        hass.services.async_remove(DOMAIN, SERVICE_PULL_DEVICES)
        hass.services.async_remove(DOMAIN, "refresh_scenarios")
        hass.data.pop(DOMAIN)
        _LOGGER.info("CAME integration unloaded successfully")
    
    return unload_ok
