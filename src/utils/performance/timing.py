"""
Timing decorators and utilities for performance monitoring.

This module provides low-overhead timing decorators and utilities for measuring
the performance of critical operations and collecting performance metrics.
"""

import time
import functools
import statistics
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast, Union
from dataclasses import dataclass, field
from datetime import datetime
import logging
import threading
import asyncio

from src.types.models import LogLevel
from src.utils.logging.structured_logger import StructuredLogger

# Type variable for generic function decorator
F = TypeVar('F', bound=Callable[..., Any])
AsyncF = TypeVar('AsyncF', bound=Callable[..., Any])

# Global performance metrics storage
_performance_metrics: Dict[str, List[float]] = {}
_metrics_lock = threading.Lock()


@dataclass
class PerformanceMetric:
    """
    Performance metric data for an operation.
    
    Attributes:
        name: Name of the operation
        count: Number of times the operation was executed
        total_time_ms: Total execution time in milliseconds
        min_time_ms: Minimum execution time in milliseconds
        max_time_ms: Maximum execution time in milliseconds
        avg_time_ms: Average execution time in milliseconds
        median_time_ms: Median execution time in milliseconds
        p95_time_ms: 95th percentile execution time in milliseconds
        last_execution: Timestamp of the last execution
    """
    name: str
    count: int
    total_time_ms: float
    min_time_ms: float
    max_time_ms: float
    avg_time_ms: float
    median_time_ms: float
    p95_time_ms: float
    last_execution: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'count': self.count,
            'total_time_ms': self.total_time_ms,
            'min_time_ms': self.min_time_ms,
            'max_time_ms': self.max_time_ms,
            'avg_time_ms': self.avg_time_ms,
            'median_time_ms': self.median_time_ms,
            'p95_time_ms': self.p95_time_ms,
            'last_execution': self.last_execution.isoformat()
        }


def timed(operation_name: str, threshold_ms: Optional[float] = None) -> Callable[[F], F]:
    """
    Decorator to time function execution and collect performance metrics.
    
    This decorator measures the execution time of a function and records
    the metrics for later analysis. It can also log warnings if the execution
    time exceeds a specified threshold.
    
    Args:
        operation_name: Name of the operation for metrics collection
        threshold_ms: Optional threshold in milliseconds for warning logs
        
    Returns:
        Decorated function
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get logger from first argument if it's a class method
            logger = None
            if args and hasattr(args[0], 'logger') and isinstance(args[0].logger, StructuredLogger):
                logger = args[0].logger
                
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000
                
                # Record metrics
                _record_metric(operation_name, duration_ms)
                
                # Log performance if logger is available
                if logger:
                    logger.performance(operation_name, duration_ms)
                    
                # Log warning if execution time exceeds threshold
                if threshold_ms is not None and duration_ms > threshold_ms:
                    if logger:
                        logger.warning(
                            f"Performance threshold exceeded: {operation_name} took {duration_ms:.2f}ms "
                            f"(threshold: {threshold_ms:.2f}ms)",
                            operation=operation_name,
                            duration_ms=duration_ms,
                            threshold_ms=threshold_ms
                        )
                    else:
                        logging.warning(
                            f"Performance threshold exceeded: {operation_name} took {duration_ms:.2f}ms "
                            f"(threshold: {threshold_ms:.2f}ms)"
                        )
                    
        return cast(F, wrapper)
    return decorator


def async_timed(operation_name: str, threshold_ms: Optional[float] = None) -> Callable[[AsyncF], AsyncF]:
    """
    Decorator to time async function execution and collect performance metrics.
    
    This decorator measures the execution time of an async function and records
    the metrics for later analysis. It can also log warnings if the execution
    time exceeds a specified threshold.
    
    Args:
        operation_name: Name of the operation for metrics collection
        threshold_ms: Optional threshold in milliseconds for warning logs
        
    Returns:
        Decorated async function
    """
    def decorator(func: AsyncF) -> AsyncF:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get logger from first argument if it's a class method
            logger = None
            if args and hasattr(args[0], 'logger') and isinstance(args[0].logger, StructuredLogger):
                logger = args[0].logger
                
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000
                
                # Record metrics
                _record_metric(operation_name, duration_ms)
                
                # Log performance if logger is available
                if logger:
                    logger.performance(operation_name, duration_ms)
                    
                # Log warning if execution time exceeds threshold
                if threshold_ms is not None and duration_ms > threshold_ms:
                    if logger:
                        logger.warning(
                            f"Performance threshold exceeded: {operation_name} took {duration_ms:.2f}ms "
                            f"(threshold: {threshold_ms:.2f}ms)",
                            operation=operation_name,
                            duration_ms=duration_ms,
                            threshold_ms=threshold_ms
                        )
                    else:
                        logging.warning(
                            f"Performance threshold exceeded: {operation_name} took {duration_ms:.2f}ms "
                            f"(threshold: {threshold_ms:.2f}ms)"
                        )
                    
        return cast(AsyncF, wrapper)
    return decorator


def _record_metric(operation_name: str, duration_ms: float) -> None:
    """
    Record a performance metric for an operation.
    
    Args:
        operation_name: Name of the operation
        duration_ms: Execution time in milliseconds
    """
    with _metrics_lock:
        if operation_name not in _performance_metrics:
            _performance_metrics[operation_name] = []
        _performance_metrics[operation_name].append(duration_ms)
        
        # Limit the number of stored metrics to prevent memory issues
        if len(_performance_metrics[operation_name]) > 1000:
            _performance_metrics[operation_name] = _performance_metrics[operation_name][-1000:]


def get_performance_metrics() -> Dict[str, PerformanceMetric]:
    """
    Get performance metrics for all operations.
    
    Returns:
        Dictionary mapping operation names to PerformanceMetric objects
    """
    result = {}
    
    with _metrics_lock:
        for operation_name, durations in _performance_metrics.items():
            if not durations:
                continue
                
            count = len(durations)
            total_time_ms = sum(durations)
            min_time_ms = min(durations)
            max_time_ms = max(durations)
            avg_time_ms = total_time_ms / count
            
            # Calculate median and 95th percentile
            sorted_durations = sorted(durations)
            median_time_ms = statistics.median(sorted_durations)
            p95_index = int(count * 0.95)
            p95_time_ms = sorted_durations[p95_index] if count > 20 else max_time_ms
            
            result[operation_name] = PerformanceMetric(
                name=operation_name,
                count=count,
                total_time_ms=total_time_ms,
                min_time_ms=min_time_ms,
                max_time_ms=max_time_ms,
                avg_time_ms=avg_time_ms,
                median_time_ms=median_time_ms,
                p95_time_ms=p95_time_ms
            )
            
    return result


def reset_performance_metrics() -> None:
    """Reset all performance metrics."""
    with _metrics_lock:
        _performance_metrics.clear()


def get_performance_report() -> str:
    """
    Generate a human-readable performance report.
    
    Returns:
        Formatted string with performance metrics
    """
    metrics = get_performance_metrics()
    
    if not metrics:
        return "No performance metrics available."
        
    lines = ["Performance Metrics:"]
    lines.append("-" * 80)
    lines.append(f"{'Operation':<30} {'Count':>8} {'Avg (ms)':>10} {'Min (ms)':>10} {'Max (ms)':>10} {'P95 (ms)':>10}")
    lines.append("-" * 80)
    
    # Sort operations by average time (descending)
    sorted_metrics = sorted(metrics.values(), key=lambda m: m.avg_time_ms, reverse=True)
    
    for metric in sorted_metrics:
        lines.append(
            f"{metric.name:<30} {metric.count:>8} {metric.avg_time_ms:>10.2f} "
            f"{metric.min_time_ms:>10.2f} {metric.max_time_ms:>10.2f} {metric.p95_time_ms:>10.2f}"
        )
        
    return "\n".join(lines)


class PerformanceContext:
    """
    Context manager for timing code blocks.
    
    Example:
        with PerformanceContext("database_query") as ctx:
            # Code to time
            result = db.execute_query()
            
        # Access timing information
        print(f"Query took {ctx.duration_ms} ms")
    """
    
    def __init__(self, operation_name: str, logger: Optional[StructuredLogger] = None,
                 threshold_ms: Optional[float] = None):
        """
        Initialize a new performance context.
        
        Args:
            operation_name: Name of the operation for metrics collection
            logger: Optional structured logger for performance logging
            threshold_ms: Optional threshold in milliseconds for warning logs
        """
        self.operation_name = operation_name
        self.logger = logger
        self.threshold_ms = threshold_ms
        self.start_time: float = 0
        self.end_time: float = 0
        self.duration_ms: float = 0
        
    def __enter__(self) -> 'PerformanceContext':
        """Start timing when entering the context."""
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop timing when exiting the context and record metrics."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        
        # Record metrics
        _record_metric(self.operation_name, self.duration_ms)
        
        # Log performance if logger is available
        if self.logger:
            self.logger.performance(self.operation_name, self.duration_ms)
            
        # Log warning if execution time exceeds threshold
        if self.threshold_ms is not None and self.duration_ms > self.threshold_ms:
            if self.logger:
                self.logger.warning(
                    f"Performance threshold exceeded: {self.operation_name} took {self.duration_ms:.2f}ms "
                    f"(threshold: {self.threshold_ms:.2f}ms)",
                    operation=self.operation_name,
                    duration_ms=self.duration_ms,
                    threshold_ms=self.threshold_ms
                )
            else:
                logging.warning(
                    f"Performance threshold exceeded: {self.operation_name} took {self.duration_ms:.2f}ms "
                    f"(threshold: {self.threshold_ms:.2f}ms)"
                )


class AsyncPerformanceContext:
    """
    Async context manager for timing async code blocks.
    
    Example:
        async with AsyncPerformanceContext("api_request") as ctx:
            # Async code to time
            response = await client.get(url)
            
        # Access timing information
        print(f"Request took {ctx.duration_ms} ms")
    """
    
    def __init__(self, operation_name: str, logger: Optional[StructuredLogger] = None,
                 threshold_ms: Optional[float] = None):
        """
        Initialize a new async performance context.
        
        Args:
            operation_name: Name of the operation for metrics collection
            logger: Optional structured logger for performance logging
            threshold_ms: Optional threshold in milliseconds for warning logs
        """
        self.operation_name = operation_name
        self.logger = logger
        self.threshold_ms = threshold_ms
        self.start_time: float = 0
        self.end_time: float = 0
        self.duration_ms: float = 0
        
    async def __aenter__(self) -> 'AsyncPerformanceContext':
        """Start timing when entering the context."""
        self.start_time = time.time()
        return self
        
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop timing when exiting the context and record metrics."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        
        # Record metrics
        _record_metric(self.operation_name, self.duration_ms)
        
        # Log performance if logger is available
        if self.logger:
            self.logger.performance(self.operation_name, self.duration_ms)
            
        # Log warning if execution time exceeds threshold
        if self.threshold_ms is not None and self.duration_ms > self.threshold_ms:
            if self.logger:
                self.logger.warning(
                    f"Performance threshold exceeded: {self.operation_name} took {self.duration_ms:.2f}ms "
                    f"(threshold: {self.threshold_ms:.2f}ms)",
                    operation=self.operation_name,
                    duration_ms=self.duration_ms,
                    threshold_ms=self.threshold_ms
                )
            else:
                logging.warning(
                    f"Performance threshold exceeded: {self.operation_name} took {self.duration_ms:.2f}ms "
                    f"(threshold: {self.threshold_ms:.2f}ms)"
                )