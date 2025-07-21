"""
Test script to verify webhook logging functionality.
"""

import asyncio
import logging
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.webhook_logging.config import WebhookConfig, LogLevel, load_webhook_config
from src.utils.webhook_logging import setup_webhook_logging
from src.utils.webhook_logging.integration import (
    log_to_webhook, log_error_to_webhook, log_performance_alert_to_webhook, log_member_event_to_webhook
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook_test")

async def test_webhook_logging():
    """Test webhook logging functionality."""
    logger.info("Starting webhook logging test")
    
    # Load config from environment
    config = load_webhook_config()
    
    # Print config for debugging
    logger.info(f"Webhook config loaded:")
    logger.info(f"  Error webhook URL: {config.error_webhook_url}")
    logger.info(f"  Info webhook URL: {config.info_webhook_url}")
    logger.info(f"  Performance webhook URL: {config.performance_webhook_url}")
    logger.info(f"  Member events webhook URL: {config.member_events_webhook_url}")
    
    # Validate config
    errors = config.validate()
    if errors:
        logger.error("Webhook configuration errors:")
        for error in errors:
            logger.error(f"  {error}")
        return
    
    # Setup webhook logging
    webhook_manager = setup_webhook_logging(config)
    await webhook_manager.start()
    
    try:
        # Test log message
        logger.info("Sending test log message")
        await webhook_manager.send_log(
            LogLevel.INFO,
            "Test info message from webhook fix script",
            component="webhook_test"
        )
        
        # Test error message
        logger.info("Sending test error message")
        try:
            raise ValueError("Test error for webhook logging")
        except ValueError as e:
            await webhook_manager.send_error(e, component="webhook_test")
        
        # Test performance alert
        logger.info("Sending test performance alert")
        await webhook_manager.send_performance_alert(
            "test_metric",
            150.0,
            100.0,
            component="webhook_test"
        )
        
        # Test member event
        logger.info("Sending test member event")
        await webhook_manager.send_member_event(
            "join",
            123456789,
            "TestUser#1234",
            guild_id=987654321
        )
        
        # Wait for messages to be processed
        logger.info("Waiting for messages to be processed")
        await asyncio.sleep(5)
        
    finally:
        # Stop webhook manager
        await webhook_manager.stop()
        logger.info("Webhook manager stopped")

if __name__ == "__main__":
    asyncio.run(test_webhook_logging())