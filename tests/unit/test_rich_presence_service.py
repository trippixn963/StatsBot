"""
Tests for the enhanced RichPresenceService.

This module contains unit tests for the RichPresenceService,
focusing on presence change detection, error handling, and caching.
"""

import pytest
import asyncio
import discord
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.presence.service import RichPresenceService
from src.core.exceptions import DiscordAPIError
from src.types.models import ServiceStatus


class TestRichPresenceService:
    """Test suite for the RichPresenceService."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create a mock Discord bot client."""
        bot = MagicMock()
        bot.change_presence = AsyncMock()
        bot.wait_until_ready = AsyncMock()
        bot.is_closed = MagicMock(return_value=False)
        
        # Create a mock guild
        guild = MagicMock()
        guild.id = 123456789
        guild.members = [MagicMock() for _ in range(100)]
        guild.bans = AsyncMock(return_value=AsyncMock())
        
        # Set up online members
        for i, member in enumerate(guild.members):
            member.status = discord.Status.online if i < 50 else discord.Status.offline
        
        # Set up ban list
        ban_entries = [MagicMock() for _ in range(5)]
        guild.bans.return_value.__aiter__.return_value = ban_entries
        
        # Add guild to bot
        bot.guilds = [guild]
        
        return bot
    
    @pytest.fixture
    def service(self, mock_bot):
        """Create a RichPresenceService instance with a mock bot."""
        return RichPresenceService(mock_bot, update_interval=60)
    
    @pytest.mark.asyncio
    async def test_update_presence_member_count(self, service):
        """Test updating presence with member count."""
        # Set current index to member_count
        service.current_index = 0  # member_count
        
        # Call update_presence
        await service.update_presence()
        
        # Verify change_presence was called with correct activity
        service.bot.change_presence.assert_called_once()
        call_args = service.bot.change_presence.call_args[1]
        
        assert call_args['status'] == discord.Status.online
        assert isinstance(call_args['activity'], discord.Activity)
        assert call_args['activity'].type == discord.ActivityType.watching
        assert "100 members" in call_args['activity'].name
    
    @pytest.mark.asyncio
    async def test_update_presence_online_count(self, service):
        """Test updating presence with online count."""
        # Set current index to online_count
        service.current_index = 1  # online_count
        
        # Call update_presence
        await service.update_presence()
        
        # Verify change_presence was called with correct activity
        service.bot.change_presence.assert_called_once()
        call_args = service.bot.change_presence.call_args[1]
        
        assert call_args['status'] == discord.Status.online
        assert isinstance(call_args['activity'], discord.Activity)
        assert call_args['activity'].type == discord.ActivityType.watching
        assert "50 online" in call_args['activity'].name
    
    @pytest.mark.asyncio
    async def test_update_presence_ban_count(self, service):
        """Test updating presence with ban count."""
        # Set current index to ban_count
        service.current_index = 2  # ban_count
        
        # Set up ban list to return a list directly for testing
        ban_entries = [MagicMock() for _ in range(5)]
        mock_ban_result = AsyncMock()
        mock_ban_result.__iter__ = lambda _: iter(ban_entries)
        service.bot.guilds[0].bans = AsyncMock(return_value=mock_ban_result)
        
        # Call update_presence
        await service.update_presence()
        
        # Verify change_presence was called with correct activity
        service.bot.change_presence.assert_called_once()
        call_args = service.bot.change_presence.call_args[1]
        
        assert call_args['status'] == discord.Status.online
        assert isinstance(call_args['activity'], discord.Activity)
        assert call_args['activity'].type == discord.ActivityType.watching
        assert "5 bans" in call_args['activity'].name
    
    @pytest.mark.asyncio
    async def test_presence_change_detection(self, service):
        """Test that identical presence updates are skipped."""
        # Test directly with _update_presence_with_retry
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="👥 100 members"
        )
        
        # First call should update presence
        await service._update_presence_with_retry(activity)
        assert service.bot.change_presence.call_count == 1
        
        # Reset mock to clear call history
        service.bot.change_presence.reset_mock()
        
        # Second call with same activity should skip API call
        await service._update_presence_with_retry(activity)
        assert service.bot.change_presence.call_count == 0
        
        # Different activity should trigger update
        new_activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="🟢 50 online"
        )
        await service._update_presence_with_retry(new_activity)
        assert service.bot.change_presence.call_count == 1
    
    @pytest.mark.asyncio
    async def test_caching(self, service):
        """Test that counts are cached and reused."""
        # Test _get_member_count directly
        guild_id = service.bot.guilds[0].id
        
        # First call should get and cache the count
        count1 = await service._get_member_count(service.bot.guilds[0])
        assert count1 == 100  # Initial mock has 100 members
        
        # Modify the guild member count
        service.bot.guilds[0].members = [MagicMock() for _ in range(200)]
        
        # Second call should return cached value
        count2 = await service._get_member_count(service.bot.guilds[0])
        assert count2 == 100  # Should still be 100 from cache
        
        # Invalidate cache
        service.invalidate_cache(guild_id)
        
        # Third call should get fresh count
        count3 = await service._get_member_count(service.bot.guilds[0])
        assert count3 == 200  # Should be 200 after cache invalidation
    
    @pytest.mark.asyncio
    async def test_error_handling(self, service):
        """Test error handling during presence update."""
        # Make change_presence raise an exception
        service.bot.change_presence.side_effect = discord.HTTPException(
            response=MagicMock(), message="Rate limited"
        )
        
        # Set current index to member_count
        service.current_index = 0  # member_count
        
        # Call _update_presence_with_retry directly to test error handling
        with pytest.raises(DiscordAPIError):
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=f"👥 100 members"
            )
            await service._update_presence_with_retry(activity)
        
        # Verify change_presence was called
        assert service.bot.change_presence.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_service_lifecycle(self, service):
        """Test service start and stop lifecycle."""
        # Mock asyncio.sleep to avoid waiting
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Set up is_closed to return True after first loop iteration
            service.bot.is_closed.side_effect = [False, True]
            
            # Start service (should run one loop iteration then exit)
            await service.start()
            
            # Verify service went through correct status transitions
            assert service.status == ServiceStatus.RUNNING
            
            # Verify bot.wait_until_ready was called
            service.bot.wait_until_ready.assert_called_once()
            
            # Verify update_presence was called at least once
            assert service.bot.change_presence.call_count >= 1
            
            # Stop service
            await service.stop()
            
            # Verify service is stopped
            assert service.status == ServiceStatus.STOPPED
    
    @pytest.mark.asyncio
    async def test_ban_count_permission_error(self, service):
        """Test handling of permission errors when getting ban count."""
        # Make bans raise a Forbidden exception
        service.bot.guilds[0].bans.side_effect = discord.Forbidden(
            response=MagicMock(), message="Missing permissions"
        )
        
        # Set current index to ban_count
        service.current_index = 2  # ban_count
        
        # Call update_presence - should handle the exception
        await service.update_presence()
        
        # Verify change_presence was called with 0 bans
        call_args = service.bot.change_presence.call_args[1]
        assert "0 bans" in call_args['activity'].name
    
    def test_invalidate_cache(self, service):
        """Test cache invalidation."""
        # Set some cache values
        service.cache.set(f"member_count:{service.bot.guilds[0].id}", 100)
        service.cache.set(f"online_count:{service.bot.guilds[0].id}", 50)
        service.cache.set(f"ban_count:{service.bot.guilds[0].id}", 5)
        
        # Verify cache has values
        assert service.cache.get(f"member_count:{service.bot.guilds[0].id}") == 100
        
        # Invalidate specific guild cache
        service.invalidate_cache(service.bot.guilds[0].id)
        
        # Verify cache is empty
        assert service.cache.get(f"member_count:{service.bot.guilds[0].id}") is None
        assert service.cache.get(f"online_count:{service.bot.guilds[0].id}") is None
        assert service.cache.get(f"ban_count:{service.bot.guilds[0].id}") is None
        
        # Set values again
        service.cache.set(f"member_count:{service.bot.guilds[0].id}", 100)
        
        # Invalidate all cache
        service.invalidate_cache()
        
        # Verify cache is empty
        assert service.cache.get(f"member_count:{service.bot.guilds[0].id}") is None