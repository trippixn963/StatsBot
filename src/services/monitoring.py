"""
StatsBot Monitoring Service

This service provides real-time monitoring and heartbeat functionality for the bot.
It sends periodic status updates and system metrics to a designated Discord channel.

Key Features:
- Hourly heartbeat messages with system metrics
- Member activity tracking and reporting
- System performance monitoring (CPU, RAM, ping)
- Log aggregation and display
- Uptime tracking in EST timezone

The service maintains a single heartbeat message that gets updated rather than
creating new messages, keeping the monitoring channel clean and organized.
"""

import discord
import asyncio
import logging
from datetime import datetime, timedelta, timezone
import pytz
from typing import Optional, List, Dict, Any
from src.utils.tree_log import log_error_with_traceback, log_perfect_tree_section
import psutil
import os
import sys
from pathlib import Path
import threading
from datetime import datetime, timezone, timedelta

class LogHandler(logging.Handler):
    """
    Custom logging handler that captures logs for display in heartbeat messages.
    
    This handler maintains a circular buffer of recent log messages that can be
    displayed in the bot's heartbeat updates.
    
    Attributes:
        monitoring_service: Reference to the parent monitoring service
        max_logs (int): Maximum number of logs to keep in memory
    """
    
    def __init__(self, monitoring_service, max_logs: int = 10):
        super().__init__()
        self.monitoring_service = monitoring_service
        self.max_logs = max_logs
    
    def emit(self, record: logging.LogRecord):
        """
        Process a log record and add it to the monitoring service's log buffer.
        
        Args:
            record (logging.LogRecord): The log record to process
        """
        try:
            self.monitoring_service.add_log({
                'level': record.levelname,
                'message': self.format(record),
                'timestamp': datetime.fromtimestamp(record.created)
            })
        except Exception:
            self.handleError(record)

class MonitoringService:
    """
    Core monitoring service that provides real-time bot status updates.
    
    This service handles:
    1. Periodic heartbeat messages with system metrics
    2. Recent member activity tracking
    3. System performance monitoring
    4. Log aggregation and display
    
    The service maintains a single heartbeat message that gets updated hourly,
    providing a clean and organized view of the bot's status.
    
    Attributes:
        bot (discord.Client): The Discord bot instance
        heartbeat_channel_id (int): Channel ID for heartbeat messages
        est_tz (timezone): EST timezone for consistent time display
        start_time (datetime): Bot start time in EST
        update_interval (int): Heartbeat update interval in seconds
    """
    
    def __init__(self, bot: discord.Client, heartbeat_channel_id: int):
        self.bot = bot
        self.heartbeat_channel_id = heartbeat_channel_id
        # Use fixed EST timezone (UTC-5)
        self.est_tz = timezone(timedelta(hours=-5))
        self.start_time = datetime.now(self.est_tz)
        self.log_handler = LogHandler(self)
        self.recent_logs: List[Dict] = []
        self.heartbeat_message: Optional[discord.Message] = None
        self.update_interval = 3600  # 1 hour in seconds
        
        # Add our custom handler to the root logger
        logging.getLogger().addHandler(self.log_handler)
        
        # Log initialization
        log_perfect_tree_section(
            "Monitoring Service",
            [
                ("status", "Initializing"),
                ("heartbeat_channel", str(heartbeat_channel_id)),
                ("timezone", "EST"),
                ("update_interval", f"{self.update_interval // 3600} hour")
            ],
            emoji="📡"
        )
        
    def add_log_entry(self, message: str, level: str = "INFO"):
        """Add a log entry to recent logs"""
        now = datetime.now(self.est_tz)
        log_entry = {
            'timestamp': now.strftime('%I:%M:%S %p EST'),
            'message': message[:100] + ('...' if len(message) > 100 else ''),
            'level': level
        }
        
        self.recent_logs.insert(0, log_entry)
        if len(self.recent_logs) > 5:
            self.recent_logs.pop()

    def get_system_metrics(self) -> Dict:
        """Get current system metrics"""
        process = psutil.Process()
        
        # Get disk usage for logs directory
        logs_path = Path('logs')
        if logs_path.exists():
            disk_usage = psutil.disk_usage(str(logs_path))
            disk_percent = disk_usage.percent
        else:
            disk_percent = 0
            
        return {
            'cpu_percent': process.cpu_percent(),
            'memory_percent': process.memory_percent(),
            'disk_percent': disk_percent,
            'threads': process.num_threads()
        }

    def format_uptime(self) -> str:
        """
        Format the bot's uptime in a human-readable format.
        
        Returns:
            str: Formatted uptime string (e.g., "5 days, 3 hours, 21 minutes")
        """
        est = pytz.timezone('US/Eastern')
        now = datetime.now(est)
        delta = now - self.start_time
        
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        seconds = delta.seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        
        return " ".join(parts)

    async def create_heartbeat_embed(self) -> discord.Embed:
        """Create the heartbeat status embed."""
        # Calculate uptime
        uptime = datetime.now(self.est_tz) - self.start_time
        days = uptime.days
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        
        # Get system metrics
        metrics = self.get_system_metrics()
        
        # Get today's member stats
        today = datetime.now(self.est_tz).strftime("%Y-%m-%d")
        stats = self.bot.stats_service.stats_tracker.get_daily_stats(today)
        
        # Create embed
        embed = discord.Embed(
            title="🤖 StatsBot Status",
            color=discord.Color.green(),
            timestamp=datetime.now(self.est_tz)
        )
        
        # Add uptime field
        uptime_str = []
        if days > 0:
            uptime_str.append(f"{days} days")
        if hours > 0:
            uptime_str.append(f"{hours} hours")
        if minutes > 0 or not uptime_str:
            uptime_str.append(f"{minutes} minutes")
        
        embed.add_field(
            name="⏱️ Uptime",
            value=" ".join(uptime_str),
            inline=True
        )
        
        # Add system metrics
        embed.add_field(
            name="💻 System",
            value=f"CPU: {metrics['cpu_percent']}%\nRAM: {metrics['memory_percent']}%\nPing: {round(self.bot.latency * 1000)}ms",
            inline=True
        )
        
        # Add today's member activity
        embed.add_field(
            name="📊 Today's Activity",
            value=f"Joins: {stats['joins']}\nLeaves: {stats['leaves']}\nNet Change: {stats['net_change']}\nBans: {stats['bans']}",
            inline=False
        )
        
        # Add recent member changes if any
        if stats['joins'] > 0:
            recent_joins = [f"<@{join['id']}>" for join in stats['join_list'][-3:]]  # Last 3 joins
            embed.add_field(
                name="👋 Recent Joins",
                value="\n".join(reversed(recent_joins)) or "None",
                inline=True
            )
        
        if stats['leaves'] > 0:
            recent_leaves = [leave['username'] for leave in stats['leave_list'][-3:]]  # Last 3 leaves
            embed.add_field(
                name="👋 Recent Leaves",
                value="\n".join(reversed(recent_leaves)) or "None",
                inline=True
            )
        
        # Add recent logs
        if self.recent_logs:
            log_text = "\n".join(
                f"`{log['timestamp']}` {log['level']}: {log['message']}"
                for log in self.recent_logs[-3:]  # Show last 3 logs
            )
            embed.add_field(
                name="📝 Recent Logs",
                value=log_text,
                inline=False
            )
        
        # Set footer with version and run ID
        embed.set_footer(text=f"StatsBot v1.0.0 • Run ID: {self.bot.stats_service.run_id}")
        
        # Set thumbnail to bot's avatar
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            
        return embed

    async def update_heartbeat(self):
        """
        Update the heartbeat message with current system metrics and activity.
        
        Generates a comprehensive status update including:
        - System metrics (CPU, RAM, ping)
        - Recent member activity
        - Latest log entries
        - Uptime information
        - Bot version and status
        
        The message is updated in place rather than creating new messages.
        """
        await self.bot.wait_until_ready()
        
        try:
            while True:
                try:
                    channel = self.bot.get_channel(self.heartbeat_channel_id)
                    if not channel:
                        log_error_with_traceback(
                            f"Failed to get heartbeat channel {self.heartbeat_channel_id}",
                            None
                        )
                        await asyncio.sleep(self.update_interval)
                        continue
                    
                    embed = await self.create_heartbeat_embed()
                    
                    # Create or update heartbeat message
                    if not self.heartbeat_message:
                        self.heartbeat_message = await channel.send(embed=embed)
                    else:
                        try:
                            await self.heartbeat_message.edit(embed=embed)
                        except discord.NotFound:
                            # Message was deleted, send a new one
                            self.heartbeat_message = await channel.send(embed=embed)
                    
                    # Log heartbeat update
                    metrics = self.get_system_metrics()
                    now = datetime.now(self.est_tz)
                    log_perfect_tree_section(
                        "Heartbeat Update",
                        [
                            ("status", "success"),
                            ("timestamp", now.strftime('%I:%M:%S %p EST')),
                            ("cpu", f"{metrics['cpu_percent']:.1f}%"),
                            ("memory", f"{metrics['memory_percent']:.1f}%"),
                            ("threads", str(metrics['threads'])),
                            ("next_update", f"in {self.update_interval // 3600} hour")
                        ],
                        emoji="💓"
                    )
                    
                except Exception as e:
                    log_error_with_traceback("Failed to update heartbeat", e)
                
                try:
                    await asyncio.sleep(self.update_interval)  # Update every hour
                except asyncio.CancelledError:
                    log_perfect_tree_section(
                        "Heartbeat Task",
                        [("status", "Shutting down")],
                        emoji="💤"
                    )
                    return
        except asyncio.CancelledError:
            log_perfect_tree_section(
                "Heartbeat Task",
                [("status", "Shutting down")],
                emoji="💤"
            )
            return 