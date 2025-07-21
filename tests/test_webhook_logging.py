"""
Unit tests for Discord Webhook Logging Service

Tests all components of the webhook logging system including:
- Configuration validation
- Message formatting and sanitization
- Rate limiting and circuit breaker functionality
- Queue management and error handling
- Integration with existing logging system
"""

import unittest
import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.services.webhook_logging import (
    WebhookLoggingService, WebhookManager, WebhookConfig, 
    WebhookLogLevel, CircuitBreaker, RateLimiter, MessageFormatter,
    QueuedMessage, WebhookStatus
)


class TestWebhookConfig(unittest.TestCase):
    """Test webhook configuration validation."""
    
    def test_valid_webhook_config(self):
        """Test valid webhook configuration."""
        config = WebhookConfig(
            url="https://discord.com/api/webhooks/123456789/abcdefg",
            name="test",
            min_level=WebhookLogLevel.INFO
        )
        self.assertEqual(config.name, "test")
        self.assertEqual(config.min_level, WebhookLogLevel.INFO)
        self.assertTrue(config.enabled)
    
    def test_invalid_webhook_url(self):
        """Test invalid webhook URL validation."""
        with self.assertRaises(ValueError):
            WebhookConfig(url="https://example.com/webhook")
    
    def test_webhook_url_masking(self):
        """Test webhook URL masking for security."""
        config = WebhookConfig(
            url="https://discord.com/api/webhooks/123456789/secret_token_here"
        )
        self.assertIn("***", config.masked_url)
        self.assertNotIn("secret_token_here", config.masked_url)


class TestCircuitBreaker(unittest.TestCase):
    """Test circuit breaker functionality."""
    
    def setUp(self):
        self.breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    
    def test_initial_state(self):
        """Test circuit breaker initial state."""
        self.assertTrue(self.breaker.can_execute())
        self.assertEqual(self.breaker.state, "closed")
    
    def test_failure_threshold(self):
        """Test circuit breaker opens after failures."""
        # Record failures up to threshold
        for _ in range(3):
            self.breaker.record_failure()
        
        self.assertFalse(self.breaker.can_execute())
        self.assertEqual(self.breaker.state, "open")
    
    def test_recovery_timeout(self):
        """Test circuit breaker recovery after timeout."""
        # Trigger open state
        for _ in range(3):
            self.breaker.record_failure()
        
        # Wait for recovery timeout
        time.sleep(1.1)
        
        # Should allow half-open state
        self.assertTrue(self.breaker.can_execute())
        
        # Success should close circuit
        self.breaker.record_success()
        self.assertEqual(self.breaker.state, "closed")


class TestRateLimiter(unittest.IsolatedAsyncioTestCase):
    """Test rate limiting functionality."""
    
    def setUp(self):
        self.limiter = RateLimiter(requests_per_second=2.0, burst_size=5)
    
    async def test_burst_capacity(self):
        """Test burst capacity allows initial requests."""
        for _ in range(5):
            self.assertTrue(await self.limiter.acquire())
    
    async def test_rate_limiting(self):
        """Test rate limiting prevents excessive requests."""
        # Exhaust burst capacity
        for _ in range(5):
            await self.limiter.acquire()
        
        # Next request should be rate limited
        self.assertFalse(await self.limiter.acquire())
    
    async def test_token_refill(self):
        """Test tokens are refilled over time."""
        # Exhaust burst capacity
        for _ in range(5):
            await self.limiter.acquire()
        
        # Wait for token refill
        await asyncio.sleep(0.6)  # Should refill ~1 token
        
        self.assertTrue(await self.limiter.acquire())


class TestMessageFormatter(unittest.TestCase):
    """Test message formatting and sanitization."""
    
    def setUp(self):
        self.formatter = MessageFormatter()
    
    def test_pii_sanitization(self):
        """Test PII masking in messages."""
        test_cases = [
            ("Email: user@example.com", "Email: [EMAIL]"),
            ("SSN: 123-45-6789", "SSN: [SSN]"),
            ("Card: 1234 5678 9012 3456", "Card: [CARD]"),
            ("token=abc123def", "token=\"[REDACTED]\""),
            ("password=secret123", "password=\"[REDACTED]\"")
        ]
        
        for input_text, expected in test_cases:
            result = self.formatter.sanitize_content(input_text)
            self.assertIn(expected.split(":")[1].strip(), result)
    
    def test_message_formatting(self):
        """Test Discord message formatting."""
        message = self.formatter.format_message(
            WebhookLogLevel.ERROR,
            "Test error message",
            timestamp="2024-01-01 12:00:00 EST"
        )
        
        self.assertIn('embeds', message)
        self.assertEqual(len(message['embeds']), 1)
        
        embed = message['embeds'][0]
        self.assertIn('title', embed)
        self.assertIn('description', embed)
        self.assertIn('color', embed)
        self.assertEqual(embed['color'], 0xFF0000)  # Error color
    
    def test_template_selection(self):
        """Test automatic template selection based on log level."""
        test_cases = [
            (WebhookLogLevel.ERROR, "❌ Error Alert"),
            (WebhookLogLevel.WARNING, "⚠️ Warning"),
            (WebhookLogLevel.INFO, "ℹ️ Information"),
            (WebhookLogLevel.CRITICAL, "🔥 Critical Alert")
        ]
        
        for level, expected_title in test_cases:
            message = self.formatter.format_message(level, "Test message")
            embed = message['embeds'][0]
            self.assertEqual(embed['title'], expected_title)


class TestWebhookManager(unittest.IsolatedAsyncioTestCase):
    """Test webhook manager functionality."""
    
    def setUp(self):
        self.manager = WebhookManager()
        self.test_config = WebhookConfig(
            url="https://discord.com/api/webhooks/123/test",
            name="test_webhook",
            min_level=WebhookLogLevel.INFO
        )
    
    def test_webhook_addition(self):
        """Test adding webhook configuration."""
        self.manager.add_webhook(self.test_config)
        
        self.assertIn("test_webhook", self.manager.webhooks)
        self.assertIn("test_webhook", self.manager.rate_limiters)
        self.assertIn("test_webhook", self.manager.circuit_breakers)
    
    def test_webhook_removal(self):
        """Test removing webhook configuration."""
        self.manager.add_webhook(self.test_config)
        self.manager.remove_webhook("test_webhook")
        
        self.assertNotIn("test_webhook", self.manager.webhooks)
        self.assertNotIn("test_webhook", self.manager.rate_limiters)
        self.assertNotIn("test_webhook", self.manager.circuit_breakers)
    
    async def test_queue_management(self):
        """Test message queue management."""
        self.manager.add_webhook(self.test_config)
        
        # Send test message
        await self.manager.send_log(
            WebhookLogLevel.INFO,
            "Test message"
        )
        
        # Check queue size
        self.assertEqual(self.manager.message_queue.qsize(), 1)
    
    async def test_queue_overflow_protection(self):
        """Test queue overflow protection."""
        self.manager.add_webhook(self.test_config)
        
        # Fill queue beyond capacity
        self.manager.message_queue = asyncio.Queue(maxsize=3)
        
        # Add messages up to capacity
        for i in range(3):
            await self.manager.send_log(WebhookLogLevel.INFO, f"Message {i}")
        
        # Add critical message - should replace non-critical
        await self.manager.send_log(WebhookLogLevel.CRITICAL, "Critical message")
        
        self.assertEqual(self.manager.message_queue.qsize(), 3)
    
    @patch('aiohttp.ClientSession.post')
    async def test_message_delivery(self, mock_post):
        """Test successful message delivery."""
        # Mock successful HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_post.return_value.__aenter__.return_value = mock_response
        
        self.manager.add_webhook(self.test_config)
        await self.manager.start()
        
        # Create test message
        message = QueuedMessage(
            content='{"test": "data"}',
            webhook_name="test_webhook",
            level=WebhookLogLevel.INFO,
            timestamp=time.time()
        )
        
        # Test delivery
        success = await self.manager._deliver_message(message)
        self.assertTrue(success)
        
        await self.manager.stop()
    
    @patch('aiohttp.ClientSession.post')
    async def test_rate_limit_handling(self, mock_post):
        """Test rate limit response handling."""
        # Mock rate limited response
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.headers = {'Retry-After': '1'}
        mock_post.return_value.__aenter__.return_value = mock_response
        
        self.manager.add_webhook(self.test_config)
        await self.manager.start()
        
        message = QueuedMessage(
            content='{"test": "data"}',
            webhook_name="test_webhook", 
            level=WebhookLogLevel.INFO,
            timestamp=time.time()
        )
        
        # Should handle rate limit gracefully
        success = await self.manager._deliver_message(message)
        self.assertFalse(success)
        
        await self.manager.stop()
    
    def test_status_reporting(self):
        """Test webhook system status reporting."""
        self.manager.add_webhook(self.test_config)
        
        status = self.manager.get_status()
        
        self.assertIn('running', status)
        self.assertIn('webhooks', status)
        self.assertIn('stats', status)
        self.assertIn('test_webhook', status['webhooks'])


class TestWebhookLoggingService(unittest.IsolatedAsyncioTestCase):
    """Test main webhook logging service."""
    
    def setUp(self):
        self.service = WebhookLoggingService()
        self.test_config = {
            'webhooks': {
                'test': {
                    'url': 'https://discord.com/api/webhooks/123/test',
                    'min_level': 'INFO',
                    'enabled': True
                }
            }
        }
    
    def test_config_loading(self):
        """Test configuration loading."""
        self.service.load_config(self.test_config)
        
        self.assertTrue(self.service.enabled)
        self.assertIn('test', self.service.manager.webhooks)
    
    def test_invalid_config_handling(self):
        """Test handling of invalid configuration."""
        invalid_config = {
            'webhooks': {
                'invalid': {
                    'url': 'https://invalid-url.com',
                    'min_level': 'INFO'
                }
            }
        }
        
        # Should not raise exception, just skip invalid config
        self.service.load_config(invalid_config)
        self.assertFalse(self.service.enabled)
    
    async def test_convenience_methods(self):
        """Test convenience logging methods."""
        self.service.load_config(self.test_config)
        await self.service.start()
        
        # Test all convenience methods
        await self.service.log_error("Test error")
        await self.service.log_critical("Test critical")
        await self.service.log_warning("Test warning")
        await self.service.log_info("Test info")
        await self.service.log_heartbeat({'cpu': '50%', 'memory': '60%'})
        await self.service.log_member_event('join', {'username': 'testuser', 'id': '123'})
        await self.service.log_performance_alert('cpu_usage', '95%', '90%')
        
        await self.service.stop()
    
    def test_status_reporting(self):
        """Test service status reporting."""
        status = self.service.get_status()
        
        self.assertIn('enabled', status)
        self.assertIn('manager_status', status)


class TestIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for webhook logging system."""
    
    async def test_full_webhook_flow(self):
        """Test complete webhook logging flow."""
        # Create service with test configuration
        service = WebhookLoggingService()
        config = {
            'webhooks': {
                'integration_test': {
                    'url': 'https://discord.com/api/webhooks/123/test',
                    'min_level': 'WARNING',
                    'max_retries': 1,
                    'timeout': 5.0,
                    'enabled': True
                }
            }
        }
        
        service.load_config(config)
        await service.start()
        
        # Test message filtering by level
        await service.log_info("This should be filtered out")
        await service.log_warning("This should be processed")
        
        # Check queue size (only warning should be queued)
        self.assertEqual(service.manager.message_queue.qsize(), 1)
        
        await service.stop()
    
    @patch('src.services.webhook_logging.aiohttp.ClientSession')
    async def test_error_handling_and_recovery(self, mock_session_class):
        """Test error handling and recovery mechanisms."""
        # Mock session that fails initially then succeeds
        mock_session = AsyncMock()
        mock_session_class.return_value = mock_session
        
        # First call fails, second succeeds
        mock_response_fail = AsyncMock()
        mock_response_fail.status = 500
        
        mock_response_success = AsyncMock()
        mock_response_success.status = 200
        
        mock_session.post.return_value.__aenter__.side_effect = [
            mock_response_fail,
            mock_response_success
        ]
        
        service = WebhookLoggingService()
        config = {
            'webhooks': {
                'test': {
                    'url': 'https://discord.com/api/webhooks/123/test',
                    'min_level': 'ERROR',
                    'max_retries': 2,
                    'enabled': True
                }
            }
        }
        
        service.load_config(config)
        await service.start()
        
        # Send test message
        await service.log_error("Test error message")
        
        # Allow time for processing
        await asyncio.sleep(0.1)
        
        await service.stop()
    
    def test_configuration_validation(self):
        """Test comprehensive configuration validation."""
        service = WebhookLoggingService()
        
        # Test various configuration scenarios
        test_configs = [
            # Valid configuration
            {
                'webhooks': {
                    'valid': {
                        'url': 'https://discord.com/api/webhooks/123/token',
                        'min_level': 'INFO',
                        'enabled': True
                    }
                }
            },
            # Invalid URL
            {
                'webhooks': {
                    'invalid_url': {
                        'url': 'https://example.com/webhook',
                        'min_level': 'INFO',
                        'enabled': True
                    }
                }
            },
            # Missing URL
            {
                'webhooks': {
                    'missing_url': {
                        'min_level': 'INFO',
                        'enabled': True
                    }
                }
            },
            # Invalid log level
            {
                'webhooks': {
                    'invalid_level': {
                        'url': 'https://discord.com/api/webhooks/123/token',
                        'min_level': 'INVALID_LEVEL',
                        'enabled': True
                    }
                }
            }
        ]
        
        for i, config in enumerate(test_configs):
            service_test = WebhookLoggingService()
            service_test.load_config(config)
            
            if i == 0:  # Valid config
                self.assertTrue(service_test.enabled)
            else:  # Invalid configs
                self.assertFalse(service_test.enabled)


if __name__ == '__main__':
    # Run tests
    unittest.main() 