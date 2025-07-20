"""
Connection recovery mechanisms for Discord connection failures.

This module provides utilities for handling Discord connection failures,
implementing automatic reconnection with progressive delays, and
maintaining state consistency during connection interruptions.
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, TypeVar, Union, cast

import discord

from src.core.exceptions import NetworkError, DiscordAPIError, StatsBotError
from src.types.models import ConnectionState, RetryConfig
from src.utils.logging.structured_logger import StructuredLogger
from .backoff import calculate_backoff_delay

# Type for connection event handlers
ConnectionEventHandler = Callable[[], Any]
ReconnectHandler = Callable[[int, float], Any]

class ConnectionRecoveryManager:
    """
    Manages automatic reconnection and state recovery for Discord connections.
    
    This class provides:
    1. Automatic reconnection with progressive delays
    2. State consistency maintenance during connection interruptions
    3. Event notifications for connection state changes
    
    Attributes:
        logger: Logger instance
        max_reconnect_attempts: Maximum number of reconnection attempts
        initial_backoff: Initial backoff delay in seconds
        max_backoff: Maximum backoff delay in seconds
        jitter_factor: Random jitter factor to add to backoff (0.0-1.0)
    """
    
    def __init__(
        self,
        logger: Optional[StructuredLogger] = None,
        max_reconnect_attempts: int = 20,
        initial_backoff: float = 1.0,
        max_backoff: float = 300.0,
        jitter_factor: float = 0.25
    ):
        """
        Initialize a new connection recovery manager.
        
        Args:
            logger: Logger instance (creates one if None)
            max_reconnect_attempts: Maximum number of reconnection attempts
            initial_backoff: Initial backoff delay in seconds
            max_backoff: Maximum backoff delay in seconds
            jitter_factor: Random jitter factor to add to backoff (0.0-1.0)
        """
        self.logger = logger or StructuredLogger("connection_recovery")
        self.max_reconnect_attempts = max_reconnect_attempts
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.jitter_factor = jitter_factor
        
        # Internal state
        self._connection_state = ConnectionState.DISCONNECTED
        self._reconnect_attempts = 0
        self._last_disconnect_time: Optional[datetime] = None
        self._last_connect_time: Optional[datetime] = None
        self._disconnect_reasons: List[str] = []
        self._connection_stats = {
            "total_disconnects": 0,
            "total_reconnects": 0,
            "failed_reconnects": 0,
            "max_downtime": 0.0,
            "current_downtime": 0.0,
            "last_disconnect_reason": None
        }
        
        # Event handlers
        self._on_disconnect_handlers: List[ConnectionEventHandler] = []
        self._on_reconnect_handlers: List[ConnectionEventHandler] = []
        self._on_reconnect_attempt_handlers: List[ReconnectHandler] = []
        self._on_reconnect_failed_handlers: List[ConnectionEventHandler] = []
        self._on_max_retries_handlers: List[ConnectionEventHandler] = []
        
        # Recovery task
        self._recovery_task: Optional[asyncio.Task] = None
        self._recovery_lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()
    
    @property
    def connection_state(self) -> ConnectionState:
        """Get current connection state."""
        return self._connection_state
    
    @property
    def reconnect_attempts(self) -> int:
        """Get current number of reconnection attempts."""
        return self._reconnect_attempts
    
    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._connection_state == ConnectionState.CONNECTED
    
    @property
    def is_reconnecting(self) -> bool:
        """Check if currently attempting to reconnect."""
        return self._connection_state == ConnectionState.RECONNECTING
    
    @property
    def current_downtime(self) -> float:
        """Get current downtime in seconds if disconnected."""
        if self._connection_state == ConnectionState.CONNECTED or self._last_disconnect_time is None:
            return 0.0
        
        return (datetime.now() - self._last_disconnect_time).total_seconds()
    
    @property
    def connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        stats = dict(self._connection_stats)
        stats["current_state"] = self._connection_state.value
        stats["reconnect_attempts"] = self._reconnect_attempts
        stats["current_downtime"] = self.current_downtime
        return stats
    
    def add_disconnect_handler(self, handler: ConnectionEventHandler) -> None:
        """Add handler to be called on disconnect."""
        self._on_disconnect_handlers.append(handler)
    
    def add_reconnect_handler(self, handler: ConnectionEventHandler) -> None:
        """Add handler to be called on successful reconnect."""
        self._on_reconnect_handlers.append(handler)
    
    def add_reconnect_attempt_handler(self, handler: ReconnectHandler) -> None:
        """Add handler to be called on reconnect attempt."""
        self._on_reconnect_attempt_handlers.append(handler)
    
    def add_reconnect_failed_handler(self, handler: ConnectionEventHandler) -> None:
        """Add handler to be called when a reconnect attempt fails."""
        self._on_reconnect_failed_handlers.append(handler)
    
    def add_max_retries_handler(self, handler: ConnectionEventHandler) -> None:
        """Add handler to be called when max retries are reached."""
        self._on_max_retries_handlers.append(handler)
    
    async def on_disconnect(self, reason: Optional[str] = None) -> None:
        """
        Handle disconnection event.
        
        This method should be called when a Discord connection is lost.
        It will start the automatic reconnection process.
        
        Args:
            reason: Reason for disconnection (if known)
        """
        async with self._recovery_lock:
            # Update state
            self._connection_state = ConnectionState.DISCONNECTED
            self._last_disconnect_time = datetime.now()
            self._connection_stats["total_disconnects"] += 1
            
            if reason:
                self._disconnect_reasons.append(reason)
                self._connection_stats["last_disconnect_reason"] = reason
            
            self.logger.warning(
                "Discord connection lost",
                reason=reason,
                disconnect_count=self._connection_stats["total_disconnects"]
            )
            
            # Notify disconnect handlers
            for handler in self._on_disconnect_handlers:
                try:
                    handler()
                except Exception as e:
                    self.logger.error(f"Error in disconnect handler: {str(e)}", exc_info=True)
            
            # Start recovery process if not already running
            if self._recovery_task is None or self._recovery_task.done():
                self._recovery_task = asyncio.create_task(self._reconnect_loop())
    
    async def on_connect(self) -> None:
        """
        Handle connection event.
        
        This method should be called when a Discord connection is established.
        It will reset the reconnection state.
        """
        async with self._recovery_lock:
            # Calculate downtime if reconnecting
            if self._connection_state == ConnectionState.RECONNECTING and self._last_disconnect_time is not None:
                downtime = (datetime.now() - self._last_disconnect_time).total_seconds()
                self._connection_stats["current_downtime"] = downtime
                self._connection_stats["max_downtime"] = max(
                    self._connection_stats["max_downtime"], 
                    downtime
                )
            
            # Update state
            previous_state = self._connection_state
            self._connection_state = ConnectionState.CONNECTED
            self._last_connect_time = datetime.now()
            
            # Reset reconnect attempts if this was a successful reconnect
            if previous_state == ConnectionState.RECONNECTING:
                self._connection_stats["total_reconnects"] += 1
                self.logger.info(
                    "Successfully reconnected to Discord",
                    reconnect_attempts=self._reconnect_attempts,
                    downtime=self._connection_stats["current_downtime"]
                )
                
                # Notify reconnect handlers
                for handler in self._on_reconnect_handlers:
                    try:
                        handler()
                    except Exception as e:
                        self.logger.error(f"Error in reconnect handler: {str(e)}", exc_info=True)
            
            # Reset reconnect attempts
            self._reconnect_attempts = 0
            self._disconnect_reasons = []
    
    async def shutdown(self) -> None:
        """
        Shutdown the recovery manager.
        
        This will stop any ongoing reconnection attempts.
        """
        self._shutdown_event.set()
        
        if self._recovery_task and not self._recovery_task.done():
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
            
        self.logger.info("Connection recovery manager shutdown")
    
    async def _reconnect_loop(self) -> None:
        """
        Main reconnection loop with progressive delays.
        
        This method implements the automatic reconnection logic with
        exponential backoff and jitter.
        """
        self._reconnect_attempts = 0
        
        while not self._shutdown_event.is_set():
            # Check if we've reached max attempts
            if self._reconnect_attempts >= self.max_reconnect_attempts:
                self.logger.error(
                    f"Maximum reconnection attempts ({self.max_reconnect_attempts}) reached",
                    max_attempts=self.max_reconnect_attempts,
                    total_disconnects=self._connection_stats["total_disconnects"],
                    disconnect_reasons=self._disconnect_reasons
                )
                
                # Notify max retries handlers
                for handler in self._on_max_retries_handlers:
                    try:
                        handler()
                    except Exception as e:
                        self.logger.error(f"Error in max retries handler: {str(e)}", exc_info=True)
                
                # Stop reconnection attempts
                break
            
            # Calculate delay with exponential backoff and jitter
            delay = calculate_backoff_delay(
                attempt=self._reconnect_attempts,
                base_delay=self.initial_backoff,
                max_delay=self.max_backoff,
                jitter=True,
                jitter_factor=self.jitter_factor
            )
            
            # Update state
            self._connection_state = ConnectionState.RECONNECTING
            self._reconnect_attempts += 1
            
            self.logger.info(
                f"Attempting to reconnect (attempt {self._reconnect_attempts}/{self.max_reconnect_attempts}) in {delay:.2f} seconds",
                attempt=self._reconnect_attempts,
                max_attempts=self.max_reconnect_attempts,
                delay=delay,
                downtime=self.current_downtime
            )
            
            # Notify reconnect attempt handlers
            for handler in self._on_reconnect_attempt_handlers:
                try:
                    handler(self._reconnect_attempts, delay)
                except Exception as e:
                    self.logger.error(f"Error in reconnect attempt handler: {str(e)}", exc_info=True)
            
            # Wait for the delay
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=delay)
                if self._shutdown_event.is_set():
                    break
            except asyncio.TimeoutError:
                pass
            
            # Check if we're already connected (might have happened during the delay)
            if self._connection_state == ConnectionState.CONNECTED:
                break
            
            # Attempt reconnection
            try:
                # The actual reconnection logic should be implemented by the bot
                # This is just a placeholder for the reconnection attempt
                # The bot should call on_connect() when reconnection succeeds
                
                # If we get here, the reconnection attempt failed
                self._connection_stats["failed_reconnects"] += 1
                
                # Notify reconnect failed handlers
                for handler in self._on_reconnect_failed_handlers:
                    try:
                        handler()
                    except Exception as e:
                        self.logger.error(f"Error in reconnect failed handler: {str(e)}", exc_info=True)
                
            except Exception as e:
                self.logger.error(
                    f"Error during reconnection attempt: {str(e)}",
                    attempt=self._reconnect_attempts,
                    exc_info=True
                )


class StateConsistencyManager:
    """
    Manages state consistency during connection interruptions.
    
    This class provides mechanisms to maintain state consistency when
    Discord connections are interrupted, ensuring that the bot's state
    is properly synchronized when reconnection occurs.
    
    Attributes:
        logger: Logger instance
    """
    
    def __init__(self, logger: Optional[StructuredLogger] = None):
        """
        Initialize a new state consistency manager.
        
        Args:
            logger: Logger instance (creates one if None)
        """
        self.logger = logger or StructuredLogger("state_consistency")
        
        # Internal state
        self._state_snapshots: Dict[str, Any] = {}
        self._pending_operations: List[Tuple[str, Callable[[], Any]]] = []
        self._lock = asyncio.Lock()
    
    async def save_state_snapshot(self, key: str, state: Any) -> None:
        """
        Save a snapshot of state that needs to be preserved.
        
        Args:
            key: Identifier for the state
            state: State data to preserve
        """
        async with self._lock:
            self._state_snapshots[key] = state
            
            self.logger.debug(
                f"Saved state snapshot for '{key}'",
                key=key,
                state_type=type(state).__name__
            )
    
    async def get_state_snapshot(self, key: str) -> Optional[Any]:
        """
        Get a saved state snapshot.
        
        Args:
            key: Identifier for the state
            
        Returns:
            Optional[Any]: The saved state, or None if not found
        """
        async with self._lock:
            return self._state_snapshots.get(key)
    
    async def register_pending_operation(self, key: str, operation: Callable[[], Any]) -> None:
        """
        Register an operation to be executed after reconnection.
        
        Args:
            key: Identifier for the operation
            operation: Function to execute after reconnection
        """
        async with self._lock:
            self._pending_operations.append((key, operation))
            
            self.logger.debug(
                f"Registered pending operation '{key}'",
                key=key,
                pending_count=len(self._pending_operations)
            )
    
    async def execute_pending_operations(self) -> None:
        """
        Execute all pending operations after reconnection.
        
        This should be called after a successful reconnection to
        restore state consistency.
        """
        async with self._lock:
            if not self._pending_operations:
                return
                
            self.logger.info(
                f"Executing {len(self._pending_operations)} pending operations",
                pending_count=len(self._pending_operations)
            )
            
            operations = self._pending_operations.copy()
            self._pending_operations = []
            
            for key, operation in operations:
                try:
                    operation()
                    self.logger.debug(f"Executed pending operation '{key}'")
                except Exception as e:
                    self.logger.error(
                        f"Error executing pending operation '{key}': {str(e)}",
                        key=key,
                        exc_info=True
                    )
    
    async def clear_state(self) -> None:
        """Clear all saved state and pending operations."""
        async with self._lock:
            self._state_snapshots = {}
            self._pending_operations = []
            
            self.logger.info("Cleared all state snapshots and pending operations")


class FallbackManager:
    """
    Manages fallback mechanisms for critical operations.
    
    This class provides a way to register fallback methods for critical
    operations, allowing the bot to continue functioning when primary
    methods fail.
    
    Attributes:
        logger: Logger instance
    """
    
    def __init__(self, logger: Optional[StructuredLogger] = None):
        """
        Initialize a new fallback manager.
        
        Args:
            logger: Logger instance (creates one if None)
        """
        self.logger = logger or StructuredLogger("fallback_manager")
        
        # Internal state
        self._fallbacks: Dict[str, List[Callable[..., Any]]] = {}
        self._fallback_stats: Dict[str, Dict[str, int]] = {}
        self._lock = asyncio.Lock()
    
    async def register_fallback(self, operation_key: str, fallback_method: Callable[..., Any]) -> None:
        """
        Register a fallback method for an operation.
        
        Args:
            operation_key: Identifier for the operation
            fallback_method: Fallback method to use when primary fails
        """
        async with self._lock:
            if operation_key not in self._fallbacks:
                self._fallbacks[operation_key] = []
                self._fallback_stats[operation_key] = {
                    "primary_failures": 0,
                    "fallback_successes": 0,
                    "fallback_failures": 0
                }
                
            self._fallbacks[operation_key].append(fallback_method)
            
            self.logger.debug(
                f"Registered fallback for operation '{operation_key}'",
                operation=operation_key,
                fallback_count=len(self._fallbacks[operation_key])
            )
    
    async def execute_with_fallbacks(
        self,
        operation_key: str,
        primary_method: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """
        Execute an operation with fallbacks if the primary method fails.
        
        Args:
            operation_key: Identifier for the operation
            primary_method: Primary method to execute
            *args: Arguments for the methods
            **kwargs: Keyword arguments for the methods
            
        Returns:
            Any: Result of the successful method
            
        Raises:
            Exception: If all methods (primary and fallbacks) fail
        """
        # Try primary method first
        try:
            result = await primary_method(*args, **kwargs)
            return result
        except Exception as primary_error:
            # Primary method failed
            async with self._lock:
                if operation_key in self._fallback_stats:
                    self._fallback_stats[operation_key]["primary_failures"] += 1
            
            self.logger.warning(
                f"Primary method for '{operation_key}' failed, trying fallbacks",
                operation=operation_key,
                error=str(primary_error),
                exc_info=True
            )
            
            # Try fallbacks in order
            last_error = primary_error
            async with self._lock:
                fallbacks = self._fallbacks.get(operation_key, []).copy()
            
            for i, fallback in enumerate(fallbacks):
                try:
                    self.logger.debug(
                        f"Trying fallback {i+1}/{len(fallbacks)} for '{operation_key}'",
                        operation=operation_key,
                        fallback_index=i
                    )
                    
                    result = await fallback(*args, **kwargs)
                    
                    # Fallback succeeded
                    async with self._lock:
                        if operation_key in self._fallback_stats:
                            self._fallback_stats[operation_key]["fallback_successes"] += 1
                    
                    self.logger.info(
                        f"Fallback {i+1} for '{operation_key}' succeeded",
                        operation=operation_key,
                        fallback_index=i
                    )
                    
                    return result
                except Exception as fallback_error:
                    # Fallback failed
                    last_error = fallback_error
                    
                    async with self._lock:
                        if operation_key in self._fallback_stats:
                            self._fallback_stats[operation_key]["fallback_failures"] += 1
                    
                    self.logger.warning(
                        f"Fallback {i+1} for '{operation_key}' failed",
                        operation=operation_key,
                        fallback_index=i,
                        error=str(fallback_error),
                        exc_info=True
                    )
            
            # All methods failed
            self.logger.error(
                f"All methods for '{operation_key}' failed",
                operation=operation_key,
                primary_error=str(primary_error),
                fallback_count=len(fallbacks)
            )
            
            # Re-raise the last error
            raise last_error
    
    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """Get statistics for fallback operations."""
        return dict(self._fallback_stats)


# Decorator for applying fallback mechanism
def with_fallbacks(
    operation_key: str,
    fallback_manager: FallbackManager
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for applying fallback mechanism to a method.
    
    Args:
        operation_key: Identifier for the operation
        fallback_manager: FallbackManager instance
        
    Returns:
        Callable: Decorated function with fallback mechanism
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await fallback_manager.execute_with_fallbacks(
                operation_key,
                func,
                *args,
                **kwargs
            )
        return wrapper
    return decorator