"""
TTL-based cache manager with memory-efficient storage.

This module provides a thread-safe, time-to-live (TTL) based cache implementation
with memory-efficient storage, cache invalidation strategies, and metrics tracking.
"""

import time
import threading
from typing import Dict, Any, Optional, List, Tuple, Set, Generic, TypeVar
import logging
from datetime import datetime
import sys

from ...core.exceptions import CacheError
from ...types.models import CacheStats, CacheOperation

T = TypeVar('T')


class CacheEntry(Generic[T]):
    """
    Cache entry with value and expiration time.
    
    Attributes:
        value: The cached value
        expiry: Expiration timestamp (seconds since epoch)
        created_at: Creation timestamp (seconds since epoch)
        last_accessed: Last access timestamp (seconds since epoch)
        access_count: Number of times this entry has been accessed
    """
    
    __slots__ = ('value', 'expiry', 'created_at', 'last_accessed', 'access_count')
    
    def __init__(self, value: T, ttl: int):
        """
        Initialize a new cache entry.
        
        Args:
            value: Value to cache
            ttl: Time to live in seconds
        """
        self.value = value
        current_time = time.time()
        self.expiry = current_time + ttl
        self.created_at = current_time
        self.last_accessed = current_time
        self.access_count = 0
        
    def is_expired(self) -> bool:
        """
        Check if the entry has expired.
        
        Returns:
            True if entry has expired, False otherwise
        """
        return time.time() > self.expiry
        
    def access(self) -> None:
        """Update last accessed time and increment access count."""
        self.last_accessed = time.time()
        self.access_count += 1
        
    def get_age(self) -> float:
        """
        Get the age of this entry in seconds.
        
        Returns:
            Age in seconds
        """
        return time.time() - self.created_at
        
    def get_time_to_expiry(self) -> float:
        """
        Get time remaining until expiry in seconds.
        
        Returns:
            Time to expiry in seconds (negative if already expired)
        """
        return self.expiry - time.time()


class CacheManager:
    """
    Thread-safe TTL-based cache manager with memory-efficient storage.
    
    This class provides a memory-efficient caching mechanism with TTL support,
    automatic expiration, cache invalidation strategies, and comprehensive
    metrics tracking.
    
    Attributes:
        default_ttl (int): Default time-to-live for cache entries in seconds
        max_size (int): Maximum number of entries the cache can hold
        _cache (Dict): Internal storage for cache entries
        _lock (threading.RLock): Lock for thread safety
        _stats (Dict): Cache statistics
    """
    
    def __init__(self, default_ttl: int = 300, max_size: int = 10000):
        """
        Initialize a new cache manager.
        
        Args:
            default_ttl: Default time-to-live for cache entries in seconds
            max_size: Maximum number of entries the cache can hold
            
        Raises:
            ValueError: If default_ttl or max_size is not positive
        """
        if default_ttl <= 0:
            raise ValueError("Default TTL must be positive")
        if max_size <= 0:
            raise ValueError("Max size must be positive")
            
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        
        # Statistics tracking
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'evictions': 0,
            'expirations': 0,
            'invalidations': 0,
            'created_at': time.time()
        }
        
        # Start background cleanup thread
        self._start_cleanup_thread()
        
    def _start_cleanup_thread(self) -> None:
        """Start background thread for periodic cache cleanup."""
        cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="CacheCleanupThread"
        )
        cleanup_thread.start()
        
    def _cleanup_loop(self) -> None:
        """Background loop for periodic cache cleanup."""
        while True:
            try:
                # Sleep first to avoid immediate cleanup on startup
                time.sleep(min(60, self.default_ttl / 2))
                self._cleanup_expired()
            except Exception as e:
                logging.error(f"Error in cache cleanup: {e}")
                
    def _cleanup_expired(self) -> int:
        """
        Remove expired entries from the cache.
        
        Returns:
            Number of entries removed
        """
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, entry in self._cache.items()
                if current_time > entry.expiry
            ]
            
            for key in expired_keys:
                del self._cache[key]
                
            self._stats['expirations'] += len(expired_keys)
            return len(expired_keys)
            
    def _evict_if_needed(self) -> int:
        """
        Evict entries if cache is over capacity.
        
        This method uses a combination of strategies to determine which
        entries to evict: least recently used, least frequently used,
        and closest to expiration.
        
        Returns:
            Number of entries evicted
        """
        with self._lock:
            if len(self._cache) <= self.max_size:
                return 0
                
            # Calculate how many entries to evict
            # At minimum, evict enough to get below max_size
            min_to_evict = len(self._cache) - self.max_size
            # Evict at least 1, up to 20% of max_size for efficiency
            to_evict = max(min_to_evict, max(1, int(self.max_size * 0.2)))
            
            # Score entries based on a combination of factors
            # Lower score = more likely to be evicted
            scored_entries = []
            current_time = time.time()
            
            for key, entry in self._cache.items():
                # Factors to consider:
                # 1. Time since last access (older = more likely to evict)
                # 2. Access frequency (less frequent = more likely to evict)
                # 3. Time to expiry (closer to expiry = more likely to evict)
                
                time_factor = current_time - entry.last_accessed
                frequency_factor = 1 / (entry.access_count + 1)
                expiry_factor = max(0.1, entry.expiry - current_time)
                
                # Combined score (lower = more likely to evict)
                score = (expiry_factor * 0.5) - (time_factor * 0.3) - (frequency_factor * 100)
                scored_entries.append((key, score))
            
            # Sort by score (ascending) and take the lowest scoring entries
            scored_entries.sort(key=lambda x: x[1])
            keys_to_evict = [key for key, _ in scored_entries[:to_evict]]
            
            # Evict selected entries
            for key in keys_to_evict:
                del self._cache[key]
                
            self._stats['evictions'] += len(keys_to_evict)
            return len(keys_to_evict)
            
    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.
        
        Args:
            key: Cache key to retrieve
            
        Returns:
            Cached value, or None if key not found or expired
            
        Raises:
            CacheError: If an error occurs during retrieval
        """
        try:
            with self._lock:
                # Check if key exists
                if key not in self._cache:
                    self._stats['misses'] += 1
                    return None
                    
                entry = self._cache[key]
                
                # Check if entry has expired
                if entry.is_expired():
                    del self._cache[key]
                    self._stats['expirations'] += 1
                    self._stats['misses'] += 1
                    return None
                    
                # Update access statistics
                entry.access()
                self._stats['hits'] += 1
                
                return entry.value
        except Exception as e:
            raise CacheError(
                f"Error retrieving from cache: {str(e)}",
                cache_key=key,
                operation=CacheOperation.GET.name
            )
            
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set a value in the cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default_ttl if None)
            
        Raises:
            CacheError: If an error occurs during storage
        """
        try:
            ttl = ttl if ttl is not None else self.default_ttl
            
            with self._lock:
                # Store the new entry
                self._cache[key] = CacheEntry(value, ttl)
                self._stats['sets'] += 1
                
                # Check if we need to evict entries (always check after adding)
                if len(self._cache) > self.max_size:
                    self._evict_if_needed()
        except Exception as e:
            raise CacheError(
                f"Error setting cache value: {str(e)}",
                cache_key=key,
                operation=CacheOperation.SET.name
            )
            
    def invalidate(self, key: str) -> bool:
        """
        Invalidate a specific cache entry.
        
        Args:
            key: Cache key to invalidate
            
        Returns:
            True if key was found and invalidated, False otherwise
            
        Raises:
            CacheError: If an error occurs during invalidation
        """
        try:
            with self._lock:
                if key in self._cache:
                    del self._cache[key]
                    self._stats['invalidations'] += 1
                    return True
                return False
        except Exception as e:
            raise CacheError(
                f"Error invalidating cache key: {str(e)}",
                cache_key=key,
                operation=CacheOperation.DELETE.name
            )
            
    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all cache entries with keys matching a pattern.
        
        Args:
            pattern: String pattern to match (using simple substring matching)
            
        Returns:
            Number of entries invalidated
            
        Raises:
            CacheError: If an error occurs during invalidation
        """
        try:
            with self._lock:
                keys_to_invalidate = [
                    key for key in self._cache.keys()
                    if pattern in key
                ]
                
                for key in keys_to_invalidate:
                    del self._cache[key]
                    
                self._stats['invalidations'] += len(keys_to_invalidate)
                return len(keys_to_invalidate)
        except Exception as e:
            raise CacheError(
                f"Error invalidating cache pattern: {str(e)}",
                cache_key=pattern,
                operation=CacheOperation.DELETE.name
            )
            
    def clear(self) -> int:
        """
        Clear all entries from the cache.
        
        Returns:
            Number of entries cleared
            
        Raises:
            CacheError: If an error occurs during clearing
        """
        try:
            with self._lock:
                count = len(self._cache)
                self._cache.clear()
                self._stats['invalidations'] += count
                return count
        except Exception as e:
            raise CacheError(
                f"Error clearing cache: {str(e)}",
                operation=CacheOperation.CLEAR.name
            )
            
    def refresh(self, key: str, ttl: Optional[int] = None) -> bool:
        """
        Refresh the TTL of a cache entry.
        
        Args:
            key: Cache key to refresh
            ttl: New TTL in seconds (uses default_ttl if None)
            
        Returns:
            True if key was found and refreshed, False otherwise
            
        Raises:
            CacheError: If an error occurs during refresh
        """
        try:
            ttl = ttl if ttl is not None else self.default_ttl
            
            with self._lock:
                if key in self._cache:
                    entry = self._cache[key]
                    entry.expiry = time.time() + ttl
                    return True
                return False
        except Exception as e:
            raise CacheError(
                f"Error refreshing cache key: {str(e)}",
                cache_key=key,
                operation=CacheOperation.REFRESH.name
            )
            
    def get_or_set(self, key: str, value_func: callable, ttl: Optional[int] = None) -> Any:
        """
        Get a value from cache or compute and store it if not present.
        
        Args:
            key: Cache key
            value_func: Function to compute the value if not in cache
            ttl: Time-to-live in seconds (uses default_ttl if None)
            
        Returns:
            Cached or computed value
            
        Raises:
            CacheError: If an error occurs during operation
        """
        try:
            # Try to get from cache first
            value = self.get(key)
            
            # If not found, compute and store
            if value is None:
                value = value_func()
                self.set(key, value, ttl)
                
            return value
        except Exception as e:
            raise CacheError(
                f"Error in get_or_set: {str(e)}",
                cache_key=key,
                operation="GET_OR_SET"
            )
            
    def get_stats(self) -> CacheStats:
        """
        Get cache statistics.
        
        Returns:
            CacheStats object with current statistics
        """
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = self._stats['hits'] / total_requests if total_requests > 0 else 0.0
            
            # Estimate memory usage
            memory_usage = self._estimate_memory_usage()
            
            return CacheStats(
                total_entries=len(self._cache),
                hit_count=self._stats['hits'],
                miss_count=self._stats['misses'],
                eviction_count=self._stats['evictions'],
                memory_usage_bytes=memory_usage
            )
            
    def _estimate_memory_usage(self) -> int:
        """
        Estimate memory usage of the cache in bytes.
        
        This is an approximation based on key sizes and value sizes.
        
        Returns:
            Estimated memory usage in bytes
        """
        with self._lock:
            # Base overhead for the cache object itself
            overhead = sys.getsizeof(self._cache)
            
            # Sample up to 100 items to estimate average size
            sample_size = min(100, len(self._cache))
            if sample_size == 0:
                return overhead
                
            # Get a sample of keys
            sample_keys = list(self._cache.keys())[:sample_size]
            
            # Calculate total size of sampled items
            total_sample_size = sum(
                sys.getsizeof(key) + sys.getsizeof(self._cache[key]) + sys.getsizeof(self._cache[key].value)
                for key in sample_keys
            )
            
            # Extrapolate to full cache size
            avg_item_size = total_sample_size / sample_size
            total_estimated_size = overhead + (avg_item_size * len(self._cache))
            
            return int(total_estimated_size)
            
    def get_keys(self) -> List[str]:
        """
        Get all cache keys.
        
        Returns:
            List of all cache keys
        """
        with self._lock:
            return list(self._cache.keys())
            
    def get_expired_keys(self) -> List[str]:
        """
        Get all expired cache keys.
        
        Returns:
            List of expired cache keys
        """
        with self._lock:
            current_time = time.time()
            return [
                key for key, entry in self._cache.items()
                if current_time > entry.expiry
            ]
            
    def get_key_info(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a cache key.
        
        Args:
            key: Cache key to get info for
            
        Returns:
            Dictionary with key information, or None if key not found
        """
        with self._lock:
            if key not in self._cache:
                return None
                
            entry = self._cache[key]
            current_time = time.time()
            
            return {
                'key': key,
                'created_at': datetime.fromtimestamp(entry.created_at).isoformat(),
                'expires_at': datetime.fromtimestamp(entry.expiry).isoformat(),
                'last_accessed': datetime.fromtimestamp(entry.last_accessed).isoformat(),
                'access_count': entry.access_count,
                'age_seconds': current_time - entry.created_at,
                'ttl_remaining': max(0, entry.expiry - current_time),
                'is_expired': current_time > entry.expiry
            }
            
    def __len__(self) -> int:
        """
        Get the current number of entries in the cache.
        
        Returns:
            Number of entries in the cache
        """
        with self._lock:
            return len(self._cache)
            
    def __contains__(self, key: str) -> bool:
        """
        Check if a key is in the cache and not expired.
        
        Args:
            key: Cache key to check
            
        Returns:
            True if key is in cache and not expired, False otherwise
        """
        with self._lock:
            if key not in self._cache:
                return False
                
            entry = self._cache[key]
            if entry.is_expired():
                del self._cache[key]
                self._stats['expirations'] += 1
                return False
                
            return True