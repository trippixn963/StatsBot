"""
Pytest Configuration and Fixtures.

This module provides comprehensive test fixtures and configuration for
the StatsBot testing suite including Discord API mocking, async utilities,
and performance testing helpers.
"""

import asyncio
import os
import pytest
import tempfile
from pathlib import Path
from typing import Any, Dict, AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import discord
import discord.ext.test as dpytest

# Import local modules for testing
from src.utils.config_validator import ConfigValidator, EnvironmentType
from src.utils.performance import PerformanceMonitor
from src.utils.memory_optimizer import MemoryEfficientStats, RetentionPolicy
from src.services.presence.service import RichPresenceService

# Test configuration
TEST_CONFIG = {
    'BOT_TOKEN': 'MTxxxxxxxxx.xxxxxx.xxxxxxxxxxxxxxxxxxxxxxx',
    'MEMBER_COUNT_CHANNEL_ID': 1234567890123456789,
    'ONLINE_COUNT_CHANNEL_ID': 1234567890123456790,
    'BAN_COUNT_CHANNEL_ID': 1234567890123456791,
    'HEARTBEAT_CHANNEL_ID': 1234567890123456792,
    'STATS_CHANNEL_ID': 1234567890123456793,
    'GUILD_ID': 1234567890123456794
}

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def temp_config_file():
    """Create a temporary configuration file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        for key, value in TEST_CONFIG.items():
            f.write(f"{key}={value}\n")
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    os.unlink(temp_path)

@pytest.fixture
async def mock_bot():
    """Create a mock Discord bot for testing."""
    bot = MagicMock(spec=discord.Client)
    bot.user = MagicMock()
    bot.user.id = 123456789
    bot.user.name = "TestBot"
    bot.is_closed.return_value = False
    
    # Mock guild
    guild = MagicMock(spec=discord.Guild)
    guild.id = TEST_CONFIG['GUILD_ID']
    guild.name = "Test Guild"
    guild.member_count = 150
    guild.members = [MagicMock(spec=discord.Member) for _ in range(150)]
    
    # Configure member statuses
    for i, member in enumerate(guild.members):
        member.id = 1000000000000000000 + i
        member.name = f"TestUser{i}"
        member.status = discord.Status.online if i < 100 else discord.Status.offline
    
    # Mock channels
    channels = {}
    for key in ['MEMBER_COUNT_CHANNEL_ID', 'ONLINE_COUNT_CHANNEL_ID', 'BAN_COUNT_CHANNEL_ID',
                'HEARTBEAT_CHANNEL_ID', 'STATS_CHANNEL_ID']:
        channel_id = TEST_CONFIG[key]
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = channel_id
        channel.name = f"test-channel-{key.lower().replace('_', '-')}"
        channel.edit = AsyncMock()
        channels[channel_id] = channel
    
    # Mock ban list
    ban_entries = []
    for i in range(5):
        ban_entry = MagicMock()
        ban_entry.user = MagicMock()
        ban_entry.user.id = 2000000000000000000 + i
        ban_entry.user.name = f"BannedUser{i}"
        ban_entries.append(ban_entry)
    
    guild.bans.return_value = AsyncMock()
    guild.bans.return_value.__aiter__ = AsyncMock(return_value=iter(ban_entries))
    
    bot.guilds = [guild]
    bot.get_channel = lambda channel_id: channels.get(channel_id)
    bot.wait_until_ready = AsyncMock()
    bot.change_presence = AsyncMock()
    
    return bot

@pytest.fixture
async def mock_discord_py():
    """Mock the discord.py library for testing."""
    with patch('discord.Client') as mock_client:
        # Setup dpytest for discord.py testing
        await dpytest.empty_queue()
        yield mock_client

@pytest.fixture
def performance_monitor():
    """Create a performance monitor instance for testing."""
    monitor = PerformanceMonitor(
        max_metrics=100,
        memory_threshold_mb=50.0,
        critical_memory_threshold_mb=100.0,
        slow_operation_threshold_ms=500.0
    )
    yield monitor
    monitor.shutdown()

@pytest.fixture
def memory_stats():
    """Create a memory-efficient stats instance for testing."""
    retention_policy = RetentionPolicy(
        max_age_hours=1,
        max_items=100,
        cleanup_interval_minutes=1,
        emergency_cleanup_threshold_mb=50.0
    )
    return MemoryEfficientStats(retention_policy)

@pytest.fixture
def config_validator():
    """Create a configuration validator for testing."""
    return ConfigValidator(environment=EnvironmentType.TESTING)

@pytest.fixture
async def rich_presence_service(mock_bot):
    """Create a rich presence service for testing."""
    from src.services.presence.types import PresenceType
    
    service = RichPresenceService(
        bot=mock_bot,
        update_interval=1,  # Short interval for testing
        presence_types=[
            PresenceType.MEMBER_COUNT,
            PresenceType.ONLINE_COUNT,
            PresenceType.BAN_COUNT
        ],
        max_errors=3
    )
    return service

@pytest.fixture
def sample_member_data():
    """Generate sample member data for testing."""
    return [
        {
            'id': 1000000000000000000 + i,
            'username': f'TestUser{i}',
            'discriminator': f'{1000 + i:04d}',
            'joined_at': datetime.now(timezone.utc),
            'status': 'online' if i < 70 else 'offline'
        }
        for i in range(100)
    ]

@pytest.fixture
def sample_performance_data():
    """Generate sample performance metrics for testing."""
    return [
        {
            'name': 'api_call_duration',
            'value': 150.5 + i * 10,
            'timestamp': datetime.now(timezone.utc),
            'category': 'discord_api'
        }
        for i in range(50)
    ]

@pytest.fixture(autouse=True)
def cleanup_environment():
    """Automatically clean up environment after each test."""
    # Store original environment
    original_env = dict(os.environ)
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)

@pytest.fixture
def mock_file_system():
    """Mock file system operations for testing."""
    with patch('pathlib.Path.exists'), \
         patch('pathlib.Path.mkdir'), \
         patch('builtins.open'), \
         patch('json.dump'), \
         patch('json.load'):
        yield

class AsyncContextManager:
    """Helper for testing async context managers."""
    
    def __init__(self, async_func):
        self.async_func = async_func
    
    async def __aenter__(self):
        return await self.async_func()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

@pytest.fixture
def async_context_manager():
    """Create async context manager helper for testing."""
    return AsyncContextManager

# Pytest markers
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as a performance test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "discord_api: mark test as requiring Discord API mocking"
    )

# Test collection hooks
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers."""
    for item in items:
        # Add markers based on test file location
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "performance" in str(item.fspath):
            item.add_marker(pytest.mark.performance)
        
        # Mark tests that use Discord fixtures
        if any(fixture in item.fixturenames for fixture in ['mock_bot', 'mock_discord_py', 'rich_presence_service']):
            item.add_marker(pytest.mark.discord_api)

# Async test helpers
def run_async(coro):
    """Helper to run async functions in sync tests."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)

# Custom assertions
def assert_performance_within_threshold(duration_ms, expected_ms, tolerance=0.1):
    """Assert that performance is within acceptable threshold."""
    tolerance_ms = expected_ms * tolerance
    assert abs(duration_ms - expected_ms) <= tolerance_ms, \
        f"Performance outside threshold: {duration_ms}ms vs {expected_ms}ms ±{tolerance_ms}ms"

def assert_memory_usage_reasonable(memory_mb, max_expected_mb):
    """Assert that memory usage is reasonable."""
    assert memory_mb <= max_expected_mb, \
        f"Memory usage too high: {memory_mb}MB > {max_expected_mb}MB"

# Export helper functions
__all__ = [
    'run_async',
    'assert_performance_within_threshold', 
    'assert_memory_usage_reasonable',
    'AsyncContextManager'
] 