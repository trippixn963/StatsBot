"""
Memory usage monitoring and alerting for resource-constrained environments.

This module provides tools for monitoring memory usage, setting up alerts
for high memory usage, and implementing memory optimization strategies.
"""

import os
import gc
import psutil
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import threading
import weakref

from src.types.models import MemoryStats, ResourceUsage
from src.utils.logging.structured_logger import StructuredLogger


class MemoryMonitor:
    """
    Memory usage monitor with alerting capabilities.
    
    This class provides tools for monitoring memory usage, setting up alerts
    for high memory usage, and implementing memory optimization strategies.
    It can run in the background and trigger alerts or cleanup actions when
    memory usage exceeds configured thresholds.
    
    Attributes:
        warning_threshold: Percentage at which to log memory warnings
        critical_threshold: Percentage at which to trigger cleanup
        check_interval: Seconds between memory checks
        logger: Logger for memory-related messages
        _running: Whether the monitor is currently running
        _monitor_task: Background task for memory monitoring
    """
    
    def __init__(
        self,
        warning_threshold: float = 75.0,
        critical_threshold: float = 90.0,
        check_interval: int = 60,
        logger: Optional[StructuredLogger] = None
    ):
        """
        Initialize a new memory monitor.
        
        Args:
            warning_threshold: Percentage at which to log memory warnings
            critical_threshold: Percentage at which to trigger cleanup
            check_interval: Seconds between memory checks
            logger: Logger for memory-related messages
        """
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.check_interval = check_interval
        self.logger = logger or logging.getLogger(__name__)
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._process = psutil.Process(os.getpid())
        self._cleanup_callbacks: List[Callable[[], None]] = []
        self._memory_history: List[MemoryStats] = []
        self._history_lock = threading.Lock()
        self._max_history_size = 100  # Keep last 100 measurements
        
    def get_memory_stats(self) -> MemoryStats:
        """
        Get current memory usage statistics.
        
        Returns:
            MemoryStats object with current memory metrics
        """
        vm = psutil.virtual_memory()
        
        stats = MemoryStats(
            total_bytes=vm.total,
            used_bytes=vm.used,
            available_bytes=vm.available,
            percent_used=vm.percent,
            timestamp=datetime.now()
        )
        
        # Add to history with lock to prevent race conditions
        with self._history_lock:
            self._memory_history.append(stats)
            if len(self._memory_history) > self._max_history_size:
                self._memory_history = self._memory_history[-self._max_history_size:]
                
        return stats
        
    def get_process_memory_usage(self) -> Tuple[int, float]:
        """
        Get memory usage of the current process.
        
        Returns:
            Tuple of (memory_bytes, memory_percent)
        """
        vm = psutil.virtual_memory()
        process_memory = self._process.memory_info().rss
        process_percent = (process_memory / vm.total) * 100
        return process_memory, process_percent
        
    def register_cleanup_callback(self, callback: Callable[[], None]) -> None:
        """
        Register a callback function to be called during cleanup operations.
        
        Args:
            callback: Function to call during cleanup
        """
        self._cleanup_callbacks.append(callback)
        
    async def start_monitoring(self) -> None:
        """Start the background memory monitoring task."""
        if self._running:
            return
            
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_memory())
        if hasattr(self.logger, 'info'):
            self.logger.info("Memory monitoring started")
        else:
            logging.info("Memory monitoring started")
            
    async def stop_monitoring(self) -> None:
        """Stop the memory monitoring task."""
        if not self._running:
            return
            
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
            
        if hasattr(self.logger, 'info'):
            self.logger.info("Memory monitoring stopped")
        else:
            logging.info("Memory monitoring stopped")
            
    async def _monitor_memory(self) -> None:
        """Background task that periodically checks memory usage and triggers alerts if needed."""
        while self._running:
            try:
                stats = self.get_memory_stats()
                process_memory, process_percent = self.get_process_memory_usage()
                
                # Log warning if memory usage is high
                if stats.percent_used > self.warning_threshold:
                    if hasattr(self.logger, 'warning'):
                        self.logger.warning(
                            f"High memory usage detected: {stats.percent_used:.1f}% "
                            f"(process: {process_percent:.1f}%)",
                            memory_percent=stats.percent_used,
                            process_percent=process_percent,
                            available_mb=stats.available_bytes / (1024 * 1024)
                        )
                    else:
                        logging.warning(
                            f"High memory usage detected: {stats.percent_used:.1f}% "
                            f"(process: {process_percent:.1f}%)"
                        )
                
                # Trigger cleanup if memory usage is critical
                if stats.percent_used > self.critical_threshold:
                    if hasattr(self.logger, 'warning'):
                        self.logger.warning(
                            f"Critical memory usage detected: {stats.percent_used:.1f}%, "
                            f"performing cleanup",
                            memory_percent=stats.percent_used,
                            process_percent=process_percent,
                            available_mb=stats.available_bytes / (1024 * 1024)
                        )
                    else:
                        logging.warning(
                            f"Critical memory usage detected: {stats.percent_used:.1f}%, "
                            f"performing cleanup"
                        )
                    await self.cleanup_memory()
                
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if hasattr(self.logger, 'error'):
                    self.logger.error(f"Error in memory monitoring: {e}", error=e)
                else:
                    logging.error(f"Error in memory monitoring: {e}")
                await asyncio.sleep(self.check_interval * 2)  # Longer delay on error
                
    async def cleanup_memory(self) -> None:
        """
        Perform memory cleanup operations.
        
        This includes running garbage collection and executing registered cleanup callbacks.
        """
        if hasattr(self.logger, 'info'):
            self.logger.info("Performing memory cleanup")
        else:
            logging.info("Performing memory cleanup")
            
        # Get memory usage before cleanup
        before_stats = self.get_memory_stats()
        before_process_memory, _ = self.get_process_memory_usage()
        
        # Run registered cleanup callbacks
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                if hasattr(self.logger, 'error'):
                    self.logger.error(f"Error in cleanup callback: {e}", error=e)
                else:
                    logging.error(f"Error in cleanup callback: {e}")
        
        # Force garbage collection
        gc.collect()
        
        # Get memory usage after cleanup
        after_stats = self.get_memory_stats()
        after_process_memory, _ = self.get_process_memory_usage()
        
        # Calculate memory freed
        memory_freed = before_process_memory - after_process_memory
        
        if hasattr(self.logger, 'info'):
            self.logger.info(
                f"Cleanup complete. Memory freed: {memory_freed / (1024 * 1024):.2f} MB. "
                f"Current usage: {after_stats.percent_used:.1f}%",
                memory_freed_mb=memory_freed / (1024 * 1024),
                current_percent=after_stats.percent_used,
                available_mb=after_stats.available_bytes / (1024 * 1024)
            )
        else:
            logging.info(
                f"Cleanup complete. Memory freed: {memory_freed / (1024 * 1024):.2f} MB. "
                f"Current usage: {after_stats.percent_used:.1f}%"
            )
            
    def get_memory_history(self) -> List[MemoryStats]:
        """
        Get historical memory usage data.
        
        Returns:
            List of MemoryStats objects
        """
        with self._history_lock:
            return list(self._memory_history)
            
    def get_memory_trend(self, minutes: int = 10) -> Dict[str, Any]:
        """
        Calculate memory usage trend over the specified time period.
        
        Args:
            minutes: Time period in minutes
            
        Returns:
            Dictionary with trend information
        """
        with self._history_lock:
            if not self._memory_history:
                return {
                    "trend": "stable",
                    "change_percent": 0.0,
                    "samples": 0
                }
                
            # Filter history by time
            cutoff_time = datetime.now().timestamp() - (minutes * 60)
            recent_history = [
                stats for stats in self._memory_history
                if stats.timestamp.timestamp() >= cutoff_time
            ]
            
            if len(recent_history) < 2:
                return {
                    "trend": "stable",
                    "change_percent": 0.0,
                    "samples": len(recent_history)
                }
                
            # Calculate trend
            first = recent_history[0].percent_used
            last = recent_history[-1].percent_used
            change = last - first
            
            trend = "stable"
            if change > 5.0:
                trend = "increasing"
            elif change < -5.0:
                trend = "decreasing"
                
            return {
                "trend": trend,
                "change_percent": change,
                "samples": len(recent_history),
                "first_value": first,
                "last_value": last,
                "min_value": min(stats.percent_used for stats in recent_history),
                "max_value": max(stats.percent_used for stats in recent_history),
                "avg_value": sum(stats.percent_used for stats in recent_history) / len(recent_history)
            }


class MemoryOptimizer:
    """
    Memory optimization strategies for resource-constrained environments.
    
    This class provides tools for optimizing memory usage, including
    weak references, object pooling, and memory-efficient data structures.
    """
    
    @staticmethod
    def use_weak_reference(obj: Any) -> weakref.ReferenceType:
        """
        Create a weak reference to an object.
        
        Weak references allow the garbage collector to collect the object
        if there are no strong references to it.
        
        Args:
            obj: Object to create a weak reference to
            
        Returns:
            Weak reference to the object
        """
        return weakref.ref(obj)
        
    @staticmethod
    def optimize_dict_memory(d: Dict) -> Dict:
        """
        Optimize memory usage of a dictionary.
        
        This method creates a copy of the dictionary with optimized memory usage.
        
        Args:
            d: Dictionary to optimize
            
        Returns:
            Optimized dictionary
        """
        return dict(d)  # This triggers dictionary resize
        
    @staticmethod
    def clear_unused_memory() -> None:
        """Force garbage collection and release memory to the OS."""
        gc.collect()
        
        # On some systems, this can release memory back to the OS
        if hasattr(gc, 'mem_free'):
            gc.mem_free()
            
    @staticmethod
    def get_object_size(obj: Any) -> int:
        """
        Get the approximate memory size of an object.
        
        Args:
            obj: Object to measure
            
        Returns:
            Size in bytes
        """
        import sys
        return sys.getsizeof(obj)
        
    @staticmethod
    def get_largest_objects(limit: int = 10) -> List[Tuple[Any, int]]:
        """
        Get the largest objects in memory.
        
        Note: This is an expensive operation and should only be used for debugging.
        
        Args:
            limit: Maximum number of objects to return
            
        Returns:
            List of (object, size) tuples
        """
        import sys
        import types
        
        # Get all objects
        objects = []
        for obj in gc.get_objects():
            try:
                if isinstance(obj, (types.ModuleType, type, types.FunctionType, types.MethodType)):
                    continue  # Skip common system objects
                size = sys.getsizeof(obj)
                objects.append((obj, size))
            except:
                pass
                
        # Sort by size (descending) and return top N
        objects.sort(key=lambda x: x[1], reverse=True)
        return objects[:limit]