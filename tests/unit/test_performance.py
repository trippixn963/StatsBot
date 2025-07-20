"""
Unit tests for performance monitoring module.

This module tests the performance monitoring functionality including
timing decorators, memory monitoring, and metrics collection.
"""

import asyncio
import time
from unittest.mock import Mock, patch
import pytest

from src.utils.performance import (
    PerformanceMonitor,
    PerformanceMetric,
    MemoryAlert,
    AlertLevel,
    timing,
    memory_timing,
    performance_context,
    get_performance_report
)


class TestPerformanceMonitor:
    """Test cases for PerformanceMonitor class."""
    
    def test_init(self):
        """Test PerformanceMonitor initialization."""
        monitor = PerformanceMonitor(
            max_metrics=500,
            memory_threshold_mb=256.0,
            critical_memory_threshold_mb=512.0,
            slow_operation_threshold_ms=500.0
        )
        
        assert monitor.thresholds['memory_warning'] == 256.0
        assert monitor.thresholds['memory_critical'] == 512.0
        assert monitor.thresholds['slow_operation'] == 500.0
        assert monitor._monitoring_active
        
        # Cleanup
        monitor.shutdown()
    
    def test_get_memory_usage(self):
        """Test memory usage retrieval."""
        monitor = PerformanceMonitor()
        
        with patch('psutil.Process') as mock_process:
            mock_process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024  # 100MB
            
            memory_usage = monitor._get_memory_usage()
            assert memory_usage == 100.0
        
        monitor.shutdown()
    
    def test_check_memory_thresholds_warning(self):
        """Test memory threshold checking for warnings."""
        monitor = PerformanceMonitor(memory_threshold_mb=50.0)
        
        # Should trigger warning
        monitor._check_memory_thresholds(75.0)
        
        alerts = monitor.get_recent_alerts(1)
        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.WARNING
        assert "High memory usage" in alerts[0].message
        
        monitor.shutdown()
    
    def test_check_memory_thresholds_critical(self):
        """Test memory threshold checking for critical alerts."""
        monitor = PerformanceMonitor(
            memory_threshold_mb=50.0,
            critical_memory_threshold_mb=100.0
        )
        
        with patch.object(monitor, '_trigger_gc') as mock_gc:
            # Should trigger critical alert and GC
            monitor._check_memory_thresholds(150.0)
            
            alerts = monitor.get_recent_alerts(1)
            assert len(alerts) == 1
            assert alerts[0].level == AlertLevel.CRITICAL
            assert "Critical memory usage" in alerts[0].message
            mock_gc.assert_called_once()
        
        monitor.shutdown()
    
    def test_timing_decorator_sync(self):
        """Test timing decorator on synchronous functions."""
        monitor = PerformanceMonitor()
        
        @monitor.timing_decorator(category="test")
        def test_function(x: int, y: int = 10) -> int:
            time.sleep(0.01)  # Small delay for testing
            return x + y
        
        result = test_function(5, y=15)
        assert result == 20
        
        # Check that metric was recorded
        summary = monitor.get_metrics_summary("test.test_function")
        assert summary['total_calls'] == 1
        assert summary['avg_duration_ms'] >= 10  # At least 10ms due to sleep
        
        monitor.shutdown()
    
    @pytest.mark.asyncio
    async def test_timing_decorator_async(self):
        """Test timing decorator on asynchronous functions."""
        monitor = PerformanceMonitor()
        
        @monitor.timing_decorator(category="test")
        async def test_async_function(x: int) -> int:
            await asyncio.sleep(0.01)  # Small delay for testing
            return x * 2
        
        result = await test_async_function(5)
        assert result == 10
        
        # Check that metric was recorded
        summary = monitor.get_metrics_summary("test.test_async_function")
        assert summary['total_calls'] == 1
        assert summary['avg_duration_ms'] >= 10  # At least 10ms due to sleep
        
        monitor.shutdown()
    
    def test_timing_decorator_with_exception(self):
        """Test timing decorator behavior when function raises exception."""
        monitor = PerformanceMonitor()
        
        @monitor.timing_decorator(category="test")
        def failing_function():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError, match="Test error"):
            failing_function()
        
        # Check that metric was recorded with exception info
        metrics = list(monitor.metrics["test.failing_function"])
        assert len(metrics) == 1
        assert metrics[0].exception == "ValueError: Test error"
        
        monitor.shutdown()
    
    def test_get_metrics_summary_empty(self):
        """Test metrics summary with no data."""
        monitor = PerformanceMonitor()
        
        summary = monitor.get_metrics_summary("nonexistent_function")
        assert summary == {"message": "No metrics available"}
        
        monitor.shutdown()
    
    def test_get_metrics_summary_with_data(self):
        """Test metrics summary with actual data."""
        monitor = PerformanceMonitor()
        
        # Add some test metrics manually
        test_metric = PerformanceMetric(
            name="test.function",
            duration=100.0,
            memory_before=50.0,
            memory_after=60.0,
            timestamp=time.time(),
            thread_id=12345,
            function_name="function",
            args_count=2,
            kwargs_count=1,
            exception=None
        )
        
        monitor.metrics["test.function"].append(test_metric)
        
        summary = monitor.get_metrics_summary("function")
        assert summary['total_calls'] == 1
        assert summary['avg_duration_ms'] == 100.0
        assert summary['min_duration_ms'] == 100.0
        assert summary['max_duration_ms'] == 100.0
        assert summary['avg_memory_delta_mb'] == 10.0
        
        monitor.shutdown()
    
    def test_get_recent_alerts(self):
        """Test getting recent memory alerts."""
        monitor = PerformanceMonitor()
        
        # Add test alerts
        alert1 = MemoryAlert(
            level=AlertLevel.WARNING,
            message="Test warning",
            memory_usage=75.0,
            threshold=50.0,
            timestamp=time.time()
        )
        
        alert2 = MemoryAlert(
            level=AlertLevel.CRITICAL,
            message="Test critical",
            memory_usage=150.0,
            threshold=100.0,
            timestamp=time.time()
        )
        
        monitor.memory_alerts.append(alert1)
        monitor.memory_alerts.append(alert2)
        
        recent_alerts = monitor.get_recent_alerts(2)
        assert len(recent_alerts) == 2
        assert recent_alerts[0] == alert1
        assert recent_alerts[1] == alert2
        
        monitor.shutdown()


class TestConvenienceDecorators:
    """Test cases for convenience decorators and context managers."""
    
    def test_timing_decorator(self):
        """Test the global timing decorator."""
        @timing(category="global_test")
        def test_function(x: int) -> int:
            return x * 2
        
        result = test_function(5)
        assert result == 10
    
    def test_memory_timing_decorator(self):
        """Test the memory timing decorator."""
        @memory_timing(category="memory_test")
        def test_function(x: int) -> int:
            return x * 2
        
        result = test_function(5)
        assert result == 10
    
    def test_performance_context(self):
        """Test performance context manager."""
        with patch('src.utils.performance.perf_logger') as mock_logger:
            with performance_context("test_operation", include_memory=False):
                time.sleep(0.01)
            
            # Check that logging was called
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0][0]
            assert "Context 'test_operation'" in call_args
            assert "ms" in call_args
    
    def test_performance_context_with_memory(self):
        """Test performance context manager with memory monitoring."""
        with patch('src.utils.performance.perf_logger') as mock_logger:
            with patch('src.utils.performance.performance_monitor._get_memory_usage') as mock_memory:
                mock_memory.side_effect = [100.0, 105.0]  # Before and after
                
                with performance_context("test_operation", include_memory=True):
                    pass
                
                # Check that logging was called with memory delta
                mock_logger.info.assert_called_once()
                call_args = mock_logger.info.call_args[0][0]
                assert "Context 'test_operation'" in call_args
                assert "memory delta: 5.00MB" in call_args


class TestPerformanceReport:
    """Test cases for performance reporting functionality."""
    
    def test_get_performance_report(self):
        """Test performance report generation."""
        with patch('src.utils.performance.performance_monitor.get_metrics_summary') as mock_summary:
            with patch('src.utils.performance.performance_monitor.get_recent_alerts') as mock_alerts:
                with patch('src.utils.performance.performance_monitor._get_memory_usage') as mock_memory:
                    
                    # Mock data
                    mock_summary.return_value = {
                        'total_calls': 100,
                        'avg_duration_ms': 50.0,
                        'slow_operations': 5,
                        'exceptions': 2
                    }
                    
                    mock_alerts.return_value = [
                        MemoryAlert(
                            level=AlertLevel.WARNING,
                            message="High memory usage: 75.0MB",
                            memory_usage=75.0,
                            threshold=50.0,
                            timestamp=time.time()
                        )
                    ]
                    
                    mock_memory.return_value = 64.5
                    
                    report = get_performance_report()
                    
                    assert "📊 Performance Report" in report
                    assert "Current Memory: 64.50MB" in report
                    assert "Total Function Calls: 100" in report
                    assert "Average Duration: 50.00ms" in report
                    assert "Slow Operations: 5" in report
                    assert "Exceptions: 2" in report
                    assert "Recent Alerts (1):" in report
                    assert "WARNING: High memory usage: 75.0MB" in report


@pytest.mark.performance
class TestPerformanceIntegration:
    """Integration tests for performance monitoring."""
    
    @pytest.mark.slow
    def test_end_to_end_monitoring(self):
        """Test end-to-end performance monitoring scenario."""
        monitor = PerformanceMonitor(
            max_metrics=10,
            memory_threshold_mb=1.0,  # Very low threshold for testing
            slow_operation_threshold_ms=50.0
        )
        
        @monitor.timing_decorator(category="integration")
        def test_operation(iterations: int) -> int:
            total = 0
            for i in range(iterations):
                total += i
            return total
        
        # Perform multiple operations
        results = []
        for i in range(5):
            result = test_operation(100)
            results.append(result)
        
        # Check results
        assert len(results) == 5
        assert all(r == 4950 for r in results)  # Sum of 0 to 99
        
        # Check metrics
        summary = monitor.get_metrics_summary("integration.test_operation")
        assert summary['total_calls'] == 5
        assert summary['avg_duration_ms'] >= 0
        assert summary['exceptions'] == 0
        
        monitor.shutdown()
    
    @pytest.mark.asyncio
    async def test_concurrent_monitoring(self):
        """Test performance monitoring with concurrent operations."""
        monitor = PerformanceMonitor()
        
        @monitor.timing_decorator(category="concurrent")
        async def async_operation(delay: float) -> str:
            await asyncio.sleep(delay)
            return f"Done after {delay}s"
        
        # Run concurrent operations
        tasks = [
            async_operation(0.01),
            async_operation(0.02),
            async_operation(0.01),
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        assert all("Done after" in result for result in results)
        
        # Check metrics
        summary = monitor.get_metrics_summary("concurrent.async_operation")
        assert summary['total_calls'] == 3
        assert summary['avg_duration_ms'] >= 10  # At least 10ms average
        
        monitor.shutdown() 