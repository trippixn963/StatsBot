"""
Optimized MonitoringService for efficient system metrics collection and heartbeat generation.

This service provides real-time monitoring and heartbeat functionality with:
- Efficient system metrics collection with minimal overhead
- Memory-efficient log aggregation with circular buffers
- Optimized heartbeat embed generation with caching
- Proper resource management and cleanup
"""

import discord
import asyncio
import logging
import psutil
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Set, cast

from src.types.models import SystemMetrics, LogLevel, ServiceStatus, HeartbeatData, DailyStats
from src.utils.cache.cache_manager import CacheManager
from src.utils.cache.circular_buffer import CircularBuffer
from src.utils.logging.structured_logger import StructuredLogger, timed
from src.utils.error_handling.circuit_breaker import circuit_breaker
from src.core.exceptions import MonitoringError


class LogBuffer:
    """
    Memory-efficient log buffer using circular buffer implementation.
    
    This class captures logs for display in heartbeat messages using a
    fixed-size circular buffer to prevent memory leaks.
    
    Attributes:
        max_logs (int): Maximum number of logs to keep in memory
        buffer (CircularBuffer): Circular buffer for storing log entries
    """
    
    def __init__(self, max_logs: int = 100):
        """
        Initialize a new log buffer.
        
        Args:
            max_logs: Maximum number of logs to keep in memory
        """
        self.max_logs = max_logs
        self.buffer = CircularBuffer[Dict[str, Any]](max_logs)
        
    def add_log(self, log_entry: Dict[str, Any]) -> None:
        """
        Add a log entry to the buffer.
        
        Args:
            log_entry: Log entry to add
        """
        self.buffer.append(log_entry)
        
    def get_recent_logs(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent log entries.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of recent log entries
        """
        logs = self.buffer.to_list()
        return logs[-limit:] if logs else []


class MonitoringService:
    """
    Optimized monitoring service for efficient system metrics collection and heartbeat generation.
    
    This service provides:
    1. Efficient system metrics collection with minimal overhead
    2. Memory-efficient log aggregation with circular buffers
    3. Optimized heartbeat embed generation with caching
    4. Proper resource management and cleanup
    
    Attributes:
        bot (discord.Client): The Discord bot instance
        heartbeat_channel_id (int): Channel ID for heartbeat messages
        update_interval (int): Heartbeat update interval in seconds
        logger (StructuredLogger): Structured logger instance
        cache (CacheManager): Cache manager for optimized heartbeat generation
        log_buffer (LogBuffer): Memory-efficient log buffer
    """
    
    def __init__(
        self,
        bot: discord.Client,
        heartbeat_channel_id: int,
        update_interval: int = 3600,
        logger: Optional[StructuredLogger] = None,
        max_logs: int = 100,
        cache_ttl: int = 300
    ):
        """
        Initialize a new monitoring service.
        
        Args:
            bot: Discord bot instance
            heartbeat_channel_id: Channel ID for heartbeat messages
            update_interval: Heartbeat update interval in seconds
            logger: Structured logger instance (creates one if None)
            max_logs: Maximum number of logs to keep in memory
            cache_ttl: Cache TTL in seconds
        """
        self.bot = bot
        self.heartbeat_channel_id = heartbeat_channel_id
        self.update_interval = update_interval
        
        # Use provided logger or create a new one
        self.logger = logger or StructuredLogger("monitoring")
        
        # Initialize cache for optimized heartbeat generation
        self.cache = CacheManager(default_ttl=cache_ttl)
        
        # Initialize log buffer
        self.log_buffer = LogBuffer(max_logs=max_logs)
        
        # Initialize state variables
        self.heartbeat_message: Optional[discord.Message] = None
        self.start_time = datetime.now(timezone.utc)
        self.heartbeat_task: Optional[asyncio.Task] = None
        self._status = ServiceStatus.STOPPED
        
        # Set up log handler
        self._setup_log_handler()
        
        # Log initialization
        self.logger.info(
            "Monitoring service initialized",
            service="monitoring",
            heartbeat_channel=str(heartbeat_channel_id),
            update_interval=f"{update_interval // 60} minutes"
        )
        
    def _setup_log_handler(self) -> None:
        """Set up log handler to capture logs for heartbeat messages."""
        # Create custom log handler
        class MonitoringLogHandler(logging.Handler):
            def __init__(self, monitoring_service: 'MonitoringService'):
                super().__init__()
                self.monitoring_service = monitoring_service
                
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    self.monitoring_service.log_buffer.add_log({
                        'level': record.levelname,
                        'message': self.format(record),
                        'timestamp': datetime.fromtimestamp(record.created, timezone.utc)
                    })
                except Exception:
                    self.handleError(record)
        
        # Create and configure handler
        handler = MonitoringLogHandler(self)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)
        
        # Add handler to root logger
        logging.getLogger().addHandler(handler)
        
    @timed("get_system_metrics")
    def get_system_metrics(self) -> SystemMetrics:
        """
        Get current system metrics with minimal overhead.
        
        Returns:
            SystemMetrics object with current metrics
        """
        # Use cache if available
        cache_key = "system_metrics"
        cached_metrics = self.cache.get(cache_key)
        if cached_metrics:
            return cached_metrics
            
        # Get process info
        process = psutil.Process()
        
        try:
            # Get CPU usage (non-blocking)
            cpu_percent = process.cpu_percent(interval=None)
            
            # Get memory usage
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            
            # Get disk usage for logs directory
            logs_path = Path('logs')
            if logs_path.exists():
                disk_usage = psutil.disk_usage(str(logs_path))
                disk_percent = disk_usage.percent
            else:
                disk_percent = 0
                
            # Calculate uptime
            uptime_seconds = int((datetime.now(timezone.utc) - self.start_time).total_seconds())
            
            # Create metrics object
            metrics = SystemMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_percent=disk_percent,
                threads=process.num_threads(),
                uptime_seconds=uptime_seconds
            )
            
            # Cache metrics for short period
            self.cache.set(cache_key, metrics, ttl=30)  # Short TTL to ensure fresh data
            
            return metrics
        except Exception as e:
            self.logger.error(
                "Failed to collect system metrics",
                error=e,
                service="monitoring"
            )
            # Return default metrics in case of error
            return SystemMetrics(
                cpu_percent=0.0,
                memory_percent=0.0,
                disk_percent=0.0,
                threads=0,
                uptime_seconds=int((datetime.now(timezone.utc) - self.start_time).total_seconds())
            )
            
    def format_uptime(self) -> str:
        """
        Format the bot's uptime in a human-readable format.
        
        Returns:
            Formatted uptime string (e.g., "5d 3h 21m")
        """
        # Use cache if available
        cache_key = "formatted_uptime"
        cached_uptime = self.cache.get(cache_key)
        if cached_uptime:
            return cached_uptime
            
        # Calculate uptime
        now = datetime.now(timezone.utc)
        delta = now - self.start_time
        
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        seconds = delta.seconds % 60
        
        # Format parts
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes}m")
        if not parts:
            parts.append(f"{seconds}s")
            
        result = " ".join(parts)
        
        # Cache result
        self.cache.set(cache_key, result, ttl=60)  # Update every minute
        
        return result
        
    @timed("create_heartbeat_embed")
    async def create_heartbeat_embed(self) -> discord.Embed:
        """
        Create optimized heartbeat status embed with caching.
        
        Returns:
            Discord embed with heartbeat information
        """
        # Use cache if available and not expired
        cache_key = "heartbeat_embed"
        cached_embed_dict = self.cache.get(cache_key)
        if cached_embed_dict:
            return discord.Embed.from_dict(cached_embed_dict)
            
        # Get system metrics
        metrics = self.get_system_metrics()
        
        # Get today's member stats
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        stats = await self._get_daily_stats(today)
        
        # Create embed
        embed = discord.Embed(
            title="🤖 StatsBot Status",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Add uptime field
        embed.add_field(
            name="⏱️ Uptime",
            value=self.format_uptime(),
            inline=True
        )
        
        # Add system metrics
        embed.add_field(
            name="💻 System",
            value=f"CPU: {metrics.cpu_percent:.1f}%\nRAM: {metrics.memory_percent:.1f}%\nPing: {round(self.bot.latency * 1000)}ms",
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
        recent_logs = self.log_buffer.get_recent_logs(limit=3)
        if recent_logs:
            log_text = "\n".join(
                f"`{log['timestamp'].strftime('%I:%M:%S %p')}` {log['level']}: {log['message'][:100]}{'...' if len(log['message']) > 100 else ''}"
                for log in recent_logs
            )
            embed.add_field(
                name="📝 Recent Logs",
                value=log_text,
                inline=False
            )
        
        # Set footer with version and run ID
        embed.set_footer(text=f"StatsBot v1.0.0 • Run ID: {getattr(self.bot.stats_service, 'run_id', 'N/A')}")
        
        # Set thumbnail to bot's avatar
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            
        # Cache embed for future use
        self.cache.set(cache_key, embed.to_dict(), ttl=60)  # Short TTL to ensure fresh data
            
        return embed
        
    async def _get_daily_stats(self, date: str) -> DailyStats:
        """
        Get daily stats with caching.
        
        Args:
            date: Date string in YYYY-MM-DD format
            
        Returns:
            DailyStats for the specified date
        """
        # Use cache if available
        cache_key = f"daily_stats_{date}"
        cached_stats = self.cache.get(cache_key)
        if cached_stats:
            return cached_stats
            
        # Get stats from stats service
        try:
            stats = self.bot.stats_service.stats_tracker.get_daily_stats(date)
            
            # Cache stats
            self.cache.set(cache_key, stats, ttl=300)  # 5 minutes TTL
            
            return stats
        except Exception as e:
            self.logger.error(
                "Failed to get daily stats",
                error=e,
                service="monitoring",
                date=date
            )
            # Return empty stats in case of error
            return {
                'date': date,
                'joins': 0,
                'leaves': 0,
                'bans': 0,
                'unbans': 0,
                'net_change': 0,
                'join_list': [],
                'leave_list': [],
                'ban_list': [],
                'unban_list': []
            }
            
    @circuit_breaker(name="update_heartbeat", failure_threshold=3, reset_timeout=300)
    async def update_heartbeat(self) -> None:
        """
        Update the heartbeat message with current system metrics and activity.
        
        This method is protected by a circuit breaker to prevent repeated failures.
        """
        try:
            channel = self.bot.get_channel(self.heartbeat_channel_id)
            if not channel:
                self.logger.error(
                    f"Failed to get heartbeat channel {self.heartbeat_channel_id}",
                    service="monitoring"
                )
                return
                
            # Create heartbeat embed
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
            self.logger.info(
                "Heartbeat updated successfully",
                service="monitoring",
                cpu=f"{metrics.cpu_percent:.1f}%",
                memory=f"{metrics.memory_percent:.1f}%",
                threads=str(metrics.threads),
                next_update=f"in {self.update_interval // 60} minutes"
            )
            
            # Clear cache to ensure fresh data next time
            self.cache.invalidate("heartbeat_embed")
            
        except Exception as e:
            self.logger.error(
                "Failed to update heartbeat",
                error=e,
                service="monitoring"
            )
            raise MonitoringError("Failed to update heartbeat") from e
            
    async def _heartbeat_loop(self) -> None:
        """Background loop for periodic heartbeat updates."""
        await self.bot.wait_until_ready()
        
        try:
            while self._status == ServiceStatus.RUNNING:
                try:
                    await self.update_heartbeat()
                except Exception as e:
                    self.logger.error(
                        "Error in heartbeat loop",
                        error=e,
                        service="monitoring"
                    )
                    
                try:
                    await asyncio.sleep(self.update_interval)
                except asyncio.CancelledError:
                    self.logger.info(
                        "Heartbeat task cancelled",
                        service="monitoring"
                    )
                    break
        except asyncio.CancelledError:
            self.logger.info(
                "Heartbeat loop shutting down",
                service="monitoring"
            )
            
    async def start(self) -> None:
        """Start the monitoring service."""
        if self._status == ServiceStatus.RUNNING:
            return
            
        self._status = ServiceStatus.STARTING
        self.logger.info(
            "Starting monitoring service",
            service="monitoring"
        )
        
        # Start heartbeat task
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        self._status = ServiceStatus.RUNNING
        self.logger.info(
            "Monitoring service started",
            service="monitoring"
        )
        
    async def stop(self) -> None:
        """Stop the monitoring service and clean up resources."""
        if self._status != ServiceStatus.RUNNING:
            return
            
        self._status = ServiceStatus.STOPPING
        self.logger.info(
            "Stopping monitoring service",
            service="monitoring"
        )
        
        # Cancel heartbeat task
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None
            
        # Clear cache
        self.cache.clear()
        
        self._status = ServiceStatus.STOPPED
        self.logger.info(
            "Monitoring service stopped",
            service="monitoring"
        )
        
    @property
    def status(self) -> ServiceStatus:
        """Get current service status."""
        return self._status
        
    def add_log(self, log_entry: Dict[str, Any]) -> None:
        """
        Add a log entry to the log buffer.
        
        Args:
            log_entry: Log entry to add
        """
        self.log_buffer.add_log(log_entry)