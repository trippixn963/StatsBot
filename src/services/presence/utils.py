"""
Utility functions for presence formatting and operations.

This module provides helper functions for formatting presence data,
managing presence rotation, and handling presence-related calculations.
"""

import discord
from typing import List, Optional, Union
from .types import PresenceType, PRESENCE_CONFIGS

def format_count(count: int, style: str = "standard") -> str:
    """
    Format a count number with appropriate styling.
    
    Args:
        count: The number to format
        style: Formatting style ('standard', 'compact', 'verbose')
        
    Returns:
        Formatted count string
    """
    if style == "compact":
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        elif count >= 1_000:
            return f"{count / 1_000:.1f}K"
        return str(count)
    elif style == "verbose":
        if count == 0:
            return "zero"
        elif count == 1:
            return "one"
        else:
            return f"{count:,}"
    else:  # standard
        return f"{count:,}"

def get_presence_name(presence_type: PresenceType, count: int) -> str:
    """
    Get formatted presence name for a given type and count.
    
    Args:
        presence_type: Type of presence to format
        count: Count value to display
        
    Returns:
        Formatted presence name string
    """
    config = PRESENCE_CONFIGS.get(presence_type)
    if not config:
        return f"Unknown: {count:,}"
    
    return config.format_name(count)

def calculate_next_presence_index(current_index: int, 
                                presence_types: List[PresenceType]) -> int:
    """
    Calculate the next presence index in rotation.
    
    Args:
        current_index: Current presence index
        presence_types: List of available presence types
        
    Returns:
        Next index in rotation
    """
    if not presence_types:
        return 0
    
    return (current_index + 1) % len(presence_types)

def validate_presence_config(config: dict) -> bool:
    """
    Validate presence configuration dictionary.
    
    Args:
        config: Configuration dictionary to validate
        
    Returns:
        True if configuration is valid
    """
    required_keys = ['emoji', 'activity_type', 'name_template', 'description']
    return all(key in config for key in required_keys)

async def get_guild_metrics(guild: discord.Guild) -> dict:
    """
    Get comprehensive guild metrics for presence display.
    
    Args:
        guild: Discord guild to analyze
        
    Returns:
        Dictionary containing various guild metrics
    """
    if not guild:
        return {}
    
    # Calculate online count
    online_count = sum(1 for member in guild.members 
                      if member.status != discord.Status.offline)
    
    # Get ban count
    bans = [entry async for entry in guild.bans()]
    
    # Calculate role counts
    role_count = len(guild.roles)
    
    # Calculate channel counts
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    
    return {
        'member_count': guild.member_count,
        'online_count': online_count,
        'ban_count': len(bans),
        'role_count': role_count,
        'text_channels': text_channels,
        'voice_channels': voice_channels,
        'boost_level': guild.premium_tier,
        'boost_count': guild.premium_subscription_count or 0
    }

def get_status_emoji(status: discord.Status) -> str:
    """
    Get emoji representation for Discord status.
    
    Args:
        status: Discord status to convert
        
    Returns:
        Emoji string representing the status
    """
    status_emojis = {
        discord.Status.online: "🟢",
        discord.Status.idle: "🟡", 
        discord.Status.dnd: "🔴",
        discord.Status.offline: "⚫"
    }
    
    return status_emojis.get(status, "❓")

def format_presence_activity(activity_type: discord.ActivityType, 
                           name: str) -> discord.Activity:
    """
    Create a Discord activity object with proper formatting.
    
    Args:
        activity_type: Type of Discord activity
        name: Name/description of the activity
        
    Returns:
        Configured Discord Activity object
    """
    return discord.Activity(type=activity_type, name=name) 