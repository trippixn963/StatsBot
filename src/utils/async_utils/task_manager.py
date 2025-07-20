"""
Task lifecycle management with graceful cancellation and cleanup.

This module provides utilities for managing asyncio tasks, including creation,
tracking, and graceful cancellation during shutdown.
"""

import asyncio
import logging
import functools
import inspect
import uuid
from typing import Dict, Set, Optional, Callable, Coroutine, Any, TypeVar, Generic, List, Union

from ...utils.logging.structured_logger import StructuredLogger

T = TypeVar('T')

class TaskManager:
    """
    Manages the lifecycle of asyncio tasks.
    
    This class provides utilities for creating, tracking, and gracefully cancelling
    asyncio tasks. It ensures proper cleanup during shutdown and prevents task leaks.
    
    Features:
    - Task creation and tracking by name
    - Automatic exception handling and logging
    - Graceful cancellation during shutdown
    - Task status monitoring
    """
    
    def __init__(self, name: str = "default", logger: Optional[Union[logging.Logger, StructuredLogger]] = None):
        """
        Initialize a new TaskManager.
        
        Args:
            name: Name for this task manager instance (for logging)
            logger: Logger instance to use (creates one if None)
        """
        self._name = name
        self._tasks: Dict[str, asyncio.Task] = {}
        self._logger = logger or StructuredLogger("task_manager")
        self._shutting_down = False
    
    def create_task(self, coro: Coroutine, name: Optional[str] = None) -> asyncio.Task:
        """
        Create and track a new asyncio task.
        
        Args:
            coro: Coroutine to run as a task
            name: Name for the task (must be unique within this manager)
                  If None, a unique name will be generated
            
        Returns:
            The created asyncio Task
            
        Raises:
            ValueError: If a task with this name already exists
        """
        # Generate a unique name if none provided
        if name is None:
            name = f"task_{uuid.uuid4().hex[:8]}"
            
        if name in self._tasks and not self._tasks[name].done():
            raise ValueError(f"Task '{name}' already exists and is still running")
        
        task = asyncio.create_task(self._task_wrapper(coro, name))
        self._tasks[name] = task
        
        self._logger.debug(
            f"Created task '{name}' in manager '{self._name}'",
            task_name=name,
            manager=self._name
        )
        return task
    
    async def _task_wrapper(self, coro: Coroutine, name: str) -> Any:
        """
        Wrapper around tasks to handle exceptions and cleanup.
        
        Args:
            coro: The coroutine to execute
            name: Name of the task
            
        Returns:
            The result of the coroutine
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            result = await coro
            duration = asyncio.get_event_loop().time() - start_time
            
            self._logger.debug(
                f"Task '{name}' completed successfully in {duration:.2f}s",
                task_name=name,
                duration=duration,
                status="completed"
            )
            return result
            
        except asyncio.CancelledError:
            duration = asyncio.get_event_loop().time() - start_time
            self._logger.debug(
                f"Task '{name}' was cancelled after {duration:.2f}s",
                task_name=name,
                duration=duration,
                status="cancelled"
            )
            raise
            
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            self._logger.error(
                f"Task '{name}' failed with exception: {e}",
                task_name=name,
                duration=duration,
                error=str(e),
                error_type=type(e).__name__,
                status="failed",
                exc_info=True
            )
            raise
            
        finally:
            # Clean up the reference if it's still there
            if name in self._tasks and self._tasks[name].done():
                del self._tasks[name]
    
    def get_task(self, name: str) -> Optional[asyncio.Task]:
        """
        Get a tracked task by name.
        
        Args:
            name: Name of the task to retrieve
            
        Returns:
            The task if found and still running, None otherwise
        """
        task = self._tasks.get(name)
        if task and task.done():
            del self._tasks[name]
            return None
        return task
    
    def cancel_task(self, name: str) -> bool:
        """
        Cancel a specific task by name.
        
        Args:
            name: Name of the task to cancel
            
        Returns:
            True if the task was found and cancelled, False otherwise
        """
        task = self.get_task(name)
        if task:
            task.cancel()
            self._logger.debug(f"Cancelled task '{name}'")
            return True
        return False
    
    async def wait_for_task(self, name: str, timeout: Optional[float] = None) -> Any:
        """
        Wait for a specific task to complete.
        
        Args:
            name: Name of the task to wait for
            timeout: Maximum time to wait in seconds, or None for no timeout
            
        Returns:
            The result of the task
            
        Raises:
            asyncio.TimeoutError: If the timeout is reached
            KeyError: If the task doesn't exist
        """
        task = self.get_task(name)
        if not task:
            raise KeyError(f"Task '{name}' not found or already completed")
        
        if timeout is not None:
            return await asyncio.wait_for(task, timeout)
        return await task
    
    def get_running_tasks(self) -> Dict[str, asyncio.Task]:
        """
        Get all currently running tasks.
        
        Returns:
            Dictionary of task names to task objects
        """
        # Clean up any completed tasks
        for name in list(self._tasks.keys()):
            if self._tasks[name].done():
                del self._tasks[name]
        
        return self._tasks.copy()
    
    async def cancel_all_tasks(self, timeout: float = 5.0) -> None:
        """
        Cancel all tracked tasks and wait for them to complete.
        
        Args:
            timeout: Maximum time to wait for tasks to cancel
        """
        if not self._tasks:
            return
        
        self._shutting_down = True
        self._logger.info(
            f"Cancelling {len(self._tasks)} tasks in manager '{self._name}'",
            task_count=len(self._tasks),
            manager=self._name
        )
        
        # Cancel all tasks
        pending = []
        for name, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
                pending.append(task)
        
        if not pending:
            return
        
        # Wait for all tasks to complete or timeout
        try:
            await asyncio.wait(pending, timeout=timeout)
        except asyncio.TimeoutError:
            still_pending = [name for name, task in self._tasks.items() if not task.done()]
            self._logger.warning(
                f"Timeout waiting for {len(still_pending)} tasks to cancel: {still_pending}",
                pending_tasks=still_pending,
                timeout=timeout,
                manager=self._name
            )
        
        # Clear the task dictionary
        self._tasks.clear()
        self._logger.info(
            f"All tasks in manager '{self._name}' have been cancelled",
            manager=self._name
        )
    
    # Alias for backward compatibility
    cancel_all = cancel_all_tasks
    
    def is_shutting_down(self) -> bool:
        """
        Check if the task manager is in the process of shutting down.
        
        Returns:
            True if cancel_all has been called, False otherwise
        """
        return self._shutting_down


    def register_task(self, task: asyncio.Task, name: str) -> None:
        """
        Register an existing task with this manager.
        
        Args:
            task: The task to register
            name: Name for the task (must be unique within this manager)
            
        Raises:
            ValueError: If a task with this name already exists
        """
        if name in self._tasks and not self._tasks[name].done():
            raise ValueError(f"Task '{name}' already exists and is still running")
            
        self._tasks[name] = task
        self._logger.debug(
            f"Registered existing task as '{name}' in manager '{self._name}'",
            task_name=name,
            manager=self._name
        )
    
    def get_task_count(self) -> int:
        """
        Get the number of active tasks.
        
        Returns:
            Number of active tasks
        """
        # Clean up any completed tasks
        for name in list(self._tasks.keys()):
            if self._tasks[name].done():
                del self._tasks[name]
                
        return len(self._tasks)
    
    def get_task_names(self) -> List[str]:
        """
        Get the names of all active tasks.
        
        Returns:
            List of task names
        """
        # Clean up any completed tasks
        for name in list(self._tasks.keys()):
            if self._tasks[name].done():
                del self._tasks[name]
                
        return list(self._tasks.keys())


# Global task manager for convenience
global_task_manager = TaskManager("global")