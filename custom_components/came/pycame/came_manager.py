"""Python async client for CAME ETI/Domo.

Versione ottimizzata ASYNC da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
Full async implementation using aiohttp with robust session management
"""

import asyncio
import json
import logging
import time
from typing import List, Optional

import aiohttp

from .const import DEBUG_DEEP, STARTUP_MESSAGE, VERSION
from .devices import get_featured_devices
from .devices.base import CameDevice, DeviceState
from .devices.came_scenarios import ScenarioManager
from .exceptions import (
    ETIDomoConnectionError,
    ETIDomoConnectionTimeoutError,
    ETIDomoError,
)
from .models import Floor, Room
from homeassistant.helpers.dispatcher import async_dispatcher_send

_LOGGER = logging.getLogger(__name__)

# Startup message flag (ensures it's printed only once)
_STARTUP = []


class CameManager:
    """Main async class for handling connections with a CAME ETI/Domo device."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: Optional[aiohttp.ClientSession] = None,
        hass: Optional["HomeAssistant"] = None,
    ):
        """Initialize async connection with the CAME ETI/Domo."""
        if not _STARTUP:
            _LOGGER.info(STARTUP_MESSAGE)
            _STARTUP.append(True)

        _LOGGER.debug("Setup CAME ETI/Domo ASYNC API for %s@%s", username, host)

        self._host = host
        self._username = username
        self._password = password
        self._session = session
        self._own_session = session is None  # Track if we created the session
        self._hass = hass
        self._client_id = None
        self._session_expiration = 0
        self._keep_alive_timeout = 900  # Default 15 minutes
        self._swver = None
        self._serial = None
        self._keycode = None
        self._features = []
        self._floors = None
        self._rooms = None
        self._devices = None
        self._lock = asyncio.Lock()  # Thread-safe operations
        self._login_in_progress = False  # Flag to prevent multiple logins
        self._request_semaphore = asyncio.Semaphore(1)  # NUOVO: Max 1 richiesta alla volta
        self.scenario_manager = ScenarioManager(self)

    async def __aenter__(self):
        """Async context manager entry."""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self):
        """Close the session if we own it."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            _LOGGER.debug("aiohttp session closed")

    @property
    def software_version(self) -> Optional[str]:
        """Return software version of ETI/Domo."""
        return self._swver

    @property
    def serial(self) -> Optional[str]:
        """Return serial number of ETI/Domo."""
        return self._serial

    @property
    def keycode(self) -> Optional[str]:
        """Return keycode for ETI/Domo."""
        return self._keycode

    async def _request(self, command: dict, resp_command: str = None) -> dict:
        """Handle an async request to a CAME ETI/Domo device."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)

        url = f"http://{self._host}/domo/"
        headers = {
            "User-Agent": f"PythonCameManagerAsync-Stefano/{VERSION}",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            if DEBUG_DEEP:
                _LOGGER.debug("Sending ASYNC API request: %s", command)

            async with self._session.post(
                url,
                data={"command": json.dumps(command)},
                headers=headers,
            ) as response:
                response.raise_for_status()
                text = await response.text()

                if DEBUG_DEEP:
                    _LOGGER.debug("Response received: %s", text)

                resp_json = json.loads(text)

        except asyncio.TimeoutError as exception:
            raise ETIDomoConnectionTimeoutError(
                "Timeout occurred while connecting to CAME ETI/Domo device."
            ) from exception

        except (
            aiohttp.ClientError,
            aiohttp.ClientConnectionError,
        ) as exception:
            raise ETIDomoConnectionError(
                "Error occurred while communicating with CAME ETI/Domo device."
            ) from exception

        try:
            ack_reason = resp_json.get("sl_data_ack_reason")

            if ack_reason == 0:
                cmd_name = resp_json.get("sl_cmd")
                if resp_command is not None and cmd_name != resp_command:
                    raise ETIDomoError(
                        f"Invalid server response. Expected {resp_command!r}. Actual {cmd_name!r}"
                    )

                return resp_json

            # Error codes mapping
            errors = {
                1: "Invalid user.",
                3: "Too many sessions during login.",
                4: "Error occurred in JSON Syntax.",
                5: "No session layer command tag.",
                6: "Unrecognized session layer command.",
                7: "No client ID in request.",
                8: "Wrong client ID in request.",
                9: "Wrong application command.",
                10: "No reply to application command, maybe service down.",
                11: "Wrong application data.",
            }

            if ack_reason in errors:
                raise ETIDomoError(errors[ack_reason], errno=ack_reason)

            raise ETIDomoError(
                f"Unknown error (#{ack_reason}).",
                errno=ack_reason,
            )

        except (ValueError, KeyError) as ex:
            raise ETIDomoError("Error parsing response.") from ex

    @property
    def connected(self) -> bool:
        """Return True if connected to CAME device."""
        return self._client_id is not None and time.time() < self._session_expiration

    async def login(self) -> None:
        """Async login function with double-check locking pattern."""
        # Fast path: check if session is valid without acquiring lock
        if self._client_id and time.time() < self._session_expiration:
            return

        # Slow path: acquire lock and check again
        async with self._lock:
            # Double-check: another coroutine might have logged in while we waited
            if self._client_id and time.time() < self._session_expiration:
                _LOGGER.debug("Session valid after lock acquired, skipping login")
                return

            # Prevent concurrent login attempts
            if self._login_in_progress:
                _LOGGER.warning("Login already in progress, waiting...")
                # Wait a bit and check again
                await asyncio.sleep(0.5)
                if self._client_id and time.time() < self._session_expiration:
                    return
                raise ETIDomoError("Login timeout: another login is in progress")

            self._login_in_progress = True
            
            try:
                _LOGGER.debug("🔑 Attempting async login to CAME device")
                response = await self._request(
                    {
                        "sl_cmd": "sl_registration_req",
                        "sl_login": self._username,
                        "sl_pwd": self._password,
                    },
                    "sl_registration_ack",
                )

                if response["sl_client_id"]:
                    _LOGGER.info("✅ Successful async authorization to CAME device")
                    self._client_id = response.get("sl_client_id")
                    self._keep_alive_timeout = response.get("sl_keep_alive_timeout_sec", 900)

                    # Calculate expiration with 30-second safety margin
                    self._session_expiration = time.time() + self._keep_alive_timeout - 30

                    _LOGGER.debug(
                        "Session valid for %d seconds (expires: %s)",
                        self._keep_alive_timeout,
                        time.ctime(self._session_expiration)
                    )

                    self._features = []
                    self._devices = None
                else:
                    raise ETIDomoError("Error in sl_client_id, can't get value.")
                    
            except KeyError as ex:
                raise ETIDomoError("Error in sl_client_id, can't find value.") from ex
            finally:
                self._login_in_progress = False

    async def keep_alive(self) -> None:
        """Send async keep-alive to maintain session."""
        if not self._client_id:
            return

        try:
            _LOGGER.debug("Sending async keep-alive to CAME device")
            await self._request(
                {
                    "sl_cmd": "sl_keep_alive_req",
                    "sl_client_id": self._client_id,
                },
                "sl_keep_alive_ack"
            )
            # Renew expiration
            self._session_expiration = time.time() + self._keep_alive_timeout - 30
            _LOGGER.debug("Keep-alive successful, session renewed")
        except Exception as exc:
            _LOGGER.warning("Keep-alive failed: %s", exc)
            self._client_id = None  # Force re-login

    async def application_request(
        self, command: dict, resp_command: str = "generic_reply"
    ) -> dict:
        """Handle an async request to application layer of CAME ETI/Domo.
        
        Uses semaphore to limit parallel requests and prevent 'Too many sessions' errors.
        """
        # MODIFICATO: Usa semaforo per limitare richieste parallele
        async with self._request_semaphore:
            await self.login()

            if DEBUG_DEEP:
                _LOGGER.debug("Sending async application layer API request: %s", command)

            cmd = command.copy()

            try:
                response = await self._request(
                    {
                        "sl_cmd": "sl_data_req",
                        "sl_client_id": self._client_id,
                        "sl_appl_msg": cmd,
                    },
                )
            except ETIDomoConnectionError as err:
                _LOGGER.debug("CAME server goes offline, resetting client_id")
                self._client_id = None
                raise err

            if resp_command is not None and response.get("cmd_name") != resp_command:
                raise ETIDomoError(
                    f"Invalid server response. Expected {resp_command!r}. Actual {response.get('cmd_name')!r}"
                )

            return response

    async def _get_features(self) -> list:
        """Get list of available features from CAME device."""
        if self._features:
            return self._features

        cmd = {
            "cmd_name": "feature_list_req",
        }
        response = await self.application_request(cmd, "feature_list_resp")
        self._swver = response.get("swver")
        self._serial = response.get("serial")
        self._keycode = response.get("keycode")
        self._features = response.get("list")

        _LOGGER.debug(
            "CAME device features loaded: sw_ver=%s, serial=%s",
            self._swver,
            self._serial
        )

        return self._features

    async def get_all_floors(self) -> List[Floor]:
        """Get list of available floors."""
        if self._floors is not None:
            return self._floors

        cmd = {
            "cmd_name": "floor_list_req",
            "topologic_scope": "plant",
        }
        response = await self.application_request(cmd, "floor_list_resp")
        self._floors = []
        for floor in response.get("floor_list", []):
            self._floors.append(Floor.from_dict(floor))

        _LOGGER.debug("Loaded %d floor(s) from CAME device", len(self._floors))
        return self._floors

    async def get_all_rooms(self) -> List[Room]:
        """Get list of available rooms."""
        if self._rooms is not None:
            return self._rooms

        cmd = {
            "cmd_name": "room_list_req",
            "topologic_scope": "plant",
        }
        response = await self.application_request(cmd, "room_list_resp")
        self._rooms = []
        for room in response.get("room_list", []):
            self._rooms.append(Room.from_dict(room))

        _LOGGER.debug("Loaded %d room(s) from CAME device", len(self._rooms))
        return self._rooms

    async def _update_devices(self) -> Optional[List[CameDevice]]:
        """Update devices info from CAME device."""
        if self._devices is None:
            _LOGGER.debug("Updating devices info from CAME")

            devices = []
            for feature in await self._get_features():
                devices.extend(await get_featured_devices(self, feature))

            self._devices = devices
            _LOGGER.info(
                "Loaded %d device(s) from CAME: %s",
                len(self._devices),
                [d.type for d in self._devices]
            )

        else:
            _LOGGER.debug("Using cached devices data")

        return self._devices

    async def get_all_devices(self) -> Optional[List[CameDevice]]:
        """Get list of all discovered devices."""
        return await self._update_devices()

    def get_device_by_id(self, device_id: str) -> Optional[CameDevice]:
        """Get device by unique ID."""
        if not self._devices:
            return None
        
        for device in self._devices:
            if device.unique_id == device_id:
                return device

        return None

    def get_device_by_act_id(self, act_id: int) -> Optional[CameDevice]:
        """Get device by device's act ID."""
        if not self._devices:
            return None
            
        for device in self._devices:
            if device.act_id == act_id:
                return device

        return None

    def get_device_by_name(self, name: str) -> Optional[CameDevice]:
        """Get device by name."""
        if not self._devices:
            return None
            
        for device in self._devices:
            if device.name == name:
                return device

        return None

    def get_devices_by_floor(self, floor_id: int) -> List[CameDevice]:
        """Get a list of devices on a floor."""
        if not self._devices:
            return []
            
        devices = []
        for device in self._devices:
            if device.floor_id == floor_id:
                devices.append(device)

        return devices

    def get_devices_by_room(self, room_id: int) -> List[CameDevice]:
        """Get a list of devices in a room."""
        if not self._devices:
            return []
            
        devices = []
        for device in self._devices:
            if device.room_id == room_id:
                devices.append(device)

        return devices

    async def status_update(self, timeout: Optional[int] = None) -> bool:
        """Async long polling which reads status updates from CAME device."""
        if self._devices is None:
            await self._update_devices()
            return True

        cmd = {
            "cmd_name": "status_update_req",
        }
        if timeout is not None:
            cmd["timeout"] = timeout

        response = await self.application_request(cmd, "status_update_resp")

        if response and DEBUG_DEEP:
            _LOGGER.debug("Status update response: %s", response)

        updated = False

        for device_info in response.get("result", []):  # type: DeviceState
            cmd_name = device_info.get("cmd_name", "")

            if DEBUG_DEEP:
                _LOGGER.debug(
                    "Received cmd_name: %s - content: %s",
                    cmd_name,
                    device_info
                )

            # Delegate scenario updates to scenario manager
            if cmd_name.startswith("scenario_"):
                self.scenario_manager.handle_update(self._hass, device_info)

            # Handle plant update (device list changed)
            if cmd_name == "plant_update_ind":
                _LOGGER.info("Plant update detected, reloading devices")
                self._devices = None
                await self._update_devices()
                return True

            # Update individual device state
            act_id = device_info.get("act_id")
            if act_id:
                device = self.get_device_by_act_id(act_id)
                if device is not None:
                    updated |= device.update_state(device_info)
                else:
                    _LOGGER.debug("Device with act_id=%s not found", act_id)

        return updated
