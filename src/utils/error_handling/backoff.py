"""
Exponential backoff implementation with jitter for rate-limited operations.

This module provides utilities for implementing exponential backoff with jitter,
which is useful for handling rate-limited operations and network failures.
"""

import asyncio
import random
import time
from functools import wraps
from typing import Any, Callable, Optional, Type, TypeVar, Union, List, Dict, cast

from src.core.exceptions import RateLimitError, NetworkError, StatsBotError
from src.types.models import RetryConfig

T = TypeVar('T')


def calculate_backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    jitter_factor: float = 0.25
) -> float:
    """
    Calculate delay for exponential backoff with optional jitter.
    
    Args:
        attempt: Current attempt number (0-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential calculation
        jitter: Whether to add random jitter
        jitter_factor: Factor for jitter calculation (0.25 = ±25%)
        
    Returns:
        float: Calculated delay in seconds
    """
    # Calculate exponential delay
    delay = min(base_delay * (exponential_base ** attempt), max_delay)
    
    # Add jitter if enabled
    if jitter and delay > 0:
        jitter_amount = delay * jitter_factor
        delay += random.uniform(-jitter_amount, jitter_amount)
    
    # Ensure delay is not negative
    return max(0.0, delay)


async def with_exponential_backoff(
    operation: Callable[..., Any],
    *args: Any,
    retry_config: Optional[RetryConfig] = None,
    retry_on_exceptions: Optional[List[Type[Exception]]] = None,
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    exponential_base: Optional[float] = None,
    jitter: Optional[bool] = None,
    on_backoff: Optional[Callable[[int, float, Exception], None]] = None,
    **kwargs: Any
) -> Any:
    """
    Execute an operation with exponential backoff retry logic.
    
    Args:
        operation: Async function to execute
        *args: Positional arguments for the operation
        retry_config: Configuration for retry behavior
        retry_on_exceptions: List of exception types to retry on
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential calculation
        jitter: Whether to add random jitter
        on_backoff: Callback function called on each backoff
        **kwargs: Keyword arguments for the operation
        
    Returns:
        Any: Result of the operation
        
    Raises:
        Exception: The last exception encountered after all retries
    """
    # Use provided retry config or create default
    config = retry_config or RetryConfig()
    
    # Override config with explicit parameters if provided
    if max_attempts is not None:
        config.max_attempts = max_attempts
    if base_delay is not None:
        config.base_delay = base_delay
    if max_delay is not None:
        config.max_delay = max_delay
    if exponential_base is not None:
        config.exponential_base = exponential_base
    if jitter is not None:
        config.jitter = jitter
    
    # Default exceptions to retry on
    if retry_on_exceptions is None:
        retry_on_exceptions = [RateLimitError, NetworkError, asyncio.TimeoutError]
    
    attempt = 0
    last_exception = None
    
    while attempt <= config.max_attempts:
        try:
            # Attempt the operation
            return await operation(*args, **kwargs)
        
        except tuple(retry_on_exceptions) as e:
            last_exception = e
            attempt += 1
            
            # If we've reached max attempts, re-raise the exception
            if attempt > config.max_attempts:
                break
            
            # Calculate delay for this attempt
            delay = config.calculate_delay(attempt)
            
            # Call the backoff callback if provided
            if on_backoff:
                on_backoff(attempt, delay, e)
            
            # Wait before retrying
            await asyncio.sleep(delay)
    
    # If we get here, we've exhausted all retries
    if isinstance(last_exception, RateLimitError):
        raise RateLimitError(
            f"Operation failed after {config.max_attempts} attempts due to rate limits",
            retry_after=getattr(last_exception, 'retry_after', None),
            endpoint=getattr(last_exception, 'endpoint', None)
        ) from last_exception
    elif isinstance(last_exception, NetworkError):
        raise NetworkError(
            f"Operation failed after {config.max_attempts} attempts due to network errors",
            retry_count=config.max_attempts
        ) from last_exception
    elif last_exception is not None:
        raise last_exception
    else:
        # This should never happen, but just in case
        raise RuntimeError(f"Operation failed after {config.max_attempts} attempts for unknown reasons")


def exponential_backoff(
    retry_config: Optional[RetryConfig] = None,
    retry_on_exceptions: Optional[List[Type[Exception]]] = None,
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    exponential_base: Optional[float] = None,
    jitter: Optional[bool] = None,
    on_backoff: Optional[Callable[[int, float, Exception], None]] = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for applying exponential backoff to an async function.
    
    Args:
        retry_config: Configuration for retry behavior
        retry_on_exceptions: List of exception types to retry on
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential calculation
        jitter: Whether to add random jitter
        on_backoff: Callback function called on each backoff
        
    Returns:
        Callable: Decorated function with exponential backoff
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await with_exponential_backoff(
                func,
                *args,
                retry_config=retry_config,
                retry_on_exceptions=retry_on_exceptions,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                exponential_base=exponential_base,
                jitter=jitter,
                on_backoff=on_backoff,
                **kwargs
            )
        return wrapper
    return decorator