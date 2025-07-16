# =============================================================================
# StatsBot - Tree Style Logging Module
# =============================================================================
# Professional-grade logging system that creates beautiful, hierarchical logs
# with perfect tree structure, timestamps, and multi-destination output.
# Originally designed for StatsBot but usable in any Python project.
#
# Key Features:
# - Beautiful tree-style log formatting
# - Multi-destination logging (console, files, JSON)
# - Perfect tree structure with proper indentation
# - Timezone-aware timestamps (EST/UTC)
# - Structured JSON log output
# - Emoji support for visual categorization
# - Run ID tracking for session management
#
# Technical Implementation:
# - Stack-based tree structure tracking
# - Atomic file writes for log persistence
# - Timezone handling with pytz
# - JSON serialization for structured logs
# - Unicode symbol management
#
# Log Structure:
# /logs/
#   YYYY-MM-DD/
#     - logs.log    - All log messages
#     - errors.log  - Only ERROR and CRITICAL messages
#     - logs.json   - Structured JSON format
#
# Required Dependencies:
# - pytz: Timezone handling
# =============================================================================

import logging
import os
from datetime import datetime, timezone, timedelta
import uuid
import json
from pathlib import Path

class TreeLogger:
    def __init__(self):
        # Use fixed EST timezone (UTC-5) instead of US/Eastern
        self.est_tz = timezone(timedelta(hours=-5))  # Always EST, never EDT
        self.start_time = datetime.now(self.est_tz)  # Add start_time
        self.log_dir = "logs"
        self.run_id = self._generate_run_id()
        
        # Create log directory for today
        self.today_dir = os.path.join(self.log_dir, datetime.now(self.est_tz).strftime("%Y-%m-%d"))
        os.makedirs(self.today_dir, exist_ok=True)
        
        # Set up logging
        self._setup_logging()
        
    def _setup_logging(self):
        """Set up logging handlers for different log files."""
        # Create formatters with fixed EST timezone
        log_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%m/%d %I:%M %p EST'
        )
        
        # Get root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Remove any existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        root_logger.addHandler(console_handler)
        
        # Main log file handler (logs.log)
        main_log_file = os.path.join(self.today_dir, "logs.log")
        main_file_handler = logging.FileHandler(main_log_file, encoding='utf-8')
        main_file_handler.setFormatter(log_formatter)
        root_logger.addHandler(main_file_handler)
        
        # Error log file handler (errors.log)
        error_log_file = os.path.join(self.today_dir, "errors.log")
        error_file_handler = logging.FileHandler(error_log_file, encoding='utf-8')
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(log_formatter)
        root_logger.addHandler(error_file_handler)
        
        # JSON log file handler
        self.json_log_path = os.path.join(self.today_dir, "logs.json")
        
    def _generate_run_id(self):
        """Generate a unique run ID."""
        return uuid.uuid4().hex[:8].upper()
        
    def _get_run_duration(self):
        """Calculate the duration of the current run."""
        end_time = datetime.now(self.est_tz)
        duration = end_time - self.start_time
        
        # Format duration nicely
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
        
    def format_time(self):
        """Format current time in fixed EST timezone (UTC-5)."""
        now = datetime.now(self.est_tz)
        return now.strftime("%m/%d %I:%M %p EST")  # Always show EST
        
    def _write_json_log(self, level: str, category: str, message: str, **extra):
        """Write a log entry to the JSON log file."""
        log_entry = {
            "timestamp": f"[{self.format_time()}]",
            "level": level,
            "category": category,
            "message": message,
            "run_id": self.run_id,
            "iso_datetime": datetime.now(self.est_tz).isoformat(),
            **extra
        }
        
        with open(self.json_log_path, 'a') as f:
            json.dump(log_entry, f)
            f.write('\n')
            
    def log_section(self, title, items, emoji=""):
        """Log a section with items in tree format."""
        logger = logging.getLogger()
        
        # Add spacing before section (two blank lines)
        logger.info("")
        logger.info("")
        
        # Log section header
        header = f"{emoji} {title}"
        logger.info(header)
        self._write_json_log("INFO", "perfect_tree_section", header)
        
        # Log items in tree format
        for i, (key, value) in enumerate(items):
            prefix = "└─" if i == len(items) - 1 else "├─"
            item_msg = f"{prefix} {key}: {value}"
            logger.info(item_msg)
            self._write_json_log("INFO", "tree_item", item_msg)
            
    def log_run_header(self, bot_name, version):
        """Log run header with bot info and unique run ID."""
        logger = logging.getLogger()
        date_str = datetime.now(self.est_tz).strftime("%Y-%m-%d")
        
        # Add visual separator for new run (except for the very first entry of the day)
        log_file_path = os.path.join(self.today_dir, "logs.log")
        if os.path.exists(log_file_path) and os.path.getsize(log_file_path) > 0:
            # Add separator lines for new run
            logger.info("")
            logger.info("=" * 80)
            logger.info(f"🔄 NEW BOT RUN SESSION - {self.format_time()}")
            logger.info("=" * 80)
            logger.info("")
        
        # Create and log header info (no extra spacing for the first entry)
        header = f"🎯 {bot_name} v{version} - Run ID: {self.run_id}"
        logger.info(header)
        self._write_json_log("INFO", "run_header", header)
        
        items = [
            ("started_at", f"[{self.format_time()}]"),
            ("version", version),
            ("run_id", self.run_id),
            ("log_session", date_str)
        ]
        
        for i, (key, value) in enumerate(items):
            prefix = "└─" if i == len(items) - 1 else "├─"
            item_msg = f"{prefix} {key}: {value}"
            logger.info(item_msg)
            self._write_json_log("INFO", "run_header", item_msg)
            
    def log_run_end(self, reason="Normal shutdown"):
        """Log run end with run ID and reason."""
        logger = logging.getLogger()
        
        # Create and log end info
        header = f"🏁 Bot Run Ended - Run ID: {self.run_id}"
        logger.info("")  # Add spacing
        logger.info("")  # Add spacing
        logger.info(header)
        self._write_json_log("INFO", "run_end", header)
        
        items = [
            ("ended_at", f"[{self.format_time()}]"),
            ("reason", reason),
            ("run_id", self.run_id),
            ("duration", self._get_run_duration())
        ]
        
        for i, (key, value) in enumerate(items):
            prefix = "└─" if i == len(items) - 1 else "├─"
            item_msg = f"{prefix} {key}: {value}"
            logger.info(item_msg)
            self._write_json_log("INFO", "run_end", item_msg)
        
        # Add final separator
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"🔚 END OF SESSION {self.run_id} - {self.format_time()}")
        logger.info("=" * 80)
        logger.info("")

def log_perfect_tree_section(title, items, emoji=""):
    """Log a perfect tree section with proper spacing."""
    logger = TreeLogger()
    log = logging.getLogger()
    
    # Add spacing before section (two blank lines)
    log.info("")
    log.info("")
    
    # Log section header
    header = f"{emoji} {title}"
    log.info(header)
    logger._write_json_log("INFO", "perfect_tree_section", header)
    
    # Log items in tree format
    for i, (key, value) in enumerate(items):
        prefix = "└─" if i == len(items) - 1 else "├─"
        item_msg = f"{prefix} {key}: {value}"
        log.info(item_msg)
        logger._write_json_log("INFO", "tree_item", item_msg)

def log_error_with_traceback(message, error, level="ERROR"):
    """Log an error with its traceback if available."""
    logger = TreeLogger()
    log = logging.getLogger()
    
    error_msg = f"❌ {level}: {message}"
    if level == "ERROR":
        log.error(error_msg)
    elif level == "CRITICAL":
        log.critical(error_msg)
    else:
        log.warning(error_msg)
        
    logger._write_json_log(level, "error", error_msg)
    
    if error:
        error_detail = f"└─ {type(error).__name__}: {str(error)}"
        log.error(error_detail)
        logger._write_json_log(level, "error_detail", error_detail)
        
        if hasattr(error, '__traceback__'):
            import traceback
            tb_lines = traceback.format_tb(error.__traceback__)
            for line in tb_lines:
                tb_msg = f"   {line.strip()}"
                log.error(tb_msg)
                logger._write_json_log(level, "traceback", tb_msg)

def log_run_header(bot_name, version):
    """Log a run header."""
    logger = TreeLogger()
    return logger.log_run_header(bot_name, version)

def log_run_end(reason="Normal shutdown"):
    """Log a run end."""
    logger = TreeLogger()
    return logger.log_run_end(reason)
