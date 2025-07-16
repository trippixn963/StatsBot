"""
StatsBot Statistics Service

This service manages all statistics-related functionality including:
- Real-time channel name updates for member counts, online status, and bans
- Daily statistics reporting at 12 AM EST
- Member activity tracking and analysis
- Rate limit handling with exponential backoff

The service implements intelligent cooldowns and backoff strategies to avoid
Discord API rate limits while maintaining accurate statistics.

Key Features:
- Automated channel updates with configurable intervals
- Rate limit handling with exponential backoff
- Daily statistics generation and reporting
- Member activity tracking (joins, leaves, bans)
"""

import discord
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from config.config import config
from src.utils.tree_log import log_perfect_tree_section, log_error_with_traceback
from .stats_tracker import StatsTracker
from .monitoring import MonitoringService
from .rich_presence import RichPresenceService
import os
import random

class StatsService:
    """
    Core statistics service for tracking and reporting server metrics.
    
    This service handles:
    1. Channel name updates for various metrics
    2. Rate limit management with exponential backoff
    3. Daily statistics generation and reporting
    4. Member activity tracking
    
    Attributes:
        bot (discord.Client): The Discord bot instance
        base_cooldown (int): Base cooldown between updates in seconds
        max_backoff (int): Maximum backoff time for rate limits in seconds
        member_cooldown (timedelta): Cooldown for member count updates
        online_cooldown (timedelta): Cooldown for online count updates
        ban_cooldown (timedelta): Cooldown for ban count updates
    """
    
    def __init__(self, bot: discord.Client):
        # Log initialization
        log_perfect_tree_section(
            "Stats Service",
            [("status", "Initializing"), ("type", "Channel Updates")],
            emoji="📊"
        )
        
        self.bot = bot
        self.stats_tracker = StatsTracker()
        
        # Set up EST timezone
        self.est_tz = timezone(timedelta(hours=-5))
        
        # Generate run ID
        self.run_id = ''.join(random.choices('0123456789ABCDEF', k=8))
        
        # Load channel IDs from environment
        self.member_count_channel_id = int(os.getenv('MEMBER_COUNT_CHANNEL_ID'))
        self.online_count_channel_id = int(os.getenv('ONLINE_COUNT_CHANNEL_ID'))
        self.ban_count_channel_id = int(os.getenv('BAN_COUNT_CHANNEL_ID'))
        self.stats_channel_id = int(os.getenv('STATS_CHANNEL_ID', '0'))  # New channel for daily stats
        
        # Initialize cooldowns and caches
        self.last_member_update = datetime.now(self.est_tz) - timedelta(minutes=5)
        self.last_online_update = datetime.now(self.est_tz) - timedelta(minutes=5)
        self.last_ban_update = datetime.now(self.est_tz) - timedelta(minutes=5)
        self.member_count_cache = 0
        self.online_count_cache = 0
        self.ban_count_cache = 0
        
        # Base cooldown settings (in seconds)
        self.base_cooldown = 300  # 5 minutes
        self.member_cooldown = timedelta(seconds=self.base_cooldown)
        self.online_cooldown = timedelta(seconds=self.base_cooldown)
        self.ban_cooldown = timedelta(seconds=self.base_cooldown)
        
        # Rate limit backoff settings
        self.max_backoff = 3600  # 1 hour max backoff
        self.member_backoff = self.base_cooldown
        self.online_backoff = self.base_cooldown
        self.ban_backoff = self.base_cooldown
        
        # Schedule daily stats task
        self.daily_stats_task = None
        
        # Log configuration
        log_perfect_tree_section(
            "Stats Configuration",
            [
                ("member_channel", str(self.member_count_channel_id)),
                ("online_channel", str(self.online_count_channel_id)),
                ("ban_channel", str(self.ban_count_channel_id)),
                ("stats_channel", str(self.stats_channel_id)),
                ("update_interval", f"{self.base_cooldown}s"),
                ("max_backoff", f"{self.max_backoff}s")
            ],
            emoji="⚙️"
        )

    async def start_daily_stats_task(self):
        """Start the daily stats task."""
        if self.daily_stats_task is None:
            self.daily_stats_task = asyncio.create_task(self._schedule_daily_stats())
            log_perfect_tree_section(
                "Daily Stats Task",
                [("status", "Started"), ("next_run", "12 AM EST")],
                emoji="📊"
            )

    async def _schedule_daily_stats(self):
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
                await asyncio.sleep(wait_seconds)
                
                # Send daily stats
                await self.send_daily_stats()
                
            except Exception as e:
                log_error_with_traceback("Error in daily stats scheduler", e)
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def send_daily_stats(self):
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
            log_perfect_tree_section(
                "Daily Stats",
                [("status", "Skipped"), ("reason", "Stats channel not configured")],
                emoji="⚠️"
            )
            return
            
        try:
            channel = self.bot.get_channel(self.stats_channel_id)
            if not channel:
                log_error_with_traceback(
                    f"Could not find stats channel {self.stats_channel_id}",
                    None
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
            
            log_perfect_tree_section(
                "Daily Stats",
                [
                    ("status", "Sent"),
                    ("date", yesterday),
                    ("channel", str(self.stats_channel_id))
                ],
                emoji="📊"
            )
            
        except Exception as e:
            log_error_with_traceback("Failed to send daily stats", e)

    async def _handle_rate_limit(self, channel_type: str, retry_after: float) -> None:
        """Handle rate limit by implementing exponential backoff."""
        if channel_type == "member":
            self.member_backoff = min(self.member_backoff * 2, self.max_backoff)
            self.member_cooldown = timedelta(seconds=self.member_backoff)
        elif channel_type == "online":
            self.online_backoff = min(self.online_backoff * 2, self.max_backoff)
            self.online_cooldown = timedelta(seconds=self.online_backoff)
        elif channel_type == "ban":
            self.ban_backoff = min(self.ban_backoff * 2, self.max_backoff)
            self.ban_cooldown = timedelta(seconds=self.ban_backoff)
            
        log_perfect_tree_section(
            "Rate Limit Backoff",
            [
                ("channel_type", channel_type),
                ("retry_after", f"{retry_after:.2f}s"),
                ("new_cooldown", f"{getattr(self, f'{channel_type}_backoff')}s")
            ],
            emoji="⏳"
        )

    async def _reset_backoff(self, channel_type: str) -> None:
        """Reset backoff after successful update."""
        if channel_type == "member":
            self.member_backoff = self.base_cooldown
            self.member_cooldown = timedelta(seconds=self.base_cooldown)
        elif channel_type == "online":
            self.online_backoff = self.base_cooldown
            self.online_cooldown = timedelta(seconds=self.base_cooldown)
        elif channel_type == "ban":
            self.ban_backoff = self.base_cooldown
            self.ban_cooldown = timedelta(seconds=self.base_cooldown)

    async def update_channel_name(self, channel_id: int, new_name: str, backoff_attr: str) -> bool:
        """
        Update a channel name with intelligent rate limit handling.
        
        Implements exponential backoff when rate limits are encountered:
        - Doubles the backoff time on each rate limit
        - Caps at max_backoff (1 hour)
        - Resets to base_cooldown on successful updates
        
        Args:
            channel_id (int): The ID of the channel to update
            new_name (str): The new name for the channel
            backoff_attr (str): The attribute name storing the current backoff time
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return False
                
            await channel.edit(name=new_name)
            setattr(self, backoff_attr, self.base_cooldown)  # Reset backoff on success
            return True
            
        except discord.errors.HTTPException as e:
            if e.status == 429:  # Rate limit error
                retry_after = e.retry_after
                current_backoff = getattr(self, backoff_attr)
                
                # Exponential backoff with max limit
                new_backoff = min(current_backoff * 2, self.max_backoff)
                setattr(self, backoff_attr, new_backoff)
                
                log_perfect_tree_section(
                    "Rate Limit",
                    [
                        ("channel", str(channel_id)),
                        ("retry_after", f"{retry_after}s"),
                        ("new_backoff", f"{new_backoff}s")
                    ],
                    emoji="⏳"
                )
                
                return False
            else:
                log_error_with_traceback(f"Failed to update channel {channel_id}", e)
                return False
        except Exception as e:
            log_error_with_traceback(f"Failed to update channel {channel_id}", e)
            return False

    async def update_member_count(self, guild: discord.Guild):
        """Update member count channel name."""
        if datetime.now(self.est_tz) - self.last_member_update < timedelta(seconds=self.member_backoff):
            return
            
        new_name = f"Members: {guild.member_count}"
        if await self.update_channel_name(self.member_count_channel_id, new_name, 'member_backoff'):
            self.last_member_update = datetime.now(self.est_tz)
            self.member_count_cache = guild.member_count

    async def update_online_count(self, guild: discord.Guild):
        """Update online count channel name."""
        if datetime.now(self.est_tz) - self.last_online_update < timedelta(seconds=self.online_backoff):
            return
            
        online_count = len([m for m in guild.members if m.status != discord.Status.offline])
        new_name = f"Online: {online_count}"
        if await self.update_channel_name(self.online_count_channel_id, new_name, 'online_backoff'):
            self.last_online_update = datetime.now(self.est_tz)
            self.online_count_cache = online_count

    async def update_ban_count(self, guild: discord.Guild):
        """Update ban count channel name."""
        if datetime.now(self.est_tz) - self.last_ban_update < timedelta(seconds=self.ban_backoff):
            return
            
        bans = [entry async for entry in guild.bans()]
        new_name = f"Bans: {len(bans)}"
        if await self.update_channel_name(self.ban_count_channel_id, new_name, 'ban_backoff'):
            self.last_ban_update = datetime.now(self.est_tz)
            self.ban_count_cache = len(bans)
    
    async def update_all_stats(self, guild: discord.Guild):
        """Update all stats channels."""
        await self.update_member_count(guild)
        await self.update_online_count(guild)
        await self.update_ban_count(guild)
    
    def record_member_join(self, member_id: int, username: str):
        """Record member join event."""
        self.stats_tracker.record_member_join(member_id, username)
        
    def record_member_leave(self, member_id: int, username: str):
        """Record member leave event."""
        self.stats_tracker.record_member_leave(member_id, username)
    
    def record_member_ban(self, member_id: int, username: str):
        """Record member ban event."""
        self.stats_tracker.record_member_ban(member_id, username)
    
    async def save_data(self):
        """Save all pending data."""
        await self.stats_tracker.save_data()

class StatsBot(discord.Client):
    def __init__(self):
        # Log initialization start
        log_perfect_tree_section(
            "Bot Initialization",
            [("status", "Starting up"), ("type", "StatsBot")],
            emoji="🚀"
        )
        
        # Set up intents - include presence intent for accurate online status
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.presences = True  # Required for accurate online status tracking
        super().__init__(intents=intents)
        
        # Initialize services
        self.stats_service = StatsService(self)
        self.monitoring_service = MonitoringService(self, int(os.getenv('HEARTBEAT_CHANNEL_ID')))
        self.rich_presence_service = RichPresenceService(self)
        self.shutdown_event = None
        
        # Log initialization complete
        log_perfect_tree_section(
            "Bot Ready",
            [("status", "Initialization complete")],
            emoji="✅"
        )

    async def setup_hook(self):
        """Set up the bot's background tasks."""
        log_perfect_tree_section(
            "Background Tasks",
            [("status", "Starting"), ("type", "Channel Updates")],
            emoji="🔄"
        )
        self.bg_task = self.loop.create_task(self.background_task())
        self.heartbeat_task = self.loop.create_task(self.monitoring_service.update_heartbeat())
        self.rich_presence_task = self.loop.create_task(self.rich_presence_service.update_presence())
        await self.stats_service.start_daily_stats_task()  # Start daily stats task
        
    async def background_task(self):
        """Background task to update channel statistics."""
        await self.wait_until_ready()
        try:
            while not self.is_closed():
                try:
                    # Check for shutdown signal
                    if self.shutdown_event and self.shutdown_event.is_set():
                        log_perfect_tree_section(
                            "Background Task Shutdown",
                            [("status", "Stopping background task")],
                            emoji="🛑"
                        )
                        break
                        
                    # Update stats for the first guild (assuming single guild bot)
                    guild = self.guilds[0] if self.guilds else None
                    if guild:
                        await self.stats_service.update_all_stats(guild)
                    
                    # Wait for next update
                    try:
                        await asyncio.sleep(60)
                    except asyncio.CancelledError:
                        log_perfect_tree_section(
                            "Background Task",
                            [("status", "Shutting down")],
                            emoji="💤"
                        )
                        return
                except Exception as e:
                    log_error_with_traceback("Background task error", e, "ERROR")
                    try:
                        await asyncio.sleep(60)  # Wait before retrying
                    except asyncio.CancelledError:
                        log_perfect_tree_section(
                            "Background Task",
                            [("status", "Shutting down")],
                            emoji="💤"
                        )
                        return
        except asyncio.CancelledError:
            log_perfect_tree_section(
                "Background Task",
                [("status", "Shutting down")],
                emoji="💤"
            )
            return
                
    async def on_ready(self):
        """Handle bot ready event."""
        log_perfect_tree_section(
            "Bot Ready",
            [
                ("name", str(self.user)),
                ("id", str(self.user.id)),
                ("guilds", str(len(self.guilds))),
                ("latency", f"{self.latency*1000:.2f}ms")
            ],
            emoji="✅"
        )
        
        # Set startup rich presence
        await self.rich_presence_service.set_startup_presence()
        
    async def on_member_join(self, member: discord.Member):
        """Handle member join event."""
        self.stats_service.record_member_join(member.id, str(member))
        
    async def on_member_remove(self, member: discord.Member):
        """Handle member leave event."""
        self.stats_service.record_member_leave(member.id, str(member))
        
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Handle member ban event."""
        self.stats_service.record_member_ban(user.id, str(user)) 