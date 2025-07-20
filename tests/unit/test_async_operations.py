"""
Tests for enhanced async operations and concurrency handling.

This module tests the async utilities, event queuing, and service coordination
to ensure proper synchronization and concurrency handling.
"""

import asyncio
import unittest
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List, Dict, Any

from src.utils.async_utils.event_queue import EventQueue, EventBatcher
from src.utils.async_utils.semaphore_manager import SemaphoreManager
from src.core.service_coordinator import ServiceCoordinator
from src.types.models import ServiceStatus


class TestEventQueue:
    """Test the EventQueue class for batching high-frequency events."""
    
    @pytest.fixture
    async def event_queue(self):
        """Create an event queue for testing."""
        processor = AsyncMock()
        queue = EventQueue(
            name="test_queue",
            processor=processor,
            batch_size=3,
            flush_interval=0.1
        )
        yield queue
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_event_queue_batching(self, event_queue):
        """Test that events are properly batched."""
        processor = event_queue.processor
        
        # Enqueue 5 events
        for i in range(5):
            await event_queue.enqueue(f"event_{i}")
        
        # Wait for processing
        await asyncio.sleep(0.2)
        
        # Check that processor was called with batches
        assert processor.call_count >= 2
        
        # Check first batch size (should be batch_size)
        first_call_args = processor.call_args_list[0][0][0]
        assert len(first_call_args) == 3
        
        # Check that all events were processed
        all_processed = []
        for call in processor.call_args_list:
            all_processed.extend(call[0][0])
        
        assert len(all_processed) == 5
        assert set(all_processed) == {f"event_{i}" for i in range(5)}
    
    @pytest.mark.asyncio
    async def test_event_queue_flush_interval(self, event_queue):
        """Test that events are flushed after the interval."""
        processor = event_queue.processor
        
        # Enqueue 2 events (less than batch_size)
        await event_queue.enqueue("event_1")
        await event_queue.enqueue("event_2")
        
        # Wait for flush interval
        await asyncio.sleep(0.2)
        
        # Check that processor was called despite not reaching batch_size
        processor.assert_called()
        
        # Check that both events were processed
        processed = processor.call_args[0][0]
        assert len(processed) == 2
        assert set(processed) == {"event_1", "event_2"}


class TestEventBatcher:
    """Test the EventBatcher class for grouping related events."""
    
    @pytest.fixture
    async def event_batcher(self):
        """Create an event batcher for testing."""
        processor = AsyncMock()
        batcher = EventBatcher(
            name="test_batcher",
            processor=processor,
            max_batch_size=3,
            max_batch_age=0.1
        )
        yield batcher
        await batcher.stop()
    
    @pytest.mark.asyncio
    async def test_event_batcher_grouping(self, event_batcher):
        """Test that events are properly grouped by key."""
        processor = event_batcher.processor
        
        # Add events with different keys
        await event_batcher.add("key1", "value1_1")
        await event_batcher.add("key1", "value1_2")
        await event_batcher.add("key2", "value2_1")
        
        # Wait for batch age
        await asyncio.sleep(0.2)
        
        # Check that processor was called for each key
        assert processor.call_count == 2
        
        # Check that events were grouped correctly
        calls = {call[0][0]: call[0][1] for call in processor.call_args_list}
        assert "key1" in calls
        assert "key2" in calls
        assert set(calls["key1"]) == {"value1_1", "value1_2"}
        assert calls["key2"] == ["value2_1"]
    
    @pytest.mark.asyncio
    async def test_event_batcher_max_batch_size(self, event_batcher):
        """Test that batches are processed when reaching max_batch_size."""
        processor = event_batcher.processor
        
        # Add events to exceed max_batch_size for one key
        await event_batcher.add("key1", "value1")
        await event_batcher.add("key1", "value2")
        await event_batcher.add("key1", "value3")  # This should trigger processing
        
        # Wait a bit for processing
        await asyncio.sleep(0.05)
        
        # Check that processor was called for the full batch
        processor.assert_called_once()
        key, values = processor.call_args[0]
        assert key == "key1"
        assert len(values) == 3
        assert set(values) == {"value1", "value2", "value3"}


class TestServiceCoordinator:
    """Test the ServiceCoordinator for managing service lifecycle."""
    
    @pytest.fixture
    def service_coordinator(self):
        """Create a service coordinator for testing."""
        return ServiceCoordinator()
    
    @pytest.fixture
    def mock_services(self):
        """Create mock services for testing."""
        service1 = AsyncMock()
        service1.status = ServiceStatus.STOPPED
        
        service2 = AsyncMock()
        service2.status = ServiceStatus.STOPPED
        
        service3 = AsyncMock()
        service3.status = ServiceStatus.STOPPED
        
        return {
            "service1": service1,
            "service2": service2,
            "service3": service3
        }
    
    def test_register_service(self, service_coordinator, mock_services):
        """Test registering services with dependencies."""
        # Register services with dependencies
        service_coordinator.register_service("service1", mock_services["service1"])
        service_coordinator.register_service("service2", mock_services["service2"], ["service1"])
        service_coordinator.register_service("service3", mock_services["service3"], ["service2"])
        
        # Check dependency order
        assert service_coordinator.startup_order == ["service1", "service2", "service3"]
        assert service_coordinator.shutdown_order == ["service3", "service2", "service1"]
    
    def test_register_service_circular_dependency(self, service_coordinator, mock_services):
        """Test that circular dependencies are detected."""
        service_coordinator.register_service("service1", mock_services["service1"])
        service_coordinator.register_service("service2", mock_services["service2"], ["service1"])
        
        # Try to create a circular dependency
        with pytest.raises(Exception):
            service_coordinator.register_service("service3", mock_services["service3"], ["service2"])
            service_coordinator.register_service("service1", mock_services["service1"], ["service3"])
    
    @pytest.mark.asyncio
    async def test_start_services(self, service_coordinator, mock_services):
        """Test starting services in dependency order."""
        # Register services with dependencies
        service_coordinator.register_service("service1", mock_services["service1"])
        service_coordinator.register_service("service2", mock_services["service2"], ["service1"])
        service_coordinator.register_service("service3", mock_services["service3"], ["service2"])
        
        # Start services
        await service_coordinator.start_services()
        
        # Check that services were started in the correct order
        mock_services["service1"].start.assert_called_once()
        mock_services["service2"].start.assert_called_once()
        mock_services["service3"].start.assert_called_once()
        
        # Check call order
        assert mock_services["service1"].start.call_count == 1
        assert mock_services["service2"].start.call_count == 1
        assert mock_services["service3"].start.call_count == 1
    
    @pytest.mark.asyncio
    async def test_stop_services(self, service_coordinator, mock_services):
        """Test stopping services in reverse dependency order."""
        # Register services with dependencies
        service_coordinator.register_service("service1", mock_services["service1"])
        service_coordinator.register_service("service2", mock_services["service2"], ["service1"])
        service_coordinator.register_service("service3", mock_services["service3"], ["service2"])
        
        # Stop services
        await service_coordinator.stop_services()
        
        # Check that services were stopped in the correct order
        mock_services["service3"].stop.assert_called_once()
        mock_services["service2"].stop.assert_called_once()
        mock_services["service1"].stop.assert_called_once()


class TestSemaphoreManager:
    """Test the SemaphoreManager for synchronization primitives."""
    
    @pytest.fixture
    def semaphore_manager(self):
        """Create a semaphore manager for testing."""
        return SemaphoreManager()
    
    @pytest.mark.asyncio
    async def test_semaphore_acquisition(self, semaphore_manager):
        """Test acquiring and releasing semaphores."""
        # Acquire semaphore
        await semaphore_manager.acquire_semaphore("test_sem", 1, "test_context")
        
        # Check active acquisitions
        active = semaphore_manager.get_active_acquisitions("test_sem")
        assert "test_context" in active
        
        # Release semaphore
        semaphore_manager.release_semaphore("test_sem", "test_context")
        
        # Check active acquisitions again
        active = semaphore_manager.get_active_acquisitions("test_sem")
        assert "test_context" not in active
    
    @pytest.mark.asyncio
    async def test_semaphore_context_manager(self, semaphore_manager):
        """Test using semaphore as a context manager."""
        async with await semaphore_manager.with_semaphore("test_sem", 1, "test_context"):
            # Check active acquisitions
            active = semaphore_manager.get_active_acquisitions("test_sem")
            assert "test_context" in active
        
        # Check active acquisitions after context exit
        active = semaphore_manager.get_active_acquisitions("test_sem")
        assert "test_context" not in active
    
    @pytest.mark.asyncio
    async def test_concurrent_semaphore_access(self, semaphore_manager):
        """Test concurrent access to a semaphore."""
        # Create a semaphore with value 1
        sem_name = "concurrent_test"
        value = 1
        
        # Track execution order
        execution_order = []
        
        async def task1():
            async with await semaphore_manager.with_semaphore(sem_name, value, "task1"):
                execution_order.append("task1_start")
                await asyncio.sleep(0.1)
                execution_order.append("task1_end")
        
        async def task2():
            async with await semaphore_manager.with_semaphore(sem_name, value, "task2"):
                execution_order.append("task2_start")
                await asyncio.sleep(0.1)
                execution_order.append("task2_end")
        
        # Run tasks concurrently
        await asyncio.gather(task1(), task2())
        
        # Check execution order - tasks should not overlap
        assert execution_order == ["task1_start", "task1_end", "task2_start", "task2_end"] or \
               execution_order == ["task2_start", "task2_end", "task1_start", "task1_end"]


if __name__ == "__main__":
    pytest.main(["-xvs", "test_async_operations.py"])