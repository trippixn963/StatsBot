"""
Type definitions and enums for presence management.

This module provides type safety and consistency for rich presence operations
including presence types, status types, and activity configurations.
"""

from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass
import discord

class PresenceType(Enum):
    """Enumeration of available presence types for cycling."""
    MEMBER_COUNT = "member_count"
    ONLINE_COUNT = "online_count" 
    BAN_COUNT = "ban_count"

class StatusType(Enum):
    """Enumeration of Discord status types."""
    ONLINE = discord.Status.online
    IDLE = discord.Status.idle
    DND = discord.Status.dnd
    INVISIBLE = discord.Status.invisible

@dataclass
class PresenceConfig:
    """Configuration for rich presence settings."""
    emoji: str
    activity_type: discord.ActivityType
    name_template: str
    description: str
    
    def format_name(self, count: int) -> str:
        """Format the presence name with count."""
        return f"{self.emoji} {count:,} {self.name_template}"

# Default presence configurations
PRESENCE_CONFIGS: Dict[PresenceType, PresenceConfig] = {
    PresenceType.MEMBER_COUNT: PresenceConfig(
        emoji="👥",
        activity_type=discord.ActivityType.watching,
        name_template="members",
        description="Total server member count"
    ),
    PresenceType.ONLINE_COUNT: PresenceConfig(
        emoji="🟢", 
        activity_type=discord.ActivityType.watching,
        name_template="online",
        description="Currently online members"
    ),
    PresenceType.BAN_COUNT: PresenceConfig(
        emoji="🔨",
        activity_type=discord.ActivityType.watching,
        name_template="bans",
        description="Total server bans"
    )
} 