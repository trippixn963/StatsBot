"""
StatsBot Rich Presence Service

This service manages the bot's Discord presence (status, activity) to display
useful server statistics and bot information to users.
"""

import discord
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from ..utils.tree_log import log_perfect_tree_section

class RichPresenceService:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.update_interval = 300  # 5 minutes
        self.current_index = 0
        
        # Available presence types to cycle through
        self.presence_types = [
            'member_count',
            'online_count',
            'ban_count'
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
        """Update the bot's presence with the next status in rotation."""
        try:
            if not self.bot.guilds:
                return
                
            guild = self.bot.guilds[0]
            presence_type = self.presence_types[self.current_index]
            
            if presence_type == 'member_count':
                member_count = len(guild.members)
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"👥 {member_count:,} members"
                )
            elif presence_type == 'online_count':
                online_count = sum(1 for m in guild.members if m.status != discord.Status.offline)
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"🟢 {online_count:,} online"
                )
            else:  # ban_count
                bans = [entry async for entry in guild.bans()]
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"🔨 {len(bans):,} bans"
                )
            
            await self.bot.change_presence(
                status=discord.Status.online,
                activity=activity
            )
            
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
        """Start the rich presence update loop."""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            await self.update_presence()
            await asyncio.sleep(self.update_interval) 