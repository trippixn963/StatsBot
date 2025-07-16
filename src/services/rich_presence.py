"""
StatsBot Rich Presence Service

This service manages the bot's Discord presence (status, activity) to display
useful server statistics and bot information to users.

Key Features:
- Dynamic status updates with server statistics
- Rotating activity messages
- Customizable update intervals
- Automatic error recovery

The service cycles through different presence types to display various
statistics and information about the server and bot status.
"""

import discord
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from ..utils.tree_log import log_perfect_tree_section

class RichPresenceService:
    """
    Service for managing the bot's rich presence on Discord.
    
    This service handles:
    1. Dynamic status updates with server metrics
    2. Rotating activity messages
    3. Presence error recovery
    4. Status update scheduling
    
    The service maintains a list of presence types that it cycles through,
    updating the bot's status at regular intervals to display different
    server statistics and information.
    
    Attributes:
        bot (discord.Client): The Discord bot instance
        update_interval (int): Time between presence updates in seconds
        current_index (int): Index of current presence type in rotation
        presence_types (List[str]): Available presence display types
    """
    
    def __init__(self, bot: discord.Client):
        """
        Initialize the rich presence service.
        
        Args:
            bot (discord.Client): The Discord bot instance
        """
        self.bot = bot
        self.update_interval = 300  # 5 minutes
        self.current_index = 0
        
        # Available presence types to cycle through
        self.presence_types = [
            'member_count',
            'online_count',
            'uptime',
            'version'
        ]
        
        # Log initialization
        log_perfect_tree_section(
            "Rich Presence Service",
            [
                ("status", "Initializing"),
                ("update_interval", f"{self.update_interval}s"),
                ("presence_types", len(self.presence_types))
            ],
            emoji="👤"
        )
    
    async def update_presence(self):
        """
        Update the bot's presence with the next status in rotation.
        
        This method:
        1. Selects the next presence type from rotation
        2. Gathers relevant statistics/information
        3. Updates the bot's status and activity
        4. Handles any errors that occur during update
        """
        try:
            presence_type = self.presence_types[self.current_index]
            
            if presence_type == 'member_count':
                member_count = len(self.bot.guilds[0].members)
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{member_count:,} members"
                )
            elif presence_type == 'online_count':
                online_count = sum(1 for m in self.bot.guilds[0].members if m.status != discord.Status.offline)
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{online_count:,} online"
                )
            elif presence_type == 'uptime':
                uptime = datetime.now() - self.bot.start_time
                days = uptime.days
                hours = uptime.seconds // 3600
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name=f"Up {days}d {hours}h"
                )
            else:  # version
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name="v1.0.0"
                )
            
            await self.bot.change_presence(activity=activity)
            
            # Update index for next rotation
            self.current_index = (self.current_index + 1) % len(self.presence_types)
            
        except Exception as e:
            log_perfect_tree_section(
                "Rich Presence Error",
                [
                    ("error", str(e)),
                    ("presence_type", presence_type)
                ],
                emoji="❌"
            )
    
    async def start(self):
        """
        Start the rich presence update loop.
        
        This method runs indefinitely, updating the bot's presence at
        regular intervals defined by update_interval.
        """
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await self.update_presence()
            await asyncio.sleep(self.update_interval) 