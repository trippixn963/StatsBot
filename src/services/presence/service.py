"""
Optimized Rich Presence Service Implementation.

This module provides a comprehensive Discord rich presence service with:
- Performance monitoring and optimization
- Memory-efficient presence cycling
- Comprehensive error handling and recovery
- Type safety and validation
- Configurable presence management
"""

# Standard library imports
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

# Third-party imports
import discord

# Local imports
from ...utils.performance import timing, performance_context
from ...utils.tree_log import log_perfect_tree_section, log_error_with_traceback
from .types import PresenceType, StatusType, PRESENCE_CONFIGS
from .utils import (
    get_presence_name, 
    calculate_next_presence_index,
    get_guild_metrics,
    format_presence_activity
)

class RichPresenceService:
    """
    Optimized Discord rich presence service.
    
    This service manages the bot's Discord presence with intelligent cycling,
    performance monitoring, and comprehensive error handling.
    
    Attributes:
        bot (discord.Client): The Discord bot instance
        update_interval (int): Interval between presence updates in seconds
        current_index (int): Current presence type index
        presence_types (List[PresenceType]): Available presence types for cycling
        _last_update (float): Timestamp of last presence update
        _error_count (int): Number of consecutive errors
        _max_errors (int): Maximum errors before disabling service
    """
    
    def __init__(self, 
                 bot: discord.Client,
                 update_interval: int = 300,
                 presence_types: Optional[List[PresenceType]] = None,
                 max_errors: int = 5):
        """
        Initialize the rich presence service.
        
        Args:
            bot: Discord bot instance
            update_interval: Update interval in seconds (default: 300 = 5 minutes)
            presence_types: List of presence types to cycle through
            max_errors: Maximum consecutive errors before disabling service
        """
        self.bot = bot
        self.update_interval = update_interval
        self.current_index = 0
        self.presence_types = presence_types or [
            PresenceType.MEMBER_COUNT,
            PresenceType.ONLINE_COUNT,
            PresenceType.BAN_COUNT
        ]
        
        # Error handling
        self._last_update = 0.0
        self._error_count = 0
        self._max_errors = max_errors
        self._service_enabled = True
        
        # Performance tracking
        self._update_count = 0
        self._total_update_time = 0.0
        
        # Caching for performance
        self._cached_metrics: Dict[str, Any] = {}
        self._cache_timestamp = 0.0
        self._cache_ttl = 60.0  # Cache for 1 minute
        
        # Initialize logging
        log_perfect_tree_section(
            "Rich Presence Service",
            [
                ("status", "Initializing"),
                ("update_interval", f"{self.update_interval}s"),
                ("presence_types", len(self.presence_types)),
                ("max_errors", max_errors)
            ],
            emoji="👤"
        )
    
    @timing(category="presence")
    async def update_presence(self) -> bool:
        """
        Update the bot's presence with the next status in rotation.
        
        Returns:
            True if update was successful, False otherwise
        """
        if not self._service_enabled:
            return False
        
        try:
            with performance_context("presence_update"):
                # Check if bot is ready
                if not self.bot.guilds:
                    return False
                
                guild = self.bot.guilds[0]
                presence_type = self.presence_types[self.current_index]
                
                # Get cached or fresh metrics
                metrics = await self._get_guild_metrics(guild)
                if not metrics:
                    return False
                
                # Create presence activity
                activity = await self._create_presence_activity(presence_type, metrics)
                if not activity:
                    return False
                
                # Update presence
                await self.bot.change_presence(
                    status=discord.Status.online,
                    activity=activity
                )
                
                # Update rotation index
                self.current_index = calculate_next_presence_index(
                    self.current_index, self.presence_types
                )
                
                # Update tracking
                self._last_update = time.time()
                self._update_count += 1
                self._error_count = 0  # Reset error count on success
                
                return True
                
        except discord.HTTPException as e:
            # Handle Discord API errors specifically
            self._handle_discord_error(e)
            return False
        except Exception as e:
            # Handle unexpected errors
            self._handle_unexpected_error(e)
            return False
    
    async def _get_guild_metrics(self, guild: discord.Guild) -> Optional[Dict[str, Any]]:
        """
        Get guild metrics with caching for performance.
        
        Args:
            guild: Discord guild to analyze
            
        Returns:
            Dictionary of guild metrics or None if failed
        """
        current_time = time.time()
        
        # Return cached metrics if still valid
        if (current_time - self._cache_timestamp < self._cache_ttl and 
            self._cached_metrics):
            return self._cached_metrics
        
        try:
            # Get fresh metrics
            with performance_context("guild_metrics_fetch"):
                metrics = await get_guild_metrics(guild)
                
            # Update cache
            self._cached_metrics = metrics
            self._cache_timestamp = current_time
            
            return metrics
            
        except Exception as e:
            log_error_with_traceback("Failed to get guild metrics", e)
            return None
    
    async def _create_presence_activity(self, 
                                      presence_type: PresenceType,
                                      metrics: Dict[str, Any]) -> Optional[discord.Activity]:
        """
        Create Discord activity for presence display.
        
        Args:
            presence_type: Type of presence to create
            metrics: Guild metrics dictionary
            
        Returns:
            Discord Activity object or None if failed
        """
        try:
            config = PRESENCE_CONFIGS.get(presence_type)
            if not config:
                return None
            
            # Get count based on presence type
            count_key = presence_type.value.replace('_count', '_count')
            count = metrics.get(count_key, 0)
            
            # Format presence name
            presence_name = config.format_name(count)
            
            # Create activity
            return format_presence_activity(config.activity_type, presence_name)
            
        except Exception as e:
            log_error_with_traceback(f"Failed to create presence activity for {presence_type}", e)
            return None
    
    def _handle_discord_error(self, error: discord.HTTPException):
        """Handle Discord API errors with appropriate logging and recovery."""
        self._error_count += 1
        
        if error.status == 429:  # Rate limited
            log_perfect_tree_section(
                "Rich Presence Rate Limited",
                [
                    ("retry_after", f"{error.retry_after}s" if hasattr(error, 'retry_after') else "unknown"),
                    ("error_count", self._error_count)
                ],
                emoji="⏱️"
            )
        elif error.status >= 500:  # Server errors
            log_perfect_tree_section(
                "Discord Server Error",
                [
                    ("status_code", error.status),
                    ("error_count", self._error_count)
                ],
                emoji="🌐"
            )
        else:
            log_error_with_traceback("Discord API error in rich presence", error)
        
        # Disable service if too many errors
        if self._error_count >= self._max_errors:
            self._disable_service()
    
    def _handle_unexpected_error(self, error: Exception):
        """Handle unexpected errors in presence updates."""
        self._error_count += 1
        log_error_with_traceback("Unexpected error in rich presence update", error)
        
        # Disable service if too many errors
        if self._error_count >= self._max_errors:
            self._disable_service()
    
    def _disable_service(self):
        """Disable the rich presence service due to repeated errors."""
        self._service_enabled = False
        log_perfect_tree_section(
            "Rich Presence Service Disabled",
            [
                ("reason", "Too many consecutive errors"),
                ("error_count", self._error_count),
                ("max_errors", self._max_errors)
            ],
            emoji="🚫"
        )
    
    def enable_service(self):
        """Re-enable the rich presence service."""
        self._service_enabled = True
        self._error_count = 0
        log_perfect_tree_section(
            "Rich Presence Service Enabled",
            [("status", "Service re-enabled")],
            emoji="✅"
        )
    
    @timing(category="presence")
    async def start(self) -> None:
        """
        Start the rich presence update loop.
        
        This method runs continuously until the bot is closed,
        updating the presence at the configured interval.
        """
        await self.bot.wait_until_ready()
        
        log_perfect_tree_section(
            "Rich Presence Loop Started",
            [
                ("update_interval", f"{self.update_interval}s"),
                ("presence_types", len(self.presence_types))
            ],
            emoji="🔄"
        )
        
        while not self.bot.is_closed():
            if self._service_enabled:
                await self.update_presence()
            
            # Sleep for the configured interval
            await asyncio.sleep(self.update_interval)
    
    async def set_shutdown_presence(self) -> bool:
        """
        Set a shutdown presence when the bot is shutting down.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name="🔄 Restarting..."
            )
            
            await self.bot.change_presence(
                status=discord.Status.idle,
                activity=activity
            )
            
            return True
            
        except Exception as e:
            log_error_with_traceback("Failed to set shutdown presence", e)
            return False
    
    def get_service_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive service statistics.
        
        Returns:
            Dictionary containing service performance and status information
        """
        uptime = time.time() - self._last_update if self._last_update > 0 else 0
        avg_update_time = (self._total_update_time / self._update_count 
                          if self._update_count > 0 else 0)
        
        return {
            "service_enabled": self._service_enabled,
            "update_count": self._update_count,
            "error_count": self._error_count,
            "current_presence_type": (self.presence_types[self.current_index].value 
                                    if self.presence_types else "none"),
            "uptime_seconds": uptime,
            "average_update_time_ms": avg_update_time * 1000,
            "cache_hit_rate": self._calculate_cache_hit_rate(),
            "next_update_in": max(0, self.update_interval - (time.time() - self._last_update))
        }
    
    def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate for performance monitoring."""
        # This is a simplified implementation
        # In a real scenario, you'd track cache hits vs misses
        if self._update_count == 0:
            return 0.0
        
        # Estimate based on cache TTL and update frequency
        cache_effectiveness = min(1.0, self._cache_ttl / self.update_interval)
        return cache_effectiveness * 100  # Return as percentage