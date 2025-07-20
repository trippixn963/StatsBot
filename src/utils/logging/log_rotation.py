"""
Log rotation and cleanup utilities.

This module provides utilities for log rotation and cleanup based on
configurable retention policies.
"""

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional


class LogRotation:
    """
    Log rotation and cleanup utility.
    
    This class provides methods for rotating log files and cleaning up
    old log files based on retention policies.
    
    Attributes:
        log_dir (Path): Base directory for logs
        retention_days (int): Number of days to keep log files
    """
    
    def __init__(self, log_dir: str = "logs", retention_days: int = 7):
        """
        Initialize a new log rotation utility.
        
        Args:
            log_dir: Base directory for logs
            retention_days: Number of days to keep log files
        """
        self.log_dir = Path(log_dir)
        self.retention_days = retention_days
        
    def rotate_logs(self) -> None:
        """
        Rotate logs by creating a new directory for the current day.
        
        This method ensures that a new directory exists for the current day's logs.
        It does not move or modify existing log files.
        """
        today_dir = self._get_today_dir()
        today_dir.mkdir(parents=True, exist_ok=True)
        
    def cleanup_old_logs(self) -> List[str]:
        """
        Remove log directories older than retention_days.
        
        Returns:
            List of removed directory names
        """
        if not self.log_dir.exists():
            return []
            
        removed_dirs = []
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        for item in self.log_dir.iterdir():
            if not item.is_dir():
                continue
                
            try:
                # Try to parse directory name as date
                dir_date = datetime.strptime(item.name, "%Y-%m-%d")
                if dir_date < cutoff_date:
                    shutil.rmtree(item)
                    removed_dirs.append(item.name)
            except ValueError:
                # Not a date-formatted directory, skip
                continue
                
        return removed_dirs
        
    def get_log_size(self, days: Optional[int] = None) -> int:
        """
        Get total size of log files in bytes.
        
        Args:
            days: Number of days to include (None for all)
            
        Returns:
            Total size in bytes
        """
        if not self.log_dir.exists():
            return 0
            
        total_size = 0
        cutoff_date = None
        
        if days is not None:
            cutoff_date = datetime.now() - timedelta(days=days)
            
        for item in self.log_dir.iterdir():
            if not item.is_dir():
                continue
                
            try:
                # Try to parse directory name as date
                dir_date = datetime.strptime(item.name, "%Y-%m-%d")
                
                # Skip if before cutoff date
                if cutoff_date and dir_date < cutoff_date:
                    continue
                    
                # Add size of all files in directory
                for file_path in item.glob("**/*"):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
            except ValueError:
                # Not a date-formatted directory, skip
                continue
                
        return total_size
        
    def get_log_file_paths(self, date: Optional[datetime] = None) -> dict:
        """
        Get paths for log files for the specified date.
        
        Args:
            date: Date to get log files for (default: today)
            
        Returns:
            Dictionary with log file paths
        """
        date_dir = self._get_date_dir(date)
        
        return {
            "main": date_dir / "logs.log",
            "error": date_dir / "errors.log",
            "json": date_dir / "logs.json"
        }
        
    def _get_today_dir(self) -> Path:
        """Get directory path for today's logs."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / today
        
    def _get_date_dir(self, date: Optional[datetime] = None) -> Path:
        """
        Get directory path for the specified date's logs.
        
        Args:
            date: Date to get directory for (default: today)
            
        Returns:
            Path to log directory for the specified date
        """
        if date is None:
            date = datetime.now()
            
        date_str = date.strftime("%Y-%m-%d")
        return self.log_dir / date_str