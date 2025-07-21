"""
Performance timing utilities.

This module provides decorators and context managers for timing code execution
and collecting performance metrics.
"""

import time
import functools
import asyncio
from typing import Dict, Any, Optional, Callable, TypeVar, cast
from contextlib import contextmanager

# Type variables for generic function types
F = TypeVar('F', bound=Callable[..., Any])
C = TypeVar('C', bound=Callable[..., Any])

# Global performance metrics storage
_performance_metrics: Dict[str, Dict[str, Any]] = {}

def get_performance_metrics() -> Dict[str, Dict[str, Any]]:
    """
    Get the current performance metrics.
    
    Returns:
        Dict: Performance metrics by category and operation
    """
    return _performance_metrics

def reset_performance_metrics() -> None:
    """Reset all performance metrics."""
    _performance_metrics.clear()

def _record_timing(category: str, operation: str, duration: float) -> None:
    """
    Record a timing measurement.
    
    Args:
        category: Category of the operation
        operation: Name of the operation
        duration: Duration in seconds
    """
    if category not in _performance_metrics:
        _performance_metrics[category] = {}
        
    if operation not in _performance_metrics[category]:
        _performance_metrics[category][operation] = {
            'count': 0,
            'total_time': 0.0,
            'min_time': float('inf'),
            'max_time': 0.0,
            'avg_time': 0.0
        }
    
    metrics = _performance_metrics[category][operation]
    metrics['count'] += 1
    metrics['total_time'] += duration
    metrics['min_time'] = min(metrics['min_time'], duration)
    metrics['max_time'] = max(metrics['max_time'], duration)
    metrics['avg_time'] = metrics['total_time'] / metrics['count']

def timing(category: str = "default", operation: Optional[str] = None) -> Callable[[F], F]:
    """
    Decorator for timing function execution.
    
    Args:
        category: Category for the timing measurement
        operation: Name of the operation (defaults to function name)
        
    Returns:
        Decorated function
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            op_name = operation or func.__name__
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                _record_timing(category, op_name, duration)
        
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            op_name = operation or func.__name__
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                _record_timing(category, op_name, duration)
        
        if asyncio.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        return cast(F, wrapper)
    
    return decorator

def async_timed(name: str) -> Callable[[C], C]:
    """
    Decorator specifically for timing async functions.
    
    Args:
        name: Name of the operation
        
    Returns:
        Decorated async function
    """
    def decorator(func: C) -> C:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.time() - start_time
                _record_timing("async", name, duration)
        
        return cast(C, wrapper)
    
    return decorator

@contextmanager
def performance_context(operation: str, category: str = "context") -> None:
    """
    Context manager for timing code blocks.
    
    Args:
        operation: Name of the operation
        category: Category for the timing measurement
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        _record_timing(category, operation, duration)