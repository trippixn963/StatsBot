"""
Tests for the optimized StatsTracker implementation.

This module contains tests for the optimized StatsTracker with atomic operations,
memory-efficient data structures, and change detection.
"""

import unittest
import asyncio
import json
import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

# Mock the config module before importing StatsTracker
import sys
sys.modules['src.core.config'] = MagicMock()
sys.modules['src.core.config'].config = MagicMock()

from src.services.stats.tracker import StatsTracker
from src.types.models import EventType, MemberEvent


class TestStatsTracker(unittest.IsolatedAsyncioTestCase):
    """Test cases for the optimized StatsTracker."""
    
    async def asyncSetUp(self):
        """Set up test environment with temporary data directory."""
        # Create temporary directory for test data
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.data_dir.mkdir(exist_ok=True)
        
        # Create test stats file
        self.stats_file = self.data_dir / "member_stats.json"
        test_data = {
            "2025-07-15": {
                "joins": [
                    {
                        "id": 1109436285405368373,
                        "username": "test_user1",
                        "timestamp": "2025-07-15T21:54:14.758212-04:00"
                    }
                ],
                "leaves": [
                    {
                        "id": 1385606452596441088,
                        "username": "test_user2",
                        "timestamp": "2025-07-15T21:56:50.633157-04:00"
                    }
                ],
                "bans": []
            }
        }
        with open(self.stats_file, 'w') as f:
            json.dump(test_data, f, indent=4)
        
        # Create tracker instance with patched data directory
        with patch('src.services.stats.tracker.Path', return_value=Path(self.temp_dir)):
            self.tracker = StatsTracker()
            # Manually set the data_dir and stats_file attributes
            self.tracker.data_dir = self.data_dir
            self.tracker.stats_file = self.stats_file
        
    async def asyncTearDown(self):
        """Clean up temporary directory after tests."""
        shutil.rmtree(self.temp_dir)
    
    async def test_load_stats_streaming(self):
        """Test loading stats with streaming approach."""
        # Verify that stats were loaded correctly
        self.assertIn("2025-07-15", self.tracker.daily_stats)
        self.assertEqual(1, len(self.tracker.daily_stats["2025-07-15"]["joins"]))
        self.assertEqual(1, len(self.tracker.daily_stats["2025-07-15"]["leaves"]))
        self.assertEqual(0, len(self.tracker.daily_stats["2025-07-15"]["bans"]))
        
        # Verify user data
        self.assertEqual("test_user1", self.tracker.daily_stats["2025-07-15"]["joins"][0]["username"])
        self.assertEqual("test_user2", self.tracker.daily_stats["2025-07-15"]["leaves"][0]["username"])
    
    async def test_save_stats_atomic(self):
        """Test atomic save operation with backup creation."""
        # Add new data to trigger a save
        with patch('asyncio.create_task'):  # Patch create_task to avoid event loop issues
            self.tracker.record_member_join(12345, "new_test_user")
        
        # Save data
        await self.tracker.save_data()
        
        # Verify file was saved
        self.assertTrue(self.stats_file.exists())
        
        # Verify backup was created
        backup_files = list(self.data_dir.glob("member_stats.json.bak*"))
        self.assertGreaterEqual(len(backup_files), 1)
        
        # Verify data was saved correctly
        with open(self.stats_file, 'r') as f:
            saved_data = json.load(f)
            
        # Check that both old and new data are present
        self.assertIn("2025-07-15", saved_data)
        
        # Get current date
        current_date = datetime.now(self.tracker.est_tz).strftime("%Y-%m-%d")
        self.assertIn(current_date, saved_data)
        
        # Check new user was added
        found = False
        for join_event in saved_data[current_date]["joins"]:
            if join_event["username"] == "new_test_user":
                found = True
                break
        self.assertTrue(found)
    
    async def test_change_detection(self):
        """Test change detection to avoid unnecessary saves."""
        # Initial state should not have changes
        self.assertFalse(self.tracker._has_changes())
        
        # Record an event to create changes
        with patch('asyncio.create_task'):  # Patch create_task to avoid event loop issues
            self.tracker.record_member_join(12345, "change_detection_user")
        
        # Should now have changes
        self.assertTrue(self.tracker._has_changes())
        
        # Save data
        await self.tracker.save_data()
        
        # After save, should not have changes
        self.assertFalse(self.tracker._has_changes())
    
    async def test_backup_rotation(self):
        """Test backup file rotation to limit the number of backups."""
        # Create multiple backups by saving multiple times
        for i in range(5):
            with patch('asyncio.create_task'):  # Patch create_task to avoid event loop issues
                self.tracker.record_member_join(10000 + i, f"backup_test_user_{i}")
            await self.tracker.save_data()
        
        # Should have limited number of backups
        backup_files = list(self.data_dir.glob("member_stats.json.bak*"))
        self.assertLessEqual(len(backup_files), self.tracker.BACKUP_RETENTION_COUNT)
    
    async def test_get_daily_stats(self):
        """Test getting daily statistics with optimized calculation."""
        # Add some test data
        current_date = datetime.now(self.tracker.est_tz).strftime("%Y-%m-%d")
        with patch('asyncio.create_task'):  # Patch create_task to avoid event loop issues
            self.tracker.record_member_join(12345, "stats_test_user1")
            self.tracker.record_member_join(12346, "stats_test_user2")
            self.tracker.record_member_leave(12347, "stats_test_user3")
        
        # Get stats for today
        stats = self.tracker.get_daily_stats()
        
        # Verify counts
        self.assertEqual(current_date, stats["date"])
        self.assertEqual(2, stats["joins"])
        self.assertEqual(1, stats["leaves"])
        self.assertEqual(0, stats["bans"])
        self.assertEqual(1, stats["net_change"])  # 2 joins - 1 leave
    
    async def test_get_weekly_stats(self):
        """Test getting weekly statistics with optimized calculation."""
        # Add some test data
        with patch('asyncio.create_task'):  # Patch create_task to avoid event loop issues
            self.tracker.record_member_join(12345, "weekly_test_user1")
            self.tracker.record_member_join(12346, "weekly_test_user2")
            self.tracker.record_member_leave(12347, "weekly_test_user3")
        
        # Get weekly stats
        stats = self.tracker.get_weekly_stats()
        
        # Verify structure
        self.assertIn("start_date", stats)
        self.assertIn("end_date", stats)
        self.assertIn("total_joins", stats)
        self.assertIn("total_leaves", stats)
        self.assertIn("daily_breakdown", stats)
        
        # Verify data includes our test users
        found_user = False
        for event in stats["join_list"]:
            if event.get("username") == "weekly_test_user1":
                found_user = True
                break
        self.assertTrue(found_user)
    
    async def test_stream_all_events(self):
        """Test streaming events for memory efficiency."""
        # Add some test data
        with patch('asyncio.create_task'):  # Patch create_task to avoid event loop issues
            self.tracker.record_member_join(12345, "stream_test_user1")
            self.tracker.record_member_join(12346, "stream_test_user2")
            self.tracker.record_member_leave(12347, "stream_test_user3")
        
        # Stream all events
        events = list(self.tracker.stream_all_events())
        
        # Verify we got all events
        self.assertGreaterEqual(len(events), 3)  # At least our 3 new events
        
        # Verify event structure
        for event in events:
            self.assertIn("date", event)
            self.assertIn("type", event)
            self.assertIn("id", event)
            self.assertIn("username", event)
            self.assertIn("timestamp", event)
    
    async def test_validate_data_integrity(self):
        """Test data integrity validation."""
        # Start with valid data
        is_valid, issues = await self.tracker.validate_data_integrity()
        self.assertTrue(is_valid)
        self.assertEqual(0, len(issues))
        
        # Introduce an invalid date
        self.tracker.daily_stats["invalid-date"] = {
            "joins": [],
            "leaves": []
        }
        
        # Should now be invalid
        is_valid, issues = await self.tracker.validate_data_integrity()
        self.assertFalse(is_valid)
        self.assertGreater(len(issues), 0)
    
    async def test_repair_data_if_needed(self):
        """Test automatic data repair."""
        # Introduce an invalid date
        self.tracker.daily_stats["invalid-date"] = {
            "joins": [],
            "leaves": []
        }
        
        # Repair should fix issues
        repairs_made = await self.tracker.repair_data_if_needed()
        self.assertTrue(repairs_made)
        
        # Data should now be valid
        is_valid, issues = await self.tracker.validate_data_integrity()
        self.assertTrue(is_valid)
        self.assertEqual(0, len(issues))
        
        # Invalid date should be removed
        self.assertNotIn("invalid-date", self.tracker.daily_stats)


if __name__ == '__main__':
    # Use asyncio to run async tests
    asyncio.run(unittest.main())