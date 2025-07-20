"""
Retry mechanisms with proper timeout handling and graceful degradation.

This module provides utilities for retrying operations with timeouts
and implementing graceful degradation when operations fail.
"""

import asyncio
import functools
import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union, cast

from src.core.exceptions import AsyncOperationError, StatsBotError

T = TypeVar('T')

logger = logging.getLogger(__name__)


async def with_timeout(
    operation: Callable[..., Any],
    *args: Any,
    timeout: float,
    timeout_message: Optional[str] = None,
    operation_name: Optional[str] = None,
    **kwargs: Any
) -> Any:
    """
    Execute an operation with a timeout.
    
    Args:
        operation: Async function to execute
        *args: Positional arguments for the operation
        timeout: Timeout in seconds
        timeout_message: Custom message for timeout error
        operation_name: Name of the operation for error reporting
        **kwargs: Keyword arguments for the operation
        
    Returns:
        Any: Result of the operation
        
    Raises:
        AsyncOperationError: If the operation times out
    """
    try:
        return await asyncio.wait_for(operation(*args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError:
        op_name = operation_name or getattr(operation, "__name__", "unknown_operation")
        message = timeout_message or f"Operation {op_name} timed out after {timeout} seconds"
        
        logger.warning(
            message,
            extra={
                "operation_name": op_name,
                "timeout_value": timeout,
                "arg_count": len(args) if args else 0,
                "kwarg_keys": list(kwargs.keys()) if kwargs else None
            }
        )
        
        raise AsyncOperationError(
            message,
            operation_name=op_name,
            timeout=timeout,
            was_cancelled=True
        )


def timeout(
    timeout_seconds: float,
    timeout_message: Optional[str] = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for applying timeout to an async function.
    
    Args:
        timeout_seconds: Timeout in seconds
        timeout_message: Custom message for timeout error
        
    Returns:
        Callable: Decorated function with timeout
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await with_timeout(
                func,
                *args,
                timeout=timeout_seconds,
                timeout_message=timeout_message,
                operation_name=func.__qualname__,
                **kwargs
            )
        return wrapper
    return decorator


async def with_retry(
    operation: Callable[..., Any],
    *args: Any,
    max_attempts: int = 3,
    retry_on_exceptions: Optional[List[Type[Exception]]] = None,
    retry_delay: float = 1.0,
    timeout: Optional[float] = None,
    operation_name: Optional[str] = None,
    fallback_value: Any = None,
    fallback_function: Optional[Callable[..., Any]] = None,
    graceful_degradation: bool = False,
    **kwargs: Any
) -> Any:
    """
    Execute an operation with retry logic and optional timeout.
    
    Args:
        operation: Async function to execute
        *args: Positional arguments for the operation
        max_attempts: Maximum number of retry attempts
        retry_on_exceptions: List of exception types to retry on
        retry_delay: Delay between retries in seconds
        timeout: Optional timeout for each attempt in seconds
        operation_name: Name of the operation for error reporting
        fallback_value: Value to return if all attempts fail
        fallback_function: Function to call if all attempts fail
        graceful_degradation: Whether to return fallback instead of raising
        **kwargs: Keyword arguments for the operation
        
    Returns:
        Any: Result of the operation or fallback
        
    Raises:
        Exception: The last exception encountered after all retries
    """
    op_name = operation_name or getattr(operation, "__name__", "unknown_operation")
    
    # Default exceptions to retry on
    if retry_on_exceptions is None:
        retry_on_exceptions = [Exception]
    
    last_exception = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Apply timeout if specified
            if timeout is not None:
                return await with_timeout(
                    operation,
                    *args,
                    timeout=timeout,
                    operation_name=op_name,
                    **kwargs
                )
            else:
                return await operation(*args, **kwargs)
        
        except tuple(retry_on_exceptions) as e:
            last_exception = e
            
            # Log the failure
            logger.warning(
                f"Attempt {attempt}/{max_attempts} for {op_name} failed: {str(e)}",
                extra={
                    "operation": op_name,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "exception": str(e),
                    "exception_type": type(e).__name__
                },
                exc_info=True
            )
            
            # If this was the last attempt, handle accordingly
            if attempt == max_attempts:
                break
            
            # Wait before retrying
            await asyncio.sleep(retry_delay)
    
    # All attempts failed, handle graceful degradation
    if graceful_degradation:
        if fallback_function is not None:
            logger.info(
                f"All {max_attempts} attempts for {op_name} failed, using fallback function",
                extra={"operation": op_name, "max_attempts": max_attempts}
            )
            return await fallback_function(*args, **kwargs)
        else:
            logger.info(
                f"All {max_attempts} attempts for {op_name} failed, using fallback value",
                extra={"operation": op_name, "max_attempts": max_attempts}
            )
            return fallback_value
    
    # No graceful degradation, raise the last exception
    if isinstance(last_exception, StatsBotError):
        raise last_exception
    elif last_exception is not None:
        raise AsyncOperationError(
            f"Operation {op_name} failed after {max_attempts} attempts",
            operation_name=op_name,
            was_cancelled=False
        ) from last_exception
    else:
        # This should never happen, but just in case
        raise RuntimeError(f"Operation {op_name} failed after {max_attempts} attempts for unknown reasons")


def retry(
    max_attempts: int = 3,
    retry_on_exceptions: Optional[List[Type[Exception]]] = None,
    retry_delay: float = 1.0,
    timeout: Optional[float] = None,
    fallback_value: Any = None,
    fallback_function: Optional[Callable[..., Any]] = None,
    graceful_degradation: bool = False
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for applying retry logic to an async function.
    
    Args:
        max_attempts: Maximum number of retry attempts
        retry_on_exceptions: List of exception types to retry on
        retry_delay: Delay between retries in seconds
        timeout: Optional timeout for each attempt in seconds
        fallback_value: Value to return if all attempts fail
        fallback_function: Function to call if all attempts fail
        graceful_degradation: Whether to return fallback instead of raising
        
    Returns:
        Callable: Decorated function with retry logic
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await with_retry(
                func,
                *args,
                max_attempts=max_attempts,
                retry_on_exceptions=retry_on_exceptions,
                retry_delay=retry_delay,
                timeout=timeout,
                operation_name=func.__qualname__,
                fallback_value=fallback_value,
                fallback_function=fallback_function,
                graceful_degradation=graceful_degradation,
                **kwargs
            )
        return wrapper
    return decorator