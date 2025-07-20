"""
Optimized StatsBot main class with improved lifecycle management.

This module contains the main bot class with proper startup and shutdown
sequencing, comprehensive error handling, and efficient event processing.
"""

import asyncio
import discord
import logging
import signal
import sys
import traceback
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Any, Tuple, Callable, Coroutine

from ..types.models import BotConfig, ServiceStatus, EventType, ConnectionState
from ..services.stats.service import OptimizedStatsService
from ..services.monitoring.service import MonitoringService
from ..services.presence.service import RichPresenceService
from ..utils.logging.structured_logger import StructuredLogger
from ..utils.async_utils.task_manager import TaskManager
from ..utils.async_utils.event_queue import EventQueue, EventBatcher
from ..utils.error_handling.connection_recovery import (
    ConnectionRecoveryManager, StateConsistencyManager, FallbackManager
)
from ..utils.performance.timing import async_timed, get_performance_metrics
from ..utils.performance.memory_monitor import MemoryMonitor
from .config import load_config
from .service_coordinator import ServiceCoordinator
from .exceptions import (
    StatsBotError, LifecycleError, DiscordAPIError, 
    ServiceError, AsyncOperationError, NetworkError
)


class OptimizedStatsBot(discord.Client):
    """
    Optimized version of the StatsBot with improved lifecycle management.
    
    This class provides:
    1. Proper startup and shutdown sequencing for all services
    2. Comprehensive error handling for bot initialization and event processing
    3. Efficient event processing without blocking the main event loop
    4. Automatic reconnection with progressive delays for Discord connection failures
    5. State consistency maintenance during connection interruptions
    6. Fallback mechanisms for critical operations when primary methods fail
    
    Attributes:
        config: Bot configuration object
        logger: Structured logger for the bot
        stats_service: Service for managing statistics
        monitoring_service: Service for system monitoring and heartbeats
        rich_presence_service: Service for managing bot presence
        task_manager: Manager for background tasks
        shutdown_event: Event to signal shutdown
        connection_recovery: Manager for handling connection recovery
        state_consistency: Manager for maintaining state consistency
        fallback_manager: Manager for fallback mechanisms
        _services_initialized: Flag indicating if services are initialized
    """
    
    def __init__(self, config: BotConfig):
        """
        Initialize the optimized StatsBot.
        
        Args:
            config: Bot configuration object
        """
        # Set up intents
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.presences = True
        
        # Set up reconnect options
        super().__init__(
            intents=intents,
            # Let our custom connection recovery handle reconnects
            reconnect=False
        )
        
        self.config = config
        self.logger = StructuredLogger("bot")
        
        # Initialize shutdown event
        self.shutdown_event = asyncio.Event()
        
        # Initialize task manager
        self.task_manager = TaskManager(logger=self.logger)
        
        # Initialize service coordinator
        self.service_coordinator = ServiceCoordinator(logger=self.logger)
        
        # Initialize connection recovery manager
        self.connection_recovery = ConnectionRecoveryManager(
            logger=self.logger,
            max_reconnect_attempts=20,
            initial_backoff=1.0,
            max_backoff=config.max_backoff or 300.0,
            jitter_factor=0.25
        )
        
        # Initialize state consistency manager
        self.state_consistency = StateConsistencyManager(logger=self.logger)
        
        # Initialize fallback manager
        self.fallback_manager = FallbackManager(logger=self.logger)
        
        # Initialize memory monitor
        self.memory_monitor = MemoryMonitor(
            warning_threshold=config.memory_warning_threshold,
            critical_threshold=config.memory_critical_threshold,
            check_interval=60,  # Check every minute
            logger=self.logger
        )
        
        # Services will be initialized in setup_hook
        self.stats_service: Optional[OptimizedStatsService] = None
        self.monitoring_service: Optional[MonitoringService] = None
        self.rich_presence_service: Optional[RichPresenceService] = None
        
        # Initialize event queue for member events
        self.member_event_queue = EventQueue(
            name="member_events",
            processor=self._process_member_events_batch,
            batch_size=10,
            flush_interval=2.0,
            logger=self.logger
        )
        
        # Initialize event batcher for channel updates
        self.channel_update_batcher = EventBatcher(
            name="channel_updates",
            processor=self._process_channel_updates_batch,
            max_batch_size=3,
            max_batch_age=5.0,
            logger=self.logger
        )
        
        # Track service initialization status
        self._services_initialized = False
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        # Set up connection recovery handlers
        self._setup_connection_recovery_handlers()
        
        # Register fallback methods
        self._register_fallbacks()
        
        self.logger.info(
            "OptimizedStatsBot initialized",
            bot_version="1.0.0",
            python_version=sys.version.split()[0],
            discord_py_version=discord.__version__
        )
    
    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        try:
            # Register signal handlers for graceful shutdown
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, self._handle_shutdown_signal)
                
            self.logger.debug("Signal handlers registered for graceful shutdown")
        except (NotImplementedError, AttributeError):
            # Windows doesn't support SIGTERM
            self.logger.warning(
                "Could not set up all signal handlers (this is normal on Windows)"
            )
    
    def _setup_connection_recovery_handlers(self) -> None:
        """Set up handlers for connection recovery events."""
        # Add disconnect handler
        self.connection_recovery.add_disconnect_handler(self._on_connection_lost)
        
        # Add reconnect handler
        self.connection_recovery.add_reconnect_handler(self._on_connection_restored)
        
        # Add reconnect attempt handler
        self.connection_recovery.add_reconnect_attempt_handler(self._on_reconnect_attempt)
        
        # Add max retries handler
        self.connection_recovery.add_max_retries_handler(self._on_max_reconnect_attempts)
        
        self.logger.debug("Connection recovery handlers registered")
    
    def _register_fallbacks(self) -> None:
        """Register fallback methods for critical operations."""
        # Register fallbacks for channel updates
        asyncio.create_task(self.fallback_manager.register_fallback(
            "update_member_count",
            self._fallback_update_member_count
        ))
        
        asyncio.create_task(self.fallback_manager.register_fallback(
            "update_online_count",
            self._fallback_update_online_count
        ))
        
        asyncio.create_task(self.fallback_manager.register_fallback(
            "update_ban_count",
            self._fallback_update_ban_count
        ))
        
        # Register fallbacks for daily stats
        asyncio.create_task(self.fallback_manager.register_fallback(
            "send_daily_stats",
            self._fallback_send_daily_stats
        ))
        
        self.logger.debug("Fallback methods registered")
    
    def _handle_shutdown_signal(self, signum, frame) -> None:
        """
        Handle shutdown signals (SIGINT, SIGTERM).
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_name = signal.Signals(signum).name
        self.logger.info(f"Received {signal_name}, initiating graceful shutdown")
        
        # Schedule the shutdown coroutine to run in the event loop
        if not self.is_closed():
            asyncio.create_task(self.close())
    
    async def setup_hook(self) -> None:
        """
        Set up the bot's services and background tasks.
        
        This method is called automatically by discord.py before the bot starts.
        It initializes all services and sets up background tasks.
        
        Raises:
            LifecycleError: If service initialization fails
        """
        try:
            self.logger.info("Setting up bot services and background tasks")
            
            # Initialize services
            await self._initialize_services()
            
            # Set up event handlers
            self._setup_event_handlers()
            
            self.logger.info("Bot setup completed successfully")
        except Exception as e:
            error_msg = f"Failed to set up bot: {str(e)}"
            self.logger.critical(error_msg, exc_info=True)
            raise LifecycleError(
                error_msg,
                phase="setup",
                component="bot"
            ) from e
    
    async def _initialize_services(self) -> None:
        """
        Initialize all bot services in the correct order.
        
        This method ensures services are initialized in the proper sequence,
        with dependencies satisfied first using the service coordinator.
        
        Raises:
            ServiceError: If service initialization fails
        """
        try:
            self.logger.info("Initializing bot services")
            
            # Initialize stats service first (other services depend on it)
            self.stats_service = OptimizedStatsService(
                bot=self,
                logger=self.logger
            )
            
            # Initialize monitoring service
            self.monitoring_service = MonitoringService(
                bot=self,
                heartbeat_channel_id=self.config.heartbeat_channel_id,
                update_interval=self.config.heartbeat_interval,
                logger=self.logger
            )
            
            # Initialize rich presence service
            self.rich_presence_service = RichPresenceService(
                bot=self,
                update_interval=self.config.presence_update_interval
            )
            
            # Register services with the coordinator with proper dependencies
            self.service_coordinator.register_service("stats", self.stats_service)
            self.service_coordinator.register_service("monitoring", self.monitoring_service, ["stats"])
            self.service_coordinator.register_service("presence", self.rich_presence_service, ["stats"])
            
            self.logger.info("All services registered with coordinator")
            self._services_initialized = True
            
        except Exception as e:
            error_msg = f"Failed to initialize services: {str(e)}"
            self.logger.critical(error_msg, exc_info=True)
            raise ServiceError(
                error_msg,
                service_name="initialization",
                operation="initialize_services"
            ) from e
    
    def _setup_event_handlers(self) -> None:
        """Set up event handlers for Discord events."""
        # Member events
        self.add_listener(self._on_member_join, "on_member_join")
        self.add_listener(self._on_member_remove, "on_member_remove")
        self.add_listener(self._on_member_ban, "on_member_ban")
        self.add_listener(self._on_member_unban, "on_member_unban")
        
        # Error handling
        self.add_listener(self._on_error, "on_error")
        
        self.logger.debug("Event handlers registered")
    
    @async_timed("start_services")
    async def start_services(self) -> None:
        """
        Start all services in the correct order using the service coordinator.
        
        This method starts each service in dependency order and schedules their background tasks.
        
        Raises:
            ServiceError: If service startup fails
        """
        if not self._services_initialized:
            raise ServiceError(
                "Cannot start services: Services not initialized",
                service_name="bot",
                operation="start_services"
            )
        
        try:
            self.logger.info("Starting bot services")
            
            # Start memory monitoring
            await self.memory_monitor.start_monitoring()
            
            # Start all services in dependency order using the coordinator
            await self.service_coordinator.start_services()
            
            # Start event queue and batcher
            await self.member_event_queue.start()
            await self.channel_update_batcher.start()
            
            # Register stats service daily task
            stats_task = await self.stats_service.start_daily_stats_task()
            self.task_manager.register_task(stats_task, "daily_stats")
            
            # Start performance metrics collection task
            perf_task = asyncio.create_task(self._collect_performance_metrics())
            self.task_manager.register_task(perf_task, "performance_metrics")
            
            self.logger.info("All services and event processors started successfully")
            
        except Exception as e:
            error_msg = f"Failed to start services: {str(e)}"
            self.logger.critical(error_msg, exc_info=True)
            raise ServiceError(
                error_msg,
                service_name="bot",
                operation="start_services"
            ) from e
    
    async def on_ready(self) -> None:
        """
        Handle bot ready event.
        
        This method is called when the bot has successfully connected to Discord.
        It starts all services and performs initial channel updates.
        """
        try:
            self.logger.info(
                f"Bot connected to Discord as {self.user.name}#{self.user.discriminator}",
                user_id=str(self.user.id)
            )
            
            # Notify connection recovery manager
            await self.connection_recovery.on_connect()
            
            # Start all services
            await self.start_services()
            
            # Execute any pending operations from previous connection
            await self.state_consistency.execute_pending_operations()
            
            # Perform initial channel updates if we have a guild
            if self.guilds:
                guild = self.guilds[0]
                self.logger.info(f"Connected to guild: {guild.name} (ID: {guild.id})")
                
                # Queue initial stats update through the batcher
                await self.channel_update_batcher.add("all", guild)
            else:
                self.logger.warning("Bot is not connected to any guilds")
        except Exception as e:
            self.logger.critical(f"Error in on_ready: {str(e)}", exc_info=True)
    
    async def on_disconnect(self) -> None:
        """
        Handle bot disconnect event.
        
        This method is called when the bot disconnects from Discord.
        It notifies the connection recovery manager to start reconnection.
        """
        # Notify connection recovery manager
        await self.connection_recovery.on_disconnect("Discord gateway disconnect")
    
    async def on_resumed(self) -> None:
        """
        Handle bot resume event.
        
        This method is called when the bot resumes a session after reconnecting.
        It notifies the connection recovery manager and restores state.
        """
        self.logger.info("Discord session resumed")
        
        # Notify connection recovery manager
        await self.connection_recovery.on_connect()
        
        # Execute any pending operations
        await self.state_consistency.execute_pending_operations()
    
    async def _on_connection_lost(self) -> None:
        """
        Handle connection lost event from connection recovery manager.
        
        This method is called when the connection recovery manager
        detects a connection loss. It saves state snapshots and
        notifies services.
        """
        self.logger.warning("Connection lost handler triggered")
        
        # Save state snapshots
        if self.stats_service:
            try:
                stats_state = await self.stats_service.get_state_snapshot()
                await self.state_consistency.save_state_snapshot("stats", stats_state)
            except Exception as e:
                self.logger.error(f"Error saving stats state snapshot: {str(e)}", exc_info=True)
        
        # Notify services about connection loss
        if self._services_initialized:
            try:
                for service_name, service in self.service_coordinator.services.items():
                    if hasattr(service, "on_connection_lost") and callable(service.on_connection_lost):
                        await service.on_connection_lost()
            except Exception as e:
                self.logger.error(f"Error notifying services about connection loss: {str(e)}", exc_info=True)
    
    async def _on_connection_restored(self) -> None:
        """
        Handle connection restored event from connection recovery manager.
        
        This method is called when the connection recovery manager
        successfully reconnects to Discord. It restores state and
        notifies services.
        """
        self.logger.info("Connection restored handler triggered")
        
        # Notify services about connection restoration
        if self._services_initialized:
            try:
                for service_name, service in self.service_coordinator.services.items():
                    if hasattr(service, "on_connection_restored") and callable(service.on_connection_restored):
                        await service.on_connection_restored()
            except Exception as e:
                self.logger.error(f"Error notifying services about connection restoration: {str(e)}", exc_info=True)
    
    async def _on_reconnect_attempt(self, attempt: int, delay: float) -> None:
        """
        Handle reconnect attempt event from connection recovery manager.
        
        This method is called when the connection recovery manager
        is about to attempt a reconnection.
        
        Args:
            attempt: Current attempt number
            delay: Delay before this attempt in seconds
        """
        self.logger.info(
            f"Reconnect attempt {attempt} scheduled in {delay:.2f} seconds",
            attempt=attempt,
            delay=delay
        )
        
        # Update presence to indicate reconnecting status if possible
        try:
            if self.rich_presence_service and not self.is_closed():
                await self.rich_presence_service.set_reconnecting_presence(attempt)
        except Exception as e:
            self.logger.error(f"Error updating presence during reconnect: {str(e)}", exc_info=True)
    
    async def _on_max_reconnect_attempts(self) -> None:
        """
        Handle max reconnect attempts event from connection recovery manager.
        
        This method is called when the connection recovery manager
        has reached the maximum number of reconnection attempts.
        """
        self.logger.critical(
            "Maximum reconnection attempts reached, bot will exit",
            max_attempts=self.connection_recovery.max_reconnect_attempts
        )
        
        # Save any pending data before exiting
        if self.stats_service:
            try:
                await self.stats_service.save_data()
                self.logger.info("Stats data saved before exit")
            except Exception as e:
                self.logger.error(f"Error saving stats data before exit: {str(e)}", exc_info=True)
        
        # Schedule shutdown
        asyncio.create_task(self.close())
    
    async def _fallback_update_member_count(self, guild: discord.Guild) -> None:
        """
        Fallback method for updating member count.
        
        This method is used when the primary update method fails.
        It uses a simplified approach with fewer features but higher reliability.
        
        Args:
            guild: Discord guild to update
        """
        if not self.stats_service:
            raise ServiceError("Stats service not initialized", service_name="stats")
            
        self.logger.info("Using fallback method for member count update")
        
        # Get channel ID from config
        channel_id = self.config.member_count_channel_id
        if not channel_id:
            raise ValueError("Member count channel ID not configured")
            
        # Get channel
        channel = self.get_channel(channel_id)
        if not channel:
            raise ValueError(f"Channel with ID {channel_id} not found")
            
        # Simple update with minimal processing
        try:
            member_count = guild.member_count
            await channel.edit(name=f"Members: {member_count}")
            self.logger.info(f"Fallback member count update successful: {member_count}")
        except Exception as e:
            self.logger.error(f"Fallback member count update failed: {str(e)}", exc_info=True)
            raise
    
    async def _fallback_update_online_count(self, guild: discord.Guild) -> None:
        """
        Fallback method for updating online count.
        
        This method is used when the primary update method fails.
        It uses a simplified approach with fewer features but higher reliability.
        
        Args:
            guild: Discord guild to update
        """
        if not self.stats_service:
            raise ServiceError("Stats service not initialized", service_name="stats")
            
        self.logger.info("Using fallback method for online count update")
        
        # Get channel ID from config
        channel_id = self.config.online_count_channel_id
        if not channel_id:
            raise ValueError("Online count channel ID not configured")
            
        # Get channel
        channel = self.get_channel(channel_id)
        if not channel:
            raise ValueError(f"Channel with ID {channel_id} not found")
            
        # Simple update with minimal processing
        try:
            # This is less accurate but more reliable than the primary method
            online_count = sum(1 for m in guild.members if m.status != discord.Status.offline)
            await channel.edit(name=f"Online: {online_count}")
            self.logger.info(f"Fallback online count update successful: {online_count}")
        except Exception as e:
            self.logger.error(f"Fallback online count update failed: {str(e)}", exc_info=True)
            raise
    
    async def _fallback_update_ban_count(self, guild: discord.Guild) -> None:
        """
        Fallback method for updating ban count.
        
        This method is used when the primary update method fails.
        It uses a simplified approach with fewer features but higher reliability.
        
        Args:
            guild: Discord guild to update
        """
        if not self.stats_service:
            raise ServiceError("Stats service not initialized", service_name="stats")
            
        self.logger.info("Using fallback method for ban count update")
        
        # Get channel ID from config
        channel_id = self.config.ban_count_channel_id
        if not channel_id:
            raise ValueError("Ban count channel ID not configured")
            
        # Get channel
        channel = self.get_channel(channel_id)
        if not channel:
            raise ValueError(f"Channel with ID {channel_id} not found")
            
        # Simple update with minimal processing
        try:
            # Use cached ban count if available
            ban_count = getattr(self.stats_service, "_cached_ban_count", 0)
            
            # If no cached value, try to get it (might fail if we don't have permissions)
            if ban_count == 0:
                try:
                    bans = await guild.bans()
                    ban_count = len(bans)
                except Exception:
                    # Use last known value or default to 0
                    ban_count = getattr(self.stats_service, "_cached_ban_count", 0)
            
            await channel.edit(name=f"Bans: {ban_count}")
            self.logger.info(f"Fallback ban count update successful: {ban_count}")
        except Exception as e:
            self.logger.error(f"Fallback ban count update failed: {str(e)}", exc_info=True)
            raise
    
    async def _fallback_send_daily_stats(self) -> None:
        """
        Fallback method for sending daily stats.
        
        This method is used when the primary daily stats method fails.
        It sends a simplified version of the daily stats with minimal formatting.
        """
        if not self.stats_service:
            raise ServiceError("Stats service not initialized", service_name="stats")
            
        self.logger.info("Using fallback method for daily stats")
        
        # Get channel ID from config
        channel_id = self.config.stats_channel_id
        if not channel_id:
            raise ValueError("Stats channel ID not configured")
            
        # Get channel
        channel = self.get_channel(channel_id)
        if not channel:
            raise ValueError(f"Channel with ID {channel_id} not found")
            
        # Simple update with minimal processing
        try:
            # Get basic stats data
            stats_data = await self.stats_service.get_daily_stats()
            
            # Create a simple message
            message = f"**Daily Stats Report (Fallback Mode)**\n\n"
            message += f"Date: {stats_data.get('date', 'Unknown')}\n"
            message += f"Joins: {stats_data.get('joins', 0)}\n"
            message += f"Leaves: {stats_data.get('leaves', 0)}\n"
            message += f"Bans: {stats_data.get('bans', 0)}\n"
            message += f"Net Change: {stats_data.get('net_change', 0)}\n\n"
            message += "*Note: This is a simplified report due to an error with the normal reporting system.*"
            
            await channel.send(message)
            self.logger.info("Fallback daily stats sent successfully")
        except Exception as e:
            self.logger.error(f"Fallback daily stats failed: {str(e)}", exc_info=True)
            raise
    
    async def _process_member_events_batch(self, events: List[Dict[str, Any]]) -> None:
        """
        Process a batch of member events.
        
        This method efficiently processes multiple member events in a single batch,
        reducing the number of database operations and API calls.
        
        Args:
            events: List of member event dictionaries
        """
        try:
            self.logger.debug(
                f"Processing batch of {len(events)} member events",
                batch_size=len(events)
            )
            
            # Group events by type for efficient processing
            joins = []
            leaves = []
            bans = []
            unbans = []
            
            for event in events:
                event_type = event["type"]
                if event_type == "join":
                    joins.append(event)
                elif event_type == "leave":
                    leaves.append(event)
                elif event_type == "ban":
                    bans.append(event)
                elif event_type == "unban":
                    unbans.append(event)
            
            # Process joins
            for event in joins:
                self.stats_service.record_member_join(event["id"], event["username"])
            
            # Process leaves
            for event in leaves:
                self.stats_service.record_member_leave(event["id"], event["username"])
            
            # Process bans
            for event in bans:
                self.stats_service.record_member_ban(event["id"], event["username"])
            
            # Update channels if needed
            if events:
                guild = events[0]["guild"]
                
                # Queue channel updates through the batcher
                if joins or leaves:
                    await self.channel_update_batcher.add("member_count", guild)
                
                if bans or unbans:
                    await self.channel_update_batcher.add("ban_count", guild)
                
        except Exception as e:
            self.logger.error(
                f"Error processing member events batch: {str(e)}",
                batch_size=len(events),
                exc_info=True
            )
    
    async def _process_channel_updates_batch(self, update_type: str, guilds: List[discord.Guild]) -> None:
        """
        Process a batch of channel updates of the same type.
        
        This method efficiently processes multiple channel updates in a single batch,
        reducing the number of API calls to Discord.
        
        Args:
            update_type: Type of update ("member_count", "online_count", "ban_count")
            guilds: List of guilds to update
        """
        try:
            # Deduplicate guilds (in case multiple events for the same guild were batched)
            unique_guilds = list({guild.id: guild for guild in guilds}.values())
            
            self.logger.debug(
                f"Processing batch of {update_type} updates for {len(unique_guilds)} guilds",
                update_type=update_type,
                guild_count=len(unique_guilds)
            )
            
            # Process updates based on type
            for guild in unique_guilds:
                if update_type == "member_count":
                    await self.stats_service.update_member_count(guild)
                elif update_type == "online_count":
                    await self.stats_service.update_online_count(guild)
                elif update_type == "ban_count":
                    await self.stats_service.update_ban_count(guild)
                elif update_type == "all":
                    await self.stats_service.update_all_stats(guild)
            
        except Exception as e:
            self.logger.error(
                f"Error processing {update_type} updates batch: {str(e)}",
                update_type=update_type,
                guild_count=len(guilds),
                exc_info=True
            )
    
    async def _on_member_join(self, member: discord.Member) -> None:
        """
        Handle member join event.
        
        Args:
            member: Discord member who joined
        """
        try:
            self.logger.info(
                f"Member joined: {member.name}#{member.discriminator}",
                member_id=str(member.id),
                guild_id=str(member.guild.id)
            )
            
            # Queue the event for batch processing
            await self.member_event_queue.enqueue({
                "type": "join",
                "id": member.id,
                "username": f"{member.name}#{member.discriminator}",
                "guild": member.guild,
                "timestamp": datetime.now(timezone.utc)
            })
            
        except Exception as e:
            self.logger.error(
                f"Error handling member join: {str(e)}",
                member_id=str(member.id),
                exc_info=True
            )
    
    async def _on_member_remove(self, member: discord.Member) -> None:
        """
        Handle member remove event.
        
        Args:
            member: Discord member who left
        """
        try:
            self.logger.info(
                f"Member left: {member.name}#{member.discriminator}",
                member_id=str(member.id),
                guild_id=str(member.guild.id)
            )
            
            # Queue the event for batch processing
            await self.member_event_queue.enqueue({
                "type": "leave",
                "id": member.id,
                "username": f"{member.name}#{member.discriminator}",
                "guild": member.guild,
                "timestamp": datetime.now(timezone.utc)
            })
            
        except Exception as e:
            self.logger.error(
                f"Error handling member remove: {str(e)}",
                member_id=str(member.id),
                exc_info=True
            )
    
    async def _on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        """
        Handle member ban event.
        
        Args:
            guild: Discord guild where the ban occurred
            user: Discord user who was banned
        """
        try:
            self.logger.info(
                f"Member banned: {user.name}#{user.discriminator}",
                user_id=str(user.id),
                guild_id=str(guild.id)
            )
            
            # Queue the event for batch processing
            await self.member_event_queue.enqueue({
                "type": "ban",
                "id": user.id,
                "username": f"{user.name}#{user.discriminator}",
                "guild": guild,
                "timestamp": datetime.now(timezone.utc)
            })
            
        except Exception as e:
            self.logger.error(
                f"Error handling member ban: {str(e)}",
                user_id=str(user.id),
                exc_info=True
            )
    
    async def _on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        """
        Handle member unban event.
        
        Args:
            guild: Discord guild where the unban occurred
            user: Discord user who was unbanned
        """
        try:
            self.logger.info(
                f"Member unbanned: {user.name}#{user.discriminator}",
                user_id=str(user.id),
                guild_id=str(guild.id)
            )
            
            # Queue the event for batch processing
            await self.member_event_queue.enqueue({
                "type": "unban",
                "id": user.id,
                "username": f"{user.name}#{user.discriminator}",
                "guild": guild,
                "timestamp": datetime.now(timezone.utc)
            })
            
        except Exception as e:
            self.logger.error(
                f"Error handling member unban: {str(e)}",
                user_id=str(user.id),
                exc_info=True
            )
    
    async def _on_error(self, event: str, *args, **kwargs) -> None:
        """
        Handle Discord event errors.
        
        Args:
            event: Name of the event that raised the error
            args: Event arguments
            kwargs: Event keyword arguments
        """
        error_type, error, error_traceback = sys.exc_info()
        
        # Format traceback
        traceback_str = "".join(traceback.format_exception(error_type, error, error_traceback))
        
        self.logger.error(
            f"Error in event {event}: {str(error)}",
            event=event,
            error_type=error_type.__name__ if error_type else "Unknown",
            traceback=traceback_str
        )
    
    async def close(self) -> None:
        """
        Clean shutdown of the bot.
        
        This method ensures all services are properly stopped in the correct order
        and resources are cleaned up before the bot disconnects from Discord.
        """
        if self.is_closed():
            return
            
        try:
            self.logger.info("Initiating bot shutdown sequence")
            
            # Set shutdown event
            self.shutdown_event.set()
            
            # Stop connection recovery manager
            try:
                await self.connection_recovery.shutdown()
                self.logger.info("Connection recovery manager stopped")
            except Exception as e:
                self.logger.error(f"Error stopping connection recovery manager: {str(e)}")
            
            # Stop event processors first
            try:
                await self.member_event_queue.stop()
                self.logger.info("Member event queue stopped")
            except Exception as e:
                self.logger.error(f"Error stopping member event queue: {str(e)}")
                
            try:
                await self.channel_update_batcher.stop()
                self.logger.info("Channel update batcher stopped")
            except Exception as e:
                self.logger.error(f"Error stopping channel update batcher: {str(e)}")
            
            # Stop services in dependency order using the coordinator
            if self._services_initialized:
                self.logger.info("Stopping bot services")
                try:
                    await self.service_coordinator.stop_services()
                    self.logger.info("All services stopped via coordinator")
                except Exception as e:
                    self.logger.error(f"Error during coordinated service shutdown: {str(e)}")
                    
                    # Fallback: try to save stats data directly if coordinator failed
                    if self.stats_service:
                        try:
                            await self.stats_service.save_data()
                            self.logger.info("Stats data saved (fallback)")
                        except Exception as e:
                            self.logger.error(f"Error saving stats data: {str(e)}")
            
            # Cancel all background tasks
            await self.task_manager.cancel_all_tasks()
            self.logger.info("All background tasks cancelled")
            
            # Clear state consistency manager
            try:
                await self.state_consistency.clear_state()
                self.logger.info("State consistency manager cleared")
            except Exception as e:
                self.logger.error(f"Error clearing state consistency manager: {str(e)}")
            
            # Call parent close method to disconnect from Discord
            self.logger.info("Disconnecting from Discord")
            await super().close()
            
            self.logger.info("Bot shutdown complete")
        except Exception as e:
            self.logger.critical(f"Error during shutdown: {str(e)}", exc_info=True)
            # Ensure we still call the parent close method
            await super().close()
    
    def run(self, *args, **kwargs) -> None:
        """
        Run the bot with error handling.
        
        This method overrides the parent run method to add comprehensive
        error handling and logging.
        
        Args:
            *args: Arguments to pass to the parent run method
            **kwargs: Keyword arguments to pass to the parent run method
        """
        try:
            self.logger.info("Starting bot")
            
            # Add reconnect=False to kwargs to disable discord.py's built-in reconnect
            # and use our custom connection recovery instead
            kwargs['reconnect'] = False
            
            super().run(self.config.bot_token, *args, **kwargs)
        except discord.LoginFailure:
            self.logger.critical(
                "Failed to login to Discord. Check your bot token.",
                exc_info=True
            )
            sys.exit(1)
        except discord.ConnectionClosed as e:
            # This should be handled by our connection recovery
            self.logger.critical(
                f"Discord connection closed unexpectedly: {str(e)}",
                code=e.code,
                reason=e.reason,
                exc_info=True
            )
            sys.exit(1)
        except discord.GatewayNotFound:
            self.logger.critical(
                "Discord gateway not found. Discord may be having issues.",
                exc_info=True
            )
            sys.exit(1)
        except discord.HTTPException as e:
            self.logger.critical(
                f"HTTP error occurred: {str(e)}",
                status=e.status,
                code=e.code,
                exc_info=True
            )
            sys.exit(1)
        except NetworkError as e:
            self.logger.critical(
                f"Network error: {str(e)}",
                exc_info=True
            )
            sys.exit(1)
        except Exception as e:
            self.logger.critical(
                f"Fatal error: {str(e)}",
                exc_info=True
            )
            sys.exit(1)
        finally:
            self.logger.info("Bot process terminated")