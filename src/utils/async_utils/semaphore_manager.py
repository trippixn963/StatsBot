"""
Synchronization primitives for async operations.

This module provides utilities for managing semaphores and locks to prevent
race conditions and ensure proper synchronization in async code.
"""

import asyncio
import logging
from typing import Dict, Optional, Any, Set

class SemaphoreManager:
    """
    Manages named semaphores and locks for synchronization across the application.
    
    This class provides a centralized way to create and access semaphores and locks
    by name, ensuring that the same synchronization primitive is used consistently
    across different parts of the application.
    """
    
    def __init__(self):
        """Initialize the semaphore manager."""
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._events: Dict[str, asyncio.Event] = {}
        self._logger = logging.getLogger(__name__)
        self._active_acquisitions: Dict[str, Set[str]] = {}
    
    def get_semaphore(self, name: str, value: int = 1) -> asyncio.Semaphore:
        """
        Get or create a named semaphore.
        
        Args:
            name: Name of the semaphore
            value: Maximum number of concurrent acquisitions
            
        Returns:
            The semaphore instance
        """
        if name not in self._semaphores:
            self._semaphores[name] = asyncio.Semaphore(value)
            self._active_acquisitions[name] = set()
        return self._semaphores[name]
    
    def get_lock(self, name: str) -> asyncio.Lock:
        """
        Get or create a named lock.
        
        Args:
            name: Name of the lock
            
        Returns:
            The lock instance
        """
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]
    
    def get_event(self, name: str, initial_state: bool = False) -> asyncio.Event:
        """
        Get or create a named event.
        
        Args:
            name: Name of the event
            initial_state: Initial state of the event (set or not)
            
        Returns:
            The event instance
        """
        if name not in self._events:
            self._events[name] = asyncio.Event()
            if initial_state:
                self._events[name].set()
        return self._events[name]
    
    async def acquire_semaphore(self, name: str, value: int = 1, context: str = "") -> bool:
        """
        Acquire a named semaphore with tracking.
        
        Args:
            name: Name of the semaphore
            value: Maximum number of concurrent acquisitions
            context: Optional context string for tracking acquisitions
            
        Returns:
            True if the semaphore was acquired
        """
        semaphore = self.get_semaphore(name, value)
        await semaphore.acquire()
        
        if context:
            self._active_acquisitions[name].add(context)
            self._logger.debug(f"Semaphore '{name}' acquired by '{context}'")
        
        return True
    
    def release_semaphore(self, name: str, context: str = "") -> None:
        """
        Release a named semaphore.
        
        Args:
            name: Name of the semaphore
            context: Optional context string for tracking acquisitions
            
        Raises:
            ValueError: If the semaphore doesn't exist
        """
        if name not in self._semaphores:
            raise ValueError(f"Semaphore '{name}' does not exist")
        
        if context and context in self._active_acquisitions[name]:
            self._active_acquisitions[name].remove(context)
            self._logger.debug(f"Semaphore '{name}' released by '{context}'")
        
        self._semaphores[name].release()
    
    async def with_semaphore(self, name: str, value: int = 1, context: str = ""):
        """
        Context manager for using a semaphore in an async with statement.
        
        Args:
            name: Name of the semaphore
            value: Maximum number of concurrent acquisitions
            context: Optional context string for tracking acquisitions
            
        Returns:
            An async context manager for the semaphore
        """
        semaphore = self.get_semaphore(name, value)
        
        class SemaphoreContext:
            async def __aenter__(self_ctx):
                await semaphore.acquire()
                if context:
                    self._active_acquisitions[name].add(context)
                    self._logger.debug(f"Semaphore '{name}' acquired by '{context}'")
                return semaphore
                
            async def __aexit__(self_ctx, exc_type, exc_val, exc_tb):
                if context and context in self._active_acquisitions[name]:
                    self._active_acquisitions[name].remove(context)
                    self._logger.debug(f"Semaphore '{name}' released by '{context}'")
                semaphore.release()
                return False  # Don't suppress exceptions
        
        return SemaphoreContext()
    
    async def with_lock(self, name: str):
        """
        Context manager for using a lock in an async with statement.
        
        Args:
            name: Name of the lock
            
        Returns:
            An async context manager for the lock
        """
        lock = self.get_lock(name)
        return lock
    
    def get_active_acquisitions(self, name: str) -> Set[str]:
        """
        Get the set of active acquisitions for a semaphore.
        
        Args:
            name: Name of the semaphore
            
        Returns:
            Set of context strings for active acquisitions
            
        Raises:
            ValueError: If the semaphore doesn't exist
        """
        if name not in self._active_acquisitions:
            raise ValueError(f"Semaphore '{name}' does not exist")
        
        return self._active_acquisitions[name].copy()


# Global semaphore manager for convenience
global_semaphore_manager = SemaphoreManager()