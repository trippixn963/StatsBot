"""
Structured logging system with JSON formatting and performance monitoring.

This module provides a comprehensive logging system with:
- JSON-structured logging with consistent field names
- Configurable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Performance timing for critical operations
- Contextual logging with proper field naming
- Log rotation and cleanup with retention policies
"""

import json
import logging
import os
import time
import shutil
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union, TypeVar, cast

from src.types.models import LogEntry, LogLevel
from src.utils.cache.circular_buffer import CircularBuffer

# Type variable for generic function decorator
F = TypeVar('F', bound=Callable[..., Any])

class StructuredLogger:
    """
    Structured logger with JSON formatting and performance monitoring.
    
    This class provides a comprehensive logging system that outputs logs in both
    human-readable and machine-readable JSON formats, with support for contextual
    information, performance timing, and log rotation.
    
    Attributes:
        name (str): Logger name
        level (LogLevel): Current log level
        log_dir (Path): Directory for log files
        max_memory_entries (int): Maximum number of log entries to keep in memory
        retention_days (int): Number of days to keep log files
        memory_buffer (CircularBuffer): In-memory buffer for recent log entries
        _context (Dict): Context data to include with all log entries
    """
    
    def __init__(
        self,
        name: str,
        level: Union[LogLevel, str] = LogLevel.INFO,
        log_dir: Union[str, Path] = "logs",
        max_memory_entries: int = 1000,
        retention_days: int = 7
    ):
        """
        Initialize a new structured logger.
        
        Args:
            name: Logger name
            level: Log level (default: INFO)
            log_dir: Directory for log files (default: "logs")
            max_memory_entries: Maximum number of log entries to keep in memory
            retention_days: Number of days to keep log files
            
        Raises:
            ValueError: If invalid log level is provided
        """
        self.name = name
        self.log_dir = Path(log_dir)
        self.max_memory_entries = max_memory_entries
        self.retention_days = retention_days
        self.memory_buffer = CircularBuffer[LogEntry](max_memory_entries)
        self._context: Dict[str, Any] = {}
        
        # Convert string level to LogLevel enum if needed
        if isinstance(level, str):
            try:
                self.level = LogLevel[level.upper()]
            except KeyError:
                valid_levels = ", ".join([l.name for l in LogLevel])
                raise ValueError(f"Invalid log level: {level}. Valid levels are: {valid_levels}")
        else:
            self.level = level
            
        # Set up Python's built-in logging
        self._setup_logging()
        
        # Create log directory if it doesn't exist
        self._ensure_log_directory()
        
        # Clean up old log files
        self._cleanup_old_logs()
        
    def _setup_logging(self) -> None:
        """Set up Python's built-in logging with appropriate handlers."""
        # Get or create logger with the specified name
        self._logger = logging.getLogger(self.name)
        self._logger.setLevel(self._get_python_log_level(self.level))
        
        # Remove any existing handlers
        for handler in self._logger.handlers[:]:
            self._logger.removeHandler(handler)
            
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self._get_python_log_level(self.level))
        
        # Create formatter
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        
        # Add handler to logger
        self._logger.addHandler(console_handler)
        
    def _get_python_log_level(self, level: LogLevel) -> int:
        """Convert LogLevel enum to Python's logging level."""
        level_map = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL
        }
        return level_map[level]
        
    def _ensure_log_directory(self) -> None:
        """Create log directory structure if it doesn't exist."""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_log_dir = self.log_dir / today
        daily_log_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_log_file_paths(self) -> Dict[str, Path]:
        """Get paths for various log files."""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_log_dir = self.log_dir / today
        
        return {
            "main": daily_log_dir / "logs.log",
            "error": daily_log_dir / "errors.log",
            "json": daily_log_dir / "logs.json"
        }
        
    def _cleanup_old_logs(self) -> None:
        """Remove log files older than retention_days."""
        if not self.log_dir.exists():
            return
            
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        for item in self.log_dir.iterdir():
            if not item.is_dir():
                continue
                
            try:
                # Try to parse directory name as date
                dir_date = datetime.strptime(item.name, "%Y-%m-%d")
                if dir_date < cutoff_date:
                    shutil.rmtree(item)
            except ValueError:
                # Not a date-formatted directory, skip
                continue
                
    def _should_log(self, level: LogLevel) -> bool:
        """Check if a message with the given level should be logged."""
        level_values = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARNING: 2,
            LogLevel.ERROR: 3,
            LogLevel.CRITICAL: 4
        }
        return level_values[level] >= level_values[self.level]
        
    def _write_to_file(self, entry: LogEntry, file_path: Path, error_only: bool = False) -> None:
        """Write log entry to file."""
        if error_only and entry.level not in [LogLevel.ERROR, LogLevel.CRITICAL]:
            return
            
        # Create parent directory if it doesn't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Format timestamp for human-readable logs
        timestamp = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        
        # Format message
        message = f"[{timestamp}] [{entry.level.value}]"
        if entry.service:
            message += f" [{entry.service}]"
        message += f" {entry.message}"
        
        # Add context if available
        if entry.context:
            context_str = " ".join([f"{k}={v}" for k, v in entry.context.items()])
            message += f" ({context_str})"
            
        # Add performance info if available
        if entry.operation and entry.duration_ms is not None:
            message += f" [operation={entry.operation}, duration={entry.duration_ms:.2f}ms]"
            
        # Add error info if available
        if entry.error:
            message += f" [error={entry.error}]"
            
        # Write to file (append mode)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(message + "\n")
            
    def _write_json_log(self, entry: LogEntry, file_path: Path) -> None:
        """Write log entry to JSON file."""
        # Create parent directory if it doesn't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert entry to dictionary
        entry_dict = entry.to_dict()
        
        # Write to file (append mode)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry_dict) + "\n")
            
    def set_level(self, level: Union[LogLevel, str]) -> None:
        """
        Set the log level.
        
        Args:
            level: New log level
            
        Raises:
            ValueError: If invalid log level is provided
        """
        if isinstance(level, str):
            try:
                self.level = LogLevel[level.upper()]
            except KeyError:
                valid_levels = ", ".join([l.name for l in LogLevel])
                raise ValueError(f"Invalid log level: {level}. Valid levels are: {valid_levels}")
        else:
            self.level = level
            
        # Update Python logger level
        self._logger.setLevel(self._get_python_log_level(self.level))
        
    def with_context(self, **context: Any) -> 'ContextLogger':
        """
        Create a new logger with additional context.
        
        Args:
            **context: Context key-value pairs
            
        Returns:
            ContextLogger with the specified context
        """
        return ContextLogger(self, context)
        
    def log(
        self,
        level: LogLevel,
        message: str,
        service: Optional[str] = None,
        operation: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error: Optional[Union[str, Exception]] = None,
        **context: Any
    ) -> None:
        """
        Log a message with the specified level and context.
        
        Args:
            level: Log level
            message: Log message
            service: Service name (optional)
            operation: Operation name for performance logging (optional)
            duration_ms: Operation duration in milliseconds (optional)
            error: Error message or exception (optional)
            **context: Additional context key-value pairs
        """
        if not self._should_log(level):
            return
            
        # Process error if it's an exception
        error_str = None
        if error is not None:
            if isinstance(error, Exception):
                error_str = f"{type(error).__name__}: {str(error)}"
            else:
                error_str = str(error)
                
        # Combine context
        combined_context = {**self._context, **context}
        
        # Create log entry
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc),
            level=level,
            message=message,
            context=combined_context,
            service=service,
            operation=operation,
            duration_ms=duration_ms,
            error=error_str
        )
        
        # Add to memory buffer
        self.memory_buffer.append(entry)
        
        # Write to files
        log_files = self._get_log_file_paths()
        self._write_to_file(entry, log_files["main"])
        self._write_to_file(entry, log_files["error"], error_only=True)
        self._write_json_log(entry, log_files["json"])
        
        # Log using Python's logging
        python_level = self._get_python_log_level(level)
        self._logger.log(python_level, message)
        
    def debug(self, message: str, **context: Any) -> None:
        """
        Log a debug message.
        
        Args:
            message: Log message
            **context: Context key-value pairs
        """
        self.log(LogLevel.DEBUG, message, **context)
        
    def info(self, message: str, **context: Any) -> None:
        """
        Log an info message.
        
        Args:
            message: Log message
            **context: Context key-value pairs
        """
        self.log(LogLevel.INFO, message, **context)
        
    def warning(self, message: str, **context: Any) -> None:
        """
        Log a warning message.
        
        Args:
            message: Log message
            **context: Context key-value pairs
        """
        self.log(LogLevel.WARNING, message, **context)
        
    def error(
        self,
        message: str,
        error: Optional[Union[str, Exception]] = None,
        **context: Any
    ) -> None:
        """
        Log an error message.
        
        Args:
            message: Log message
            error: Error message or exception (optional)
            **context: Context key-value pairs
        """
        self.log(LogLevel.ERROR, message, error=error, **context)
        
    def critical(
        self,
        message: str,
        error: Optional[Union[str, Exception]] = None,
        **context: Any
    ) -> None:
        """
        Log a critical message.
        
        Args:
            message: Log message
            error: Error message or exception (optional)
            **context: Context key-value pairs
        """
        self.log(LogLevel.CRITICAL, message, error=error, **context)
        
    def performance(
        self,
        operation: str,
        duration_ms: float,
        **context: Any
    ) -> None:
        """
        Log a performance metric.
        
        Args:
            operation: Operation name
            duration_ms: Operation duration in milliseconds
            **context: Context key-value pairs
        """
        self.log(
            LogLevel.INFO,
            f"Performance: {operation} completed in {duration_ms:.2f}ms",
            operation=operation,
            duration_ms=duration_ms,
            **context
        )
        
    def get_recent_logs(
        self,
        level: Optional[LogLevel] = None,
        limit: Optional[int] = None
    ) -> List[LogEntry]:
        """
        Get recent log entries from memory buffer.
        
        Args:
            level: Filter by log level (optional)
            limit: Maximum number of entries to return (optional)
            
        Returns:
            List of log entries
        """
        entries = self.memory_buffer.to_list()
        
        # Filter by level if specified
        if level is not None:
            entries = [e for e in entries if e.level == level]
            
        # Apply limit if specified
        if limit is not None:
            entries = entries[-limit:]
            
        return entries
        
    def rotate_logs(self) -> None:
        """
        Force log rotation.
        
        This method creates a new set of log files for the current day
        and cleans up old log files.
        """
        self._ensure_log_directory()
        self._cleanup_old_logs()


class ContextLogger:
    """
    Logger with additional context.
    
    This class wraps a StructuredLogger and adds additional context
    to all log messages.
    
    Attributes:
        _logger (StructuredLogger): Parent logger
        _context (Dict): Context data to include with all log entries
    """
    
    def __init__(self, logger: StructuredLogger, context: Dict[str, Any]):
        """
        Initialize a new context logger.
        
        Args:
            logger: Parent logger
            context: Context data to include with all log entries
        """
        self._logger = logger
        self._context = context
        
    def with_context(self, **context: Any) -> 'ContextLogger':
        """
        Create a new logger with additional context.
        
        Args:
            **context: Additional context key-value pairs
            
        Returns:
            ContextLogger with combined context
        """
        combined_context = {**self._context, **context}
        return ContextLogger(self._logger, combined_context)
        
    def log(
        self,
        level: LogLevel,
        message: str,
        service: Optional[str] = None,
        operation: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error: Optional[Union[str, Exception]] = None,
        **context: Any
    ) -> None:
        """
        Log a message with the specified level and context.
        
        Args:
            level: Log level
            message: Log message
            service: Service name (optional)
            operation: Operation name for performance logging (optional)
            duration_ms: Operation duration in milliseconds (optional)
            error: Error message or exception (optional)
            **context: Additional context key-value pairs
        """
        combined_context = {**self._context, **context}
        self._logger.log(
            level,
            message,
            service=service,
            operation=operation,
            duration_ms=duration_ms,
            error=error,
            **combined_context
        )
        
    def debug(self, message: str, **context: Any) -> None:
        """
        Log a debug message.
        
        Args:
            message: Log message
            **context: Additional context key-value pairs
        """
        self.log(LogLevel.DEBUG, message, **context)
        
    def info(self, message: str, **context: Any) -> None:
        """
        Log an info message.
        
        Args:
            message: Log message
            **context: Additional context key-value pairs
        """
        self.log(LogLevel.INFO, message, **context)
        
    def warning(self, message: str, **context: Any) -> None:
        """
        Log a warning message.
        
        Args:
            message: Log message
            **context: Additional context key-value pairs
        """
        self.log(LogLevel.WARNING, message, **context)
        
    def error(
        self,
        message: str,
        error: Optional[Union[str, Exception]] = None,
        **context: Any
    ) -> None:
        """
        Log an error message.
        
        Args:
            message: Log message
            error: Error message or exception (optional)
            **context: Additional context key-value pairs
        """
        self.log(LogLevel.ERROR, message, error=error, **context)
        
    def critical(
        self,
        message: str,
        error: Optional[Union[str, Exception]] = None,
        **context: Any
    ) -> None:
        """
        Log a critical message.
        
        Args:
            message: Log message
            error: Error message or exception (optional)
            **context: Additional context key-value pairs
        """
        self.log(LogLevel.CRITICAL, message, error=error, **context)
        
    def performance(
        self,
        operation: str,
        duration_ms: float,
        **context: Any
    ) -> None:
        """
        Log a performance metric.
        
        Args:
            operation: Operation name
            duration_ms: Operation duration in milliseconds
            **context: Additional context key-value pairs
        """
        self.log(
            LogLevel.INFO,
            f"Performance: {operation} completed in {duration_ms:.2f}ms",
            operation=operation,
            duration_ms=duration_ms,
            **context
        )


def timed(operation_name: str) -> Callable[[F], F]:
    """
    Decorator to time function execution and log performance.
    
    Args:
        operation_name: Name of the operation for logging
        
    Returns:
        Decorated function
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get logger from first argument if it's a class method
            logger = None
            if args and hasattr(args[0], 'logger') and isinstance(args[0].logger, StructuredLogger):
                logger = args[0].logger
                
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000
                
                # Log performance if logger is available
                if logger:
                    logger.performance(operation_name, duration_ms)
                    
        return cast(F, wrapper)
    return decorator