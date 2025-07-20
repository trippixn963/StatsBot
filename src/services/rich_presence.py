"""
Rich Presence Service module.

This module re-exports the RichPresenceService from the presence package
for backward compatibility and easier imports.
"""

from .presence.service import RichPresenceService

__all__ = ['RichPresenceService']