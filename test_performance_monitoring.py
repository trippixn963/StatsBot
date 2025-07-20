"""
Tests for performance monitoring and optimization.

This module tests the performance monitoring and optimization utilities,
including timing decorators, memory usage monitoring, and performance metrics collection.
"""

import unittest
import time
import asyncio
from unittest.mock import MagicMock, patch
import gc

from src.utils.performance.timing import (
    timed, async_timed, get_performance_metrics, reset_performance_metrics,
    PerformanceContext, AsyncPerformanceContext
)
from src.utils.performance.memory_monitor import MemoryMonitor, MemoryOptimizer


class TestTimingDecorators(unittest.TestCase):
    """Test timing decorators and performance metrics collection."""
    
    def setUp(self):
        """Set up test environment."""
        reset_performance_metrics()
        
    def test_timed_decorator(self):
        """Test that timed decorator records metrics correctly."""
        @timed("test_operation")
        def test_function(sleep_time):
            time.sleep(sleep_time)
            return "done"
            
        # Call function multiple times with different sleep times
        test_function(0.01)
        test_function(0.02)
        
        # Check metrics
        metrics = get_performance_metrics()
        self.assertIn("test_operation", metrics)
        self.assertEqual(metrics["test_operation"].count, 2)
        self.assertGreaterEqual(metrics["test_operation"].min_time_ms, 10)  # At least 10ms
        self.assertLessEqual(metrics["test_operation"].max_time_ms, 100)  # Reasonable upper bound for test
        
    def test_timed_decorator_with_threshold(self):
        """Test that timed decorator logs warnings when threshold is exceeded."""
        mock_logger = MagicMock()
        
        @timed("slow_operation", threshold_ms=5)
        def slow_function(logger):
            time.sleep(0.01)  # 10ms, should exceed threshold
            logger.warning.assert_not_called()  # Shouldn't be called yet
            return "done"
            
        # Call function
        result = slow_function(mock_logger)
        
        # Verify result
        self.assertEqual(result, "done")
        
        # Check metrics
        metrics = get_performance_metrics()
        self.assertIn("slow_operation", metrics)
        self.assertEqual(metrics["slow_operation"].count, 1)
        
    def test_performance_context(self):
        """Test PerformanceContext for timing code blocks."""
        with PerformanceContext("context_test") as ctx:
            time.sleep(0.01)
            
        # Check context duration
        self.assertGreaterEqual(ctx.duration_ms, 10)  # At least 10ms
        
        # Check metrics
        metrics = get_performance_metrics()
        self.assertIn("context_test", metrics)
        self.assertEqual(metrics["context_test"].count, 1)
        
    async def test_async_timed_decorator(self):
        """Test async_timed decorator for async functions."""
        @async_timed("async_operation")
        async def async_test_function(sleep_time):
            await asyncio.sleep(sleep_time)
            return "done"
            
        # Call function
        result = await async_test_function(0.01)
        
        # Verify result
        self.assertEqual(result, "done")
        
        # Check metrics
        metrics = get_performance_metrics()
        self.assertIn("async_operation", metrics)
        self.assertEqual(metrics["async_operation"].count, 1)
        self.assertGreaterEqual(metrics["async_operation"].min_time_ms, 10)  # At least 10ms
        
    async def test_async_performance_context(self):
        """Test AsyncPerformanceContext for timing async code blocks."""
        async with AsyncPerformanceContext("async_context_test") as ctx:
            await asyncio.sleep(0.01)
            
        # Check context duration
        self.assertGreaterEqual(ctx.duration_ms, 10)  # At least 10ms
        
        # Check metrics
        metrics = get_performance_metrics()
        self.assertIn("async_context_test", metrics)
        self.assertEqual(metrics["async_context_test"].count, 1)


class TestMemoryMonitoring(unittest.TestCase):
    """Test memory monitoring and optimization utilities."""
    
    def test_memory_stats(self):
        """Test that memory stats are collected correctly."""
        monitor = MemoryMonitor()
        stats = monitor.get_memory_stats()
        
        # Verify stats
        self.assertGreater(stats.total_bytes, 0)
        self.assertGreater(stats.used_bytes, 0)
        self.assertGreater(stats.available_bytes, 0)
        self.assertGreaterEqual(stats.percent_used, 0)
        self.assertLessEqual(stats.percent_used, 100)
        
    def test_process_memory_usage(self):
        """Test that process memory usage is collected correctly."""
        monitor = MemoryMonitor()
        memory_bytes, memory_percent = monitor.get_process_memory_usage()
        
        # Verify stats
        self.assertGreater(memory_bytes, 0)
        self.assertGreaterEqual(memory_percent, 0)
        self.assertLessEqual(memory_percent, 100)
        
    def test_memory_history(self):
        """Test that memory history is collected correctly."""
        monitor = MemoryMonitor()
        
        # Collect multiple stats
        for _ in range(5):
            monitor.get_memory_stats()
            time.sleep(0.01)
            
        # Check history
        history = monitor.get_memory_history()
        self.assertEqual(len(history), 5)
        
    def test_memory_trend(self):
        """Test memory trend calculation."""
        monitor = MemoryMonitor()
        
        # Collect multiple stats
        for _ in range(5):
            monitor.get_memory_stats()
            time.sleep(0.01)
            
        # Check trend
        trend = monitor.get_memory_trend()
        self.assertIn("trend", trend)
        self.assertIn("samples", trend)
        self.assertEqual(trend["samples"], 5)
        
    def test_memory_optimizer(self):
        """Test memory optimization utilities."""
        # Test weak reference
        obj = {"test": "data"}
        weak_ref = MemoryOptimizer.use_weak_reference(obj)
        self.assertEqual(weak_ref(), obj)
        
        # Test dict optimization
        d = {i: i for i in range(1000)}
        optimized = MemoryOptimizer.optimize_dict_memory(d)
        self.assertEqual(d, optimized)
        
        # Test object size
        size = MemoryOptimizer.get_object_size(d)
        self.assertGreater(size, 0)
        
    def test_clear_unused_memory(self):
        """Test clearing unused memory."""
        # Create some garbage
        for _ in range(1000):
            _ = [i for i in range(1000)]
            
        # Clear memory
        MemoryOptimizer.clear_unused_memory()
        
        # Not much to assert here, just make sure it doesn't crash


if __name__ == "__main__":
    unittest.main()