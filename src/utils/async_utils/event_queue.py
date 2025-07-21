"""
Event queuing and batching for high-frequency events.

This module provides utilities for efficiently handling high-frequency events
through intelligent queuing and batching strategies. It helps prevent overwhelming
downstream systems while ensuring timely processing of events.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Callable, Awaitable, TypeVar, Generic, Optional, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

# Define a local AsyncOperationError to avoid circular imports
class AsyncOperationError(Exception):
    """
    Raised when asynchronous operations fail.
    
    This is a local version of the exception to avoid circular imports.
    """
    
    def __init__(
        self, 
        message: str, 
        operation_name: Optional[str] = None,
        task_id: Optional[str] = None,
        timeout: Optional[float] = None,
        was_cancelled: bool = False
    ):
        super().__init__(message)
        self.message = message
        self.operation_name = operation_name
        self.task_id = task_id
        self.timeout = timeout
        self.was_cancelled = was_cancelled
        self.error_code = "ASYNC_OPERATION_ERROR"
        self.context = {}
        if operation_name:
            self.context['operation_name'] = operation_name
        if task_id:
            self.context['task_id'] = task_id
        if timeout is not None:
            self.context['timeout'] = timeout
        self.context['was_cancelled'] = was_cancelled

# Import StructuredLogger
from ...utils.logging.structured_logger import StructuredLogger

T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')


class EventQueue(Generic[T]):
    """
    Queue for handling high-frequency events with batching capabilities.
    
    This class provides a way to efficiently process high-frequency events by:
    - Batching events together to reduce processing overhead
    - Implementing backpressure mechanisms to prevent overwhelming consumers
    - Providing configurable flush triggers (size, time)
    
    Attributes:
        name: Name of the event queue (for logging)
        batch_size: Maximum number of events to process in a batch
        max_queue_size: Maximum queue size before applying backpressure
        flush_interval: Time in seconds between automatic flushes
        processor: Async function to process batches of events
        logger: Logger instance
    """
    
    def __init__(
        self,
        name: str,
        processor: Callable[[List[T]], Awaitable[None]],
        batch_size: int = 50,
        max_queue_size: int = 1000,
        flush_interval: float = 1.0,
        logger: Optional[StructuredLogger] = None
    ):
        """
        Initialize a new event queue.
        
        Args:
            name: Name of the event queue (for logging)
            processor: Async function to process batches of events
            batch_size: Maximum number of events to process in a batch
            max_queue_size: Maximum queue size before applying backpressure
            flush_interval: Time in seconds between automatic flushes
            logger: Logger instance (creates one if None)
        """
        self.name = name
        self.processor = processor
        self.batch_size = batch_size
        self.max_queue_size = max_queue_size
        self.flush_interval = flush_interval
        self.logger = logger or StructuredLogger("event_queue")
        
        # Internal state
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=max_queue_size)
        self._processing_task: Optional[asyncio.Task] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()
        self._last_flush_time = 0
        self._stats = {
            "enqueued": 0,
            "processed": 0,
            "batches": 0,
            "backpressure_events": 0,
            "errors": 0
        }
    
    async def start(self) -> None:
        """Start the event queue processor."""
        async with self._lock:
            if self._running:
                return
                
            self._running = True
            self._last_flush_time = time.time()
            
            # Start processing task
            self._processing_task = asyncio.create_task(self._process_events())
            
            # Start periodic flush task
            self._flush_task = asyncio.create_task(self._periodic_flush())
            
            self.logger.info(
                f"Event queue '{self.name}' started",
                queue=self.name,
                batch_size=self.batch_size,
                flush_interval=self.flush_interval
            )
    
    async def stop(self) -> None:
        """Stop the event queue processor and process remaining events."""
        async with self._lock:
            if not self._running:
                return
                
            self._running = False
            
            # Cancel periodic flush task
            if self._flush_task:
                self._flush_task.cancel()
                try:
                    await self._flush_task
                except asyncio.CancelledError:
                    pass
                self._flush_task = None
            
            # Process remaining events
            await self._flush()
            
            # Cancel processing task
            if self._processing_task:
                self._processing_task.cancel()
                try:
                    await self._processing_task
                except asyncio.CancelledError:
                    pass
                self._processing_task = None
                
            self.logger.info(
                f"Event queue '{self.name}' stopped",
                queue=self.name,
                stats=self._stats
            )
    
    async def enqueue(self, event: T) -> None:
        """
        Add an event to the queue.
        
        If the queue is full, this will block until space is available,
        implementing backpressure to prevent memory issues.
        
        Args:
            event: Event to enqueue
        """
        if not self._running:
            await self.start()
            
        try:
            # Use put_nowait with exception handling for backpressure metrics
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                self._stats["backpressure_events"] += 1
                # Fall back to blocking put
                await self._queue.put(event)
                
            self._stats["enqueued"] += 1
            
            # Auto-flush if batch size reached
            if self._queue.qsize() >= self.batch_size:
                asyncio.create_task(self._flush())
                
        except Exception as e:
            self._stats["errors"] += 1
            self.logger.error(
                f"Error enqueueing event in '{self.name}'",
                error=str(e),
                queue=self.name,
                exc_info=True
            )
            raise AsyncOperationError(
                f"Failed to enqueue event: {str(e)}",
                operation_name=f"enqueue_{self.name}"
            )
    
    async def _process_events(self) -> None:
        """Process events from the queue continuously."""
        while self._running:
            try:
                # Wait for events or periodic flush
                await asyncio.sleep(0.01)  # Small sleep to prevent CPU spinning
                
                # Check if it's time to flush based on interval
                if time.time() - self._last_flush_time >= self.flush_interval:
                    await self._flush()
                    
            except asyncio.CancelledError:
                self.logger.debug(f"Event processor for '{self.name}' cancelled")
                break
            except Exception as e:
                self._stats["errors"] += 1
                self.logger.error(
                    f"Error in event processor for '{self.name}'",
                    error=str(e),
                    queue=self.name,
                    exc_info=True
                )
                # Sleep briefly to prevent tight error loops
                await asyncio.sleep(1)
    
    async def _periodic_flush(self) -> None:
        """Periodically flush the queue based on the flush interval."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._stats["errors"] += 1
                self.logger.error(
                    f"Error in periodic flush for '{self.name}'",
                    error=str(e),
                    queue=self.name,
                    exc_info=True
                )
    
    async def _flush(self) -> None:
        """Flush current events in the queue to the processor."""
        if self._queue.empty():
            return
            
        # Update last flush time
        self._last_flush_time = time.time()
        
        # Collect events up to batch size
        events = []
        try:
            # Get up to batch_size events without blocking
            for _ in range(min(self.batch_size, self._queue.qsize())):
                if not self._queue.empty():
                    events.append(self._queue.get_nowait())
                    
            if not events:
                return
                
            # Process the batch
            batch_size = len(events)
            self.logger.debug(
                f"Processing batch of {batch_size} events from '{self.name}'",
                queue=self.name,
                batch_size=batch_size
            )
            
            await self.processor(events)
            
            # Update stats
            self._stats["processed"] += batch_size
            self._stats["batches"] += 1
            
            # Mark tasks as done
            for _ in range(batch_size):
                self._queue.task_done()
                
        except Exception as e:
            self._stats["errors"] += 1
            self.logger.error(
                f"Error processing batch from '{self.name}'",
                error=str(e),
                queue=self.name,
                batch_size=len(events),
                exc_info=True
            )
            
            # Put events back in queue if processor failed
            # This is a best-effort approach and may not preserve order
            for event in events:
                try:
                    await self._queue.put(event)
                except:
                    pass
    
    def get_stats(self) -> Dict[str, int]:
        """Get current statistics for this event queue."""
        stats = dict(self._stats)
        stats["queue_size"] = self._queue.qsize()
        stats["running"] = self._running
        return stats


class EventBatcher(Generic[K, V]):
    """
    Groups related events together for efficient batch processing.
    
    This class provides a way to group events by a key and process them
    in batches, reducing the number of operations needed for high-frequency
    events that can be logically grouped.
    
    Attributes:
        name: Name of the event batcher (for logging)
        processor: Async function to process batches of events
        max_batch_size: Maximum number of events in a batch
        max_batch_age: Maximum age of a batch before processing (seconds)
        logger: Logger instance
    """
    
    @dataclass
    class Batch:
        """Represents a batch of events with the same key."""
        items: List[V] = field(default_factory=list)
        created_at: float = field(default_factory=time.time)
        last_updated: float = field(default_factory=time.time)
    
    def __init__(
        self,
        name: str,
        processor: Callable[[K, List[V]], Awaitable[None]],
        max_batch_size: int = 100,
        max_batch_age: float = 5.0,
        logger: Optional[StructuredLogger] = None
    ):
        """
        Initialize a new event batcher.
        
        Args:
            name: Name of the event batcher (for logging)
            processor: Async function to process batches of events
            max_batch_size: Maximum number of events in a batch
            max_batch_age: Maximum age of a batch before processing (seconds)
            logger: Logger instance (creates one if None)
        """
        self.name = name
        self.processor = processor
        self.max_batch_size = max_batch_size
        self.max_batch_age = max_batch_age
        self.logger = logger or StructuredLogger("event_batcher")
        
        # Internal state
        self._batches: Dict[K, EventBatcher.Batch] = {}
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        self._stats = {
            "added_events": 0,
            "processed_events": 0,
            "processed_batches": 0,
            "errors": 0
        }
    
    async def start(self) -> None:
        """Start the event batcher."""
        async with self._lock:
            if self._running:
                return
                
            self._running = True
            
            # Start periodic flush task
            self._flush_task = asyncio.create_task(self._periodic_flush())
            
            self.logger.info(
                f"Event batcher '{self.name}' started",
                batcher=self.name,
                max_batch_size=self.max_batch_size,
                max_batch_age=self.max_batch_age
            )
    
    async def stop(self) -> None:
        """Stop the event batcher and process remaining batches."""
        async with self._lock:
            if not self._running:
                return
                
            self._running = False
            
            # Cancel periodic flush task
            if self._flush_task:
                self._flush_task.cancel()
                try:
                    await self._flush_task
                except asyncio.CancelledError:
                    pass
                self._flush_task = None
            
            # Process remaining batches
            await self._flush_all()
            
            self.logger.info(
                f"Event batcher '{self.name}' stopped",
                batcher=self.name,
                stats=self._stats
            )
    
    async def add(self, key: K, value: V) -> None:
        """
        Add an event to a batch.
        
        Events with the same key are grouped together. If adding this event
        causes the batch to reach max_batch_size, the batch will be processed.
        
        Args:
            key: Key to group events by
            value: Event value to add
        """
        if not self._running:
            await self.start()
            
        try:
            async with self._lock:
                # Create batch if it doesn't exist
                if key not in self._batches:
                    self._batches[key] = self.Batch()
                
                # Add item to batch
                self._batches[key].items.append(value)
                self._batches[key].last_updated = time.time()
                self._stats["added_events"] += 1
                
                # Process batch if it's full
                if len(self._batches[key].items) >= self.max_batch_size:
                    await self._process_batch(key)
                    
        except Exception as e:
            self._stats["errors"] += 1
            self.logger.error(
                f"Error adding event to batcher '{self.name}'",
                error=str(e),
                batcher=self.name,
                key=str(key),
                exc_info=True
            )
    
    async def _periodic_flush(self) -> None:
        """Periodically check for and flush old batches."""
        check_interval = min(1.0, self.max_batch_age / 2)  # Check at least twice per max_batch_age
        
        while self._running:
            try:
                await asyncio.sleep(check_interval)
                await self._flush_old_batches()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._stats["errors"] += 1
                self.logger.error(
                    f"Error in periodic flush for batcher '{self.name}'",
                    error=str(e),
                    batcher=self.name,
                    exc_info=True
                )
    
    async def _flush_old_batches(self) -> None:
        """Flush batches that have exceeded max_batch_age."""
        now = time.time()
        keys_to_process = []
        
        async with self._lock:
            for key, batch in self._batches.items():
                if now - batch.last_updated >= self.max_batch_age and batch.items:
                    keys_to_process.append(key)
            
            for key in keys_to_process:
                await self._process_batch(key)
    
    async def _flush_all(self) -> None:
        """Flush all current batches."""
        async with self._lock:
            keys = list(self._batches.keys())
            for key in keys:
                if self._batches[key].items:
                    await self._process_batch(key)
    
    async def _process_batch(self, key: K) -> None:
        """
        Process a single batch by key.
        
        Args:
            key: Batch key to process
        """
        if key not in self._batches or not self._batches[key].items:
            return
            
        try:
            # Get batch items
            items = self._batches[key].items
            batch_size = len(items)
            
            if batch_size == 0:
                return
                
            self.logger.debug(
                f"Processing batch of {batch_size} events for key '{key}' from batcher '{self.name}'",
                batcher=self.name,
                key=str(key),
                batch_size=batch_size
            )
            
            # Process the batch
            await self.processor(key, items)
            
            # Update stats
            self._stats["processed_events"] += batch_size
            self._stats["processed_batches"] += 1
            
            # Clear the batch
            self._batches[key] = self.Batch()
            
        except Exception as e:
            self._stats["errors"] += 1
            self.logger.error(
                f"Error processing batch for key '{key}' from batcher '{self.name}'",
                error=str(e),
                batcher=self.name,
                key=str(key),
                exc_info=True
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics for this event batcher."""
        stats = dict(self._stats)
        stats["active_batches"] = len(self._batches)
        stats["pending_events"] = sum(len(batch.items) for batch in self._batches.values())
        stats["running"] = self._running
        return stats