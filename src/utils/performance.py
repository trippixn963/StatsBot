"""
Performance Monitoring and Optimization Module.

This module provides comprehensive performance monitoring capabilities including:
- Timing decorators for critical operations with minimal overhead
- Memory usage monitoring and alerting for resource-constrained environments
- Performance metrics collection and reporting
- Resource optimization utilities

Key Features:
- Low-overhead timing decorators
- Memory usage tracking and alerts
- Performance metrics aggregation
- Resource optimization helpers
- Configurable thresholds and alerts
"""

import time
import functools
import asyncio
import threading
import psutil
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable, Any, Union
from collections import defaultdict, deque
from contextlib import contextmanager
import weakref
import gc
from dataclasses import dataclass, field
from enum import Enum

# Performance monitoring logger
perf_logger = logging.getLogger('performance')

class AlertLevel(Enum):
    """Alert severity levels for performance monitoring."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class PerformanceMetric:
    """Data class for storing performance metrics."""
    name: str
    duration: float
    memory_before: float
    memory_after: float
    timestamp: datetime
    thread_id: int
    function_name: str
    args_count: int
    kwargs_count: int
    exception: Optional[str] = None

@dataclass
class MemoryAlert:
    """Data class for memory usage alerts."""
    level: AlertLevel
    message: str
    memory_usage: float
    threshold: float
    timestamp: datetime

class PerformanceMonitor:
    """
    Comprehensive performance monitoring system.
    
    This class provides timing decorators, memory monitoring, and performance
    metrics collection with configurable thresholds and alerting.
    
    Attributes:
        metrics (Dict): Collection of performance metrics by function name
        memory_alerts (deque): Recent memory alerts
        thresholds (Dict): Performance thresholds for monitoring
        _lock (threading.Lock): Thread-safe operations lock
    """
    
    def __init__(self, 
                 max_metrics: int = 1000,
                 memory_threshold_mb: float = 512.0,
                 critical_memory_threshold_mb: float = 1024.0,
                 slow_operation_threshold_ms: float = 1000.0):
        """
        Initialize performance monitor.
        
        Args:
            max_metrics: Maximum number of metrics to store
            memory_threshold_mb: Memory threshold for warnings (MB)
            critical_memory_threshold_mb: Critical memory threshold (MB)
            slow_operation_threshold_ms: Threshold for slow operations (ms)
        """
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_metrics))
        self.memory_alerts: deque = deque(maxlen=100)
        self.thresholds = {
            'memory_warning': memory_threshold_mb,
            'memory_critical': critical_memory_threshold_mb,
            'slow_operation': slow_operation_threshold_ms
        }
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._last_gc_time = time.time()
        
        # Start background monitoring
        self._monitoring_active = True
        self._monitor_thread = threading.Thread(target=self._background_monitor, daemon=True)
        self._monitor_thread.start()
    
    def timing_decorator(self, 
                        include_memory: bool = True,
                        log_slow: bool = True,
                        category: str = "general") -> Callable:
        """
        Decorator for timing function execution with minimal overhead.
        
        Args:
            include_memory: Whether to include memory monitoring
            log_slow: Whether to log slow operations
            category: Category for grouping metrics
            
        Returns:
            Decorated function with performance monitoring
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await self._time_async_function(
                    func, args, kwargs, include_memory, log_slow, category
                )
            
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                return self._time_sync_function(
                    func, args, kwargs, include_memory, log_slow, category
                )
            
            # Return appropriate wrapper based on function type
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
                
        return decorator
    
    async def _time_async_function(self, 
                                 func: Callable, 
                                 args: tuple, 
                                 kwargs: dict,
                                 include_memory: bool,
                                 log_slow: bool,
                                 category: str) -> Any:
        """Time async function execution."""
        start_time = time.perf_counter()
        memory_before = self._get_memory_usage() if include_memory else 0.0
        exception_info = None
        
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            exception_info = f"{type(e).__name__}: {str(e)}"
            raise
        finally:
            duration = (time.perf_counter() - start_time) * 1000  # Convert to ms
            memory_after = self._get_memory_usage() if include_memory else 0.0
            
            self._record_metric(
                func, duration, memory_before, memory_after, 
                args, kwargs, exception_info, category, log_slow
            )
    
    def _time_sync_function(self, 
                           func: Callable, 
                           args: tuple, 
                           kwargs: dict,
                           include_memory: bool,
                           log_slow: bool,
                           category: str) -> Any:
        """Time sync function execution."""
        start_time = time.perf_counter()
        memory_before = self._get_memory_usage() if include_memory else 0.0
        exception_info = None
        
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            exception_info = f"{type(e).__name__}: {str(e)}"
            raise
        finally:
            duration = (time.perf_counter() - start_time) * 1000  # Convert to ms
            memory_after = self._get_memory_usage() if include_memory else 0.0
            
            self._record_metric(
                func, duration, memory_before, memory_after, 
                args, kwargs, exception_info, category, log_slow
            )
    
    def _record_metric(self, 
                      func: Callable, 
                      duration: float,
                      memory_before: float,
                      memory_after: float,
                      args: tuple,
                      kwargs: dict,
                      exception_info: Optional[str],
                      category: str,
                      log_slow: bool):
        """Record performance metric."""
        metric = PerformanceMetric(
            name=f"{category}.{func.__name__}",
            duration=duration,
            memory_before=memory_before,
            memory_after=memory_after,
            timestamp=datetime.now(timezone.utc),
            thread_id=threading.get_ident(),
            function_name=func.__name__,
            args_count=len(args),
            kwargs_count=len(kwargs),
            exception=exception_info
        )
        
        with self._lock:
            self.metrics[metric.name].append(metric)
        
        # Log slow operations
        if log_slow and duration > self.thresholds['slow_operation']:
            perf_logger.warning(
                f"Slow operation detected: {metric.name} took {duration:.2f}ms"
            )
        
        # Check memory usage
        if memory_after > 0:
            self._check_memory_thresholds(memory_after)
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024  # Convert to MB
        except Exception:
            return 0.0
    
    def _check_memory_thresholds(self, memory_usage: float):
        """Check memory usage against thresholds."""
        if memory_usage > self.thresholds['memory_critical']:
            alert = MemoryAlert(
                level=AlertLevel.CRITICAL,
                message=f"Critical memory usage: {memory_usage:.2f}MB",
                memory_usage=memory_usage,
                threshold=self.thresholds['memory_critical'],
                timestamp=datetime.now(timezone.utc)
            )
            self.memory_alerts.append(alert)
            perf_logger.critical(alert.message)
            
            # Trigger garbage collection for critical memory usage
            self._trigger_gc()
            
        elif memory_usage > self.thresholds['memory_warning']:
            alert = MemoryAlert(
                level=AlertLevel.WARNING,
                message=f"High memory usage: {memory_usage:.2f}MB",
                memory_usage=memory_usage,
                threshold=self.thresholds['memory_warning'],
                timestamp=datetime.now(timezone.utc)
            )
            self.memory_alerts.append(alert)
            perf_logger.warning(alert.message)
    
    def _trigger_gc(self):
        """Trigger garbage collection with rate limiting."""
        current_time = time.time()
        if current_time - self._last_gc_time > 60:  # Rate limit to once per minute
            gc.collect()
            self._last_gc_time = current_time
            perf_logger.info("Triggered garbage collection due to high memory usage")
    
    def _background_monitor(self):
        """Background monitoring thread."""
        while self._monitoring_active:
            try:
                memory_usage = self._get_memory_usage()
                if memory_usage > 0:
                    self._check_memory_thresholds(memory_usage)
                
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                perf_logger.error(f"Background monitoring error: {e}")
                time.sleep(60)  # Longer sleep on error
    
    def get_metrics_summary(self, function_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get performance metrics summary.
        
        Args:
            function_name: Optional function name to filter metrics
            
        Returns:
            Dictionary containing metrics summary
        """
        with self._lock:
            if function_name:
                metrics = [m for name, deque_metrics in self.metrics.items() 
                          if function_name in name for m in deque_metrics]
            else:
                metrics = [m for deque_metrics in self.metrics.values() 
                          for m in deque_metrics]
        
        if not metrics:
            return {"message": "No metrics available"}
        
        durations = [m.duration for m in metrics]
        memory_deltas = [m.memory_after - m.memory_before for m in metrics if m.memory_after > 0]
        
        summary = {
            "total_calls": len(metrics),
            "avg_duration_ms": sum(durations) / len(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
            "total_duration_ms": sum(durations),
            "exceptions": len([m for m in metrics if m.exception]),
            "slow_operations": len([m for m in metrics if m.duration > self.thresholds['slow_operation']])
        }
        
        if memory_deltas:
            summary.update({
                "avg_memory_delta_mb": sum(memory_deltas) / len(memory_deltas),
                "max_memory_delta_mb": max(memory_deltas),
                "min_memory_delta_mb": min(memory_deltas)
            })
        
        return summary
    
    def get_recent_alerts(self, count: int = 10) -> List[MemoryAlert]:
        """Get recent memory alerts."""
        with self._lock:
            return list(self.memory_alerts)[-count:]
    
    def shutdown(self):
        """Shutdown performance monitoring."""
        self._monitoring_active = False
        if self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)

# Global performance monitor instance
performance_monitor = PerformanceMonitor()

# Convenience decorators
timing = performance_monitor.timing_decorator
memory_timing = functools.partial(performance_monitor.timing_decorator, include_memory=True)
simple_timing = functools.partial(performance_monitor.timing_decorator, include_memory=False)

@contextmanager
def performance_context(name: str, include_memory: bool = True):
    """Context manager for timing code blocks."""
    start_time = time.perf_counter()
    memory_before = performance_monitor._get_memory_usage() if include_memory else 0.0
    
    try:
        yield
    finally:
        duration = (time.perf_counter() - start_time) * 1000
        memory_after = performance_monitor._get_memory_usage() if include_memory else 0.0
        
        perf_logger.info(
            f"Context '{name}': {duration:.2f}ms"
            + (f", memory delta: {memory_after - memory_before:.2f}MB" if include_memory else "")
        )

def optimize_memory():
    """Manual memory optimization trigger."""
    performance_monitor._trigger_gc()
    return performance_monitor._get_memory_usage()

def get_performance_report() -> str:
    """Get formatted performance report."""
    summary = performance_monitor.get_metrics_summary()
    alerts = performance_monitor.get_recent_alerts(5)
    current_memory = performance_monitor._get_memory_usage()
    
    report = f"""
📊 Performance Report
━━━━━━━━━━━━━━━━━━━━
Current Memory: {current_memory:.2f}MB
Total Function Calls: {summary.get('total_calls', 0)}
Average Duration: {summary.get('avg_duration_ms', 0):.2f}ms
Slow Operations: {summary.get('slow_operations', 0)}
Exceptions: {summary.get('exceptions', 0)}

Recent Alerts ({len(alerts)}):
"""
    
    for alert in alerts[-3:]:
        report += f"  {alert.level.value.upper()}: {alert.message}\n"
    
    return report.strip() 