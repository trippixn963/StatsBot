"""
Core module for StatsBot optimization.

This module contains the core infrastructure components including:
- Bot class with improved lifecycle management
- Configuration management system
- Custom exception classes for better error categorization
"""

from .bot import OptimizedStatsBot
from .config import BotConfig, ConfigManager, get_config, load_config
from .exceptions import (
    StatsBotError,
    ConfigurationError,
    DiscordAPIError,
    DataPersistenceError,
    ResourceError,
    ValidationError,
    CacheError,
    CircuitBreakerError,
    AsyncOperationError,
    RateLimitError,
    ServiceError,
    NetworkError,
    LifecycleError
)

__all__ = [
    # Bot and configuration
    'OptimizedStatsBot',
    'BotConfig',
    'ConfigManager',
    'get_config',
    'load_config',
    
    # Exception classes
    'StatsBotError',
    'ConfigurationError',
    'DiscordAPIError',
    'DataPersistenceError',
    'ResourceError',
    'ValidationError',
    'CacheError',
    'CircuitBreakerError',
    'AsyncOperationError',
    'RateLimitError',
    'ServiceError',
    'NetworkError',
    'LifecycleError'
]