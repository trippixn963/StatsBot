"""
Unit tests for the optimized StatsBot main class.

This module tests the lifecycle management, error handling, and event processing
of the OptimizedStatsBot class.
"""

import pytest
import asyncio
import discord
from unittest.mock import AsyncMock, MagicMock, patch, call, PropertyMock
from datetime import datetime, timezone

from src.core.bot import OptimizedStatsBot
from src.types.models import BotConfig, ServiceStatus
from src.core.exceptions import LifecycleError, ServiceError


@pytest.fixture
def mock_config():
    """Create a mock bot configuration."""
    config = MagicMock(spec=BotConfig)
    config.bot_token = "mock_token"
    config.member_count_channel_id = 123
    config.online_count_channel_id = 456
    config.ban_count_channel_id = 789
    config.heartbeat_channel_id = 101112
    config.stats_channel_id = 131415
    config.heartbeat_interval = 3600
    config.presence_update_interval = 300
    return config


@pytest.fixture
def mock_logger():
    """Create a mock structured logger."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.debug = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    logger.critical = MagicMock()
    return logger


@pytest.fixture
def mock_stats_service():
    """Create a mock stats service."""
    service = AsyncMock()
    service.start_daily_stats_task = AsyncMock(return_value=asyncio.Future())
    service.update_all_stats = AsyncMock()
    service.update_member_count = AsyncMock()
    service.update_ban_count = AsyncMock()
    service.save_data = AsyncMock()
    service.record_member_join = MagicMock()
    service.record_member_leave = MagicMock()
    service.record_member_ban = MagicMock()
    return service


@pytest.fixture
def mock_monitoring_service():
    """Create a mock monitoring service."""
    service = AsyncMock()
    service.start = AsyncMock()
    service.stop = AsyncMock()
    service.status = ServiceStatus.RUNNING
    return service


@pytest.fixture
def mock_presence_service():
    """Create a mock rich presence service."""
    service = AsyncMock()
    service.start = AsyncMock()
    service.stop = AsyncMock()
    service.status = ServiceStatus.RUNNING
    return service


@pytest.fixture
def mock_task_manager():
    """Create a mock task manager."""
    manager = MagicMock()
    manager.create_task = MagicMock()
    manager.register_task = MagicMock()
    manager.cancel_all_tasks = AsyncMock()
    return manager


@pytest.fixture
def bot(mock_config, mock_logger, mock_stats_service, mock_monitoring_service, 
        mock_presence_service, mock_task_manager):
    """Create a bot instance with mocked dependencies."""
    with patch('src.core.bot.StructuredLogger', return_value=mock_logger), \
         patch('src.core.bot.TaskManager', return_value=mock_task_manager), \
         patch('src.core.bot.OptimizedStatsService', return_value=mock_stats_service), \
         patch('src.core.bot.MonitoringService', return_value=mock_monitoring_service), \
         patch('src.core.bot.RichPresenceService', return_value=mock_presence_service), \
         patch('src.core.bot.discord.Client.__init__', return_value=None), \
         patch('src.core.bot.signal.signal'):
        
        bot = OptimizedStatsBot(mock_config)
        bot.stats_service = mock_stats_service
        bot.monitoring_service = mock_monitoring_service
        bot.rich_presence_service = mock_presence_service
        bot.task_manager = mock_task_manager
        bot._services_initialized = True
        
        # Mock the user property
        mock_user = MagicMock()
        mock_user.name = "TestBot"
        mock_user.discriminator = "1234"
        mock_user.id = 987654321
        type(bot).user = PropertyMock(return_value=mock_user)
        
        return bot


@pytest.mark.asyncio
async def test_setup_hook(bot, mock_logger):
    """Test the setup_hook method initializes services correctly."""
    # Mock the internal methods
    bot._initialize_services = AsyncMock()
    bot._setup_event_handlers = MagicMock()
    
    # Call setup_hook
    await bot.setup_hook()
    
    # Verify method calls
    bot._initialize_services.assert_called_once()
    bot._setup_event_handlers.assert_called_once()
    mock_logger.info.assert_any_call("Setting up bot services and background tasks")
    mock_logger.info.assert_any_call("Bot setup completed successfully")


@pytest.mark.asyncio
async def test_setup_hook_error(bot, mock_logger):
    """Test setup_hook handles errors correctly."""
    # Mock the internal methods to raise an exception
    bot._initialize_services = AsyncMock(side_effect=Exception("Test error"))
    
    # Call setup_hook and expect an exception
    with pytest.raises(LifecycleError):
        await bot.setup_hook()
    
    # Verify error logging
    mock_logger.critical.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_services(bot, mock_logger, mock_stats_service, 
                                  mock_monitoring_service, mock_presence_service):
    """Test service initialization."""
    # Reset the initialization flag
    bot._services_initialized = False
    
    # Call the method directly (bypassing setup_hook)
    with patch('src.core.bot.OptimizedStatsService', return_value=mock_stats_service), \
         patch('src.core.bot.MonitoringService', return_value=mock_monitoring_service), \
         patch('src.core.bot.RichPresenceService', return_value=mock_presence_service):
        
        await bot._initialize_services()
    
    # Verify services were initialized
    assert bot._services_initialized is True
    mock_logger.info.assert_any_call("Initializing bot services")
    mock_logger.info.assert_any_call("Stats service initialized")
    mock_logger.info.assert_any_call("Monitoring service initialized")
    mock_logger.info.assert_any_call("Rich presence service initialized")


@pytest.mark.asyncio
async def test_start_services(bot, mock_logger, mock_stats_service, 
                             mock_monitoring_service, mock_presence_service,
                             mock_task_manager):
    """Test starting all services."""
    # Call the method
    await bot.start_services()
    
    # Verify service start methods were called
    mock_monitoring_service.start.assert_called_once()
    mock_stats_service.start_daily_stats_task.assert_called_once()
    mock_task_manager.register_task.assert_called()
    
    # Verify rich presence service was started
    assert mock_task_manager.register_task.call_count >= 1
    mock_logger.info.assert_any_call("Starting bot services")
    mock_logger.info.assert_any_call("All services started successfully")


@pytest.mark.asyncio
async def test_start_services_error(bot, mock_logger, mock_monitoring_service):
    """Test error handling when starting services."""
    # Make monitoring service raise an exception
    mock_monitoring_service.start = AsyncMock(side_effect=Exception("Test error"))
    
    # Call the method and expect an exception
    with pytest.raises(ServiceError):
        await bot.start_services()
    
    # Verify error logging
    mock_logger.critical.assert_called_once()


@pytest.mark.asyncio
async def test_on_ready(bot, mock_logger, mock_stats_service, mock_task_manager):
    """Test on_ready event handler."""
    # Mock the start_services method
    bot.start_services = AsyncMock()
    
    # Create a mock guild
    mock_guild = MagicMock()
    mock_guild.name = "Test Guild"
    mock_guild.id = 123456789
    type(bot).guilds = PropertyMock(return_value=[mock_guild])
    
    # Call on_ready
    await bot.on_ready()
    
    # Verify method calls
    bot.start_services.assert_called_once()
    mock_task_manager.create_task.assert_called_once()
    mock_logger.info.assert_any_call(
        f"Bot connected to Discord as {bot.user.name}#{bot.user.discriminator}",
        user_id=str(bot.user.id)
    )


@pytest.mark.asyncio
async def test_on_member_join(bot, mock_stats_service, mock_task_manager):
    """Test member join event handler."""
    # Create a mock member
    mock_member = MagicMock()
    mock_member.name = "TestUser"
    mock_member.discriminator = "5678"
    mock_member.id = 123456
    mock_member.guild.id = 789012
    
    # Call the event handler
    await bot._on_member_join(mock_member)
    
    # Verify method calls
    mock_stats_service.record_member_join.assert_called_once_with(
        mock_member.id, f"{mock_member.name}#{mock_member.discriminator}"
    )
    mock_task_manager.create_task.assert_called_once()


@pytest.mark.asyncio
async def test_on_member_remove(bot, mock_stats_service, mock_task_manager):
    """Test member remove event handler."""
    # Create a mock member
    mock_member = MagicMock()
    mock_member.name = "TestUser"
    mock_member.discriminator = "5678"
    mock_member.id = 123456
    mock_member.guild.id = 789012
    
    # Call the event handler
    await bot._on_member_remove(mock_member)
    
    # Verify method calls
    mock_stats_service.record_member_leave.assert_called_once_with(
        mock_member.id, f"{mock_member.name}#{mock_member.discriminator}"
    )
    mock_task_manager.create_task.assert_called_once()


@pytest.mark.asyncio
async def test_on_member_ban(bot, mock_stats_service, mock_task_manager):
    """Test member ban event handler."""
    # Create mock guild and user
    mock_guild = MagicMock()
    mock_guild.id = 789012
    
    mock_user = MagicMock()
    mock_user.name = "TestUser"
    mock_user.discriminator = "5678"
    mock_user.id = 123456
    
    # Call the event handler
    await bot._on_member_ban(mock_guild, mock_user)
    
    # Verify method calls
    mock_stats_service.record_member_ban.assert_called_once_with(
        mock_user.id, f"{mock_user.name}#{mock_user.discriminator}"
    )
    mock_task_manager.create_task.assert_called_once()


@pytest.mark.asyncio
async def test_close(bot, mock_logger, mock_stats_service, 
                    mock_monitoring_service, mock_presence_service,
                    mock_task_manager):
    """Test graceful shutdown sequence."""
    # Mock is_closed method
    bot.is_closed = MagicMock(return_value=False)
    
    # Mock the parent close method
    with patch('src.core.bot.discord.Client.close', new_callable=AsyncMock) as mock_close:
        # Call close
        await bot.close()
        
        # Verify shutdown sequence
        assert bot.shutdown_event.is_set()
        mock_presence_service.stop.assert_called_once()
        mock_monitoring_service.stop.assert_called_once()
        mock_stats_service.save_data.assert_called_once()
        mock_task_manager.cancel_all_tasks.assert_called_once()
        mock_close.assert_called_once()
        
        # Verify logging
        mock_logger.info.assert_any_call("Initiating bot shutdown sequence")
        mock_logger.info.assert_any_call("Stopping bot services")
        mock_logger.info.assert_any_call("Rich presence service stopped")
        mock_logger.info.assert_any_call("Monitoring service stopped")
        mock_logger.info.assert_any_call("Stats data saved")
        mock_logger.info.assert_any_call("All background tasks cancelled")
        mock_logger.info.assert_any_call("Disconnecting from Discord")
        mock_logger.info.assert_any_call("Bot shutdown complete")


@pytest.mark.asyncio
async def test_close_already_closed(bot, mock_task_manager):
    """Test close method when bot is already closed."""
    # Mock is_closed method to return True
    bot.is_closed = MagicMock(return_value=True)
    
    # Call close
    await bot.close()
    
    # Verify no actions were taken
    mock_task_manager.cancel_all_tasks.assert_not_called()


@pytest.mark.asyncio
async def test_close_with_errors(bot, mock_logger, mock_stats_service, 
                                mock_monitoring_service, mock_presence_service):
    """Test close method handles errors gracefully."""
    # Mock is_closed method
    bot.is_closed = MagicMock(return_value=False)
    
    # Make services raise exceptions
    mock_presence_service.stop = AsyncMock(side_effect=Exception("Presence error"))
    mock_monitoring_service.stop = AsyncMock(side_effect=Exception("Monitoring error"))
    mock_stats_service.save_data = AsyncMock(side_effect=Exception("Stats error"))
    
    # Mock the parent close method
    with patch('src.core.bot.discord.Client.close', new_callable=AsyncMock) as mock_close:
        # Call close
        await bot.close()
        
        # Verify parent close was still called despite errors
        mock_close.assert_called_once()
        
        # Verify error logging
        mock_logger.error.assert_any_call("Error stopping rich presence service: Presence error")
        mock_logger.error.assert_any_call("Error stopping monitoring service: Monitoring error")
        mock_logger.error.assert_any_call("Error saving stats data: Stats error")


def test_run(bot, mock_config):
    """Test run method with error handling."""
    # Mock the parent run method
    with patch('src.core.bot.discord.Client.run') as mock_run:
        # Call run
        bot.run()
        
        # Verify parent run was called with the token
        mock_run.assert_called_once_with(mock_config.bot_token)


def test_run_login_failure(bot, mock_logger):
    """Test run method handles login failures."""
    # Mock the parent run method to raise LoginFailure
    with patch('src.core.bot.discord.Client.run', 
              side_effect=discord.LoginFailure("Invalid token")), \
         patch('src.core.bot.sys.exit') as mock_exit:
        
        # Call run
        bot.run()
        
        # Verify error logging and exit
        mock_logger.critical.assert_called_once()
        mock_exit.assert_called_once_with(1)


def test_run_general_error(bot, mock_logger):
    """Test run method handles general errors."""
    # Mock the parent run method to raise a general exception
    with patch('src.core.bot.discord.Client.run', 
              side_effect=Exception("General error")), \
         patch('src.core.bot.sys.exit') as mock_exit:
        
        # Call run
        bot.run()
        
        # Verify error logging and exit
        mock_logger.critical.assert_called_once()
        mock_exit.assert_called_once_with(1)


if __name__ == "__main__":
    pytest.main(["-xvs", "test_core_bot.py"])