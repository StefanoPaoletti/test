"""CAME ETI/Domo devices subpackage.
Versione ottimizzata ASYNC da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
"""
import logging
from typing import List

from .came_analog_sensor import CameAnalogSensor
from .came_energy_sensor import CameEnergySensor
from .base import CameDevice
from .came_light import CameLight
from .came_thermo import CameThermo
from .came_relay import CameRelay
from .came_opening import CameOpening
from .came_digitalin import CameDigitalIn
from .came_scenarios import ScenarioDevice

_LOGGER = logging.getLogger(__name__)


async def get_featured_devices(manager, feature: str) -> List[CameDevice]:
    """Get device implementations for the given feature type - ASYNC.
    
    Args:
        manager: CameManager instance
        feature: Feature type (lights, openings, relays, thermoregulation, energy, digitalin, scenarios)
    
    Returns:
        List of CameDevice instances for the given feature
    """
    devices = []
    
    # Map feature types to their corresponding CAME API commands
    if feature == "lights":
        cmd_name = "light_list_req"
        response_name = "light_list_resp"
    elif feature == "openings":
        cmd_name = "openings_list_req"
        response_name = "openings_list_resp"
    elif feature == "relays":
        cmd_name = "relays_list_req"
        response_name = "relays_list_resp"
    elif feature == "thermoregulation":
        cmd_name = "thermo_list_req"
        response_name = "thermo_list_resp"
    elif feature == "energy":
        cmd_name = "meters_list_req"
        response_name = "meters_list_resp"
    elif feature == "digitalin":
        cmd_name = "digitalin_list_req"
        response_name = "digitalin_list_resp"
    elif feature == "scenarios":
        # Scenarios use centralized manager, not individual devices
        _LOGGER.debug("Loading scenario manager device")
        return [ScenarioDevice(manager)]
    else:
        _LOGGER.warning("Unsupported feature type: %s", feature)
        return devices
    
    # Request device list from CAME device - ASYNC!
    cmd = {
        "cmd_name": cmd_name,
        "topologic_scope": "plant",
    }
    
    _LOGGER.debug("⚡ ASYNC requesting %s device list from CAME", feature)
    response = await manager.application_request(cmd, response_name)  # ← AGGIUNTO await!
    
    # Create device instances based on feature type
    device_count = 0
    for device_info in response.get("array", []):
        if feature == "lights":
            devices.append(CameLight(manager, device_info))
        elif feature == "openings":
            devices.append(CameOpening(manager, device_info))
        elif feature == "relays":
            devices.append(CameRelay(manager, device_info))
        elif feature == "thermoregulation":
            devices.append(CameThermo(manager, device_info))
        elif feature == "energy":
            devices.append(CameEnergySensor(manager, device_info))
        elif feature == "digitalin":
            devices.append(CameDigitalIn(manager, device_info))
        device_count += 1
    
    # Special handling for thermoregulation: add analog sensors
    if feature == "thermoregulation":
        for sensor in ["temperature", "humidity", "pressure"]:
            res = response.get(sensor)
            if res is not None:
                devices.append(
                    CameAnalogSensor(
                        manager, res, "thermo", sensor, device_class=sensor
                    )
                )
                device_count += 1
    
    _LOGGER.debug(
        "✅ Loaded %d device(s) for feature '%s'",
        device_count,
        feature
    )
    
    return devices
