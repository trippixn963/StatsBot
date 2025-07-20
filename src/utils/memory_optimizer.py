"""
Memory Optimization Strategies Module.

This module provides memory-efficient data structures, streaming capabilities,
and automatic cleanup mechanisms for resource-constrained environments.

Key Features:
- Memory-efficient data structures for statistics storage
- Streaming and pagination for large dataset processing
- Automatic cleanup of old data with configurable retention policies
- Memory pooling and reuse strategies
- Garbage collection optimization
"""

# Standard library imports
import gc
import sys
import time
import weakref
import threading
from collections import deque, defaultdict
from datetime import datetime, timedelta, timezone
from typing import (
    Dict, List, Optional, Any, Union, Iterator, Callable,
    TypeVar, Generic, Tuple, NamedTuple
)
from dataclasses import dataclass, field
from contextlib import contextmanager
import heapq

# Third-party imports
import psutil

# Local imports
from .performance import timing, performance_context, performance_monitor
from .tree_log import log_perfect_tree_section, log_error_with_traceback

T = TypeVar('T')

class MemoryStats(NamedTuple):
    """Memory usage statistics."""
    rss_mb: float
    vms_mb: float
    percent: float
    available_mb: float

@dataclass
class RetentionPolicy:
    """Data retention policy configuration."""
    max_age_hours: int = 24
    max_items: int = 1000
    cleanup_interval_minutes: int = 30
    emergency_cleanup_threshold_mb: float = 512.0

class CircularBuffer(Generic[T]):
    """
    Memory-efficient circular buffer with automatic cleanup.
    
    This buffer maintains a fixed maximum size and automatically
    overwrites old entries when the limit is reached.
    
    Attributes:
        maxsize (int): Maximum number of items to store
        data (deque): Internal storage using collections.deque
        total_added (int): Total number of items ever added
    """
    
    def __init__(self, maxsize: int = 1000):
        """
        Initialize circular buffer.
        
        Args:
            maxsize: Maximum number of items to store
        """
        self.maxsize = maxsize
        self.data: deque = deque(maxlen=maxsize)
        self.total_added = 0
        self._lock = threading.RLock()
    
    def append(self, item: T) -> None:
        """
        Add item to buffer.
        
        Args:
            item: Item to add to buffer
        """
        with self._lock:
            self.data.append(item)
            self.total_added += 1
    
    def extend(self, items: List[T]) -> None:
        """
        Add multiple items to buffer.
        
        Args:
            items: List of items to add
        """
        with self._lock:
            self.data.extend(items)
            self.total_added += len(items)
    
    def get_recent(self, count: int) -> List[T]:
        """
        Get the most recent items.
        
        Args:
            count: Number of recent items to get
            
        Returns:
            List of recent items (up to count)
        """
        with self._lock:
            return list(self.data)[-count:] if count < len(self.data) else list(self.data)
    
    def clear(self) -> None:
        """Clear all items from buffer."""
        with self._lock:
            self.data.clear()
    
    def __len__(self) -> int:
        return len(self.data)
    
    def __iter__(self) -> Iterator[T]:
        with self._lock:
            return iter(list(self.data))

class TimeBasedCache(Generic[T]):
    """
    Time-based cache with automatic expiration and memory optimization.
    
    This cache automatically removes expired entries and provides
    memory-efficient storage with configurable TTL.
    
    Attributes:
        default_ttl (float): Default time-to-live in seconds
        max_size (int): Maximum number of cached items
        _cache (Dict): Internal cache storage
        _expiry_times (List): Heap of expiry times for efficient cleanup
    """
    
    def __init__(self, default_ttl: float = 300.0, max_size: int = 1000):
        """
        Initialize time-based cache.
        
        Args:
            default_ttl: Default time-to-live in seconds
            max_size: Maximum number of items to cache
        """
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._cache: Dict[str, Tuple[T, float]] = {}
        self._expiry_times: List[Tuple[float, str]] = []
        self._lock = threading.RLock()
        self._last_cleanup = time.time()
    
    def set(self, key: str, value: T, ttl: Optional[float] = None) -> None:
        """
        Set cache value with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        ttl = ttl or self.default_ttl
        expiry_time = time.time() + ttl
        
        with self._lock:
            # Remove old entry if exists
            if key in self._cache:
                self._remove_key(key)
            
            # Add new entry
            self._cache[key] = (value, expiry_time)
            heapq.heappush(self._expiry_times, (expiry_time, key))
            
            # Cleanup if needed
            self._maybe_cleanup()
    
    def get(self, key: str) -> Optional[T]:
        """
        Get cached value.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                return None
            
            value, expiry_time = self._cache[key]
            
            # Check if expired
            if time.time() > expiry_time:
                self._remove_key(key)
                return None
            
            return value
    
    def _remove_key(self, key: str) -> None:
        """Remove key from cache (internal method)."""
        if key in self._cache:
            del self._cache[key]
    
    def _maybe_cleanup(self) -> None:
        """Perform cleanup if needed."""
        current_time = time.time()
        
        # Cleanup expired entries
        while self._expiry_times:
            expiry_time, key = self._expiry_times[0]
            if expiry_time <= current_time:
                heapq.heappop(self._expiry_times)
                self._remove_key(key)
            else:
                break
        
        # Cleanup if too many items
        if len(self._cache) > self.max_size:
            # Remove oldest entries
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1][1])
            items_to_remove = len(self._cache) - self.max_size
            
            for i in range(items_to_remove):
                key = sorted_items[i][0]
                self._remove_key(key)
    
    def clear(self) -> None:
        """Clear all cached items."""
        with self._lock:
            self._cache.clear()
            self._expiry_times.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)

class MemoryEfficientStats:
    """
    Memory-efficient statistics storage and processing.
    
    This class provides optimized storage for bot statistics with
    automatic data rotation and memory usage monitoring.
    
    Attributes:
        retention_policy (RetentionPolicy): Data retention configuration
        _daily_stats (Dict): Daily statistics storage
        _member_events (CircularBuffer): Recent member events
        _performance_metrics (CircularBuffer): Performance metrics
        _cache (TimeBasedCache): Frequently accessed data cache
    """
    
    def __init__(self, retention_policy: Optional[RetentionPolicy] = None):
        """
        Initialize memory-efficient stats storage.
        
        Args:
            retention_policy: Data retention policy configuration
        """
        self.retention_policy = retention_policy or RetentionPolicy()
        
        # Circular buffers for recent data
        self._member_events = CircularBuffer(maxsize=1000)
        self._performance_metrics = CircularBuffer(maxsize=500)
        self._log_entries = CircularBuffer(maxsize=200)
        
        # Time-based cache for frequently accessed data
        self._cache = TimeBasedCache(default_ttl=300.0, max_size=100)
        
        # Daily stats with automatic cleanup
        self._daily_stats: Dict[str, Dict[str, Any]] = {}
        
        # Cleanup scheduling
        self._last_cleanup = time.time()
        self._cleanup_lock = threading.Lock()
        
        log_perfect_tree_section(
            "Memory-Efficient Stats",
            [
                ("retention_hours", self.retention_policy.max_age_hours),
                ("max_items", self.retention_policy.max_items),
                ("cleanup_interval", f"{self.retention_policy.cleanup_interval_minutes}m")
            ],
            emoji="💾"
        )
    
    @timing(category="stats")
    def add_member_event(self, event_type: str, member_id: int, 
                        username: str, timestamp: Optional[datetime] = None) -> None:
        """
        Add a member event to statistics.
        
        Args:
            event_type: Type of event ('join', 'leave', 'ban')
            member_id: Discord member ID
            username: Member username
            timestamp: Event timestamp (current time if None)
        """
        timestamp = timestamp or datetime.now(timezone.utc)
        
        event = {
            'type': event_type,
            'member_id': member_id,
            'username': username[:50],  # Limit username length
            'timestamp': timestamp
        }
        
        self._member_events.append(event)
        
        # Update daily stats
        date_key = timestamp.strftime('%Y-%m-%d')
        if date_key not in self._daily_stats:
            self._daily_stats[date_key] = {
                'joins': [],
                'leaves': [],
                'bans': []
            }
        
        # Store only essential data in daily stats
        essential_event = {
            'member_id': member_id,
            'username': username[:30],  # Even shorter for daily storage
            'timestamp': timestamp.isoformat()
        }
        
        self._daily_stats[date_key][f"{event_type}s"].append(essential_event)
        
        # Trigger cleanup if needed
        self._maybe_trigger_cleanup()
    
    @timing(category="stats")
    def add_performance_metric(self, metric_name: str, value: float, 
                             metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a performance metric.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            metadata: Optional metadata (kept minimal for memory efficiency)
        """
        metric = {
            'name': metric_name,
            'value': value,
            'timestamp': time.time(),
            'metadata': metadata or {}
        }
        
        # Limit metadata size
        if len(str(metric['metadata'])) > 500:
            metric['metadata'] = {'oversized': True}
        
        self._performance_metrics.append(metric)
    
    def get_recent_member_events(self, count: int = 50, 
                               event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get recent member events.
        
        Args:
            count: Number of events to retrieve
            event_type: Filter by event type (None for all)
            
        Returns:
            List of recent member events
        """
        events = self._member_events.get_recent(count * 2)  # Get more to filter
        
        if event_type:
            events = [e for e in events if e.get('type') == event_type]
        
        return events[:count]
    
    def get_daily_stats(self, date: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific date.
        
        Args:
            date: Date string in YYYY-MM-DD format
            
        Returns:
            Daily statistics or None if not found
        """
        # Check cache first
        cache_key = f"daily_stats_{date}"
        cached_stats = self._cache.get(cache_key)
        if cached_stats:
            return cached_stats
        
        # Get from storage
        stats = self._daily_stats.get(date)
        if stats:
            # Create summary for caching (more memory efficient)
            summary = {
                'date': date,
                'total_joins': len(stats.get('joins', [])),
                'total_leaves': len(stats.get('leaves', [])),
                'total_bans': len(stats.get('bans', [])),
                'net_growth': len(stats.get('joins', [])) - len(stats.get('leaves', [])),
                'events': stats  # Full data
            }
            
            # Cache the summary
            self._cache.set(cache_key, summary, ttl=3600)  # Cache for 1 hour
            return summary
        
        return None
    
    def _maybe_trigger_cleanup(self) -> None:
        """Trigger cleanup if conditions are met."""
        current_time = time.time()
        cleanup_interval_seconds = self.retention_policy.cleanup_interval_minutes * 60
        
        if current_time - self._last_cleanup > cleanup_interval_seconds:
            self._perform_cleanup()
    
    @timing(category="cleanup")
    def _perform_cleanup(self) -> None:
        """Perform memory cleanup operations."""
        with self._cleanup_lock:
            current_time = time.time()
            
            # Check memory usage
            memory_stats = get_memory_stats()
            
            if memory_stats.rss_mb > self.retention_policy.emergency_cleanup_threshold_mb:
                log_perfect_tree_section(
                    "Emergency Memory Cleanup",
                    [
                        ("memory_usage_mb", f"{memory_stats.rss_mb:.2f}"),
                        ("threshold_mb", self.retention_policy.emergency_cleanup_threshold_mb)
                    ],
                    emoji="🚨"
                )
                self._emergency_cleanup()
            else:
                self._regular_cleanup()
            
            self._last_cleanup = current_time
    
    def _regular_cleanup(self) -> None:
        """Regular cleanup based on retention policy."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.retention_policy.max_age_hours)
        cutoff_date = cutoff_time.strftime('%Y-%m-%d')
        
        # Remove old daily stats
        dates_to_remove = []
        for date in self._daily_stats:
            if date < cutoff_date:
                dates_to_remove.append(date)
        
        for date in dates_to_remove:
            del self._daily_stats[date]
        
        # Clear caches
        self._cache.clear()
        
        # Force garbage collection
        gc.collect()
        
        log_perfect_tree_section(
            "Regular Cleanup Completed",
            [
                ("removed_dates", len(dates_to_remove)),
                ("remaining_dates", len(self._daily_stats))
            ],
            emoji="🧹"
        )
    
    def _emergency_cleanup(self) -> None:
        """Emergency cleanup to free memory immediately."""
        # Clear all caches
        self._cache.clear()
        
        # Reduce buffer sizes temporarily
        self._member_events = CircularBuffer(maxsize=100)
        self._performance_metrics = CircularBuffer(maxsize=50)
        self._log_entries = CircularBuffer(maxsize=20)
        
        # Keep only last 3 days of daily stats
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime('%Y-%m-%d')
        dates_to_remove = [date for date in self._daily_stats if date < cutoff_date]
        
        for date in dates_to_remove:
            del self._daily_stats[date]
        
        # Aggressive garbage collection
        for _ in range(3):
            gc.collect()
        
        log_perfect_tree_section(
            "Emergency Cleanup Completed",
            [
                ("removed_dates", len(dates_to_remove)),
                ("buffers_reduced", True),
                ("memory_after_mb", f"{get_memory_stats().rss_mb:.2f}")
            ],
            emoji="🚨"
        )
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """
        Get memory usage statistics for this stats object.
        
        Returns:
            Dictionary containing memory usage information
        """
        return {
            'member_events_count': len(self._member_events),
            'performance_metrics_count': len(self._performance_metrics),
            'daily_stats_dates': len(self._daily_stats),
            'cache_size': self._cache.size(),
            'total_member_events_added': self._member_events.total_added,
            'estimated_memory_mb': self._estimate_memory_usage()
        }
    
    def _estimate_memory_usage(self) -> float:
        """Estimate memory usage of stored data."""
        # Rough estimation based on data structures
        member_events_size = len(self._member_events) * 200  # ~200 bytes per event
        performance_metrics_size = len(self._performance_metrics) * 100  # ~100 bytes per metric
        daily_stats_size = sum(
            len(str(stats)) for stats in self._daily_stats.values()
        )
        cache_size = self._cache.size() * 150  # ~150 bytes per cache entry
        
        total_bytes = member_events_size + performance_metrics_size + daily_stats_size + cache_size
        return total_bytes / (1024 * 1024)  # Convert to MB

class StreamProcessor:
    """
    Memory-efficient stream processor for large datasets.
    
    This processor handles large datasets without loading everything
    into memory at once, using streaming and pagination techniques.
    """
    
    def __init__(self, batch_size: int = 100):
        """
        Initialize stream processor.
        
        Args:
            batch_size: Number of items to process in each batch
        """
        self.batch_size = batch_size
    
    @timing(category="stream")
    def process_member_data_stream(self, data_source: Iterator[Dict[str, Any]], 
                                 processor_func: Callable[[List[Dict[str, Any]]], None]) -> int:
        """
        Process member data in batches to conserve memory.
        
        Args:
            data_source: Iterator yielding member data dictionaries
            processor_func: Function to process each batch
            
        Returns:
            Total number of items processed
        """
        total_processed = 0
        batch = []
        
        try:
            for item in data_source:
                batch.append(item)
                
                if len(batch) >= self.batch_size:
                    processor_func(batch)
                    total_processed += len(batch)
                    batch.clear()  # Clear batch to free memory
                    
                    # Yield control to allow other tasks
                    if total_processed % (self.batch_size * 10) == 0:
                        gc.collect()  # Periodic garbage collection
            
            # Process remaining items
            if batch:
                processor_func(batch)
                total_processed += len(batch)
        
        except Exception as e:
            log_error_with_traceback("Error in stream processing", e)
            raise
        
        return total_processed

def get_memory_stats() -> MemoryStats:
    """
    Get current memory usage statistics.
    
    Returns:
        MemoryStats containing current memory information
    """
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()
        
        # Get system memory info
        system_memory = psutil.virtual_memory()
        
        return MemoryStats(
            rss_mb=memory_info.rss / (1024 * 1024),
            vms_mb=memory_info.vms / (1024 * 1024),
            percent=memory_percent,
            available_mb=system_memory.available / (1024 * 1024)
        )
    except Exception:
        return MemoryStats(0.0, 0.0, 0.0, 0.0)

@contextmanager
def memory_monitor(operation_name: str, log_threshold_mb: float = 10.0):
    """
    Context manager for monitoring memory usage during operations.
    
    Args:
        operation_name: Name of the operation being monitored
        log_threshold_mb: Log if memory usage exceeds this threshold
    """
    start_memory = get_memory_stats()
    start_time = time.time()
    
    try:
        yield
    finally:
        end_memory = get_memory_stats()
        duration = time.time() - start_time
        memory_delta = end_memory.rss_mb - start_memory.rss_mb
        
        if abs(memory_delta) > log_threshold_mb:
            log_perfect_tree_section(
                f"Memory Usage: {operation_name}",
                [
                    ("duration_ms", f"{duration * 1000:.2f}"),
                    ("memory_delta_mb", f"{memory_delta:+.2f}"),
                    ("final_memory_mb", f"{end_memory.rss_mb:.2f}")
                ],
                emoji="📊"
            )

def optimize_garbage_collection():
    """Optimize garbage collection settings for long-running bot."""
    # Adjust GC thresholds for better performance
    # More aggressive collection of generation 0 (short-lived objects)
    # Less frequent collection of generation 2 (long-lived objects)
    gc.set_threshold(700, 10, 10)  # Default is (700, 10, 10)
    
    # Enable debug mode in development
    if __debug__:
        gc.set_debug(gc.DEBUG_STATS)

# Global memory-efficient stats instance
memory_stats = MemoryEfficientStats()

# Initialize GC optimization
optimize_garbage_collection() 