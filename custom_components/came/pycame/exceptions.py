"""Exceptions for Came Connect.

Versione ottimizzata da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
"""
from typing import Optional


class ETIDomoError(Exception):
    """Generic CAME ETI/Domo exception."""

    def __init__(self, status: str, errno: Optional[int] = None):
        """Initialize ETI/Domo error."""
        super().__init__(status)
        self.status = status
        self.errno = errno


class ETIDomoConnectionError(ETIDomoError):
    """CAME ETI/Domo connection exception."""


class ETIDomoConnectionTimeoutError(ETIDomoConnectionError, TimeoutError):
    """CAME ETI/Domo connection timeout exception."""


class ETIDomoUnmanagedDeviceError(ETIDomoError):
    """CAME ETI/Domo exception for unmanaged device."""

    def __init__(
        self, status: str = "This device is unmanageable", errno: Optional[int] = None
    ):
        """Initialize unmanaged device error."""
        super().__init__(status, errno)
