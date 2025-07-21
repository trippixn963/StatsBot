"""
Unit tests for webhook logging system.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import aiohttp
from datetime import datetime, timezone

from src.utils.webhook_logging.config import WebhookConfig, LogLevel
from src.utils.webhook_logging.webhook_manager import WebhookManager, WebhookClient
from src.utils.webhook_logging.message_formatter import MessageFormatter, WebhookMessage


class TestWebhookConfig:
    """Tests for WebhookConfig."""
    
    def test_config_validation_valid(self):
        """Test validation with valid configuration."""
        config = WebhookConfig(
            error_webhook_url="https://discord.com/api/webhooks/123456789/abcdefg"
        )
        errors = config.validate()
        assert len(errors) == 0
    
    def test_config_validation_invalid_url(self):
        """Test validation with invalid webhook URL."""
        config = WebhookConfig(
            error_webhook_url="https://example.com/not-a-webhook"
        )
        errors = config.validate()
        assert len(errors) > 0
        assert any("Invalid webhook URL" in error for error in errors)
    
    def test_config_validation_no_urls(self):
        """Test validation with no webhook URLs."""
        config = WebhookConfig()
        errors = config.validate()
        assert len(errors) > 0
        assert any("No webhook URLs provided" in error for error in errors)
    
    def test_get_webhooks_for_level(self):
        """Test getting webhooks for a specific log level."""
        config = WebhookConfig(
            error_webhook_url="https://discord.com/api/webhooks/123/error",
            info_webhook_url="https://discord.com/api/webhooks/123/info"
        )
        
        # Critical should go to both error and info webhooks
        critical_webhooks = config.get_webhooks_for_level(LogLevel.CRITICAL)
        assert len(critical_webhooks) == 2
        assert config.error_webhook_url in critical_webhooks
        assert config.info_webhook_url in critical_webhooks
        
        # Error should only go to error webhook
        error_webhooks = config.get_webhooks_for_level(LogLevel.ERROR)
        assert len(error_webhooks) == 1
        assert config.error_webhook_url in error_webhooks
        
        # Info should only go to info webhook
        info_webhooks = config.get_webhooks_for_level(LogLevel.INFO)
        assert len(info_webhooks) == 1
        assert config.info_webhook_url in info_webhooks
        
        # Debug should not go to any webhook by default
        debug_webhooks = config.get_webhooks_for_level(LogLevel.DEBUG)
        assert len(debug_webhooks) == 0


class TestMessageFormatter:
    """Tests for MessageFormatter."""
    
    def test_format_log_message_embed(self):
        """Test formatting log message as embed."""
        config = WebhookConfig(use_embeds=True)
        formatter = MessageFormatter(config)
        
        message = formatter.format_log_message(
            LogLevel.ERROR,
            "Test error message",
            component="test_component",
            user_id=123456789
        )
        
        assert isinstance(message, WebhookMessage)
        assert len(message.embeds) == 1
        assert message.embeds[0]["title"] == "❌ ERROR"
        assert message.embeds[0]["description"] == "Test error message"
        
        # Check fields
        fields = {field["name"]: field["value"] for field in message.embeds[0]["fields"]}
        assert "Component" in fields
        assert fields["Component"] == "test_component"
        assert "User Id" in fields
        assert fields["User Id"] == "123456789"
    
    def test_format_log_message_text(self):
        """Test formatting log message as plain text."""
        config = WebhookConfig(use_embeds=False)
        formatter = MessageFormatter(config)
        
        message = formatter.format_log_message(
            LogLevel.INFO,
            "Test info message",
            component="test_component"
        )
        
        assert isinstance(message, WebhookMessage)
        assert message.content is not None
        assert "INFO" in message.content
        assert "Test info message" in message.content
        assert "Component" in message.content
        assert "test_component" in message.content
    
    def test_format_error_message(self):
        """Test formatting error message."""
        config = WebhookConfig(use_embeds=True)
        formatter = MessageFormatter(config)
        
        try:
            # Generate an exception
            raise ValueError("Test error")
        except ValueError as e:
            message = formatter.format_error_message(e, {"component": "test_component"})
        
        assert isinstance(message, WebhookMessage)
        assert len(message.embeds) == 1
        
        # Check fields
        fields = {field["name"]: field["value"] for field in message.embeds[0]["fields"]}
        assert "Error Type" in fields
        assert fields["Error Type"] == "ValueError"
        assert "Component" in fields
        assert fields["Component"] == "test_component"
        assert "Stack Trace" in fields
        assert "```" in fields["Stack Trace"]
    
    def test_format_performance_alert(self):
        """Test formatting performance alert."""
        config = WebhookConfig(use_embeds=True)
        formatter = MessageFormatter(config)
        
        message = formatter.format_performance_alert(
            "memory_usage",
            150.0,
            100.0,
            component="test_component"
        )
        
        assert isinstance(message, WebhookMessage)
        assert len(message.embeds) == 1
        assert "Performance Alert" in message.embeds[0]["title"]
        
        # Check fields
        fields = {field["name"]: field["value"] for field in message.embeds[0]["fields"]}
        assert "Current Value" in fields
        assert "150.00" in fields["Current Value"]
        assert "Threshold" in fields
        assert "100.00" in fields["Threshold"]
        assert "Ratio" in fields
        assert "1.50" in fields["Ratio"]
        assert "Component" in fields
        assert fields["Component"] == "test_component"
    
    def test_format_member_event(self):
        """Test formatting member event."""
        config = WebhookConfig(use_embeds=True)
        formatter = MessageFormatter(config)
        
        message = formatter.format_member_event(
            "join",
            123456789,
            "TestUser#1234",
            guild_id=987654321
        )
        
        assert isinstance(message, WebhookMessage)
        assert len(message.embeds) == 1
        assert "Member Joined" in message.embeds[0]["title"]
        assert "TestUser#1234" in message.embeds[0]["description"]
        assert "123456789" in message.embeds[0]["description"]
        
        # Check fields
        fields = {field["name"]: field["value"] for field in message.embeds[0]["fields"]}
        assert "Guild Id" in fields
        assert fields["Guild Id"] == "987654321"


@pytest.mark.asyncio
class TestWebhookClient:
    """Tests for WebhookClient."""
    
    async def test_send_message_success(self):
        """Test successful message sending."""
        # Mock session and response
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        client = WebhookClient("https://discord.com/api/webhooks/123/test", mock_session)
        message = WebhookMessage(content="Test message")
        
        result = await client.send_message(message)
        
        assert result is True
        assert client.consecutive_failures == 0
        assert client.total_sent == 1
        assert client.total_failed == 0
        mock_session.post.assert_called_once()
    
    async def test_send_message_failure(self):
        """Test message sending failure."""
        # Mock session and response
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Bad Request")
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        client = WebhookClient("https://discord.com/api/webhooks/123/test", mock_session)
        message = WebhookMessage(content="Test message")
        
        result = await client.send_message(message)
        
        assert result is False
        assert client.consecutive_failures == 1
        assert client.total_sent == 0
        assert client.total_failed == 1
        mock_session.post.assert_called_once()
    
    async def test_circuit_breaker(self):
        """Test circuit breaker functionality."""
        # Mock session and response
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Server Error")
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        client = WebhookClient("https://discord.com/api/webhooks/123/test", mock_session)
        client.max_failures = 2  # Set lower threshold for testing
        message = WebhookMessage(content="Test message")
        
        # First failure
        result1 = await client.send_message(message)
        assert result1 is False
        assert client.consecutive_failures == 1
        assert client.circuit_open is False
        
        # Second failure - should open circuit
        result2 = await client.send_message(message)
        assert result2 is False
        assert client.consecutive_failures == 2
        assert client.circuit_open is True
        
        # Third attempt - should skip due to open circuit
        mock_session.post.reset_mock()
        result3 = await client.send_message(message)
        assert result3 is False
        mock_session.post.assert_not_called()


@pytest.mark.asyncio
class TestWebhookManager:
    """Tests for WebhookManager."""
    
    async def test_initialization(self):
        """Test webhook manager initialization."""
        config = WebhookConfig(
            error_webhook_url="https://discord.com/api/webhooks/123/error",
            info_webhook_url="https://discord.com/api/webhooks/123/info"
        )
        
        with patch('aiohttp.ClientSession'):
            manager = WebhookManager(config)
            
            assert len(manager.webhooks) == 2
            assert config.error_webhook_url in manager.webhooks
            assert config.info_webhook_url in manager.webhooks
    
    async def test_send_log(self):
        """Test sending log message."""
        config = WebhookConfig(
            error_webhook_url="https://discord.com/api/webhooks/123/error",
            info_webhook_url="https://discord.com/api/webhooks/123/info"
        )
        
        with patch('aiohttp.ClientSession'):
            manager = WebhookManager(config)
            
            # Mock message formatter
            manager.message_formatter = MagicMock()
            manager.message_formatter.format_log_message.return_value = WebhookMessage(content="Test")
            
            # Send log message
            await manager.send_log(LogLevel.ERROR, "Test error message", component="test")
            
            # Check that message was queued
            assert manager.message_queue.qsize() == 1
            
            # Check formatter was called correctly
            manager.message_formatter.format_log_message.assert_called_once_with(
                LogLevel.ERROR, "Test error message", component="test"
            )
    
    async def test_send_error(self):
        """Test sending error message."""
        config = WebhookConfig(
            error_webhook_url="https://discord.com/api/webhooks/123/error"
        )
        
        with patch('aiohttp.ClientSession'):
            manager = WebhookManager(config)
            
            # Mock message formatter
            manager.message_formatter = MagicMock()
            manager.message_formatter.format_error_message.return_value = WebhookMessage(content="Test")
            
            # Create test exception
            test_error = ValueError("Test error")
            
            # Send error message
            await manager.send_error(test_error, component="test")
            
            # Check that message was queued
            assert manager.message_queue.qsize() == 1
            
            # Check formatter was called correctly
            manager.message_formatter.format_error_message.assert_called_once_with(
                test_error, {"component": "test"}
            )
    
    async def test_queue_processing(self):
        """Test message queue processing."""
        config = WebhookConfig(
            error_webhook_url="https://discord.com/api/webhooks/123/error"
        )
        
        with patch('aiohttp.ClientSession'):
            manager = WebhookManager(config)
            
            # Mock webhook client
            mock_client = AsyncMock()
            mock_client.send_message.return_value = True
            manager.webhooks = {config.error_webhook_url: mock_client}
            
            # Start queue processor
            await manager.start()
            
            # Queue a message
            test_message = WebhookMessage(content="Test message")
            await manager.message_queue.put((config.error_webhook_url, test_message))
            
            # Wait for processing
            await asyncio.sleep(0.1)
            
            # Check that client was called
            mock_client.send_message.assert_called_once_with(test_message)
            
            # Stop queue processor
            await manager.stop()