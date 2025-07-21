"""
Test script to verify that the webhook logging system works correctly.
"""

import sys
import os
import asyncio
import re

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

async def test_webhook_logging():
    """Test the webhook logging system."""
    print("Testing webhook logging system...")
    
    # Import webhook config
    print("Importing webhook config...")
    from src.utils.webhook_logging.config import WebhookConfig, LogLevel, _is_valid_webhook_url
    print("✓ Successfully imported webhook config")
    
    # Test webhook URL validation
    print("\nTesting webhook URL validation...")
    valid_urls = [
        "https://discord.com/api/webhooks/123456789/abcdefg",
        "https://discord.com/api/webhooks/123456789/abcdefg-hijklmn",
        "https://ptb.discord.com/api/webhooks/123456789/abcdefg",
        "https://canary.discord.com/api/webhooks/123456789/abcdefg"
    ]
    
    invalid_urls = [
        "https://example.com/not-a-webhook",
        "https://discord.com/api/not-a-webhook",
        "https://discord.com/api/webhooks/",
        "https://discord.com/api/webhooks/abc/def",
        "http://discord.com/api/webhooks/123456789/abcdefg"  # Not HTTPS
    ]
    
    # Test valid URLs
    for url in valid_urls:
        result = _is_valid_webhook_url(url)
        print(f"  {url}: {'✓ Valid' if result else '✗ Invalid'}")
        assert result, f"URL should be valid: {url}"
    
    # Test invalid URLs
    for url in invalid_urls:
        result = _is_valid_webhook_url(url)
        print(f"  {url}: {'✗ Valid' if result else '✓ Invalid'}")
        assert not result, f"URL should be invalid: {url}"
    
    # Test webhook config validation
    print("\nTesting webhook config validation...")
    
    # Valid config
    valid_config = WebhookConfig(
        error_webhook_url="https://discord.com/api/webhooks/123456789/abcdefg"
    )
    errors = valid_config.validate()
    print(f"  Valid config: {len(errors)} errors")
    assert len(errors) == 0, "Valid config should have no errors"
    
    # Invalid config (no URLs)
    invalid_config = WebhookConfig()
    errors = invalid_config.validate()
    print(f"  Invalid config (no URLs): {len(errors)} errors")
    assert len(errors) > 0, "Invalid config should have errors"
    
    # Invalid config (invalid URL)
    invalid_url_config = WebhookConfig(
        error_webhook_url="https://example.com/not-a-webhook"
    )
    errors = invalid_url_config.validate()
    print(f"  Invalid config (invalid URL): {len(errors)} errors")
    assert len(errors) > 0, "Invalid config with invalid URL should have errors"
    
    # Test webhook routing
    print("\nTesting webhook routing...")
    
    # Create config with multiple webhook URLs
    routing_config = WebhookConfig(
        error_webhook_url="https://discord.com/api/webhooks/123/error",
        info_webhook_url="https://discord.com/api/webhooks/123/info"
    )
    
    # Test routing for different log levels
    critical_webhooks = routing_config.get_webhooks_for_level(LogLevel.CRITICAL)
    print(f"  CRITICAL level routes to {len(critical_webhooks)} webhooks")
    assert len(critical_webhooks) == 2, "CRITICAL should route to both error and info webhooks"
    
    error_webhooks = routing_config.get_webhooks_for_level(LogLevel.ERROR)
    print(f"  ERROR level routes to {len(error_webhooks)} webhooks")
    assert len(error_webhooks) == 1, "ERROR should route to error webhook only"
    
    info_webhooks = routing_config.get_webhooks_for_level(LogLevel.INFO)
    print(f"  INFO level routes to {len(info_webhooks)} webhooks")
    assert len(info_webhooks) == 1, "INFO should route to info webhook only"
    
    debug_webhooks = routing_config.get_webhooks_for_level(LogLevel.DEBUG)
    print(f"  DEBUG level routes to {len(debug_webhooks)} webhooks")
    assert len(debug_webhooks) == 0, "DEBUG should not route to any webhooks by default"
    
    print("\nAll webhook logging tests passed!")

if __name__ == "__main__":
    asyncio.run(test_webhook_logging())