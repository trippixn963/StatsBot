"""
Mock objects for testing.

This module provides mock implementations of services and utilities
for use in unit tests.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, List, Optional, Any

from src.types.models import ServiceStatus


class MockStatsService:
    """Mock implementation of OptimizedStatsService for testing."""
    
    def __init__(self):
        self.start_daily_stats_task = AsyncMock(return_value=asyncio.Future())
        self.update_all_stats = AsyncMock()
        self.update_member_count = AsyncMock()
        self.update_online_count = AsyncMock()
        self.update_ban_count = AsyncMock()
        self.save_data = AsyncMock()
        self.record_member_join = MagicMock()
        self.record_member_leave = MagicMock()
        self.record_member_ban = MagicMock()
        self.run_id = "MOCK1234"


class MockMonitoringService:
    """Mock implementation of MonitoringService for testing."""
    
    def __init__(self):
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self._status = ServiceStatus.STOPPED
    
    @property
    def status(self):
        return self._status
    
    async def update_heartbeat(self):
        """Mock heartbeat update."""
        pass


class MockPresenceService:
    """Mock implementation of RichPresenceService for testing."""
    
    def __init__(self):
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self._status = ServiceStatus.STOPPED
    
    @property
    def status(self):
        return self._status
    
    async def update_presence(self):
        """Mock presence update."""
        pass


class MockTaskManager:
    """Mock implementation of TaskManager for testing."""
    
    def __init__(self):
        self.tasks = {}
        self.create_task = MagicMock()
        self.register_task = MagicMock()
        self.cancel_all_tasks = AsyncMock()
        self.get_task = MagicMock()
        self.cancel_task = MagicMock()
        self.wait_for_task = AsyncMock()
        self.get_running_tasks = MagicMock(return_value={})
        self.get_task_count = MagicMock(return_value=0)
        self.get_task_names = MagicMock(return_value=[])


class MockStructuredLogger:
    """Mock implementation of StructuredLogger for testing."""
    
    def __init__(self, name="test"):
        self.name = name
        self.info = MagicMock()
        self.debug = MagicMock()
        self.warning = MagicMock()
        self.error = MagicMock()
        self.critical = MagicMock()
        self.performance = MagicMock()