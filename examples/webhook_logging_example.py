"""
Example script demonstrating how to use the webhook logging system.

This script shows how to set up and use the webhook logging system
for various types of logs and events.

Usage:
    python examples/webhook_logging_example.py

Environment Variables:
    WEBHOOK_ERROR_URL: Discord webhook URL for error logs
    WEBHOOK_INFO_URL: Discord webhook URL for info logs
    WEBHOOK_PERFORMANCE_URL: Discord webhook URL for performance alerts
    WEBHOOK_MEMBER_EVENTS_URL: Discord webhook URL for member events
"""

import os
import asyncio
import logging
import random
from datetime import datetime, timezone

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("webhook_example")

# Import webhook logging
from src.utils.webhook_logging import (
    setup_webhook_logging,
    WebhookConfig,
    LogLevel
)
from src.utils.webhook_logging.integration import (
    log_to_webhook,
    log_error_to_webhook,
    log_performance_alert_to_webhook,
    log_member_event_to_webhook
)

async def main():
    """Main example function."""
    logger.info("Starting webhook logging example")
    
    # Load webhook configuration from environment
    webhook_config = WebhookConfig(
        # Primary webhook URLs - use the same URL for all in this example if needed
        error_webhook_url=os.getenv('WEBHOOK_ERROR_URL'),
        info_webhook_url=os.getenv('WEBHOOK_INFO_URL') or os.getenv('WEBHOOK_ERROR_URL'),
        performance_webhook_url=os.getenv('WEBHOOK_PERFORMANCE_URL') or os.getenv('WEBHOOK_ERROR_URL'),
        member_events_webhook_url=os.getenv('WEBHOOK_MEMBER_EVENTS_URL') or os.getenv('WEBHOOK_ERROR_URL'),
        
        # Use embeds for rich formatting
        use_embeds=True
    )
    
    # Validate configuration
    errors = webhook_config.validate()
    if errors:
        logger.error("Webhook configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.error("Please set at least WEBHOOK_ERROR_URL environment variable")
        return
    
    # Initialize webhook logging
    webhook_manager = setup_webhook_logging(webhook_config)
    await webhook_manager.start()
    
    try:
        # Example 1: Send info log
        logger.info("Sending info log to webhook")
        log_to_webhook(
            LogLevel.INFO,
            "This is an example info message",
            component="webhook_example",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        await asyncio.sleep(1)  # Wait for webhook to process
        
        # Example 2: Send warning log
        logger.info("Sending warning log to webhook")
        log_to_webhook(
            LogLevel.WARNING,
            "This is an example warning message",
            component="webhook_example",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        await asyncio.sleep(1)  # Wait for webhook to process
        
        # Example 3: Send error log
        logger.info("Sending error log to webhook")
        try:
            # Generate an exception
            result = 1 / 0
        except Exception as e:
            log_error_to_webhook(
                e,
                component="webhook_example",
                operation="division",
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        await asyncio.sleep(1)  # Wait for webhook to process
        
        # Example 4: Send performance alert
        logger.info("Sending performance alert to webhook")
        log_performance_alert_to_webhook(
            "memory_usage",
            random.uniform(600, 800),  # Random memory usage between 600-800 MB
            512.0,  # Threshold at 512 MB
            component="webhook_example",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        await asyncio.sleep(1)  # Wait for webhook to process
        
        # Example 5: Send member event
        logger.info("Sending member event to webhook")
        log_member_event_to_webhook(
            "join",
            123456789012345678,  # Example member ID
            "ExampleUser#1234",  # Example username
            guild_id=987654321098765432,  # Example guild ID
            guild_name="Example Server",  # Example guild name
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        await asyncio.sleep(1)  # Wait for webhook to process
        
        logger.info("All example messages sent!")
        
        # Wait for all messages to be processed
        await asyncio.sleep(2)
        
    finally:
        # Clean up
        await webhook_manager.stop()
        logger.info("Webhook logging example completed")

if __name__ == "__main__":
    # Create directory if it doesn't exist
    os.makedirs("examples", exist_ok=True)
    
    # Run the example
    asyncio.run(main())