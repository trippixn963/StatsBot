"""
Tests for connection recovery mechanisms.

This module contains tests for the connection recovery mechanisms,
including automatic reconnection, state consistency maintenance,
and fallback mechanisms.
"""

import asyncio
import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import pytest
from datetime import datetime, timedelta

from src.utils.error_handling.connection_recovery import (
    ConnectionRecoveryManager, StateConsistencyManager, FallbackManager
)
from src.types.models import ConnectionState
from src.utils.logging.structured_logger import StructuredLogger


class TestConnectionRecoveryManager:
    """Tests for the ConnectionRecoveryManager class."""
    
    @pytest.fixture
    def logger_mock(self):
        """Create a mock logger."""
        return Mock(spec=StructuredLogger)
    
    @pytest.fixture
    def recovery_manager(self, logger_mock):
        """Create a ConnectionRecoveryManager instance for testing."""
        return ConnectionRecoveryManager(
            logger=logger_mock,
            max_reconnect_attempts=5,
            initial_backoff=0.1,
            max_backoff=1.0,
            jitter_factor=0.1
        )
    
    @pytest.mark.asyncio
    async def test_initial_state(self, recovery_manager):
        """Test initial state of the recovery manager."""
        assert recovery_manager.connection_state == ConnectionState.DISCONNECTED
        assert recovery_manager.reconnect_attempts == 0
        assert recovery_manager.is_connected is False
        assert recovery_manager.is_reconnecting is False
    
    @pytest.mark.asyncio
    async def test_on_connect(self, recovery_manager):
        """Test on_connect method."""
        # Initial state
        assert recovery_manager.connection_state == ConnectionState.DISCONNECTED
        
        # Connect
        await recovery_manager.on_connect()
        
        # Should be connected
        assert recovery_manager.connection_state == ConnectionState.CONNECTED
        assert recovery_manager.is_connected is True
        assert recovery_manager.is_reconnecting is False
    
    @pytest.mark.asyncio
    async def test_on_disconnect(self, recovery_manager):
        """Test on_disconnect method."""
        # Start connected
        await recovery_manager.on_connect()
        assert recovery_manager.connection_state == ConnectionState.CONNECTED
        
        # Mock the _reconnect_loop method to prevent it from running
        recovery_manager._reconnect_loop = AsyncMock()
        
        # Disconnect
        await recovery_manager.on_disconnect("Test disconnect")
        
        # Should be disconnected
        assert recovery_manager.connection_state == ConnectionState.DISCONNECTED
        assert recovery_manager.is_connected is False
        
        # Should have called _reconnect_loop
        recovery_manager._reconnect_loop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_reconnect_handlers(self, recovery_manager):
        """Test reconnect handlers are called."""
        # Create mock handlers
        disconnect_handler = Mock()
        reconnect_handler = Mock()
        reconnect_attempt_handler = Mock()
        
        # Register handlers
        recovery_manager.add_disconnect_handler(disconnect_handler)
        recovery_manager.add_reconnect_handler(reconnect_handler)
        recovery_manager.add_reconnect_attempt_handler(reconnect_attempt_handler)
        
        # Start connected
        await recovery_manager.on_connect()
        
        # Mock the _reconnect_loop method to prevent it from running
        recovery_manager._reconnect_loop = AsyncMock()
        
        # Disconnect
        await recovery_manager.on_disconnect("Test disconnect")
        
        # Disconnect handler should be called
        disconnect_handler.assert_called_once()
        
        # Reconnect
        await recovery_manager.on_connect()
        
        # Reconnect handler should be called
        reconnect_handler.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_connection_stats(self, recovery_manager):
        """Test connection statistics are updated correctly."""
        # Start connected
        await recovery_manager.on_connect()
        
        # Mock the _reconnect_loop method to prevent it from running
        recovery_manager._reconnect_loop = AsyncMock()
        
        # Disconnect
        await recovery_manager.on_disconnect("Test disconnect")
        
        # Check stats
        stats = recovery_manager.connection_stats
        assert stats["total_disconnects"] == 1
        assert stats["last_disconnect_reason"] == "Test disconnect"
        
        # Reconnect
        await recovery_manager.on_connect()
        
        # Check stats
        stats = recovery_manager.connection_stats
        assert stats["total_reconnects"] == 1
    
    @pytest.mark.asyncio
    async def test_shutdown(self, recovery_manager):
        """Test shutdown method."""
        # Mock the _reconnect_loop method
        recovery_manager._reconnect_loop = AsyncMock()
        recovery_manager._recovery_task = asyncio.create_task(asyncio.sleep(10))
        
        # Shutdown
        await recovery_manager.shutdown()
        
        # Should have set shutdown event
        assert recovery_manager._shutdown_event.is_set()
        
        # Task should be cancelled
        assert recovery_manager._recovery_task.cancelled()


class TestStateConsistencyManager:
    """Tests for the StateConsistencyManager class."""
    
    @pytest.fixture
    def logger_mock(self):
        """Create a mock logger."""
        return Mock(spec=StructuredLogger)
    
    @pytest.fixture
    def state_manager(self, logger_mock):
        """Create a StateConsistencyManager instance for testing."""
        return StateConsistencyManager(logger=logger_mock)
    
    @pytest.mark.asyncio
    async def test_save_and_get_state_snapshot(self, state_manager):
        """Test saving and retrieving state snapshots."""
        # Save state
        test_state = {"key": "value", "number": 42}
        await state_manager.save_state_snapshot("test", test_state)
        
        # Get state
        retrieved_state = await state_manager.get_state_snapshot("test")
        
        # Should be the same
        assert retrieved_state == test_state
    
    @pytest.mark.asyncio
    async def test_register_and_execute_pending_operations(self, state_manager):
        """Test registering and executing pending operations."""
        # Create mock operations
        operation1 = Mock()
        operation2 = Mock()
        
        # Register operations
        await state_manager.register_pending_operation("op1", operation1)
        await state_manager.register_pending_operation("op2", operation2)
        
        # Execute operations
        await state_manager.execute_pending_operations()
        
        # Operations should be called
        operation1.assert_called_once()
        operation2.assert_called_once()
        
        # Pending operations should be cleared
        assert len(state_manager._pending_operations) == 0
    
    @pytest.mark.asyncio
    async def test_clear_state(self, state_manager):
        """Test clearing state."""
        # Save state
        await state_manager.save_state_snapshot("test", {"key": "value"})
        
        # Register operation
        await state_manager.register_pending_operation("op", Mock())
        
        # Clear state
        await state_manager.clear_state()
        
        # State should be cleared
        assert len(state_manager._state_snapshots) == 0
        assert len(state_manager._pending_operations) == 0


class TestFallbackManager:
    """Tests for the FallbackManager class."""
    
    @pytest.fixture
    def logger_mock(self):
        """Create a mock logger."""
        return Mock(spec=StructuredLogger)
    
    @pytest.fixture
    def fallback_manager(self, logger_mock):
        """Create a FallbackManager instance for testing."""
        return FallbackManager(logger=logger_mock)
    
    @pytest.mark.asyncio
    async def test_register_fallback(self, fallback_manager):
        """Test registering fallback methods."""
        # Create mock fallback
        fallback = AsyncMock()
        
        # Register fallback
        await fallback_manager.register_fallback("test_operation", fallback)
        
        # Should be registered
        assert "test_operation" in fallback_manager._fallbacks
        assert fallback_manager._fallbacks["test_operation"][0] == fallback
    
    @pytest.mark.asyncio
    async def test_execute_with_fallbacks_primary_success(self, fallback_manager):
        """Test executing with fallbacks when primary method succeeds."""
        # Create mock methods
        primary = AsyncMock(return_value="primary result")
        fallback = AsyncMock(return_value="fallback result")
        
        # Register fallback
        await fallback_manager.register_fallback("test_operation", fallback)
        
        # Execute with fallbacks
        result = await fallback_manager.execute_with_fallbacks(
            "test_operation", primary, "arg1", "arg2", kwarg1="value1"
        )
        
        # Primary should be called with correct args
        primary.assert_called_once_with("arg1", "arg2", kwarg1="value1")
        
        # Fallback should not be called
        fallback.assert_not_called()
        
        # Result should be from primary
        assert result == "primary result"
    
    @pytest.mark.asyncio
    async def test_execute_with_fallbacks_primary_failure(self, fallback_manager):
        """Test executing with fallbacks when primary method fails."""
        # Create mock methods
        primary = AsyncMock(side_effect=ValueError("Primary failed"))
        fallback = AsyncMock(return_value="fallback result")
        
        # Register fallback
        await fallback_manager.register_fallback("test_operation", fallback)
        
        # Execute with fallbacks
        result = await fallback_manager.execute_with_fallbacks(
            "test_operation", primary, "arg1", "arg2", kwarg1="value1"
        )
        
        # Primary should be called
        primary.assert_called_once()
        
        # Fallback should be called with same args
        fallback.assert_called_once_with("arg1", "arg2", kwarg1="value1")
        
        # Result should be from fallback
        assert result == "fallback result"
    
    @pytest.mark.asyncio
    async def test_execute_with_fallbacks_all_failure(self, fallback_manager):
        """Test executing with fallbacks when all methods fail."""
        # Create mock methods
        primary = AsyncMock(side_effect=ValueError("Primary failed"))
        fallback1 = AsyncMock(side_effect=ValueError("Fallback 1 failed"))
        fallback2 = AsyncMock(side_effect=ValueError("Fallback 2 failed"))
        
        # Register fallbacks
        await fallback_manager.register_fallback("test_operation", fallback1)
        await fallback_manager.register_fallback("test_operation", fallback2)
        
        # Execute with fallbacks - should raise the last error
        with pytest.raises(ValueError, match="Fallback 2 failed"):
            await fallback_manager.execute_with_fallbacks(
                "test_operation", primary, "arg1", "arg2"
            )
        
        # All methods should be called
        primary.assert_called_once()
        fallback1.assert_called_once()
        fallback2.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_stats(self, fallback_manager):
        """Test getting fallback statistics."""
        # Register fallback
        await fallback_manager.register_fallback("test_operation", AsyncMock())
        
        # Update stats manually for testing
        fallback_manager._fallback_stats["test_operation"]["primary_failures"] = 2
        fallback_manager._fallback_stats["test_operation"]["fallback_successes"] = 1
        fallback_manager._fallback_stats["test_operation"]["fallback_failures"] = 1
        
        # Get stats
        stats = fallback_manager.get_stats()
        
        # Check stats
        assert "test_operation" in stats
        assert stats["test_operation"]["primary_failures"] == 2
        assert stats["test_operation"]["fallback_successes"] == 1
        assert stats["test_operation"]["fallback_failures"] == 1


if __name__ == "__main__":
    pytest.main()