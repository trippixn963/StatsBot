"""
Rich Presence Package.

This package provides Discord rich presence functionality for the bot,
including status updates, activity management, and presence cycling.

Modules:
    service: Core rich presence service implementation
    types: Type definitions and enums for presence management
    utils: Utility functions for presence formatting
"""

from .service import RichPresenceService
from .types import PresenceType, StatusType
from .utils import format_count

__all__ = [
    'RichPresenceService',
    'PresenceType', 
    'StatusType',
    'format_count'
]