"""
Memory usage monitoring and optimization.

This module provides tools for monitoring memory usage, detecting memory leaks,
and optimizing memory usage through garbage collection and other techniques.
"""

import gc
import os
import sys
import time
import logging
import asyncio
import tracemalloc
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("performance.memory")

@dataclass
class MemoryAlert:
    """Memory usage alert with context information."""
    
    timestamp: datetime
    usage_mb: float
    threshold_mb: float
    context: Dict[str, Any] = field(default_factory=dict)
    
    def __str__(self) -> str:
        """Format alert as string."""
        return f"Memory Alert: {self.usage_mb:.2f}MB (threshold: {self.threshold_mb:.2f}MB)"


class MemoryMonitor:
    """
    Memory usage monitoring and optimization.
    
    This class provides tools for monitoring memory usage, detecting memory leaks,
    and optimizing memory usage through garbage collection and other techniques.
    
    Attributes:
        warning_threshold: Memory usage threshold for warnings (MB)
        critical_threshold: Memory usage threshold for critical alerts (MB)
        check_interval: Interval between memory checks (seconds)
        logger: Logger instance
    """
    
    def __init__(
        self,
        warning_threshold: float = 100.0,
        critical_threshold: float = 200.0,
        check_interval: int = 60,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize memory monitor.
        
        Args:
            warning_threshold: Memory usage threshold for warnings (MB)
            critical_threshold: Memory usage threshold for critical alerts (MB)
            check_interval: Interval between memory checks (seconds)
            logger: Logger instance (creates one if None)
        """
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.check_interval = check_interval
        self.logger = logger or logging.getLogger("performance.memory")
        
        # Internal state
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False
        self._recent_alerts: List[MemoryAlert] = []
        self._peak_memory = 0.0
        self._last_check = 0.0
        self._tracemalloc_enabled = False
        
        # Statistics
        self._stats = {
            "checks": 0,
            "warnings": 0,
            "critical_alerts": 0,
            "gc_collections": 0,
            "memory_saved_mb": 0.0
        }
    
    async def start_monitoring(self) -> None:
        """Start memory monitoring task."""
        if self._running:
            return
            
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitor_memory())
        
        self.logger.info(
            f"Memory monitoring started (warning: {self.warning_threshold}MB, "
            f"critical: {self.critical_threshold}MB, interval: {self.check_interval}s)"
        )
    
    async def stop_monitoring(self) -> None:
        """Stop memory monitoring task."""
        if not self._running:
            return
            
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
            
        self.logger.info("Memory monitoring stopped")
    
    async def _monitor_memory(self) -> None:
        """Periodic memory monitoring task."""
        while self._running:
            try:
                # Check memory usage
                memory_usage = self._get_memory_usage()
                self._stats["checks"] += 1
                self._last_check = time.time()
                
                # Update peak memory
                if memory_usage > self._peak_memory:
                    self._peak_memory = memory_usage
                
                # Check thresholds
                self._check_memory_thresholds(memory_usage)
                
                # Wait for next check
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                self.logger.debug("Memory monitoring task cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in memory monitoring: {str(e)}", exc_info=True)
                await asyncio.sleep(self.check_interval)  # Wait before retrying
    
    def _check_memory_thresholds(self, memory_usage: float) -> None:
        """
        Check memory usage against thresholds and trigger alerts if needed.
        
        Args:
            memory_usage: Current memory usage in MB
        """
        if memory_usage > self.critical_threshold:
            # Critical alert
            self._stats["critical_alerts"] += 1
            alert = MemoryAlert(
                timestamp=datetime.now(),
                usage_mb=memory_usage,
                threshold_mb=self.critical_threshold,
                context={"level": "CRITICAL"}
            )
            self._recent_alerts.append(alert)
            
            # Log alert
            self.logger.critical(
                f"Critical memory usage: {memory_usage:.2f}MB "
                f"(threshold: {self.critical_threshold:.2f}MB)"
            )
            
            # Trigger garbage collection
            saved = self._trigger_gc()
            
            # Log garbage collection results
            self.logger.info(f"Emergency garbage collection freed {saved:.2f}MB")
            
        elif memory_usage > self.warning_threshold:
            # Warning alert
            self._stats["warnings"] += 1
            alert = MemoryAlert(
                timestamp=datetime.now(),
                usage_mb=memory_usage,
                threshold_mb=self.warning_threshold,
                context={"level": "WARNING"}
            )
            self._recent_alerts.append(alert)
            
            # Log alert
            self.logger.warning(
                f"High memory usage: {memory_usage:.2f}MB "
                f"(threshold: {self.warning_threshold:.2f}MB)"
            )
            
            # Consider garbage collection if significantly over threshold
            if memory_usage > self.warning_threshold * 1.5:
                saved = self._trigger_gc()
                self.logger.info(f"Preventive garbage collection freed {saved:.2f}MB")
        
        # Keep only recent alerts (last 10)
        if len(self._recent_alerts) > 10:
            self._recent_alerts = self._recent_alerts[-10:]
    
    def _get_memory_usage(self) -> float:
        """
        Get current memory usage in MB.
        
        Returns:
            float: Memory usage in MB
        """
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            return memory_info.rss / (1024 * 1024)  # Convert to MB
        except ImportError:
            # Fallback if psutil is not available
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == 'darwin':
                # macOS returns bytes
                return usage / 1024  # Convert to MB
            else:
                # Linux returns KB
                return usage / 1024  # Convert to MB
    
    def _trigger_gc(self) -> float:
        """
        Trigger garbage collection to free memory.
        
        Returns:
            float: Amount of memory freed in MB
        """
        # Get memory usage before GC
        before = self._get_memory_usage()
        
        # Disable garbage collection during manual collection
        gc_enabled = gc.isenabled()
        if gc_enabled:
            gc.disable()
        
        try:
            # Run garbage collection
            gc.collect(2)  # Full collection
            self._stats["gc_collections"] += 1
        finally:
            # Restore previous garbage collection state
            if gc_enabled:
                gc.enable()
        
        # Get memory usage after GC
        after = self._get_memory_usage()
        
        # Calculate memory saved
        saved = max(0, before - after)
        self._stats["memory_saved_mb"] += saved
        
        return saved
    
    def start_tracemalloc(self) -> None:
        """Start detailed memory allocation tracking."""
        if not self._tracemalloc_enabled:
            tracemalloc.start()
            self._tracemalloc_enabled = True
            self.logger.info("Tracemalloc memory tracking enabled")
    
    def stop_tracemalloc(self) -> None:
        """Stop detailed memory allocation tracking."""
        if self._tracemalloc_enabled:
            tracemalloc.stop()
            self._tracemalloc_enabled = False
            self.logger.info("Tracemalloc memory tracking disabled")
    
    def get_memory_snapshot(self) -> Optional[tracemalloc.Snapshot]:
        """
        Get current memory allocation snapshot.
        
        Returns:
            tracemalloc.Snapshot or None if tracemalloc is not enabled
        """
        if not self._tracemalloc_enabled:
            return None
        
        return tracemalloc.take_snapshot()
    
    def compare_snapshots(self, old_snapshot: tracemalloc.Snapshot, new_snapshot: tracemalloc.Snapshot) -> List[Tuple]:
        """
        Compare two memory snapshots to find memory leaks.
        
        Args:
            old_snapshot: Previous memory snapshot
            new_snapshot: Current memory snapshot
            
        Returns:
            List of (size_diff, traceback) tuples sorted by size difference
        """
        if not self._tracemalloc_enabled:
            return []
        
        # Get top differences
        statistics = new_snapshot.compare_to(old_snapshot, 'traceback')
        
        # Return top differences
        return [(stat.size_diff, stat.traceback) for stat in statistics[:10]]
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get memory statistics.
        
        Returns:
            Dict with memory statistics
        """
        return {
            "current_usage_mb": self._get_memory_usage(),
            "peak_usage_mb": self._peak_memory,
            "warning_threshold_mb": self.warning_threshold,
            "critical_threshold_mb": self.critical_threshold,
            "checks": self._stats["checks"],
            "warnings": self._stats["warnings"],
            "critical_alerts": self._stats["critical_alerts"],
            "gc_collections": self._stats["gc_collections"],
            "memory_saved_mb": self._stats["memory_saved_mb"],
            "tracemalloc_enabled": self._tracemalloc_enabled,
            "last_check": self._last_check
        }
    
    def get_recent_alerts(self) -> List[MemoryAlert]:
        """
        Get recent memory alerts.
        
        Returns:
            List of recent memory alerts
        """
        return list(self._recent_alerts)
    
    def get_memory_report(self) -> str:
        """
        Get formatted memory usage report.
        
        Returns:
            str: Formatted memory report
        """
        current = self._get_memory_usage()
        stats = self.get_memory_stats()
        
        report = [
            "Memory Usage Report",
            "===================",
            f"Current Usage: {current:.2f}MB",
            f"Peak Usage: {stats['peak_usage_mb']:.2f}MB",
            f"Warning Threshold: {self.warning_threshold:.2f}MB",
            f"Critical Threshold: {self.critical_threshold:.2f}MB",
            "",
            "Statistics:",
            f"- Memory Checks: {stats['checks']}",
            f"- Warning Alerts: {stats['warnings']}",
            f"- Critical Alerts: {stats['critical_alerts']}",
            f"- GC Collections: {stats['gc_collections']}",
            f"- Memory Saved: {stats['memory_saved_mb']:.2f}MB",
            "",
            "Recent Alerts:"
        ]
        
        # Add recent alerts
        for alert in self._recent_alerts:
            report.append(
                f"- {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}: "
                f"{alert.usage_mb:.2f}MB ({alert.context.get('level', 'ALERT')})"
            )
        
        if not self._recent_alerts:
            report.append("- No recent alerts")
        
        return "\n".join(report)

# Global memory monitor instance
memory_monitor = MemoryMonitor()