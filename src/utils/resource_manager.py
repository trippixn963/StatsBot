"""
Resource manager for memory monitoring and cleanup.

This module provides utilities for monitoring memory usage and managing resources
efficiently, including automatic cleanup mechanisms.
"""

import os
import gc
import psutil
import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

from src.utils.cache.circular_buffer import CircularBuffer
from src.core.exceptions import ResourceExhaustionError
from src.utils.performance.memory_monitor import MemoryMonitor

@dataclass
class MemoryStats:
    """Container for memory usage statistics."""
    total_memory: int  # Total physical memory in bytes
    available_memory: int  # Available memory in bytes
    used_memory: int  # Used memory in bytes
    memory_percent: float  # Memory usage as percentage
    process_memory: int  # Current process memory usage in bytes
    process_percent: float  # Process memory as percentage of total


class ResourceManager:
    """
    Manages system resources and provides utilities for memory monitoring and cleanup.
    
    This class helps track resource usage, provides circular buffers for memory-efficient
    storage, and implements cleanup mechanisms to prevent resource exhaustion.
    """
    
    def __init__(self, 
                 memory_warning_threshold: float = 80.0,
                 memory_critical_threshold: float = 90.0,
                 cleanup_interval: int = 300):
        """
        Initialize the resource manager.
        
        Args:
            memory_warning_threshold: Percentage at which to log memory warnings
            memory_critical_threshold: Percentage at which to trigger cleanup
            cleanup_interval: Seconds between automatic cleanup checks
        """
        self._memory_warning_threshold = memory_warning_threshold
        self._memory_critical_threshold = memory_critical_threshold
        self._cleanup_interval = cleanup_interval
        self._logger = logging.getLogger(__name__)
        self._process = psutil.Process(os.getpid())
        self._registered_buffers: List[CircularBuffer] = []
        self._cleanup_callbacks: List[Callable[[], None]] = []
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Initialize memory monitor
        self._memory_monitor = MemoryMonitor(
            warning_threshold=memory_warning_threshold,
            critical_threshold=memory_critical_threshold,
            check_interval=cleanup_interval,
            logger=self._logger
        )
    
    def create_circular_buffer(self, size: int) -> CircularBuffer:
        """
        Create a memory-efficient circular buffer and register it for monitoring.
        
        Args:
            size: Maximum number of items to store in the buffer
            
        Returns:
            A new CircularBuffer instance
        """
        buffer = CircularBuffer(size)
        self._registered_buffers.append(buffer)
        return buffer
    
    def register_cleanup_callback(self, callback: Callable[[], None]) -> None:
        """
        Register a callback function to be called during cleanup operations.
        
        Args:
            callback: Function to call during cleanup
        """
        self._cleanup_callbacks.append(callback)
        self._memory_monitor.register_cleanup_callback(callback)
    
    def get_memory_stats(self) -> MemoryStats:
        """
        Get current memory usage statistics.
        
        Returns:
            MemoryStats object with current memory metrics
        """
        vm = psutil.virtual_memory()
        process_memory = self._process.memory_info().rss
        process_percent = (process_memory / vm.total) * 100
        
        return MemoryStats(
            total_memory=vm.total,
            available_memory=vm.available,
            used_memory=vm.used,
            memory_percent=vm.percent,
            process_memory=process_memory,
            process_percent=process_percent
        )
    
    def get_memory_trend(self, minutes: int = 10) -> Dict[str, Any]:
        """
        Get memory usage trend over the specified time period.
        
        Args:
            minutes: Time period in minutes
            
        Returns:
            Dictionary with trend information
        """
        return self._memory_monitor.get_memory_trend(minutes)
    
    async def start_monitoring(self) -> None:
        """Start the automatic resource monitoring and cleanup task."""
        if self._running:
            return
            
        self._running = True
        await self._memory_monitor.start_monitoring()
        self._logger.info("Resource monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop the resource monitoring task and perform final cleanup."""
        if not self._running:
            return
            
        self._running = False
        await self._memory_monitor.stop_monitoring()
        await self.cleanup_resources()
        self._logger.info("Resource monitoring stopped")
    
    async def cleanup_resources(self) -> None:
        """
        Perform resource cleanup operations.
        
        This includes running garbage collection, clearing circular buffers,
        and executing registered cleanup callbacks.
        """
        self._logger.info("Performing resource cleanup")
        
        # Run registered cleanup callbacks
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                self._logger.error(f"Error in cleanup callback: {e}")
        
        # Clear circular buffers if they're taking too much memory
        stats = self.get_memory_stats()
        if stats.memory_percent > self._memory_critical_threshold:
            for buffer in self._registered_buffers:
                buffer.clear()
            self._logger.info("Cleared circular buffers due to memory pressure")
        
        # Force garbage collection
        gc.collect()
        
        # Log new memory stats after cleanup
        new_stats = self.get_memory_stats()
        memory_freed = stats.process_memory - new_stats.process_memory
        self._logger.info(
            f"Cleanup complete. Memory freed: {memory_freed / 1024 / 1024:.2f} MB. "
            f"Current usage: {new_stats.memory_percent:.1f}%"
        )