"""
Tests for the optimized MonitoringService.

This module contains tests for the MonitoringService implementation,
focusing on efficient metrics collection, log aggregation, and heartbeat generation.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import discord
from datetime import datetime, timezone
import logging

from src.services.monitoring import MonitoringService, LogBuffer
from src.types.models import SystemMetrics, ServiceStatus


class TestLogBuffer(unittest.TestCase):
    """Tests for the LogBuffer class."""
    
    def test_add_log(self):
        """Test adding logs to the buffer."""
        buffer = LogBuffer(max_logs=3)
        
        # Add logs
        buffer.add_log({"level": "INFO", "message": "Log 1", "timestamp": datetime.now(timezone.utc)})
        buffer.add_log({"level": "INFO", "message": "Log 2", "timestamp": datetime.now(timezone.utc)})
        
        # Check buffer size
        self.assertEqual(len(buffer.buffer), 2)
        
    def test_get_recent_logs(self):
        """Test getting recent logs from the buffer."""
        buffer = LogBuffer(max_logs=5)
        
        # Add logs
        for i in range(10):
            buffer.add_log({"level": "INFO", "message": f"Log {i}", "timestamp": datetime.now(timezone.utc)})
            
        # Get recent logs
        logs = buffer.get_recent_logs(limit=3)
        
        # Check logs
        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[-1]["message"], "Log 9")
        
    def test_circular_buffer_behavior(self):
        """Test circular buffer behavior when exceeding max size."""
        buffer = LogBuffer(max_logs=3)
        
        # Add logs
        for i in range(5):
            buffer.add_log({"level": "INFO", "message": f"Log {i}", "timestamp": datetime.now(timezone.utc)})
            
        # Check buffer size
        self.assertEqual(len(buffer.buffer), 3)
        
        # Check buffer contents (should only have the last 3 logs)
        logs = buffer.get_recent_logs()
        messages = [log["message"] for log in logs]
        self.assertEqual(messages, ["Log 2", "Log 3", "Log 4"])


class TestMonitoringService(unittest.TestCase):
    """Tests for the MonitoringService class."""
    
    def setUp(self):
        """Set up test environment."""
        # Mock bot
        self.bot = MagicMock()
        self.bot.latency = 0.05
        self.bot.stats_service = MagicMock()
        self.bot.stats_service.stats_tracker = MagicMock()
        self.bot.stats_service.stats_tracker.get_daily_stats.return_value = {
            'date': '2025-07-20',
            'joins': 5,
            'leaves': 3,
            'bans': 1,
            'unbans': 0,
            'net_change': 2,
            'join_list': [{'id': '123', 'username': 'user1'} for _ in range(5)],
            'leave_list': [{'id': '456', 'username': 'user2'} for _ in range(3)],
            'ban_list': [{'id': '789', 'username': 'user3'}],
            'unban_list': []
        }
        
        # Create service
        self.service = MonitoringService(
            bot=self.bot,
            heartbeat_channel_id=123456789,
            update_interval=60,
            max_logs=10,
            cache_ttl=30
        )
        
    def test_initialization(self):
        """Test service initialization."""
        self.assertEqual(self.service.heartbeat_channel_id, 123456789)
        self.assertEqual(self.service.update_interval, 60)
        self.assertEqual(self.service.status, ServiceStatus.STOPPED)
        self.assertIsNone(self.service.heartbeat_message)
        self.assertIsNone(self.service.heartbeat_task)
        
    @patch('psutil.Process')
    def test_get_system_metrics(self, mock_process):
        """Test getting system metrics."""
        # Mock process methods
        process_instance = mock_process.return_value
        process_instance.cpu_percent.return_value = 10.5
        process_instance.memory_percent.return_value = 25.3
        process_instance.num_threads.return_value = 5
        
        # Get metrics
        metrics = self.service.get_system_metrics()
        
        # Check metrics
        self.assertIsInstance(metrics, SystemMetrics)
        self.assertEqual(metrics.cpu_percent, 10.5)
        self.assertEqual(metrics.memory_percent, 25.3)
        self.assertEqual(metrics.threads, 5)
        
    def test_format_uptime(self):
        """Test formatting uptime."""
        # Set start time to a known value
        self.service.start_time = datetime.now(timezone.utc) - asyncio.timedelta(days=2, hours=5, minutes=30)
        
        # Format uptime
        uptime = self.service.format_uptime()
        
        # Check format
        self.assertIn("2d", uptime)
        self.assertIn("5h", uptime)
        
    @patch('discord.Embed')
    async def test_create_heartbeat_embed(self, mock_embed):
        """Test creating heartbeat embed."""
        # Mock embed
        embed_instance = mock_embed.return_value
        
        # Create embed
        await self.service.create_heartbeat_embed()
        
        # Check embed creation
        mock_embed.assert_called_once()
        self.assertEqual(embed_instance.add_field.call_count, 3)  # Base fields
        
    async def test_start_stop(self):
        """Test starting and stopping the service."""
        # Start service
        await self.service.start()
        self.assertEqual(self.service.status, ServiceStatus.RUNNING)
        self.assertIsNotNone(self.service.heartbeat_task)
        
        # Stop service
        await self.service.stop()
        self.assertEqual(self.service.status, ServiceStatus.STOPPED)
        self.assertIsNone(self.service.heartbeat_task)
        
    @patch('discord.TextChannel')
    async def test_update_heartbeat(self, mock_channel):
        """Test updating heartbeat message."""
        # Mock channel and message
        channel_instance = mock_channel.return_value
        message = AsyncMock()
        channel_instance.send = AsyncMock(return_value=message)
        
        # Mock bot.get_channel
        self.bot.get_channel.return_value = channel_instance
        
        # Update heartbeat
        await self.service.update_heartbeat()
        
        # Check message creation
        channel_instance.send.assert_called_once()
        self.assertEqual(self.service.heartbeat_message, message)
        
        # Update again (should edit existing message)
        await self.service.update_heartbeat()
        message.edit.assert_called_once()
        
    def test_add_log(self):
        """Test adding logs to the service."""
        # Add log
        self.service.add_log({
            'level': 'INFO',
            'message': 'Test log',
            'timestamp': datetime.now(timezone.utc)
        })
        
        # Check log buffer
        logs = self.service.log_buffer.get_recent_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]['message'], 'Test log')


if __name__ == '__main__':
    unittest.main()