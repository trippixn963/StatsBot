"""
Circuit breaker pattern implementation for failing operations.

This module provides a circuit breaker implementation that prevents
repeated calls to failing operations, allowing them time to recover.
"""

import asyncio
import time
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union, List, cast

from src.core.exceptions import CircuitBreakerError, StatsBotError
from src.types.models import CircuitBreakerState

T = TypeVar('T')

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    Circuit breaker implementation for preventing calls to failing services.
    
    The circuit breaker has three states:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Service is failing, calls are blocked
    - HALF_OPEN: Testing if service has recovered
    
    Attributes:
        name: Name of the circuit breaker (for logging)
        failure_threshold: Number of failures before opening circuit
        reset_timeout: Seconds to wait before attempting reset (half-open)
        half_open_max_calls: Maximum calls allowed in half-open state
        exclude_exceptions: Exception types that don't count as failures
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout: int = 60,
        half_open_max_calls: int = 1,
        exclude_exceptions: Optional[List[Type[Exception]]] = None
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_calls = half_open_max_calls
        self.exclude_exceptions = exclude_exceptions or []
        
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self._state
    
    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (calls blocked)."""
        return self._state == CircuitBreakerState.OPEN
    
    @property
    def last_failure_time(self) -> Optional[datetime]:
        """Get time of last failure."""
        return self._last_failure_time
    
    @property
    def remaining_timeout(self) -> Optional[float]:
        """Get remaining timeout before reset attempt."""
        if self._state != CircuitBreakerState.OPEN or self._last_failure_time is None:
            return None
        
        elapsed = (datetime.now() - self._last_failure_time).total_seconds()
        remaining = max(0, self.reset_timeout - elapsed)
        return remaining
    
    async def _update_state(self, new_state: CircuitBreakerState) -> None:
        """Update circuit breaker state with proper logging."""
        if new_state == self._state:
            return
        
        old_state = self._state
        self._state = new_state
        
        logger.info(
            f"Circuit breaker '{self.name}' state changed from {old_state.value} to {new_state.value}",
            extra={
                "circuit_breaker": self.name,
                "old_state": old_state.value,
                "new_state": new_state.value,
                "failure_count": self._failure_count,
                "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None
            }
        )
    
    async def _record_success(self) -> None:
        """Record successful operation."""
        async with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                # Successful call in half-open state, reset circuit
                self._failure_count = 0
                self._last_failure_time = None
                self._half_open_calls = 0
                await self._update_state(CircuitBreakerState.CLOSED)
    
    async def _record_failure(self, exception: Exception) -> None:
        """Record failed operation."""
        # Don't count excluded exceptions as failures
        if any(isinstance(exception, exc_type) for exc_type in self.exclude_exceptions):
            return
        
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()
            
            if self._state == CircuitBreakerState.CLOSED and self._failure_count >= self.failure_threshold:
                # Too many failures, open the circuit
                await self._update_state(CircuitBreakerState.OPEN)
            elif self._state == CircuitBreakerState.HALF_OPEN:
                # Failure in half-open state, reopen the circuit
                await self._update_state(CircuitBreakerState.OPEN)
    
    async def _check_state(self) -> None:
        """Check and potentially update circuit state."""
        async with self._lock:
            if self._state == CircuitBreakerState.OPEN and self._last_failure_time is not None:
                # Check if reset timeout has elapsed
                elapsed = (datetime.now() - self._last_failure_time).total_seconds()
                if elapsed >= self.reset_timeout:
                    # Timeout elapsed, move to half-open state
                    self._half_open_calls = 0
                    await self._update_state(CircuitBreakerState.HALF_OPEN)
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                # Check if we've reached max calls for half-open state
                if self._half_open_calls >= self.half_open_max_calls:
                    # Too many calls in half-open state, reopen circuit
                    await self._update_state(CircuitBreakerState.OPEN)
                else:
                    # Increment half-open call counter
                    self._half_open_calls += 1
    
    async def execute(self, operation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute operation with circuit breaker protection.
        
        Args:
            operation: Async function to execute
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation
            
        Returns:
            Any: Result of the operation
            
        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception raised by the operation
        """
        await self._check_state()
        
        if self._state == CircuitBreakerState.OPEN:
            # Circuit is open, block the call
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is open",
                service_name=self.name,
                failure_count=self._failure_count,
                next_retry_time=self._last_failure_time.timestamp() + self.reset_timeout if self._last_failure_time else None
            )
        
        try:
            # Execute the operation
            result = await operation(*args, **kwargs)
            # Record success
            await self._record_success()
            return result
        except Exception as e:
            # Record failure
            await self._record_failure(e)
            # Re-raise the exception
            raise
    
    def reset(self) -> None:
        """
        Manually reset the circuit breaker to closed state.
        
        This can be useful for testing or manual intervention.
        """
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._half_open_calls = 0
        
        logger.info(
            f"Circuit breaker '{self.name}' manually reset to CLOSED state",
            extra={"circuit_breaker": self.name}
        )


# Global registry of circuit breakers
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str) -> Optional[CircuitBreaker]:
    """
    Get a circuit breaker by name from the global registry.
    
    Args:
        name: Name of the circuit breaker
        
    Returns:
        Optional[CircuitBreaker]: The circuit breaker, or None if not found
    """
    return _circuit_breakers.get(name)


def register_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    reset_timeout: int = 60,
    half_open_max_calls: int = 1,
    exclude_exceptions: Optional[List[Type[Exception]]] = None
) -> CircuitBreaker:
    """
    Register a new circuit breaker in the global registry.
    
    Args:
        name: Name of the circuit breaker
        failure_threshold: Number of failures before opening circuit
        reset_timeout: Seconds to wait before attempting reset
        half_open_max_calls: Maximum calls allowed in half-open state
        exclude_exceptions: Exception types that don't count as failures
        
    Returns:
        CircuitBreaker: The created circuit breaker
    """
    if name in _circuit_breakers:
        return _circuit_breakers[name]
    
    circuit_breaker = CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        reset_timeout=reset_timeout,
        half_open_max_calls=half_open_max_calls,
        exclude_exceptions=exclude_exceptions
    )
    
    _circuit_breakers[name] = circuit_breaker
    return circuit_breaker


def circuit_breaker(
    name: Optional[str] = None,
    failure_threshold: int = 5,
    reset_timeout: int = 60,
    half_open_max_calls: int = 1,
    exclude_exceptions: Optional[List[Type[Exception]]] = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for applying circuit breaker to an async function.
    
    Args:
        name: Name of the circuit breaker (defaults to function name)
        failure_threshold: Number of failures before opening circuit
        reset_timeout: Seconds to wait before attempting reset
        half_open_max_calls: Maximum calls allowed in half-open state
        exclude_exceptions: Exception types that don't count as failures
        
    Returns:
        Callable: Decorated function with circuit breaker
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # Use function name if no name provided
        cb_name = name or f"{func.__module__}.{func.__qualname__}"
        
        # Get or create circuit breaker
        cb = register_circuit_breaker(
            name=cb_name,
            failure_threshold=failure_threshold,
            reset_timeout=reset_timeout,
            half_open_max_calls=half_open_max_calls,
            exclude_exceptions=exclude_exceptions
        )
        
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await cb.execute(func, *args, **kwargs)
        
        # Attach circuit breaker to function for inspection
        setattr(wrapper, "_circuit_breaker", cb)
        return wrapper
    
    return decorator