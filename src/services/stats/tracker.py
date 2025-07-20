"""
Optimized StatsTracker for efficient data persistence and statistics calculation.

This module provides an optimized implementation of the StatsTracker with:
- Atomic file writes with backup and recovery mechanisms
- Memory-efficient data structures for statistics storage
- Streaming operations for large datasets
- Optimized statistics calculation with change detection
"""

import json
import asyncio
import os
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import pytz
from typing import Dict, List, Optional, Any, Union, Set, Iterator, Generator, Tuple
import time
import hashlib
import io

from src.utils.logging.structured_logger import StructuredLogger, timed
from src.core.exceptions import DataPersistenceError
from src.utils.cache.circular_buffer import CircularBuffer
from src.types.models import MemberEvent, EventType


class StatsTracker:
    """
    Optimized statistics tracker with efficient data persistence and atomic operations.
    
    This class manages the storage and retrieval of member statistics,
    providing efficient data structures, atomic file operations, and change detection.
    
    Attributes:
        est_tz (pytz.timezone): Eastern Standard Time timezone
        data_dir (Path): Directory for data files
        stats_file (Path): File for member statistics
        daily_stats (Dict): In-memory cache of daily statistics
        logger (StructuredLogger): Structured logger
        _lock (asyncio.Lock): Lock for thread-safe operations
        _change_detected (bool): Flag indicating if changes have been made
        _last_hash (str): Hash of the last saved data for change detection
        _recent_events (CircularBuffer): Circular buffer for recent events
    """
    
    # Constants for file operations
    MAX_RECENT_EVENTS = 100
    BACKUP_RETENTION_COUNT = 3
    CHUNK_SIZE = 8192  # 8KB chunks for streaming operations   
    
    def __init__(self, logger: Optional[StructuredLogger] = None):
        """
        Initialize the stats tracker.
        
        Args:
            logger: Structured logger (optional)
        """
        self.est_tz = pytz.timezone('US/Eastern')
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.stats_file = self.data_dir / "member_stats.json"
        self.daily_stats: Dict[str, dict] = {}
        self.logger = logger or StructuredLogger("stats_tracker")
        self._lock = asyncio.Lock()
        self._change_detected = False
        self._last_hash = ""
        
        # Use circular buffer for recent events to limit memory usage
        self._recent_events = CircularBuffer[MemberEvent](self.MAX_RECENT_EVENTS)
        
        # Load stats with streaming for large files
        self._load_stats_streaming()
        
        # Initialize empty stats for today if needed
        current_date = datetime.now(self.est_tz).strftime("%Y-%m-%d")
        if current_date not in self.daily_stats:
            self.daily_stats[current_date] = {
                "joins": [],
                "leaves": [],
                "bans": [],
                "unbans": []
            }
        
        self.logger.info(
            "Stats Tracker initialized",
            service="StatsTracker",
            data_file=str(self.stats_file),
            timezone="EST",
            dates_loaded=len(self.daily_stats)
        )
    
    def _load_stats_streaming(self) -> None:
        """
        Load stats from JSON file using streaming for memory efficiency.
        
        This method uses the stream_json_from_file utility to handle potentially
        large JSON files without loading the entire file into memory at once.
        It also includes data validation and automatic repair for corrupted files.
        
        Raises:
            DataPersistenceError: If file cannot be read or parsed
        """
        if not self.stats_file.exists():
            self.daily_stats = {}
            return
        
        from src.utils.file_io.json_utils import stream_json_from_file
        from src.utils.file_io.data_validator import DataValidator
        
        try:
            # Use the streaming JSON utility
            self.daily_stats = stream_json_from_file(self.stats_file)
            
            # Calculate hash for change detection
            self._last_hash = self._calculate_data_hash(self.daily_stats)
            
            # Validate and repair data if needed
            validator = DataValidator(logger=self.logger)
            is_valid, errors = validator.validate_stats_data(self.daily_stats)
            
            if not is_valid:
                self.logger.warning(
                    "Stats data validation failed, attempting repair",
                    service="StatsTracker",
                    errors=errors
                )
                
                # Try to repair the data
                repaired_data, repairs_made, repair_messages = validator.repair_stats_data(self.daily_stats)
                
                if repairs_made:
                    self.logger.info(
                        "Stats data repaired successfully",
                        service="StatsTracker",
                        repairs=repair_messages
                    )
                    
                    # Use the repaired data
                    self.daily_stats = repaired_data
                    self._change_detected = True  # Mark for saving
            
        except json.JSONDecodeError as e:
            self.logger.error(
                "JSON decode error when loading stats file",
                error=e,
                service="StatsTracker",
                file_path=str(self.stats_file)
            )
            # Try to restore from backup
            self._restore_from_backup()
        except Exception as e:
            self.logger.error(
                "Failed to load stats file",
                error=e,
                service="StatsTracker",
                file_path=str(self.stats_file)
            )
            # Try to restore from backup
            self._restore_from_backup()
    
    async def _restore_from_backup(self) -> None:
        """
        Attempt to restore data from the most recent backup file.
        
        This method uses the AtomicWriter utility to find and restore
        from the most recent valid backup file when the primary data file
        is corrupted or cannot be read.
        """
        self.logger.warning(
            "Attempting to restore from backup",
            service="StatsTracker"
        )
        
        from src.utils.file_io.atomic_writer import AtomicWriter
        from src.utils.file_io.json_utils import stream_json_from_file
        
        # Use the atomic writer utility
        writer = AtomicWriter(backup_retention_count=self.BACKUP_RETENTION_COUNT)
        
        # Attempt to restore from backup
        restored_file = await writer.restore_from_backup(self.stats_file)
        
        if restored_file:
            try:
                # Load the restored file
                self.daily_stats = stream_json_from_file(self.stats_file)
                
                # Calculate hash for change detection
                self._last_hash = self._calculate_data_hash(self.daily_stats)
                
                self.logger.info(
                    f"Successfully restored from backup: {restored_file}",
                    service="StatsTracker"
                )
                return
            except Exception as e:
                self.logger.error(
                    "Failed to load restored file",
                    error=e,
                    service="StatsTracker"
                )
        
        # If we get here, restoration failed
        self.logger.error(
            "Backup restoration failed, starting with empty data",
            service="StatsTracker"
        )
        self.daily_stats = {}
    
    def _calculate_data_hash(self, data: Dict) -> str:
        """
        Calculate a hash of the data for change detection.
        
        Args:
            data: Data to hash
            
        Returns:
            String hash of the data
        """
        # Use a deterministic JSON serialization for consistent hashing
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.md5(serialized.encode()).hexdigest()
    
    def _has_changes(self) -> bool:
        """
        Check if data has changed since last save.
        
        Returns:
            True if changes detected, False otherwise
        """
        if self._change_detected:
            return True
            
        current_hash = self._calculate_data_hash(self.daily_stats)
        return current_hash != self._last_hash 
   
    async def _save_stats_atomic(self) -> None:
        """
        Save stats to file atomically to prevent data corruption.
        
        This method uses the AtomicWriter utility to write data atomically,
        ensuring data integrity even in case of system crashes or power failures.
        It also maintains a series of backup files for recovery purposes.
        
        Raises:
            DataPersistenceError: If file cannot be written
        """
        # Skip save if no changes detected
        if not self._has_changes():
            self.logger.debug(
                "No changes detected, skipping save",
                service="StatsTracker"
            )
            return
        
        from src.utils.file_io.atomic_writer import AtomicWriter
        from src.utils.file_io.json_utils import stream_json_to_file
        
        try:
            # Use the atomic writer utility
            writer = AtomicWriter(backup_retention_count=self.BACKUP_RETENTION_COUNT)
            
            # Stream JSON to file atomically
            await stream_json_to_file(
                self.stats_file,
                self.daily_stats,
                indent=4,
                atomic=True,
                create_backup=True
            )
            
            # Update hash after successful save
            self._last_hash = self._calculate_data_hash(self.daily_stats)
            self._change_detected = False
            
            self.logger.debug(
                "Stats saved successfully",
                service="StatsTracker",
                data_file=str(self.stats_file)
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to save stats file",
                error=e,
                service="StatsTracker",
                data_file=str(self.stats_file)
            )
            
            raise DataPersistenceError(
                f"Failed to save stats file: {str(e)}",
                file_path=str(self.stats_file),
                operation="write",
                original_error=e
            )
    
    async def _cleanup_old_backups(self) -> None:
        """
        Clean up old backup files, keeping only the most recent ones.
        
        This method uses the AtomicWriter utility to manage backup files,
        preventing the data directory from filling up while still maintaining
        a reasonable backup history.
        """
        from src.utils.file_io.atomic_writer import AtomicWriter
        
        try:
            # Use the atomic writer utility
            writer = AtomicWriter(backup_retention_count=self.BACKUP_RETENTION_COUNT)
            
            # Clean up old backups
            await writer.cleanup_old_backups(self.stats_file)
            
        except Exception as e:
            self.logger.warning(
                "Error during backup cleanup",
                error=e,
                service="StatsTracker"
            )
    
    @timed("save_data")
    async def save_data(self) -> None:
        """
        Save all pending data with thread safety.
        
        This method only performs the save operation if changes have been
        detected since the last save, improving performance.
        
        Raises:
            DataPersistenceError: If file cannot be written
        """
        if not self._has_changes():
            self.logger.debug(
                "No changes to save",
                service="StatsTracker"
            )
            return
            
        self.logger.info(
            "Saving stats data",
            service="StatsTracker",
            data_file=str(self.stats_file)
        )
        
        async with self._lock:
            await self._save_stats_atomic()
    
    def _create_member_event(self, event_type: EventType, member_id: int, username: str) -> Dict[str, Any]:
        """
        Create a member event dictionary with consistent format.
        
        Args:
            event_type: Type of event
            member_id: Member ID
            username: Member username
            
        Returns:
            Dictionary representing the event
        """
        event = {
            "id": member_id,
            "username": username,
            "timestamp": datetime.now(self.est_tz).isoformat()
        }
        
        # Add to recent events circular buffer
        member_event = MemberEvent(
            member_id=member_id,
            username=username,
            timestamp=datetime.now(self.est_tz),
            event_type=event_type
        )
        self._recent_events.append(member_event)
        
        return event  
  
    def _ensure_date_entry(self, date: str) -> None:
        """
        Ensure a date entry exists in the daily stats.
        
        Args:
            date: Date string in YYYY-MM-DD format
        """
        if date not in self.daily_stats:
            self.daily_stats[date] = {
                "joins": [],
                "leaves": [],
                "bans": [],
                "unbans": []
            }
    
    def record_member_join(self, member_id: int, username: str) -> None:
        """
        Record a member join event.
        
        Args:
            member_id: Member ID
            username: Member username
        """
        current_date = datetime.now(self.est_tz).strftime("%Y-%m-%d")
        self._ensure_date_entry(current_date)
        
        event = self._create_member_event(EventType.JOIN, member_id, username)
        self.daily_stats[current_date]["joins"].append(event)
        
        # Mark that changes have been made
        self._change_detected = True
        
        # Schedule async save
        asyncio.create_task(self._save_stats_atomic())
        
        self.logger.info(
            f"Member join recorded: {username}",
            service="StatsTracker",
            member_id=member_id,
            username=username,
            date=current_date
        )
    
    def record_member_leave(self, member_id: int, username: str) -> None:
        """
        Record a member leave event.
        
        Args:
            member_id: Member ID
            username: Member username
        """
        current_date = datetime.now(self.est_tz).strftime("%Y-%m-%d")
        self._ensure_date_entry(current_date)
        
        event = self._create_member_event(EventType.LEAVE, member_id, username)
        self.daily_stats[current_date]["leaves"].append(event) 
       
        # Mark that changes have been made
        self._change_detected = True
        
        # Schedule async save
        asyncio.create_task(self._save_stats_atomic())
        
        self.logger.info(
            f"Member leave recorded: {username}",
            service="StatsTracker",
            member_id=member_id,
            username=username,
            date=current_date
        )
    
    def record_member_ban(self, member_id: int, username: str) -> None:
        """
        Record a member ban event.
        
        Args:
            member_id: Member ID
            username: Member username
        """
        current_date = datetime.now(self.est_tz).strftime("%Y-%m-%d")
        self._ensure_date_entry(current_date)
        
        event = self._create_member_event(EventType.BAN, member_id, username)
        self.daily_stats[current_date]["bans"].append(event)
        
        # Mark that changes have been made
        self._change_detected = True
        
        # Schedule async save
        asyncio.create_task(self._save_stats_atomic())
        
        self.logger.info(
            f"Member ban recorded: {username}",
            service="StatsTracker",
            member_id=member_id,
            username=username,
            date=current_date
        )
    
    def record_member_unban(self, member_id: int, username: str) -> None:
        """
        Record a member unban event.
        
        Args:
            member_id: Member ID
            username: Member username
        """
        current_date = datetime.now(self.est_tz).strftime("%Y-%m-%d")
        self._ensure_date_entry(current_date)
        
        # Ensure unbans list exists (for backward compatibility)
        if "unbans" not in self.daily_stats[current_date]:
            self.daily_stats[current_date]["unbans"] = []  
          
        event = self._create_member_event(EventType.UNBAN, member_id, username)
        self.daily_stats[current_date]["unbans"].append(event)
        
        # Mark that changes have been made
        self._change_detected = True
        
        # Schedule async save
        asyncio.create_task(self._save_stats_atomic())
        
        self.logger.info(
            f"Member unban recorded: {username}",
            service="StatsTracker",
            member_id=member_id,
            username=username,
            date=current_date
        )

    def get_daily_stats(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get stats for a specific date or today.
        
        Args:
            date: Date string in YYYY-MM-DD format (default: today)
            
        Returns:
            Dictionary with daily statistics
        """
        if date is None:
            date = datetime.now(self.est_tz).strftime("%Y-%m-%d")
            
        if date in self.daily_stats:
            stats = self.daily_stats[date]
            
            # Use efficient list length calculation instead of creating new lists
            joins_count = len(stats["joins"])
            leaves_count = len(stats["leaves"])
            bans_count = len(stats.get("bans", []))
            unbans_count = len(stats.get("unbans", []))
            
            return {
                "date": date,
                "joins": joins_count,
                "leaves": leaves_count,
                "bans": bans_count,
                "unbans": unbans_count,
                "net_change": joins_count - leaves_count,
                "join_list": stats["joins"],
                "leave_list": stats["leaves"],
                "ban_list": stats.get("bans", []),
                "unban_list": stats.get("unbans", [])
            }    
    
        # Return empty stats for dates with no data
        return {
            "date": date,
            "joins": 0,
            "leaves": 0,
            "bans": 0,
            "unbans": 0,
            "net_change": 0,
            "join_list": [],
            "leave_list": [],
            "ban_list": [],
            "unban_list": []
        }
    
    def get_weekly_stats(self) -> Dict[str, Any]:
        """
        Get stats for the past week with optimized calculation.
        
        Returns:
            Dictionary with weekly statistics
        """
        end_date = datetime.now(self.est_tz)
        start_date = end_date - timedelta(days=7)
        
        weekly_stats = {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "total_joins": 0,
            "total_leaves": 0,
            "total_bans": 0,
            "total_unbans": 0,
            "net_change": 0,
            "daily_breakdown": [],
            "most_active_day": None,
            "join_list": [],
            "leave_list": [],
            "ban_list": [],
            "unban_list": []
        }
        
        max_activity = 0
        current_date = start_date
        
        # Pre-calculate date strings for the week to avoid recalculation
        date_range = []
        temp_date = start_date
        while temp_date <= end_date:
            date_range.append(temp_date.strftime("%Y-%m-%d"))
            temp_date += timedelta(days=1)
        
        # Process each date in the range
        for date_str in date_range:
            # Use our optimized daily stats method
            daily_stats = self.get_daily_stats(date_str)      
      
            # Accumulate totals
            weekly_stats["total_joins"] += daily_stats["joins"]
            weekly_stats["total_leaves"] += daily_stats["leaves"]
            weekly_stats["total_bans"] += daily_stats["bans"]
            weekly_stats["total_unbans"] += daily_stats["unbans"]
            
            # Track most active day
            daily_activity = daily_stats["joins"] + daily_stats["leaves"] + daily_stats["bans"]
            if daily_activity > max_activity:
                max_activity = daily_activity
                weekly_stats["most_active_day"] = {
                    "date": date_str,
                    "joins": daily_stats["joins"],
                    "leaves": daily_stats["leaves"],
                    "bans": daily_stats["bans"],
                    "unbans": daily_stats["unbans"],
                    "total_activity": daily_activity
                }
            
            # Add to daily breakdown
            weekly_stats["daily_breakdown"].append({
                "date": date_str,
                "joins": daily_stats["joins"],
                "leaves": daily_stats["leaves"],
                "bans": daily_stats["bans"],
                "unbans": daily_stats["unbans"],
                "net_change": daily_stats["net_change"]
            })
            
            # Collect event lists efficiently
            if date_str in self.daily_stats:
                stats = self.daily_stats[date_str]
                weekly_stats["join_list"].extend(stats["joins"])
                weekly_stats["leave_list"].extend(stats["leaves"])
                if "bans" in stats:
                    weekly_stats["ban_list"].extend(stats["bans"])
                if "unbans" in stats:
                    weekly_stats["unban_list"].extend(stats["unbans"])
        
        # Calculate net change
        weekly_stats["net_change"] = weekly_stats["total_joins"] - weekly_stats["total_leaves"]
        return weekly_stats    

    def get_recent_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recent member events.
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of recent events
        """
        events = []
        for event in reversed(self._recent_events.to_list()):
            if len(events) >= limit:
                break
            events.append(event.to_dict())
        return events
    
    async def validate_data_integrity(self) -> Tuple[bool, List[str]]:
        """
        Validate the integrity of the stats data.
        
        This method checks for data corruption, invalid formats, and other
        issues that could affect the reliability of the statistics.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        from src.utils.file_io.data_validator import DataValidator
        
        validator = DataValidator(logger=self.logger)
        return validator.validate_stats_data(self.daily_stats)
    
    async def repair_data_if_needed(self) -> bool:
        """
        Check and repair data integrity issues if needed.
        
        This method validates the data and attempts to repair any issues
        found, such as invalid date formats, missing fields, or corrupted entries.
        
        Returns:
            True if repairs were made, False otherwise
        """
        from src.utils.file_io.data_validator import DataValidator
        
        validator = DataValidator(logger=self.logger)
        
        # Validate the data
        is_valid, errors = await self.validate_data_integrity()
        
        if not is_valid:
            self.logger.warning(
                "Data integrity issues detected, attempting repair",
                service="StatsTracker",
                errors=errors
            )
            
            # Try to repair the data
            repaired_data, repairs_made, repair_messages = validator.repair_stats_data(self.daily_stats)
            
            if repairs_made:
                self.logger.info(
                    "Data repaired successfully",
                    service="StatsTracker",
                    repairs=repair_messages
                )
                
                # Use the repaired data
                self.daily_stats = repaired_data
                self._change_detected = True  # Mark for saving
                
                # Save the repaired data
                await self.save_data()
                
                return True
        
        return False
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all statistics.
        
        Returns:
            Dictionary with statistics summary
        """
        total_dates = len(self.daily_stats)
        total_joins = 0
        total_leaves = 0
        total_bans = 0
        
        # Calculate totals efficiently
        for date, stats in self.daily_stats.items():
            total_joins += len(stats["joins"])
            total_leaves += len(stats["leaves"])
            total_bans += len(stats.get("bans", []))
        
        return {
            "total_dates": total_dates,
            "total_joins": total_joins,
            "total_leaves": total_leaves,
            "total_bans": total_bans,
            "net_change": total_joins - total_leaves,
            "has_unsaved_changes": self._has_changes()
        }
    
    def stream_all_events(self, event_type: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
        """
        Stream all events of a specific type or all types.
        
        This method uses a generator to efficiently stream events without
        loading all of them into memory at once, which is useful for
        processing large datasets. 
       
        Args:
            event_type: Type of events to stream (joins, leaves, bans, unbans) or None for all
            
        Yields:
            Event dictionaries with date information added
        """
        for date, stats in self.daily_stats.items():
            if event_type is None or event_type == "all":
                # Stream all event types
                for event in stats.get("joins", []):
                    yield {"date": date, "type": "join", **event}
                for event in stats.get("leaves", []):
                    yield {"date": date, "type": "leave", **event}
                for event in stats.get("bans", []):
                    yield {"date": date, "type": "ban", **event}
                for event in stats.get("unbans", []):
                    yield {"date": date, "type": "unban", **event}
            elif event_type in stats:
                # Stream specific event type
                for event in stats[event_type]:
                    yield {"date": date, "type": event_type[:-1], **event}
    
    async def export_stats_to_file(self, output_file: Path) -> None:
        """
        Export all statistics to a file using streaming for memory efficiency.
        
        This method uses the stream_json_to_file utility to efficiently export
        statistics data to a file, with atomic writes and proper error handling.
        
        Args:
            output_file: Path to output file
            
        Raises:
            DataPersistenceError: If export fails
        """
        from src.utils.file_io.json_utils import stream_json_to_file
        
        try:
            # Use the streaming JSON utility
            await stream_json_to_file(
                output_file,
                self.daily_stats,
                indent=4,
                atomic=True,
                create_backup=True
            )
            
            self.logger.info(
                f"Stats exported to {output_file}",
                service="StatsTracker"
            )
            
        except Exception as e:
            self.logger.error(
                f"Failed to export stats to {output_file}",
                error=e,
                service="StatsTracker"
            )
            
            raise DataPersistenceError(
                f"Failed to export stats: {str(e)}",
                file_path=str(output_file),
                operation="export",
                original_error=e
            )