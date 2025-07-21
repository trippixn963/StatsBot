"""
Test script to verify project integrity.

This script checks that all the necessary modules and functions are properly defined
and can be imported without errors.
"""

import sys
import os
import asyncio
import logging

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

async def test_imports():
    """Test importing key modules."""
    logger.info("Testing imports...")
    
    # Import core modules
    logger.info("Importing core modules...")
    from src.core.bot import OptimizedStatsBot
    from src.core.config import load_config
    from src.core.exceptions import StatsBotError
    logger.info("✓ Successfully imported core modules")
    
    # Import service modules
    logger.info("Importing service modules...")
    from src.services.stats.service import OptimizedStatsService
    from src.services.monitoring.service import MonitoringService
    from src.services.presence.service import RichPresenceService
    logger.info("✓ Successfully imported service modules")
    
    # Import utility modules
    logger.info("Importing utility modules...")
    from src.utils.tree_log import log_perfect_tree_section, log_error_with_traceback
    from src.utils.performance import timing, performance_context, memory_monitor
    from src.utils.cache.cache_manager import CacheManager
    from src.utils.async_utils.task_manager import TaskManager
    from src.utils.async_utils.event_queue import EventQueue, EventBatcher
    logger.info("✓ Successfully imported utility modules")
    
    # Import webhook logging modules
    logger.info("Importing webhook logging modules...")
    from src.utils.webhook_logging import setup_webhook_logging, get_webhook_manager
    from src.utils.webhook_logging.config import WebhookConfig, LogLevel
    from src.utils.webhook_logging.webhook_manager import WebhookManager
    from src.utils.webhook_logging.message_formatter import MessageFormatter
    from src.utils.webhook_logging.integration import integrate_with_tree_log
    logger.info("✓ Successfully imported webhook logging modules")
    
    logger.info("All imports successful!")

async def test_config_loading():
    """Test loading configuration."""
    logger.info("Testing configuration loading...")
    
    from src.core.config import load_config
    try:
        config = load_config()
        logger.info(f"✓ Successfully loaded configuration with {len(vars(config))} settings")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return False
    
    return True

async def test_webhook_config():
    """Test webhook configuration."""
    logger.info("Testing webhook configuration...")
    
    from src.utils.webhook_logging.config import load_webhook_config, _is_valid_webhook_url
    
    # Test URL validation
    valid_url = "https://discord.com/api/webhooks/123456789/abcdefg"
    invalid_url = "https://example.com/not-a-webhook"
    
    assert _is_valid_webhook_url(valid_url), f"URL should be valid: {valid_url}"
    assert not _is_valid_webhook_url(invalid_url), f"URL should be invalid: {invalid_url}"
    
    # Test config loading
    try:
        config = load_webhook_config()
        logger.info(f"✓ Successfully loaded webhook configuration")
    except Exception as e:
        logger.error(f"Failed to load webhook configuration: {e}")
        return False
    
    return True

async def main():
    """Run all tests."""
    try:
        # Test imports
        await test_imports()
        
        # Test configuration loading
        await test_config_loading()
        
        # Test webhook configuration
        await test_webhook_config()
        
        logger.info("All tests passed!")
        return True
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)