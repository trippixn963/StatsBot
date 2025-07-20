"""
Tests for the enhanced caching infrastructure.

This module contains tests for the CircularBuffer and CacheManager classes.
"""

import unittest
import time
from src.utils.cache import CircularBuffer, CacheManager


class TestCircularBuffer(unittest.TestCase):
    """Test cases for the CircularBuffer class."""
    
    def test_initialization(self):
        """Test buffer initialization."""
        buffer = CircularBuffer(5)
        self.assertEqual(len(buffer), 0)
        self.assertEqual(buffer.capacity, 5)
        self.assertTrue(buffer.is_empty())
        self.assertFalse(buffer.is_full())
        
    def test_append(self):
        """Test appending items to the buffer."""
        buffer = CircularBuffer(3)
        buffer.append(1)
        buffer.append(2)
        
        self.assertEqual(len(buffer), 2)
        self.assertEqual(buffer.peek(), 2)
        self.assertEqual(buffer.peek_oldest(), 1)
        
    def test_circular_behavior(self):
        """Test circular behavior when buffer is full."""
        buffer = CircularBuffer(3)
        buffer.append(1)
        buffer.append(2)
        buffer.append(3)
        buffer.append(4)  # This should evict 1
        
        self.assertEqual(len(buffer), 3)
        self.assertEqual(buffer.peek_oldest(), 2)
        self.assertEqual(buffer.peek(), 4)
        self.assertTrue(buffer.is_full())
        
    def test_to_list(self):
        """Test conversion to list."""
        buffer = CircularBuffer(5)
        buffer.append(1)
        buffer.append(2)
        buffer.append(3)
        
        self.assertEqual(buffer.to_list(), [1, 2, 3])
        
    def test_extend(self):
        """Test extending the buffer with multiple items."""
        buffer = CircularBuffer(5)
        buffer.extend([1, 2, 3, 4, 5, 6])  # 1 should be evicted
        
        self.assertEqual(len(buffer), 5)
        self.assertEqual(buffer.peek_oldest(), 2)
        self.assertEqual(buffer.peek(), 6)
        
    def test_clear(self):
        """Test clearing the buffer."""
        buffer = CircularBuffer(5)
        buffer.extend([1, 2, 3])
        buffer.clear()
        
        self.assertEqual(len(buffer), 0)
        self.assertTrue(buffer.is_empty())
        
    def test_contains(self):
        """Test item containment check."""
        buffer = CircularBuffer(5)
        buffer.extend([1, 2, 3])
        
        self.assertTrue(2 in buffer)
        self.assertFalse(4 in buffer)
        
    def test_get_stats(self):
        """Test getting buffer statistics."""
        buffer = CircularBuffer(5)
        buffer.extend([1, 2, 3])
        
        stats = buffer.get_stats()
        self.assertEqual(stats['capacity'], 5)
        self.assertEqual(stats['size'], 3)
        self.assertEqual(stats['utilization'], 0.6)


class TestCacheManager(unittest.TestCase):
    """Test cases for the CacheManager class."""
    
    def test_initialization(self):
        """Test cache manager initialization."""
        cache = CacheManager(default_ttl=60, max_size=100)
        self.assertEqual(cache.default_ttl, 60)
        self.assertEqual(cache.max_size, 100)
        self.assertEqual(len(cache), 0)
        
    def test_set_get(self):
        """Test setting and getting cache values."""
        cache = CacheManager()
        cache.set("key1", "value1")
        
        self.assertEqual(cache.get("key1"), "value1")
        self.assertIsNone(cache.get("nonexistent"))
        
    def test_ttl_expiration(self):
        """Test TTL-based expiration."""
        cache = CacheManager(default_ttl=1)  # 1 second TTL
        cache.set("key1", "value1")
        
        self.assertEqual(cache.get("key1"), "value1")
        time.sleep(1.1)  # Wait for expiration
        self.assertIsNone(cache.get("key1"))
        
    def test_invalidate(self):
        """Test cache invalidation."""
        cache = CacheManager()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        self.assertTrue(cache.invalidate("key1"))
        self.assertFalse(cache.invalidate("nonexistent"))
        self.assertIsNone(cache.get("key1"))
        self.assertEqual(cache.get("key2"), "value2")
        
    def test_invalidate_pattern(self):
        """Test pattern-based cache invalidation."""
        cache = CacheManager()
        cache.set("prefix:key1", "value1")
        cache.set("prefix:key2", "value2")
        cache.set("other:key3", "value3")
        
        self.assertEqual(cache.invalidate_pattern("prefix:"), 2)
        self.assertIsNone(cache.get("prefix:key1"))
        self.assertIsNone(cache.get("prefix:key2"))
        self.assertEqual(cache.get("other:key3"), "value3")
        
    def test_clear(self):
        """Test clearing the entire cache."""
        cache = CacheManager()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        self.assertEqual(cache.clear(), 2)
        self.assertEqual(len(cache), 0)
        
    def test_refresh(self):
        """Test refreshing cache TTL."""
        cache = CacheManager(default_ttl=1)
        cache.set("key1", "value1")
        
        time.sleep(0.5)  # Wait half the TTL
        self.assertTrue(cache.refresh("key1"))
        time.sleep(0.7)  # This would expire without the refresh
        self.assertEqual(cache.get("key1"), "value1")
        
    def test_get_or_set(self):
        """Test get_or_set functionality."""
        cache = CacheManager()
        
        # First call should compute the value
        value = cache.get_or_set("key1", lambda: "computed_value")
        self.assertEqual(value, "computed_value")
        
        # Second call should use cached value
        value = cache.get_or_set("key1", lambda: "different_value")
        self.assertEqual(value, "computed_value")
        
    def test_get_stats(self):
        """Test getting cache statistics."""
        cache = CacheManager()
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss
        
        stats = cache.get_stats()
        self.assertEqual(stats.total_entries, 1)
        self.assertEqual(stats.hit_count, 1)
        self.assertEqual(stats.miss_count, 1)
        self.assertEqual(stats.eviction_count, 0)
        
    def test_eviction(self):
        """Test cache eviction when over capacity."""
        cache = CacheManager(max_size=2)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Should trigger eviction
        
        # One of the first two keys should be evicted
        self.assertEqual(len(cache), 2)
        self.assertTrue(
            (cache.get("key1") is None and cache.get("key2") is not None and cache.get("key3") is not None) or
            (cache.get("key1") is not None and cache.get("key2") is None and cache.get("key3") is not None)
        )


if __name__ == "__main__":
    unittest.main()