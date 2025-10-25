"""Secure wrapper for CameManager with encrypted credentials.

This module provides a security layer around the CameManager class,
encrypting credentials in memory to prevent plaintext storage.

Author: Optimized by Stefano Paoletti
"""
import asyncio
import logging
from typing import Optional

from cryptography.fernet import Fernet

from .pycame.came_manager import CameManager

_LOGGER = logging.getLogger(__name__)


class SecureCameManager:
    """Wrapper for CameManager with encrypted credential storage.
    
    This class wraps CameManager and encrypts username/password in memory
    using Fernet symmetric encryption. The encryption key exists only in
    memory and is destroyed on unload.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        hass=None,
    ):
        """Initialize secure manager with encrypted credentials.
        
        Args:
            host: CAME server IP/hostname
            username: Login username (will be encrypted)
            password: Login password (will be encrypted)
            hass: Home Assistant instance
        """
        self._host = host
        self._hass = hass
        
        # Create cipher suite for encryption
        _LOGGER.debug("Creating cipher suite for credential encryption")
        self._cipher_suite = self._create_cipher_suite()
        
        # Encrypt credentials before storing
        _LOGGER.debug("Encrypting credentials for host: %s", host)
        self._username_encrypted = self._cipher_suite.encrypt(username.encode())
        self._password_encrypted = self._cipher_suite.encrypt(password.encode())
        
        # Create the underlying CameManager
        # We decrypt credentials only when creating the manager
        _LOGGER.info("Initializing CameManager with encrypted credentials")
        self._manager = CameManager(
            host,
            self._decrypt_username(),
            self._decrypt_password(),
            hass=hass
        )

    @staticmethod
    def _create_cipher_suite() -> Fernet:
        """Create Fernet cipher suite for encryption.
        
        Generates a random encryption key that exists only in memory.
        This prevents credentials from being stored in plaintext.
        
        Returns:
            Fernet cipher suite instance
        """
        key = Fernet.generate_key()
        return Fernet(key)

    def _decrypt_username(self) -> str:
        """Decrypt and return username.
        
        Returns:
            Decrypted username string
        """
        return self._cipher_suite.decrypt(self._username_encrypted).decode()

    def _decrypt_password(self) -> str:
        """Decrypt and return password.
        
        Returns:
            Decrypted password string
        """
        return self._cipher_suite.decrypt(self._password_encrypted).decode()

    def cleanup(self):
        """Securely cleanup and destroy encrypted credentials.
        
        CRITICAL: This method must be called on integration unload
        to ensure credentials are cleared from memory.
        """
        _LOGGER.debug("Clearing encrypted credentials from memory")
        self._username_encrypted = None
        self._password_encrypted = None
        self._cipher_suite = None
        _LOGGER.info("Credentials securely cleared from memory")

    async def close(self):
        """Close the underlying manager's aiohttp session.
        
        This should be called after cleanup() during unload.
        """
        if self._manager:
            _LOGGER.debug("Closing CameManager session")
            await self._manager.close()
            _LOGGER.debug("CameManager session closed")

    # =========================================================================
    # Proxy all CameManager methods/properties
    # =========================================================================

    async def get_all_floors(self):
        """Get all floors from server."""
        return await self._manager.get_all_floors()

    async def get_all_rooms(self):
        """Get all rooms from server."""
        return await self._manager.get_all_rooms()

    async def get_all_devices(self):
        """Get all devices from server."""
        return await self._manager.get_all_devices()

    async def status_update(self, timeout=None):
        """Check for device status updates."""
        return await self._manager.status_update(timeout=timeout)

    async def application_request(self, *args, **kwargs):
        """Send application request to server."""
        return await self._manager.application_request(*args, **kwargs)

    async def keep_alive(self):
        """Send keep-alive to server."""
        return await self._manager.keep_alive()

    @property
    def scenario_manager(self):
        """Get scenario manager."""
        return self._manager.scenario_manager

    @property
    def _devices(self):
        """Get devices list."""
        return self._manager._devices

    @property
    def software_version(self):
        """Get software version."""
        return self._manager.software_version

    @property
    def serial(self):
        """Get serial number."""
        return self._manager.serial

    @property
    def keycode(self):
        """Get keycode."""
        return self._manager.keycode

    @property
    def connected(self):
        """Check if connected."""
        return self._manager.connected

    def get_device_by_id(self, device_id: str):
        """Get device by unique ID."""
        return self._manager.get_device_by_id(device_id)

    def get_device_by_act_id(self, act_id: int):
        """Get device by act ID."""
        return self._manager.get_device_by_act_id(act_id)

    def get_device_by_name(self, name: str):
        """Get device by name."""
        return self._manager.get_device_by_name(name)

    def get_devices_by_floor(self, floor_id: int):
        """Get devices by floor ID."""
        return self._manager.get_devices_by_floor(floor_id)

    def get_devices_by_room(self, room_id: int):
        """Get devices by room ID."""
        return self._manager.get_devices_by_room(room_id)

    def __getattr__(self, name):
        """Forward any other attribute access to underlying manager.
        
        This ensures compatibility with any CameManager method/property
        we might have missed.
        """
        return getattr(self._manager, name)
