"""
Circular buffer implementation for memory-constrained environments.

This module provides a fixed-size circular buffer implementation that
automatically evicts oldest entries when the buffer is full, making it
ideal for memory-constrained environments.
"""

from typing import TypeVar, Generic, List, Optional, Iterator, Any
from collections import deque
import threading

T = TypeVar('T')


class CircularBuffer(Generic[T]):
    """
    Fixed-size circular buffer that automatically evicts oldest entries.
    
    This data structure maintains a fixed maximum size and automatically
    removes the oldest items when new items are added beyond capacity.
    It's thread-safe and provides efficient operations for common use cases.
    
    Attributes:
        capacity (int): Maximum number of items the buffer can hold
        _buffer (deque): Internal storage for buffer items
        _lock (threading.RLock): Lock for thread safety
    """
    
    def __init__(self, capacity: int):
        """
        Initialize a new circular buffer with the specified capacity.
        
        Args:
            capacity: Maximum number of items the buffer can hold
            
        Raises:
            ValueError: If capacity is not a positive integer
        """
        if not isinstance(capacity, int) or capacity <= 0:
            raise ValueError("Capacity must be a positive integer")
            
        self.capacity = capacity
        self._buffer: deque = deque(maxlen=capacity)
        self._lock = threading.RLock()
        
    def append(self, item: T) -> None:
        """
        Add an item to the buffer, evicting oldest item if at capacity.
        
        Args:
            item: Item to add to the buffer
        """
        with self._lock:
            self._buffer.append(item)
            
    def extend(self, items: List[T]) -> None:
        """
        Add multiple items to the buffer.
        
        Args:
            items: List of items to add to the buffer
        """
        with self._lock:
            self._buffer.extend(items)
            
    def get(self, index: int) -> T:
        """
        Get item at the specified index.
        
        Args:
            index: Index of the item to retrieve (negative indices supported)
            
        Returns:
            Item at the specified index
            
        Raises:
            IndexError: If index is out of range
        """
        with self._lock:
            return self._buffer[index]
            
    def peek(self) -> Optional[T]:
        """
        Get the most recently added item without removing it.
        
        Returns:
            Most recent item, or None if buffer is empty
        """
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer[-1]
            
    def peek_oldest(self) -> Optional[T]:
        """
        Get the oldest item without removing it.
        
        Returns:
            Oldest item, or None if buffer is empty
        """
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer[0]
            
    def clear(self) -> None:
        """Clear all items from the buffer."""
        with self._lock:
            self._buffer.clear()
            
    def is_empty(self) -> bool:
        """
        Check if the buffer is empty.
        
        Returns:
            True if buffer is empty, False otherwise
        """
        with self._lock:
            return len(self._buffer) == 0
            
    def is_full(self) -> bool:
        """
        Check if the buffer is at capacity.
        
        Returns:
            True if buffer is full, False otherwise
        """
        with self._lock:
            return len(self._buffer) == self.capacity
            
    def __len__(self) -> int:
        """
        Get the current number of items in the buffer.
        
        Returns:
            Number of items in the buffer
        """
        with self._lock:
            return len(self._buffer)
            
    def __iter__(self) -> Iterator[T]:
        """
        Get an iterator over the buffer items.
        
        Returns:
            Iterator over buffer items from oldest to newest
        """
        # Create a copy to avoid concurrent modification issues
        with self._lock:
            items = list(self._buffer)
        return iter(items)
        
    def __contains__(self, item: Any) -> bool:
        """
        Check if an item is in the buffer.
        
        Args:
            item: Item to check for
            
        Returns:
            True if item is in buffer, False otherwise
        """
        with self._lock:
            return item in self._buffer
            
    def to_list(self) -> List[T]:
        """
        Convert buffer to a list.
        
        Returns:
            List containing all items in the buffer from oldest to newest
        """
        with self._lock:
            return list(self._buffer)
            
    def get_stats(self) -> dict:
        """
        Get statistics about the buffer.
        
        Returns:
            Dictionary with buffer statistics
        """
        with self._lock:
            return {
                'capacity': self.capacity,
                'size': len(self._buffer),
                'is_full': len(self._buffer) == self.capacity,
                'utilization': len(self._buffer) / self.capacity if self.capacity > 0 else 0
            }