"""
Optimized StatsService with intelligent caching and rate limit handling.

This module provides an optimized implementation of the StatsService with:
- Intelligent caching to avoid redundant API calls
- Consolidated rate limit handling with exponential backoff
- Efficient batch processing for multiple channel updates
- Change detection to minimize Discord API usage
"""

import asyncio
import discord
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any, Set

from src.core.config import get_config
from src.core.exceptions import RateLimitError, DiscordAPIError
from src.types.models import ChannelStats, EventType, MemberEvent
# Import CacheManager lazily to avoid circular imports
from src.utils.error_handling.backoff import exponential_backoff
from src.utils.logging.structured_logger import StructuredLogger, timed

from .tracker import StatsTracker


class OptimizedStatsService:
    """
    Optimized statistics service with intelligent caching and rate limit handling.
    
    This service efficiently manages Discord channel statistics updates by:
    - Caching previous values and only updating when changes are detected
    - Using exponential backoff for rate limit handling
    - Batching related operations when possible
    - Providing comprehensive error handling and recovery
    
    Attributes:
        bot (discord.Client): Discord bot client
        stats_tracker (StatsTracker): Statistics tracking and persistence
        cache (CacheManager): Cache for statistics and API responses
        logger (StructuredLogger): Structured logger for the service
    """
    
    # Cache keys
    CACHE_KEY_MEMBER_COUNT = "stats:member_count:{guild_id}"
    CACHE_KEY_ONLINE_COUNT = "stats:online_count:{guild_id}"
    CACHE_KEY_BAN_COUNT = "stats:ban_count:{guild_id}"
    CACHE_KEY_CHANNEL_PREFIX = "stats:channel:{channel_id}"
    CACHE_KEY_STATS = "stats:channel_stats:{guild_id}"
    
    def __init__(
        self, 
        bot: discord.Client,
        logger: Optional[StructuredLogger] = None,
        cache_ttl: int = 300
    ):
        """
        Initialize the optimized stats service.
        
        Args:
            bot: Discord bot client
            logger: Structured logger (optional)
            cache_ttl: Default cache TTL in seconds (default: 300)
        """
        self.bot = bot
        self.stats_tracker = StatsTracker()
        # Import CacheManager lazily to avoid circular imports
        from src.utils.cache.cache_manager import CacheManager
        self.cache = CacheManager(default_ttl=cache_ttl)
        self.logger = logger or StructuredLogger("stats_service")
        
        # Set up EST timezone
        self.est_tz = timezone(timedelta(hours=-5))
        
        # Generate run ID for this service instance
        self.run_id = ''.join(random.choices('0123456789ABCDEF', k=8))
        
        # Load channel IDs from configuration
        config = get_config()
        self.member_count_channel_id = config.member_count_channel_id
        self.online_count_channel_id = config.online_count_channel_id
        self.ban_count_channel_id = config.ban_count_channel_id
        self.stats_channel_id = config.stats_channel_id
        
        # Set up locks for concurrent operations
        self._member_lock = asyncio.Lock()
        self._online_lock = asyncio.Lock()
        self._ban_lock = asyncio.Lock()
        
        self.logger.info(
            "Optimized Stats Service initialized",
            service="StatsService",
            run_id=self.run_id,
            member_channel=self.member_count_channel_id,
            online_channel=self.online_count_channel_id,
            ban_channel=self.ban_count_channel_id,
            stats_channel=self.stats_channel_id
        )
        
    async def start_daily_stats_task(self) -> asyncio.Task:
        """
        Start the daily stats task.
        
        Returns:
            asyncio.Task: The scheduled task
        """
        self.logger.info(
            "Starting daily stats task",
            service="StatsService",
            next_run="12 AM EST"
        )
        return asyncio.create_task(self._schedule_daily_stats())
        
    async def _schedule_daily_stats(self) -> None:
        """Schedule daily stats to be sent at 12 AM EST."""
        while True:
            try:
                # Calculate time until next 12 AM EST
                now = datetime.now(self.est_tz)
                next_run = now.replace(hour=0, minute=0, second=0, microsecond=0)
                if now >= next_run:
                    next_run = next_run + timedelta(days=1)
                
                # Wait until next run time
                wait_seconds = (next_run - now).total_seconds()
                self.logger.info(
                    f"Scheduled next daily stats in {wait_seconds:.1f} seconds",
                    service="StatsService",
                    next_run=next_run.isoformat()
                )
                await asyncio.sleep(wait_seconds)
                
                # Send daily stats
                await self.send_daily_stats()
                
            except asyncio.CancelledError:
                self.logger.info("Daily stats task cancelled", service="StatsService")
                break
            except Exception as e:
                self.logger.error(
                    "Error in daily stats scheduler",
                    error=e,
                    service="StatsService"
                )
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    @timed("send_daily_stats")
    async def send_daily_stats(self) -> None:
        """
        Generate and send comprehensive daily statistics report.
        
        The report includes:
        - Member activity (joins, leaves, net change)
        - Moderation activity (bans, unbans)
        - Server growth metrics
        - Recent member changes
        
        This is automatically scheduled to run at 12 AM EST daily.
        """
        if self.stats_channel_id == 0:
            self.logger.warning(
                "Daily stats skipped - stats channel not configured",
                service="StatsService"
            )
            return
            
        try:
            channel = self.bot.get_channel(self.stats_channel_id)
            if not channel:
                self.logger.error(
                    f"Could not find stats channel {self.stats_channel_id}",
                    service="StatsService"
                )
                return
                
            # Get yesterday's date since we're running at midnight
            yesterday = (datetime.now(self.est_tz) - timedelta(days=1)).strftime("%Y-%m-%d")
            stats = self.stats_tracker.get_daily_stats(yesterday)
            
            # Create embed
            embed = discord.Embed(
                title=f"📊 Daily Stats Report - {yesterday}",
                color=discord.Color.blue(),
                timestamp=datetime.now(self.est_tz)
            )
            
            # Add stats fields
            embed.add_field(
                name="Member Activity",
                value=f"Joins: {stats['joins']}\nLeaves: {stats['leaves']}\nNet Change: {stats['net_change']}",
                inline=False
            )
            
            if stats['bans'] > 0:
                embed.add_field(
                    name="Moderation",
                    value=f"Bans: {stats['bans']}",
                    inline=False
                )
            
            # Add detailed lists if there was activity
            if stats['joins'] > 0:
                join_list = "\n".join([f"<@{join['id']}>" for join in stats['join_list'][:10]])
                if len(stats['join_list']) > 10:
                    join_list += f"\n*...and {len(stats['join_list']) - 10} more*"
                embed.add_field(name="New Members", value=join_list or "None", inline=False)
            
            if stats['leaves'] > 0:
                leave_list = "\n".join([f"{leave['username']}" for leave in stats['leave_list'][:10]])
                if len(stats['leave_list']) > 10:
                    leave_list += f"\n*...and {len(stats['leave_list']) - 10} more*"
                embed.add_field(name="Members Left", value=leave_list or "None", inline=False)
            
            await channel.send(embed=embed)
            
            self.logger.info(
                "Daily stats sent successfully",
                service="StatsService",
                date=yesterday,
                channel_id=self.stats_channel_id,
                joins=stats['joins'],
                leaves=stats['leaves'],
                bans=stats['bans'],
                net_change=stats['net_change']
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to send daily stats",
                error=e,
                service="StatsService"
            )
    
    @exponential_backoff(max_attempts=5, base_delay=2.0, max_delay=60.0)
    async def _update_channel_name_with_backoff(
        self, 
        channel_id: int, 
        new_name: str
    ) -> None:
        """
        Update a channel name with exponential backoff for rate limits.
        
        Args:
            channel_id: Channel ID to update
            new_name: New channel name
            
        Raises:
            RateLimitError: If rate limit is hit after max retries
            DiscordAPIError: If channel update fails for other reasons
        """
        channel = self.bot.get_channel(channel_id)
        if not channel:
            self.logger.warning(
                f"Channel {channel_id} not found",
                service="StatsService",
                channel_id=channel_id
            )
            return
            
        try:
            # Check if the name actually changed to avoid unnecessary API calls
            if channel.name == new_name:
                self.logger.debug(
                    f"Channel {channel_id} name unchanged, skipping update",
                    service="StatsService",
                    channel_id=channel_id,
                    channel_name=new_name
                )
                return
                
            # Update the channel name
            await channel.edit(name=new_name)
            
            # Cache the new channel name
            cache_key = self.CACHE_KEY_CHANNEL_PREFIX.format(channel_id=channel_id)
            self.cache.set(cache_key, new_name)
            
            self.logger.info(
                f"Updated channel {channel_id} name to '{new_name}'",
                service="StatsService",
                channel_id=channel_id,
                new_name=new_name
            )
            
        except discord.errors.HTTPException as e:
            if e.status == 429:  # Rate limit error
                retry_after = e.retry_after if hasattr(e, 'retry_after') else 5.0
                self.logger.warning(
                    f"Rate limited when updating channel {channel_id}",
                    service="StatsService",
                    channel_id=channel_id,
                    retry_after=retry_after
                )
                raise RateLimitError(
                    f"Rate limited when updating channel {channel_id}",
                    retry_after=retry_after,
                    endpoint=f"channels/{channel_id}"
                )
            else:
                self.logger.error(
                    f"Failed to update channel {channel_id}",
                    error=e,
                    service="StatsService",
                    channel_id=channel_id
                )
                raise DiscordAPIError(
                    f"Failed to update channel {channel_id}: {str(e)}",
                    status_code=e.status,
                    operation="channel_update"
                )
    
    @timed("update_member_count")
    async def update_member_count(self, guild: discord.Guild) -> bool:
        """
        Update member count channel name if the count has changed.
        
        Args:
            guild: Discord guild
            
        Returns:
            bool: True if update was performed, False if skipped
        """
        async with self._member_lock:
            # Get cached member count
            cache_key = self.CACHE_KEY_MEMBER_COUNT.format(guild_id=guild.id)
            cached_count = self.cache.get(cache_key)
            
            # Check if count has changed
            if cached_count is not None and cached_count == guild.member_count:
                self.logger.debug(
                    "Member count unchanged, skipping update",
                    service="StatsService",
                    guild_id=guild.id,
                    member_count=guild.member_count
                )
                return False
                
            # Get channel and extract prefix
            channel = self.bot.get_channel(self.member_count_channel_id)
            if not channel:
                self.logger.warning(
                    f"Member count channel {self.member_count_channel_id} not found",
                    service="StatsService"
                )
                return False
                
            # Extract the current name prefix before the number
            current_name = channel.name
            name_parts = current_name.split(":")
            if len(name_parts) > 1:
                prefix = name_parts[0] + ":"
            else:
                prefix = "Members:"  # Fallback if no prefix found
                
            # Update channel name
            new_name = f"{prefix} {guild.member_count}"
            try:
                await self._update_channel_name_with_backoff(self.member_count_channel_id, new_name)
                
                # Cache the new count
                self.cache.set(cache_key, guild.member_count)
                
                # Update channel stats in cache
                await self._update_cached_stats(guild)
                
                return True
            except Exception as e:
                self.logger.error(
                    "Failed to update member count channel",
                    error=e,
                    service="StatsService"
                )
                return False
    
    @timed("update_online_count")
    async def update_online_count(self, guild: discord.Guild) -> bool:
        """
        Update online count channel name if the count has changed.
        
        Args:
            guild: Discord guild
            
        Returns:
            bool: True if update was performed, False if skipped
        """
        async with self._online_lock:
            # Calculate online count
            online_count = len([m for m in guild.members if m.status != discord.Status.offline])
            
            # Get cached online count
            cache_key = self.CACHE_KEY_ONLINE_COUNT.format(guild_id=guild.id)
            cached_count = self.cache.get(cache_key)
            
            # Check if count has changed
            if cached_count is not None and cached_count == online_count:
                self.logger.debug(
                    "Online count unchanged, skipping update",
                    service="StatsService",
                    guild_id=guild.id,
                    online_count=online_count
                )
                return False
                
            # Get channel and extract prefix
            channel = self.bot.get_channel(self.online_count_channel_id)
            if not channel:
                self.logger.warning(
                    f"Online count channel {self.online_count_channel_id} not found",
                    service="StatsService"
                )
                return False
                
            # Extract the current name prefix before the number
            current_name = channel.name
            name_parts = current_name.split(":")
            if len(name_parts) > 1:
                prefix = name_parts[0] + ":"
            else:
                prefix = "Online:"  # Fallback if no prefix found
                
            # Update channel name
            new_name = f"{prefix} {online_count}"
            try:
                await self._update_channel_name_with_backoff(self.online_count_channel_id, new_name)
                
                # Cache the new count
                self.cache.set(cache_key, online_count)
                
                # Update channel stats in cache
                await self._update_cached_stats(guild)
                
                return True
            except Exception as e:
                self.logger.error(
                    "Failed to update online count channel",
                    error=e,
                    service="StatsService"
                )
                return False
    
    @timed("update_ban_count")
    async def update_ban_count(self, guild: discord.Guild) -> bool:
        """
        Update ban count channel name if the count has changed.
        
        Args:
            guild: Discord guild
            
        Returns:
            bool: True if update was performed, False if skipped
        """
        async with self._ban_lock:
            try:
                # Get ban count (this is an expensive API call, so we cache it longer)
                cache_key = self.CACHE_KEY_BAN_COUNT.format(guild_id=guild.id)
                ban_count = self.cache.get(cache_key)
                
                if ban_count is None:
                    # Cache miss, need to fetch bans
                    bans = [entry async for entry in guild.bans()]
                    ban_count = len(bans)
                    # Cache ban count with longer TTL (10 minutes) since it changes less frequently
                    self.cache.set(cache_key, ban_count, ttl=600)
                    
                    self.logger.debug(
                        f"Fetched ban count: {ban_count}",
                        service="StatsService",
                        guild_id=guild.id
                    )
                else:
                    self.logger.debug(
                        f"Using cached ban count: {ban_count}",
                        service="StatsService",
                        guild_id=guild.id
                    )
                
                # Get channel and extract prefix
                channel = self.bot.get_channel(self.ban_count_channel_id)
                if not channel:
                    self.logger.warning(
                        f"Ban count channel {self.ban_count_channel_id} not found",
                        service="StatsService"
                    )
                    return False
                    
                # Extract the current name prefix before the number
                current_name = channel.name
                name_parts = current_name.split(":")
                if len(name_parts) > 1:
                    prefix = name_parts[0] + ":"
                else:
                    prefix = "Bans:"  # Fallback if no prefix found
                    
                # Check if the current name already has the correct count
                current_count = None
                try:
                    if len(name_parts) > 1 and name_parts[1].strip().isdigit():
                        current_count = int(name_parts[1].strip())
                except (ValueError, IndexError):
                    pass
                    
                if current_count == ban_count:
                    self.logger.debug(
                        "Ban count unchanged, skipping update",
                        service="StatsService",
                        guild_id=guild.id,
                        ban_count=ban_count
                    )
                    return False
                    
                # Update channel name
                new_name = f"{prefix} {ban_count}"
                await self._update_channel_name_with_backoff(self.ban_count_channel_id, new_name)
                
                # Update channel stats in cache
                await self._update_cached_stats(guild)
                
                return True
            except Exception as e:
                self.logger.error(
                    "Failed to update ban count channel",
                    error=e,
                    service="StatsService"
                )
                return False
    
    async def _update_cached_stats(self, guild: discord.Guild) -> None:
        """
        Update the cached channel statistics.
        
        Args:
            guild: Discord guild
        """
        try:
            # Get current counts
            member_count = guild.member_count
            online_count = len([m for m in guild.members if m.status != discord.Status.offline])
            
            # Get ban count from cache or fetch if needed
            ban_cache_key = self.CACHE_KEY_BAN_COUNT.format(guild_id=guild.id)
            ban_count = self.cache.get(ban_cache_key)
            if ban_count is None:
                # This is an expensive operation, so we only do it if necessary
                bans = [entry async for entry in guild.bans()]
                ban_count = len(bans)
                self.cache.set(ban_cache_key, ban_count, ttl=600)
            
            # Create stats object
            stats = ChannelStats(
                member_count=member_count,
                online_count=online_count,
                ban_count=ban_count,
                last_updated=datetime.now(timezone.utc),
                guild_id=guild.id
            )
            
            # Cache the stats
            stats_cache_key = self.CACHE_KEY_STATS.format(guild_id=guild.id)
            self.cache.set(stats_cache_key, stats)
            
            self.logger.debug(
                "Updated cached channel stats",
                service="StatsService",
                guild_id=guild.id,
                member_count=member_count,
                online_count=online_count,
                ban_count=ban_count
            )
        except Exception as e:
            self.logger.error(
                "Failed to update cached stats",
                error=e,
                service="StatsService"
            )
    
    @timed("update_all_stats")
    async def update_all_stats(self, guild: discord.Guild) -> Dict[str, bool]:
        """
        Update all stats channels efficiently.
        
        This method batches the updates to minimize API calls and
        uses cached values to avoid unnecessary updates.
        
        Args:
            guild: Discord guild
            
        Returns:
            Dict with update status for each stat type
        """
        # Run updates concurrently
        results = await asyncio.gather(
            self.update_member_count(guild),
            self.update_online_count(guild),
            self.update_ban_count(guild),
            return_exceptions=True
        )
        
        # Process results
        status = {
            "member_count": isinstance(results[0], bool) and results[0],
            "online_count": isinstance(results[1], bool) and results[1],
            "ban_count": isinstance(results[2], bool) and results[2]
        }
        
        # Log any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                stat_type = ["member_count", "online_count", "ban_count"][i]
                self.logger.error(
                    f"Error updating {stat_type}",
                    error=result,
                    service="StatsService"
                )
        
        return status
    
    async def get_cached_stats(self, guild_id: int) -> Optional[ChannelStats]:
        """
        Get cached channel statistics.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            ChannelStats object if available, None otherwise
        """
        cache_key = self.CACHE_KEY_STATS.format(guild_id=guild_id)
        return self.cache.get(cache_key)
    
    def record_member_event(
        self, 
        event_type: EventType, 
        member_id: int, 
        username: str
    ) -> None:
        """
        Record a member event (join, leave, ban).
        
        Args:
            event_type: Type of event
            member_id: Member ID
            username: Member username
        """
        try:
            # Create event object
            event = MemberEvent(
                member_id=member_id,
                username=username,
                timestamp=datetime.now(timezone.utc),
                event_type=event_type
            )
            
            # Record event based on type
            if event_type == EventType.JOIN:
                self.stats_tracker.record_member_join(member_id, username)
                self.logger.info(
                    f"Member joined: {username}",
                    service="StatsService",
                    member_id=member_id,
                    username=username,
                    event_type=event_type.value
                )
            elif event_type == EventType.LEAVE:
                self.stats_tracker.record_member_leave(member_id, username)
                self.logger.info(
                    f"Member left: {username}",
                    service="StatsService",
                    member_id=member_id,
                    username=username,
                    event_type=event_type.value
                )
            elif event_type == EventType.BAN:
                self.stats_tracker.record_member_ban(member_id, username)
                self.logger.info(
                    f"Member banned: {username}",
                    service="StatsService",
                    member_id=member_id,
                    username=username,
                    event_type=event_type.value
                )
            
            # Invalidate relevant caches
            guild_id = self.bot.guilds[0].id if self.bot.guilds else None
            if guild_id:
                self.cache.invalidate(self.CACHE_KEY_MEMBER_COUNT.format(guild_id=guild_id))
                if event_type == EventType.BAN:
                    self.cache.invalidate(self.CACHE_KEY_BAN_COUNT.format(guild_id=guild_id))
        except Exception as e:
            self.logger.error(
                f"Failed to record {event_type.value} event",
                error=e,
                service="StatsService",
                member_id=member_id,
                username=username
            )
    
    def record_member_join(self, member_id: int, username: str) -> None:
        """Record member join event."""
        self.record_member_event(EventType.JOIN, member_id, username)
        
    def record_member_leave(self, member_id: int, username: str) -> None:
        """Record member leave event."""
        self.record_member_event(EventType.LEAVE, member_id, username)
    
    def record_member_ban(self, member_id: int, username: str) -> None:
        """Record member ban event."""
        self.record_member_event(EventType.BAN, member_id, username)
    
    async def save_data(self) -> None:
        """Save all pending data."""
        try:
            await self.stats_tracker.save_data()
            self.logger.info(
                "Stats data saved successfully",
                service="StatsService"
            )
        except Exception as e:
            self.logger.error(
                "Failed to save stats data",
                error=e,
                service="StatsService"
            )
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        stats = self.cache.get_stats()
        return {
            "total_entries": stats.total_entries,
            "hit_count": stats.hit_count,
            "miss_count": stats.miss_count,
            "hit_rate": stats.hit_rate,
            "memory_usage_bytes": stats.memory_usage_bytes
        }