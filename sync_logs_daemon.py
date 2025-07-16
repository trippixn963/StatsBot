#!/usr/bin/env python3
"""
StatsBot Log Sync Daemon
Continuously syncs logs from VPS to local Mac with recovery and monitoring.
"""

import os
import sys
import time
import signal
import subprocess
import logging
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import threading
import pytz
from typing import Optional, Dict, Any

class LogSyncDaemon:
    def __init__(self):
        # Use fixed EST timezone (UTC-5)
        self.est_tz = timezone(timedelta(hours=-5))
        self.vps_host = "root@159.89.90.90"
        self.vps_path = "/opt/DiscordBots/StatsBot/logs/"
        self.local_path = "./logs/"
        self.sync_interval = 10  # seconds
        self.running = False
        self.stats = {
            'syncs_completed': 0,
            'syncs_failed': 0,
            'last_sync': None,
            'errors': [],
            'uptime_start': datetime.now(self.est_tz)
        }
        
        # Setup logging
        self.setup_logging()
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        self.logger.info("🚀 StatsBot Log Sync Daemon Started")
        self.logger.info(f"├─ VPS: {self.vps_host}")
        self.logger.info(f"├─ Remote Path: {self.vps_path}")
        self.logger.info(f"├─ Local Path: {self.local_path}")
        self.logger.info(f"└─ Sync Interval: {self.sync_interval}s")

    def setup_logging(self):
        """Setup logging configuration using the same structure as main bot."""
        # Setup main logger
        self.logger = logging.getLogger('LogSyncDaemon')
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Create formatters with fixed EST timezone
        log_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%m/%d %I:%M %p EST'
        )
        
        # Main log file handler (logs.log)
        main_log_file = os.path.join(self.today_dir, "logs.log")
        main_file_handler = logging.FileHandler(main_log_file, mode='a', encoding='utf-8')
        main_file_handler.setFormatter(log_formatter)
        self.logger.addHandler(main_file_handler)
        
        # Error log file handler (errors.log)  
        error_log_file = os.path.join(self.today_dir, "errors.log")
        error_file_handler = logging.FileHandler(error_log_file, mode='a', encoding='utf-8')
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(log_formatter)
        self.logger.addHandler(error_file_handler)
        
        # Console handler for debugging
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        self.logger.addHandler(console_handler)
        
        # Setup JSON logger for structured logs (logs.json)
        self.json_log_file = os.path.join(self.today_dir, "logs.json")

    def write_json_log(self, level: str, category: str, message: str):
        """Write structured JSON log entry."""
        try:
            now = datetime.now(self.est_tz)
            tz_abbrev = now.strftime('%Z')
            log_entry = {
                "timestamp": f"[{now.strftime(f'%m/%d %I:%M %p {tz_abbrev}')}]",
                "level": level,
                "category": category,
                "message": message,
                "daemon": "logsync",
                "iso_datetime": now.isoformat()
            }
            
            with open(self.json_log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            # Fallback - don't let JSON logging break the main functionality
            pass

    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        self.logger.info(f"🛑 Received {signal_name}, shutting down gracefully...")
        self.write_json_log("INFO", "daemon_shutdown", f"Received {signal_name}")
        self.running = False

    def test_ssh_connection(self) -> bool:
        """Test SSH connection to VPS."""
        try:
            cmd = [
                "ssh", "-i", self.ssh_key, 
                "-o", "ConnectTimeout=10",
                "-o", "BatchMode=yes",
                f"{self.vps_user}@{self.vps_host}",
                "echo 'Connection test successful'"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"SSH connection test failed: {e}")
            self.write_json_log("ERROR", "ssh_test", f"Connection test failed: {e}")
            return False

    def sync_logs(self) -> bool:
        """Sync logs from VPS to local machine."""
        try:
            # Ensure local log directory exists
            os.makedirs(self.local_log_path, exist_ok=True)
            
            # Build rsync command
            cmd = [
                "rsync", "-avz", "--delete",
                "-e", f"ssh -i {self.ssh_key} -o ConnectTimeout=30",
                f"{self.vps_user}@{self.vps_host}:{self.vps_log_path}/",
                f"{self.local_log_path}/"
            ]
            
            # Execute rsync
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                self.sync_stats["successful_syncs"] += 1
                self.consecutive_failures = 0
                self.last_sync_time = datetime.now()
                
                # Log sync success (only every 10th success to avoid spam)
                if self.sync_stats["successful_syncs"] % 10 == 0:
                    self.logger.info(f"✅ Log sync successful (#{self.sync_stats['successful_syncs']})")
                    self.write_json_log("INFO", "sync_success", f"Sync #{self.sync_stats['successful_syncs']} completed")
                
                return True
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                self.logger.error(f"❌ rsync failed: {error_msg}")
                self.write_json_log("ERROR", "sync_failed", error_msg)
                self.sync_stats["failed_syncs"] += 1
                self.sync_stats["last_error"] = error_msg
                self.consecutive_failures += 1
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("❌ rsync timed out")
            self.write_json_log("ERROR", "sync_timeout", "rsync operation timed out")
            self.sync_stats["failed_syncs"] += 1
            self.sync_stats["last_error"] = "Timeout"
            self.consecutive_failures += 1
            return False
        except Exception as e:
            self.logger.error(f"❌ Sync error: {e}")
            self.write_json_log("ERROR", "sync_error", str(e))
            self.sync_stats["failed_syncs"] += 1
            self.sync_stats["last_error"] = str(e)
            self.consecutive_failures += 1
            return False

    def check_vps_bot_status(self) -> Dict[str, Any]:
        """Check the status of the bot on the VPS."""
        try:
            cmd = [
                "ssh", "-i", self.ssh_key,
                "-o", "ConnectTimeout=10",
                f"{self.vps_user}@{self.vps_host}",
                "systemctl is-active statsbot && systemctl show statsbot --property=MainPID,ActiveState,LoadState"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                status = lines[0].strip() if lines else "unknown"
                
                bot_info = {"status": status, "active": status == "active"}
                for line in lines[1:]:
                    if '=' in line:
                        key, value = line.split('=', 1)
                        bot_info[key.lower()] = value
                
                return bot_info
            else:
                return {"status": "error", "active": False, "error": result.stderr.strip()}
                
        except Exception as e:
            return {"status": "connection_error", "active": False, "error": str(e)}

    def log_status_report(self):
        """Log periodic status report."""
        uptime = datetime.now() - self.sync_stats["start_time"]
        uptime_str = str(uptime).split('.')[0]  # Remove microseconds
        
        bot_status = self.check_vps_bot_status()
        
        self.logger.info("📊 Status Report")
        self.logger.info(f"├─ Daemon Uptime: {uptime_str}")
        self.logger.info(f"├─ Total Syncs: {self.sync_stats['total_syncs']}")
        self.logger.info(f"├─ Successful: {self.sync_stats['successful_syncs']}")
        self.logger.info(f"├─ Failed: {self.sync_stats['failed_syncs']}")
        self.logger.info(f"├─ Consecutive Failures: {self.consecutive_failures}")
        self.logger.info(f"├─ Last Sync: {self.last_sync_time.strftime('%I:%M:%S %p') if self.last_sync_time else 'Never'}")
        self.logger.info(f"├─ VPS Bot Status: {bot_status.get('status', 'unknown')}")
        self.logger.info(f"└─ Bot Active: {'Yes' if bot_status.get('active') else 'No'}")
        
        # Write status to JSON log
        self.write_json_log("INFO", "status_report", f"Uptime: {uptime_str}, Syncs: {self.sync_stats['successful_syncs']}/{self.sync_stats['total_syncs']}")
        
        if self.sync_stats["last_error"]:
            self.logger.warning(f"⚠️  Last Error: {self.sync_stats['last_error']}")

    def recovery_procedure(self):
        """Attempt to recover from connection issues."""
        self.logger.warning(f"🔧 Attempting recovery (failure #{self.consecutive_failures})")
        self.write_json_log("WARNING", "recovery_attempt", f"Recovery attempt #{self.consecutive_failures}")
        
        # Test SSH connection
        if not self.test_ssh_connection():
            self.logger.error("❌ SSH connection test failed")
            return False
        
        # Check VPS bot status
        bot_status = self.check_vps_bot_status()
        if not bot_status.get("active"):
            self.logger.warning(f"⚠️  VPS bot is not active: {bot_status.get('status')}")
            # Could add bot restart logic here if needed
        
        self.logger.info("✅ Recovery checks completed")
        self.write_json_log("INFO", "recovery_complete", "Recovery checks passed")
        return True

    def run(self):
        """Main daemon loop."""
        status_report_interval = 300  # 5 minutes
        last_status_report = time.time()
        
        try:
            while self.running:
                # Update stats
                self.sync_stats["total_syncs"] += 1
                
                # Perform sync
                sync_success = self.sync_logs()
                
                # Handle consecutive failures
                if self.consecutive_failures >= 3 and self.consecutive_failures % 3 == 0:
                    if not self.recovery_procedure():
                        # Exponential backoff for severe failures
                        backoff_time = min(300, self.retry_delay * (2 ** (self.consecutive_failures // 3)))
                        self.logger.warning(f"⏳ Backing off for {backoff_time}s due to consecutive failures")
                        time.sleep(backoff_time)
                        continue
                
                # Periodic status report
                current_time = time.time()
                if current_time - last_status_report >= status_report_interval:
                    self.log_status_report()
                    last_status_report = current_time
                
                # Sleep before next sync
                if self.running:
                    time.sleep(self.sync_interval)
                    
        except KeyboardInterrupt:
            self.logger.info("🛑 Received keyboard interrupt")
        except Exception as e:
            self.logger.error(f"💥 Unexpected error: {e}")
            self.write_json_log("ERROR", "daemon_error", str(e))
        finally:
            self.shutdown()

    def shutdown(self):
        """Clean shutdown procedures."""
        self.logger.info("🏁 Shutting down log sync daemon")
        
        # Final status report
        uptime = datetime.now() - self.sync_stats["start_time"]
        self.logger.info(f"├─ Total Runtime: {str(uptime).split('.')[0]}")
        self.logger.info(f"├─ Total Syncs: {self.sync_stats['total_syncs']}")
        self.logger.info(f"├─ Success Rate: {(self.sync_stats['successful_syncs']/max(1,self.sync_stats['total_syncs'])*100):.1f}%")
        self.logger.info(f"└─ Final Status: Graceful shutdown")
        
        # Write final JSON log
        self.write_json_log("INFO", "daemon_shutdown", f"Graceful shutdown after {str(uptime).split('.')[0]}")
        
        self.running = False

def main():
    """Main entry point."""
    daemon = LogSyncDaemon()
    daemon.run()

if __name__ == "__main__":
    main() 