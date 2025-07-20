"""
Tests for core infrastructure components including resource management and async utilities.
"""

import asyncio
import unittest
import time
from unittest.mock import patch, MagicMock

from src.utils.resource_manager import ResourceManager, MemoryStats
from src.utils.async_utils.task_manager import TaskManager
from src.utils.async_utils.semaphore_manager import SemaphoreManager
from src.utils.async_utils.async_helpers import (
    gather_with_concurrency,
    run_with_timeout,
    debounce,
    throttle
)


class TestResourceManager(unittest.TestCase):
    """Tests for the ResourceManager class."""
    
    def test_create_circular_buffer(self):
        """Test creating and registering a circular buffer."""
        manager = ResourceManager()
        buffer = manager.create_circular_buffer(10)
        
        self.assertEqual(buffer.capacity, 10)
        self.assertEqual(len(manager._registered_buffers), 1)
    
    @patch('psutil.virtual_memory')
    @patch('psutil.Process')
    def test_get_memory_stats(self, mock_process, mock_vm):
        """Test getting memory statistics."""
        # Setup mocks
        mock_vm_obj = MagicMock()
        mock_vm_obj.total = 16000000000  # 16GB
        mock_vm_obj.available = 8000000000  # 8GB
        mock_vm_obj.used = 8000000000  # 8GB
        mock_vm_obj.percent = 50.0
        mock_vm.return_value = mock_vm_obj
        
        mock_process_obj = MagicMock()
        mock_process_info = MagicMock()
        mock_process_info.rss = 500000000  # 500MB
        mock_process_obj.memory_info.return_value = mock_process_info
        mock_process.return_value = mock_process_obj
        
        # Test
        manager = ResourceManager()
        stats = manager.get_memory_stats()
        
        # Verify
        self.assertEqual(stats.total_memory, 16000000000)
        self.assertEqual(stats.available_memory, 8000000000)
        self.assertEqual(stats.used_memory, 8000000000)
        self.assertEqual(stats.memory_percent, 50.0)
        self.assertEqual(stats.process_memory, 500000000)
        self.assertAlmostEqual(stats.process_percent, 3.125)
    
    @patch('src.utils.resource_manager.ResourceManager.get_memory_stats')
    def test_cleanup_resources(self, mock_get_stats):
        """Test resource cleanup."""
        # Setup
        manager = ResourceManager()
        mock_callback = MagicMock()
        manager.register_cleanup_callback(mock_callback)
        
        # Mock memory stats
        mock_stats1 = MemoryStats(
            total_memory=16000000000,
            available_memory=2000000000,
            used_memory=14000000000,
            memory_percent=95.0,  # Critical threshold
            process_memory=1000000000,
            process_percent=6.25
        )
        mock_stats2 = MemoryStats(
            total_memory=16000000000,
            available_memory=4000000000,
            used_memory=12000000000,
            memory_percent=75.0,  # Below critical after cleanup
            process_memory=800000000,
            process_percent=5.0
        )
        mock_get_stats.side_effect = [mock_stats1, mock_stats2]
        
        # Create a buffer and add some items
        buffer = manager.create_circular_buffer(5)
        for i in range(5):
            buffer.append(f"item{i}")
        
        # Test
        loop = asyncio.get_event_loop()
        loop.run_until_complete(manager.cleanup_resources())
        
        # Verify
        mock_callback.assert_called_once()
        self.assertEqual(len(buffer), 0)  # Buffer should be cleared due to high memory


class TestTaskManager(unittest.TestCase):
    """Tests for the TaskManager class."""
    
    def test_create_task(self):
        """Test creating and tracking a task."""
        manager = TaskManager("test")
        
        async def dummy_task():
            return "done"
        
        async def test_create():
            task = manager.create_task(dummy_task(), "test_task")
            return task
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(test_create())
        
        self.assertEqual(len(manager._tasks), 1)
        self.assertIn("test_task", manager._tasks)
    
    def test_cancel_task(self):
        """Test cancelling a task."""
        manager = TaskManager("test")
        
        async def long_task():
            await asyncio.sleep(0.1)
            return "done"
        
        async def test_cancel():
            manager.create_task(long_task(), "long_task")
            
            # Cancel the task
            result = manager.cancel_task("long_task")
            self.assertTrue(result)
            
            # Try to cancel non-existent task
            result = manager.cancel_task("nonexistent")
            self.assertFalse(result)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(test_cancel())
    
    def test_cancel_all(self):
        """Test cancelling all tasks."""
        manager = TaskManager("test")
        
        async def task1():
            await asyncio.sleep(0.1)
            return "task1 done"
        
        async def task2():
            await asyncio.sleep(0.1)
            return "task2 done"
        
        async def test_cancel_all():
            manager.create_task(task1(), "task1")
            manager.create_task(task2(), "task2")
            
            # Cancel all tasks
            await manager.cancel_all()
            
            # Verify all tasks are cancelled
            self.assertEqual(len(manager._tasks), 0)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(test_cancel_all())


class TestSemaphoreManager(unittest.TestCase):
    """Tests for the SemaphoreManager class."""
    
    def test_get_semaphore(self):
        """Test getting a named semaphore."""
        manager = SemaphoreManager()
        sem1 = manager.get_semaphore("test", 2)
        sem2 = manager.get_semaphore("test", 3)  # Should return the existing one
        
        self.assertIs(sem1, sem2)
        self.assertEqual(sem1._value, 2)  # Should use the first value
    
    def test_get_lock(self):
        """Test getting a named lock."""
        manager = SemaphoreManager()
        lock1 = manager.get_lock("test_lock")
        lock2 = manager.get_lock("test_lock")
        
        self.assertIs(lock1, lock2)
    
    def test_acquire_release_semaphore(self):
        """Test acquiring and releasing a semaphore with tracking."""
        manager = SemaphoreManager()
        
        async def test_acquire_release():
            await manager.acquire_semaphore("test_sem", 1, "test_context")
            acquisitions = manager.get_active_acquisitions("test_sem")
            self.assertIn("test_context", acquisitions)
            
            manager.release_semaphore("test_sem", "test_context")
            acquisitions = manager.get_active_acquisitions("test_sem")
            self.assertNotIn("test_context", acquisitions)
        
        loop = asyncio.get_event_loop()
        loop.run_until_complete(test_acquire_release())


class TestAsyncHelpers(unittest.TestCase):
    """Tests for async helper functions."""
    
    def test_gather_with_concurrency(self):
        """Test gathering tasks with concurrency limit."""
        async def test():
            # Create tasks that track when they run
            running = set()
            max_concurrent = 0
            results = []
            
            async def task(i):
                nonlocal max_concurrent
                running.add(i)
                max_concurrent = max(max_concurrent, len(running))
                await asyncio.sleep(0.1)
                running.remove(i)
                return i * 2
            
            # Run 10 tasks with concurrency limit of 3
            results = await gather_with_concurrency(3, *(task(i) for i in range(10)))
            
            # Verify results and max concurrency
            self.assertEqual(results, [0, 2, 4, 6, 8, 10, 12, 14, 16, 18])
            self.assertEqual(max_concurrent, 3)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(test())
    
    def test_run_with_timeout(self):
        """Test running a coroutine with timeout."""
        async def fast_task():
            await asyncio.sleep(0.1)
            return "fast done"
        
        async def slow_task():
            await asyncio.sleep(1.0)
            return "slow done"
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Task completes before timeout
        result = loop.run_until_complete(run_with_timeout(fast_task(), 0.5))
        self.assertEqual(result, "fast done")
        
        # Task exceeds timeout
        with self.assertRaises(asyncio.TimeoutError):
            loop.run_until_complete(run_with_timeout(slow_task(), 0.5))
    
    def test_debounce(self):
        """Test debounce decorator."""
        call_count = 0
        
        @debounce(0.2)
        async def debounced_func():
            nonlocal call_count
            call_count += 1
        
        async def test():
            # Call multiple times in quick succession
            for _ in range(5):
                asyncio.create_task(debounced_func())
                await asyncio.sleep(0.05)
            
            # Wait for debounce period to complete
            await asyncio.sleep(0.3)
            
            # Should only be called once
            self.assertEqual(call_count, 1)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(test())
    
    def test_throttle(self):
        """Test throttle decorator."""
        call_times = []
        
        @throttle(0.2)
        async def throttled_func():
            call_times.append(time.time())
        
        async def test():
            # Call multiple times in quick succession
            start_time = time.time()
            tasks = [throttled_func() for _ in range(3)]
            await asyncio.gather(*tasks)
            
            # Verify minimum time between calls
            self.assertEqual(len(call_times), 3)
            for i in range(1, len(call_times)):
                time_diff = call_times[i] - call_times[i-1]
                self.assertGreaterEqual(time_diff, 0.19)  # Allow small margin of error
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(test())


if __name__ == '__main__':
    unittest.main()