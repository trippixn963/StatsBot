"""
Tests for the optimized StatsService implementation.

This module contains tests for the optimized StatsService with intelligent caching,
rate limit handling, and batch processing.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import discord
from datetime import datetime, timezone

from src.services.stats.service import OptimizedStatsService
from src.types.models import ChannelStats, EventType


class TestOptimizedStatsService(unittest.TestCase):
    """Test cases for the OptimizedStatsService."""
    
    def setUp(self):
        """Set up test environment."""
        # Mock Discord bot
        self.bot = MagicMock()
        self.bot.get_channel = MagicMock(return_value=MagicMock())
        
        # Create service instance
        self.service = OptimizedStatsService(self.bot)
        
        # Mock guild
        self.guild = MagicMock()
        self.guild.id = 123456789
        self.guild.member_count = 100
        
        # Mock members with statuses
        self.guild.members = [MagicMock() for _ in range(100)]
        for i, member in enumerate(self.guild.members):
            # Make 30% of members online
            member.status = discord.Status.online if i < 30 else discord.Status.offline
            
        # Mock guild.bans() to return an async iterator
        async def mock_bans():
            for i in range(5):
                yield MagicMock()
        self.guild.bans = mock_bans
        
        # Add guild to bot
        self.bot.guilds = [self.guild]
    
    async def test_update_member_count_with_change(self):
        """Test updating member count when it has changed."""
        # Ensure cache is empty
        self.service.cache.clear()
        
        # Mock channel
        channel = MagicMock()
        channel.name = "Members: 99"  # Different from current count
        channel.edit = AsyncMock()
        self.bot.get_channel.return_value = channel
        
        # Update member count
        result = await self.service.update_member_count(self.guild)
        
        # Verify results
        self.assertTrue(result)
        channel.edit.assert_called_once_with(name="Members: 100")
        
        # Check cache
        cache_key = self.service.CACHE_KEY_MEMBER_COUNT.format(guild_id=self.guild.id)
        self.assertEqual(self.service.cache.get(cache_key), 100)
    
    async def test_update_member_count_no_change(self):
        """Test updating member count when it hasn't changed."""
        # Set up cache with current count
        cache_key = self.service.CACHE_KEY_MEMBER_COUNT.format(guild_id=self.guild.id)
        self.service.cache.set(cache_key, 100)
        
        # Mock channel
        channel = MagicMock()
        channel.name = "Members: 100"  # Same as current count
        channel.edit = AsyncMock()
        self.bot.get_channel.return_value = channel
        
        # Update member count
        result = await self.service.update_member_count(self.guild)
        
        # Verify results
        self.assertFalse(result)
        channel.edit.assert_not_called()
    
    async def test_update_online_count_with_change(self):
        """Test updating online count when it has changed."""
        # Ensure cache is empty
        self.service.cache.clear()
        
        # Mock channel
        channel = MagicMock()
        channel.name = "Online: 20"  # Different from current count
        channel.edit = AsyncMock()
        self.bot.get_channel.return_value = channel
        
        # Update online count
        result = await self.service.update_online_count(self.guild)
        
        # Verify results
        self.assertTrue(result)
        channel.edit.assert_called_once_with(name="Online: 30")
        
        # Check cache
        cache_key = self.service.CACHE_KEY_ONLINE_COUNT.format(guild_id=self.guild.id)
        self.assertEqual(self.service.cache.get(cache_key), 30)
    
    async def test_update_ban_count_with_change(self):
        """Test updating ban count when it has changed."""
        # Ensure cache is empty
        self.service.cache.clear()
        
        # Mock channel
        channel = MagicMock()
        channel.name = "Bans: 3"  # Different from current count
        channel.edit = AsyncMock()
        self.bot.get_channel.return_value = channel
        
        # Update ban count
        result = await self.service.update_ban_count(self.guild)
        
        # Verify results
        self.assertTrue(result)
        channel.edit.assert_called_once_with(name="Bans: 5")
        
        # Check cache
        cache_key = self.service.CACHE_KEY_BAN_COUNT.format(guild_id=self.guild.id)
        self.assertEqual(self.service.cache.get(cache_key), 5)
    
    async def test_update_all_stats(self):
        """Test updating all stats concurrently."""
        # Mock individual update methods
        self.service.update_member_count = AsyncMock(return_value=True)
        self.service.update_online_count = AsyncMock(return_value=True)
        self.service.update_ban_count = AsyncMock(return_value=True)
        
        # Update all stats
        result = await self.service.update_all_stats(self.guild)
        
        # Verify results
        self.assertEqual(result, {
            "member_count": True,
            "online_count": True,
            "ban_count": True
        })
        
        # Verify all methods were called
        self.service.update_member_count.assert_called_once_with(self.guild)
        self.service.update_online_count.assert_called_once_with(self.guild)
        self.service.update_ban_count.assert_called_once_with(self.guild)
    
    async def test_get_cached_stats(self):
        """Test getting cached stats."""
        # Create stats object
        stats = ChannelStats(
            member_count=100,
            online_count=30,
            ban_count=5,
            last_updated=datetime.now(timezone.utc),
            guild_id=self.guild.id
        )
        
        # Cache the stats
        cache_key = self.service.CACHE_KEY_STATS.format(guild_id=self.guild.id)
        self.service.cache.set(cache_key, stats)
        
        # Get cached stats
        result = await self.service.get_cached_stats(self.guild.id)
        
        # Verify results
        self.assertEqual(result, stats)
    
    def test_record_member_event(self):
        """Test recording member events."""
        # Mock stats tracker
        self.service.stats_tracker.record_member_join = MagicMock()
        self.service.stats_tracker.record_member_leave = MagicMock()
        self.service.stats_tracker.record_member_ban = MagicMock()
        
        # Record events
        self.service.record_member_event(EventType.JOIN, 123, "user1")
        self.service.record_member_event(EventType.LEAVE, 456, "user2")
        self.service.record_member_event(EventType.BAN, 789, "user3")
        
        # Verify calls
        self.service.stats_tracker.record_member_join.assert_called_once_with(123, "user1")
        self.service.stats_tracker.record_member_leave.assert_called_once_with(456, "user2")
        self.service.stats_tracker.record_member_ban.assert_called_once_with(789, "user3")
    
    async def test_rate_limit_handling(self):
        """Test handling of rate limits."""
        # Mock channel
        channel = MagicMock()
        channel.name = "Members: 99"
        
        # Mock edit to raise rate limit error first, then succeed
        rate_limit_exception = discord.errors.HTTPException(
            response=MagicMock(status=429),
            message="You are being rate limited."
        )
        rate_limit_exception.retry_after = 1.0
        
        # Set up edit to fail once then succeed
        channel.edit = AsyncMock(side_effect=[rate_limit_exception, None])
        self.bot.get_channel.return_value = channel
        
        # Update member count (should retry and succeed)
        result = await self.service.update_member_count(self.guild)
        
        # Verify results
        self.assertTrue(result)
        self.assertEqual(channel.edit.call_count, 2)


if __name__ == '__main__':
    # Use asyncio to run async tests
    loop = asyncio.get_event_loop()
    unittest.main()