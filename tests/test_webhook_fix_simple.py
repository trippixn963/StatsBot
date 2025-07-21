"""
Simple test script to verify webhook URL validation.
"""

import re
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def is_valid_webhook_url(url: str) -> bool:
    """
    Validate a Discord webhook URL.
    
    Args:
        url: The webhook URL to validate.
        
    Returns:
        bool: True if the URL is valid, False otherwise.
    """
    # Basic Discord webhook URL pattern
    pattern = r'^https://(?:ptb\.|canary\.)?discord\.com/api/webhooks/\d+/[\w-]+$'
    return bool(re.match(pattern, url))

def test_webhook_validation():
    """Test webhook URL validation."""
    # Valid webhook URLs
    valid_urls = [
        "https://discord.com/api/webhooks/123456789/abcdefg",
        "https://discord.com/api/webhooks/123456789/abcdefg-hijklmn",
        "https://ptb.discord.com/api/webhooks/123456789/abcdefg",
        "https://canary.discord.com/api/webhooks/123456789/abcdefg"
    ]
    
    # Invalid webhook URLs
    invalid_urls = [
        "https://example.com/not-a-webhook",
        "https://discord.com/api/not-a-webhook",
        "https://discord.com/api/webhooks/",
        "https://discord.com/api/webhooks/abc/def",
        "http://discord.com/api/webhooks/123456789/abcdefg"  # Not HTTPS
    ]
    
    # Test valid URLs
    print("Testing valid webhook URLs:")
    for url in valid_urls:
        result = is_valid_webhook_url(url)
        print(f"  {url}: {'Valid' if result else 'Invalid'}")
        assert result, f"URL should be valid: {url}"
    
    # Test invalid URLs
    print("\nTesting invalid webhook URLs:")
    for url in invalid_urls:
        result = is_valid_webhook_url(url)
        print(f"  {url}: {'Valid' if result else 'Invalid'}")
        assert not result, f"URL should be invalid: {url}"
    
    print("\nAll tests passed!")

if __name__ == "__main__":
    test_webhook_validation()