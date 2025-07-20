"""
Helper functions for common async operations.

This module provides utility functions for common async patterns like
concurrency limiting, timeouts, periodic tasks, and rate limiting.
"""

import asyncio
import functools
import logging
import time
from typing import TypeVar, List, Callable, Coroutine, Any, Optional, Dict, Set, Tuple

T = TypeVar('T')
logger = logging.getLogger(__name__)

async def gather_with_concurrency(limit: int, *tasks) -> List[Any]:
    """
    Run coroutines with a concurrency limit.
    
    Similar to asyncio.gather but limits the number of coroutines
    running concurrently.
    
    Args:
        limit: Maximum number of coroutines to run concurrently
        *tasks: Coroutines to run
        
    Returns:
        List of results from the coroutines in the same order
    """
    semaphore = asyncio.Semaphore(limit)
    
    async def sem_task(task):
        async with semaphore:
            return await task
    
    return await asyncio.gather(*(sem_task(task) for task in tasks))

async def run_with_timeout(coro: Coroutine[Any, Any, T], timeout: float) -> T:
    """
    Run a coroutine with a timeout.
    
    Args:
        coro: Coroutine to run
        timeout: Timeout in seconds
        
    Returns:
        Result of the coroutine
        
    Raises:
        asyncio.TimeoutError: If the coroutine doesn't complete within the timeout
    """
    return await asyncio.wait_for(coro, timeout)

def periodic_task(interval: float):
    """
    Decorator to run a coroutine function periodically.
    
    Args:
        interval: Time between executions in seconds
        
    Returns:
        Decorator function
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            while True:
                try:
                    start_time = time.time()
                    await func(*args, **kwargs)
                    
                    # Calculate sleep time, accounting for execution time
                    elapsed = time.time() - start_time
                    sleep_time = max(0, interval - elapsed)
                    await asyncio.sleep(sleep_time)
                except asyncio.CancelledError:
                    logger.debug(f"Periodic task {func.__name__} cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in periodic task {func.__name__}: {e}", exc_info=True)
                    await asyncio.sleep(interval)  # Still sleep on error
        return wrapper
    return decorator

def debounce(wait_time: float):
    """
    Decorator to debounce a coroutine function.
    
    Only runs the function after wait_time seconds have elapsed since the last call.
    
    Args:
        wait_time: Time to wait in seconds
        
    Returns:
        Decorator function
    """
    def decorator(func):
        pending_calls: Dict[Tuple, asyncio.Task] = {}
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Create a key based on the function arguments
            call_key = (args, tuple(sorted(kwargs.items())))
            
            # Cancel any pending call with the same arguments
            if call_key in pending_calls and not pending_calls[call_key].done():
                pending_calls[call_key].cancel()
            
            # Create a task for the new call
            async def delayed_call():
                await asyncio.sleep(wait_time)
                try:
                    await func(*args, **kwargs)
                finally:
                    # Clean up the reference
                    if call_key in pending_calls:
                        del pending_calls[call_key]
            
            pending_calls[call_key] = asyncio.create_task(delayed_call())
        
        return wrapper
    return decorator

def throttle(wait_time: float):
    """
    Decorator to throttle a coroutine function.
    
    Ensures the function is not called more than once every wait_time seconds.
    
    Args:
        wait_time: Minimum time between calls in seconds
        
    Returns:
        Decorator function
    """
    def decorator(func):
        last_called = 0.0
        lock = asyncio.Lock()
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal last_called
            
            async with lock:
                now = time.time()
                time_since_last = now - last_called
                
                if time_since_last < wait_time:
                    # Need to wait before calling again
                    await asyncio.sleep(wait_time - time_since_last)
                
                # Update the last called time and call the function
                last_called = time.time()
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator