"""
Tests for the error handling framework.

This module contains tests for the exponential backoff, circuit breaker,
and retry mechanisms implemented in the error handling framework.
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.error_handling.backoff import calculate_backoff_delay, with_exponential_backoff
from src.utils.error_handling.circuit_breaker import CircuitBreaker, circuit_breaker
from src.utils.error_handling.retry import with_retry, with_timeout
from src.core.exceptions import CircuitBreakerError, AsyncOperationError, RateLimitError
from src.types.models import RetryConfig


class TestExponentialBackoff:
    """Tests for exponential backoff functionality."""
    
    def test_calculate_backoff_delay(self):
        """Test backoff delay calculation."""
        # Test without jitter
        delay = calculate_backoff_delay(0, base_delay=1.0, jitter=False)
        assert delay == 1.0
        
        delay = calculate_backoff_delay(1, base_delay=1.0, jitter=False)
        assert delay == 2.0
        
        delay = calculate_backoff_delay(2, base_delay=1.0, jitter=False)
        assert delay == 4.0
        
        # Test with max_delay
        delay = calculate_backoff_delay(10, base_delay=1.0, max_delay=30.0, jitter=False)
        assert delay == 30.0
        
        # Test with jitter (can only test range)
        delay = calculate_backoff_delay(1, base_delay=1.0, jitter=True, jitter_factor=0.25)
        assert 1.5 <= delay <= 2.5
    
    @pytest.mark.asyncio
    async def test_with_exponential_backoff_success(self):
        """Test successful operation with backoff."""
        mock_operation = AsyncMock(return_value="success")
        
        result = await with_exponential_backoff(
            mock_operation,
            "arg1",
            kwarg1="value1",
            max_attempts=3
        )
        
        assert result == "success"
        mock_operation.assert_called_once_with("arg1", kwarg1="value1")
    
    @pytest.mark.asyncio
    async def test_with_exponential_backoff_retry_and_succeed(self):
        """Test operation that fails then succeeds."""
        mock_operation = AsyncMock(side_effect=[RateLimitError("Rate limited"), "success"])
        
        result = await with_exponential_backoff(
            mock_operation,
            max_attempts=3,
            base_delay=0.01  # Small delay for testing
        )
        
        assert result == "success"
        assert mock_operation.call_count == 2
    
    @pytest.mark.asyncio
    async def test_with_exponential_backoff_max_retries(self):
        """Test operation that always fails."""
        mock_operation = AsyncMock(side_effect=RateLimitError("Rate limited"))
        
        with pytest.raises(RateLimitError):
            await with_exponential_backoff(
                mock_operation,
                max_attempts=3,
                base_delay=0.01  # Small delay for testing
            )
        
        assert mock_operation.call_count == 4  # Initial + 3 retries


class TestCircuitBreaker:
    """Tests for circuit breaker functionality."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_success(self):
        """Test successful operation with circuit breaker."""
        cb = CircuitBreaker("test_cb", failure_threshold=3)
        mock_operation = AsyncMock(return_value="success")
        
        result = await cb.execute(mock_operation, "arg1", kwarg1="value1")
        
        assert result == "success"
        mock_operation.assert_called_once_with("arg1", kwarg1="value1")
        assert cb.state.value == "closed"
        assert cb.failure_count == 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_open_after_failures(self):
        """Test circuit opens after threshold failures."""
        cb = CircuitBreaker("test_cb", failure_threshold=3)
        mock_operation = AsyncMock(side_effect=Exception("Failed"))
        
        # First 2 calls should fail but circuit stays closed
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.execute(mock_operation)
        
        # Circuit should still be closed after 2 failures
        assert cb.state.value == "closed"
        
        # 3rd call should open the circuit
        with pytest.raises(Exception):
            await cb.execute(mock_operation)
        
        # Now the circuit should be open
        assert cb.state.value == "open"
        assert cb.failure_count == 3
        
        # Next call should fail with CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            await cb.execute(mock_operation)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_after_timeout(self):
        """Test circuit goes to half-open after timeout."""
        cb = CircuitBreaker("test_cb", failure_threshold=2, reset_timeout=0.1)
        mock_operation = AsyncMock(side_effect=Exception("Failed"))
        
        # Open the circuit
        for _ in range(3):
            with pytest.raises(Exception):
                await cb.execute(mock_operation)
        
        assert cb.state.value == "open"
        
        # Wait for reset timeout
        await asyncio.sleep(0.2)
        
        # Circuit should go to half-open on next call
        mock_operation.side_effect = ["success"]  # Next call succeeds
        result = await cb.execute(mock_operation)
        
        assert result == "success"
        assert cb.state.value == "closed"  # Success in half-open closes circuit
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_decorator(self):
        """Test circuit breaker decorator."""
        # Create a function with circuit breaker
        failure_count = 0
        
        @circuit_breaker(name="test_decorator", failure_threshold=2, reset_timeout=0.1)
        async def test_function(succeed: bool = False):
            nonlocal failure_count
            if not succeed and failure_count < 3:
                failure_count += 1
                raise Exception("Failed")
            return "success"
        
        # First 2 calls should fail but circuit stays closed
        for _ in range(2):
            with pytest.raises(Exception):
                await test_function()
        
        # 3rd call should open the circuit
        with pytest.raises(Exception):
            await test_function()
        
        # Next call should fail with CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            await test_function(succeed=True)  # Even with succeed=True
        
        # Wait for reset timeout
        await asyncio.sleep(0.2)
        
        # Circuit should go to half-open and succeed
        result = await test_function(succeed=True)
        assert result == "success"


class TestRetryMechanisms:
    """Tests for retry mechanisms."""
    
    @pytest.mark.asyncio
    async def test_with_timeout_success(self):
        """Test successful operation with timeout."""
        async def fast_operation():
            await asyncio.sleep(0.1)
            return "success"
        
        result = await with_timeout(fast_operation, timeout=1.0)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_with_timeout_failure(self):
        """Test operation that times out."""
        async def slow_operation():
            await asyncio.sleep(0.5)
            return "success"
        
        with pytest.raises(AsyncOperationError) as exc_info:
            await with_timeout(slow_operation, timeout=0.1)
        
        assert "timed out" in str(exc_info.value)
        assert exc_info.value.was_cancelled
    
    @pytest.mark.asyncio
    async def test_with_retry_success(self):
        """Test successful operation with retry."""
        mock_operation = AsyncMock(return_value="success")
        
        result = await with_retry(
            mock_operation,
            "arg1",
            kwarg1="value1",
            max_attempts=3
        )
        
        assert result == "success"
        mock_operation.assert_called_once_with("arg1", kwarg1="value1")
    
    @pytest.mark.asyncio
    async def test_with_retry_and_succeed(self):
        """Test operation that fails then succeeds."""
        mock_operation = AsyncMock(side_effect=[Exception("Failed"), "success"])
        
        result = await with_retry(
            mock_operation,
            max_attempts=3,
            retry_delay=0.01  # Small delay for testing
        )
        
        assert result == "success"
        assert mock_operation.call_count == 2
    
    @pytest.mark.asyncio
    async def test_with_retry_max_attempts(self):
        """Test operation that always fails."""
        mock_operation = AsyncMock(side_effect=Exception("Failed"))
        
        with pytest.raises(AsyncOperationError):
            await with_retry(
                mock_operation,
                max_attempts=3,
                retry_delay=0.01  # Small delay for testing
            )
        
        assert mock_operation.call_count == 3
    
    @pytest.mark.asyncio
    async def test_with_retry_graceful_degradation(self):
        """Test graceful degradation with fallback value."""
        mock_operation = AsyncMock(side_effect=Exception("Failed"))
        
        result = await with_retry(
            mock_operation,
            max_attempts=2,
            retry_delay=0.01,
            graceful_degradation=True,
            fallback_value="fallback"
        )
        
        assert result == "fallback"
        assert mock_operation.call_count == 2
    
    @pytest.mark.asyncio
    async def test_with_retry_fallback_function(self):
        """Test graceful degradation with fallback function."""
        mock_operation = AsyncMock(side_effect=Exception("Failed"))
        mock_fallback = AsyncMock(return_value="fallback_result")
        
        result = await with_retry(
            mock_operation,
            "arg1",
            max_attempts=2,
            retry_delay=0.01,
            graceful_degradation=True,
            fallback_function=mock_fallback
        )
        
        assert result == "fallback_result"
        assert mock_operation.call_count == 2
        mock_fallback.assert_called_once_with("arg1")


if __name__ == "__main__":
    pytest.main(["-xvs", "test_error_handling.py"])