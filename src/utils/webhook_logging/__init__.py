"""
Discord Webhook Logging System.

This module provides comprehensive webhook logging capabilities for StatsBot,
enabling real-time monitoring of bot operations, errors, performance metrics,
and system events directly within Discord channels.

Key Features:
- Multiple webhook endpoints for different log levels
- Structured message formatting with rich embeds
- Rate limiting and batching to respect Discord API limits
- Automatic error handling and recovery
- Privacy-focused data handling
"""

from .config import WebhookConfig, LogLevel
from .webhook_manager import WebhookManager
from .message_formatter import MessageFormatter

__all__ = [
    'WebhookConfig',
    'LogLevel',
    'WebhookManager',
    'MessageFormatter',
    'setup_webhook_logging',
]

# Global webhook manager instance
_webhook_manager = None

def setup_webhook_logging(config=None):
    """
    Set up the webhook logging system.
    
    Args:
        config: Optional WebhookConfig object. If not provided,
               configuration will be loaded from environment variables.
    
    Returns:
        WebhookManager: The initialized webhook manager instance.
    """
    global _webhook_manager
    
    if _webhook_manager is None:
        from .config import load_webhook_config
        
        # Load config from environment if not provided
        if config is None:
            config = load_webhook_config()
        
        # Initialize the webhook manager
        _webhook_manager = WebhookManager(config)
    
    return _webhook_manager

def get_webhook_manager():
    """
    Get the global webhook manager instance.
    
    Returns:
        WebhookManager: The global webhook manager instance.
    """
    if _webhook_manager is None:
        return setup_webhook_logging()
    return _webhook_manager