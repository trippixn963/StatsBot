"""
Async utilities for efficient asynchronous operations.

This module provides helpers for working with asyncio, including synchronization
primitives, task management, event queuing, and other async operation utilities.
"""

# Import task_manager and semaphore_manager directly
from .task_manager import TaskManager
from .semaphore_manager import SemaphoreManager

# Import async_helpers directly
from .async_helpers import (
    gather_with_concurrency,
    run_with_timeout,
    periodic_task,
    debounce,
    throttle
)

# Use lazy imports for event_queue to avoid circular imports
def _import_event_queue():
    from .event_queue import EventQueue, EventBatcher
    return EventQueue, EventBatcher

# Define properties for lazy imports
class _LazyModule:
    @property
    def EventQueue(self):
        return _import_event_queue()[0]
    
    @property
    def EventBatcher(self):
        return _import_event_queue()[1]

# Create lazy module instance
_lazy = _LazyModule()

# Export symbols
EventQueue = _lazy.EventQueue
EventBatcher = _lazy.EventBatcher

__all__ = [
    'TaskManager',
    'SemaphoreManager',
    'EventQueue',
    'EventBatcher',
    'gather_with_concurrency',
    'run_with_timeout',
    'periodic_task',
    'debounce',
    'throttle'
]