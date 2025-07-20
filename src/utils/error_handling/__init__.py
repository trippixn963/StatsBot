"""
Error handling utilities for StatsBot.

This module provides error handling utilities including:
- Exponential backoff with jitter for rate-limited operations
- Circuit breaker pattern for failing operations
- Retry mechanisms with proper timeout handling
"""

from .backoff import with_exponential_backoff, calculate_backoff_delay
from .circuit_breaker import CircuitBreaker, circuit_breaker
from .retry import with_retry, with_timeout

__all__ = [
    'with_exponential_backoff',
    'calculate_backoff_delay',
    'CircuitBreaker',
    'circuit_breaker',
    'with_retry',
    'with_timeout'
]