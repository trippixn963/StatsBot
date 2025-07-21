"""
Webhook configuration management.

This module handles loading, validating, and managing webhook configurations
from environment variables or explicit settings.
"""

import os
import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("webhook_logging")

class LogLevel(Enum):
    """Log levels for webhook routing."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    
    @classmethod
    def from_string(cls, level_str: str) -> "LogLevel":
        """Convert string to LogLevel enum."""
        try:
            return cls(level_str.lower())
        except ValueError:
            # Default to INFO if invalid
            logger.warning(f"Invalid log level: {level_str}, defaulting to INFO")
            return cls.INFO

@dataclass
class WebhookConfig:
    """Configuration for webhook logging system."""
    
    # Primary webhook URLs
    error_webhook_url: Optional[str] = None
    info_webhook_url: Optional[str] = None
    performance_webhook_url: Optional[str] = None
    member_events_webhook_url: Optional[str] = None
    
    # Rate limiting settings
    max_requests_per_minute: int = 30
    batch_size: int = 5
    batch_timeout_seconds: float = 10.0
    
    # Message formatting
    use_embeds: bool = True
    include_timestamps: bool = True
    include_bot_info: bool = True
    
    # Privacy settings
    mask_user_ids: bool = False
    include_stack_traces: bool = True
    max_message_length: int = 2000
    
    # Webhook routing configuration
    webhook_routing: Dict[LogLevel, List[str]] = field(default_factory=lambda: {
        LogLevel.CRITICAL: ["error_webhook_url", "info_webhook_url"],
        LogLevel.ERROR: ["error_webhook_url"],
        LogLevel.WARNING: ["error_webhook_url"],
        LogLevel.INFO: ["info_webhook_url"],
        LogLevel.DEBUG: []  # Only if explicitly enabled
    })
    
    def validate(self) -> List[str]:
        """
        Validate the webhook configuration.
        
        Returns:
            List[str]: List of validation errors, empty if valid.
        """
        errors = []
        
        # Check if at least one webhook URL is provided
        if not any([
            self.error_webhook_url,
            self.info_webhook_url,
            self.performance_webhook_url,
            self.member_events_webhook_url
        ]):
            errors.append("No webhook URLs provided. At least one webhook URL is required.")
        
        # Validate webhook URLs
        for name, url in [
            ("error_webhook_url", self.error_webhook_url),
            ("info_webhook_url", self.info_webhook_url),
            ("performance_webhook_url", self.performance_webhook_url),
            ("member_events_webhook_url", self.member_events_webhook_url)
        ]:
            if url and not _is_valid_webhook_url(url):
                errors.append(f"Invalid webhook URL for {name}: {url}")
        
        # Validate rate limiting settings
        if self.max_requests_per_minute <= 0:
            errors.append(f"Invalid max_requests_per_minute: {self.max_requests_per_minute}. Must be > 0.")
        
        if self.batch_size <= 0:
            errors.append(f"Invalid batch_size: {self.batch_size}. Must be > 0.")
        
        if self.batch_timeout_seconds <= 0:
            errors.append(f"Invalid batch_timeout_seconds: {self.batch_timeout_seconds}. Must be > 0.")
        
        # Validate message length
        if self.max_message_length <= 0 or self.max_message_length > 2000:
            errors.append(f"Invalid max_message_length: {self.max_message_length}. Must be > 0 and <= 2000.")
        
        return errors
    
    def get_webhooks_for_level(self, level: LogLevel) -> List[str]:
        """
        Get webhook URLs for a specific log level.
        
        Args:
            level: The log level to get webhooks for.
            
        Returns:
            List of webhook URLs for the specified log level.
        """
        webhook_names = self.webhook_routing.get(level, [])
        webhooks = []
        
        for name in webhook_names:
            url = getattr(self, name, None)
            if url:
                webhooks.append(url)
        
        return webhooks

def _is_valid_webhook_url(url: str) -> bool:
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

def _parse_bool(value: str) -> bool:
    """
    Parse a string to boolean.
    
    Args:
        value: String value to parse.
        
    Returns:
        bool: Parsed boolean value.
    """
    return value.lower() in ('true', 'yes', '1', 'y', 't')

def load_webhook_config() -> WebhookConfig:
    """
    Load webhook configuration from environment variables.
    
    Returns:
        WebhookConfig: Loaded configuration.
    """
    config = WebhookConfig(
        # Primary webhook URLs
        error_webhook_url=os.getenv('WEBHOOK_ERROR_URL'),
        info_webhook_url=os.getenv('WEBHOOK_INFO_URL'),
        performance_webhook_url=os.getenv('WEBHOOK_PERFORMANCE_URL'),
        member_events_webhook_url=os.getenv('WEBHOOK_MEMBER_EVENTS_URL'),
        
        # Rate limiting settings
        max_requests_per_minute=int(os.getenv('WEBHOOK_MAX_REQUESTS_PER_MINUTE', '30')),
        batch_size=int(os.getenv('WEBHOOK_BATCH_SIZE', '5')),
        batch_timeout_seconds=float(os.getenv('WEBHOOK_BATCH_TIMEOUT', '10.0')),
        
        # Message formatting
        use_embeds=_parse_bool(os.getenv('WEBHOOK_USE_EMBEDS', 'true')),
        include_timestamps=_parse_bool(os.getenv('WEBHOOK_INCLUDE_TIMESTAMPS', 'true')),
        include_bot_info=_parse_bool(os.getenv('WEBHOOK_INCLUDE_BOT_INFO', 'true')),
        
        # Privacy settings
        mask_user_ids=_parse_bool(os.getenv('WEBHOOK_MASK_USER_IDS', 'false')),
        include_stack_traces=_parse_bool(os.getenv('WEBHOOK_INCLUDE_STACK_TRACES', 'true')),
        max_message_length=int(os.getenv('WEBHOOK_MAX_MESSAGE_LENGTH', '2000')),
    )
    
    # Validate configuration
    errors = config.validate()
    if errors:
        for error in errors:
            logger.warning(f"Webhook configuration error: {error}")
        
        if not any([
            config.error_webhook_url,
            config.info_webhook_url,
            config.performance_webhook_url,
            config.member_events_webhook_url
        ]):
            logger.warning("Webhook logging disabled due to missing webhook URLs")
    
    return config