"""
Centralized configuration management system.

This module provides type-safe configuration loading and validation
with clear error messages and environment-specific defaults.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from dotenv import load_dotenv

from ..types.models import BotConfig
from .exceptions import ConfigurationError


class ConfigManager:
    """
    Centralized configuration manager with validation and type safety.
    
    This class handles loading configuration from environment variables,
    validating required values, and providing clear error messages for
    configuration issues. It supports environment-specific defaults and
    comprehensive validation at startup.
    """
    
    # Required environment variables
    REQUIRED_VARS = [
        'BOT_TOKEN',
        'MEMBER_COUNT_CHANNEL_ID',
        'ONLINE_COUNT_CHANNEL_ID',
        'BAN_COUNT_CHANNEL_ID',
        'HEARTBEAT_CHANNEL_ID',
        'STATS_CHANNEL_ID'
    ]
    
    # Optional environment variables with their default values
    OPTIONAL_VARS = {
        'GUILD_ID': None,
        'UPDATE_INTERVAL': 300,
        'MAX_BACKOFF': 3600,
        'LOG_LEVEL': 'INFO',
        'CACHE_TTL': 300,
        'MAX_RETRY_ATTEMPTS': 3,
        'HEARTBEAT_INTERVAL': 3600,
        'PRESENCE_UPDATE_INTERVAL': 300,
        'MAX_LOG_ENTRIES': 1000,
        'MAX_CACHE_SIZE': 10000,
        'MEMORY_WARNING_THRESHOLD': 80.0,
        'MEMORY_CRITICAL_THRESHOLD': 95.0,
        'ENVIRONMENT': 'development',
        'DEBUG_MODE': 'false'
    }
    
    # Environment variable types for validation
    VAR_TYPES = {
        'BOT_TOKEN': str,
        'MEMBER_COUNT_CHANNEL_ID': int,
        'ONLINE_COUNT_CHANNEL_ID': int,
        'BAN_COUNT_CHANNEL_ID': int,
        'HEARTBEAT_CHANNEL_ID': int,
        'STATS_CHANNEL_ID': int,
        'GUILD_ID': int,
        'UPDATE_INTERVAL': int,
        'MAX_BACKOFF': int,
        'LOG_LEVEL': str,
        'CACHE_TTL': int,
        'MAX_RETRY_ATTEMPTS': int,
        'HEARTBEAT_INTERVAL': int,
        'PRESENCE_UPDATE_INTERVAL': int,
        'MAX_LOG_ENTRIES': int,
        'MAX_CACHE_SIZE': int,
        'MEMORY_WARNING_THRESHOLD': float,
        'MEMORY_CRITICAL_THRESHOLD': float,
        'ENVIRONMENT': str,
        'DEBUG_MODE': bool
    }
    
    def __init__(self, env_file_path: Optional[str] = None):
        """
        Initialize the configuration manager.
        
        Args:
            env_file_path: Optional path to .env file. If not provided,
                          will look for config/.env relative to project root.
        """
        self._config: Optional[BotConfig] = None
        self._env_file_path = env_file_path
        self._load_environment(env_file_path)
    
    def _load_environment(self, env_file_path: Optional[str] = None) -> None:
        """
        Load environment variables from .env file.
        
        Args:
            env_file_path: Optional path to .env file
        """
        if env_file_path:
            env_path = Path(env_file_path)
        else:
            # Default to config/.env relative to project root
            env_path = Path(__file__).parent.parent.parent / 'config' / '.env'
        
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
        else:
            print(f"Warning: Environment file not found at {env_path}")
    
    def load_config(self) -> BotConfig:
        """
        Load and validate configuration from environment variables.
        
        This method performs comprehensive validation of all configuration values,
        applies environment-specific defaults, and provides clear error messages
        for any configuration issues.
        
        Returns:
            BotConfig: Validated configuration object
            
        Raises:
            ConfigurationError: If required variables are missing or invalid
        """
        if self._config is not None:
            return self._config
        
        # Check for missing required variables
        missing_vars = []
        for var in self.REQUIRED_VARS:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ConfigurationError(
                f"Missing required environment variables: {', '.join(missing_vars)}. "
                f"Please check your config/.env file and ensure all required variables are set.",
                missing_keys=missing_vars
            )
        
        # Load and validate configuration values
        try:
            # Extract basic configuration values from environment
            config_data = self._extract_config_values()
            
            # Create initial config object
            self._config = BotConfig(**config_data)
            
            # Apply environment-specific defaults
            self._apply_environment_specific_defaults()
            
            # Validate the final configuration
            self._config.validate()
            
            return self._config
            
        except ValueError as e:
            raise ConfigurationError(f"Invalid configuration: {str(e)}")
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {str(e)}")
    
    def _extract_config_values(self) -> Dict[str, Any]:
        """
        Extract and convert configuration values from environment variables.
        
        This method handles type conversion and validation for all environment
        variables, providing clear error messages for invalid values.
        
        Returns:
            Dict[str, Any]: Dictionary of configuration values
            
        Raises:
            ConfigurationError: If any values are invalid
        """
        config_data = {}
        invalid_values = {}
        
        # Process required string values
        config_data['bot_token'] = os.getenv('BOT_TOKEN')
        
        # Process required integer values
        int_fields = [
            ('MEMBER_COUNT_CHANNEL_ID', 'member_count_channel_id'),
            ('ONLINE_COUNT_CHANNEL_ID', 'online_count_channel_id'),
            ('BAN_COUNT_CHANNEL_ID', 'ban_count_channel_id'),
            ('HEARTBEAT_CHANNEL_ID', 'heartbeat_channel_id'),
            ('STATS_CHANNEL_ID', 'stats_channel_id')
        ]
        
        for env_var, field_name in int_fields:
            try:
                config_data[field_name] = int(os.getenv(env_var))
            except (ValueError, TypeError) as e:
                invalid_values[env_var] = os.getenv(env_var)
        
        # Process optional values with defaults
        for env_var, default_value in self.OPTIONAL_VARS.items():
            field_name = env_var.lower()
            env_value = os.getenv(env_var)
            
            if env_value is None:
                config_data[field_name] = default_value
            else:
                try:
                    # Convert value based on expected type
                    var_type = self.VAR_TYPES.get(env_var)
                    if var_type == int:
                        config_data[field_name] = int(env_value)
                    elif var_type == float:
                        config_data[field_name] = float(env_value)
                    elif var_type == bool:
                        config_data[field_name] = env_value.lower() in ('true', 'yes', '1', 'y')
                    else:
                        config_data[field_name] = env_value
                except (ValueError, TypeError):
                    invalid_values[env_var] = env_value
        
        if invalid_values:
            raise ConfigurationError(
                f"Invalid values for environment variables: {invalid_values}. "
                f"Please check the data types and formats.",
                invalid_values=invalid_values
            )
        
        return config_data
    
    def _apply_environment_specific_defaults(self) -> None:
        """
        Apply environment-specific default values to the configuration.
        
        This method adjusts configuration values based on the current environment
        (development, testing, production) to provide appropriate defaults.
        """
        if not self._config:
            return
            
        # Get environment-specific defaults
        env_defaults = self._config.get_environment_specific_defaults()
        
        # Apply defaults only if not explicitly set in environment variables
        for key, value in env_defaults.items():
            env_var = key.upper()
            if os.getenv(env_var) is None:
                setattr(self._config, key, value)
    
    def get_config(self) -> BotConfig:
        """
        Get the current configuration.
        
        Returns:
            BotConfig: Current configuration object
            
        Raises:
            ConfigurationError: If configuration hasn't been loaded yet
        """
        if self._config is None:
            raise ConfigurationError("Configuration not loaded. Call load_config() first.")
        
        return self._config
    
    def validate_config(self, config: BotConfig) -> None:
        """
        Validate a configuration object.
        
        Args:
            config: Configuration object to validate
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        try:
            config.validate()
        except ValueError as e:
            raise ConfigurationError(f"Configuration validation failed: {str(e)}")
    
    def reload_config(self) -> BotConfig:
        """
        Reload configuration from environment variables.
        
        This is useful when environment variables have changed and you
        want to refresh the configuration without restarting the application.
        
        Returns:
            BotConfig: Updated configuration object
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Reload environment variables
        self._load_environment(self._env_file_path)
        
        # Clear current config
        self._config = None
        
        # Load and validate new config
        return self.load_config()
    
    def get_troubleshooting_info(self) -> Dict[str, Any]:
        """
        Get troubleshooting information for configuration issues.
        
        This method provides detailed information about the current configuration
        state, including environment variables, missing values, and validation status.
        
        Returns:
            Dict containing information about current environment variables
            and configuration status.
        """
        info = {
            'required_variables': self.REQUIRED_VARS,
            'optional_variables': list(self.OPTIONAL_VARS.keys()),
            'current_env_vars': {},
            'missing_required': [],
            'config_loaded': self._config is not None,
            'environment': os.getenv('ENVIRONMENT', 'development'),
            'validation_errors': []
        }
        
        # Check current environment variables
        for var in self.REQUIRED_VARS:
            value = os.getenv(var)
            info['current_env_vars'][var] = '***SET***' if value else 'NOT SET'
            if not value:
                info['missing_required'].append(var)
        
        for var in self.OPTIONAL_VARS.keys():
            value = os.getenv(var)
            info['current_env_vars'][var] = value if value else f'DEFAULT ({self.OPTIONAL_VARS[var]})'
        
        # Check for validation errors if config is loaded
        if self._config:
            try:
                self._config.validate()
            except ValueError as e:
                info['validation_errors'].append(str(e))
        
        return info
    
    def get_config_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current configuration.
        
        This method provides a sanitized view of the current configuration,
        hiding sensitive values like tokens.
        
        Returns:
            Dict containing a summary of the current configuration
        """
        if not self._config:
            return {'status': 'not_loaded'}
            
        config_dict = self._config.to_dict()
        
        # Sanitize sensitive values
        if 'bot_token' in config_dict:
            config_dict['bot_token'] = '***REDACTED***'
            
        return {
            'status': 'loaded',
            'environment': config_dict.get('environment', 'development'),
            'debug_mode': config_dict.get('debug_mode', False),
            'values': config_dict
        }
    
    @staticmethod
    def create_example_env_file(file_path: str = "config/.env.example") -> None:
        """
        Create an example .env file with all required and optional variables.
        
        This method generates a well-documented example configuration file
        that users can copy and customize for their own environment.
        
        Args:
            file_path: Path where to create the example file
        """
        env_path = Path(file_path)
        env_path.parent.mkdir(parents=True, exist_ok=True)
        
        content = [
            "# StatsBot Configuration",
            "# Copy this file to .env and fill in your values",
            "",
            "# Required Discord Configuration",
            "BOT_TOKEN=your_bot_token_here",
            "MEMBER_COUNT_CHANNEL_ID=123456789012345678",
            "ONLINE_COUNT_CHANNEL_ID=123456789012345678",
            "BAN_COUNT_CHANNEL_ID=123456789012345678",
            "HEARTBEAT_CHANNEL_ID=123456789012345678",
            "STATS_CHANNEL_ID=123456789012345678",
            "",
            "# Optional Discord Configuration",
            "# GUILD_ID=123456789012345678",
            "",
            "# Environment Configuration",
            "# ENVIRONMENT=development  # Options: development, testing, production",
            "# DEBUG_MODE=false",
            "",
            "# Update Intervals (in seconds)",
            "# UPDATE_INTERVAL=300",
            "# HEARTBEAT_INTERVAL=3600",
            "# PRESENCE_UPDATE_INTERVAL=300",
            "",
            "# Error Handling Configuration",
            "# MAX_BACKOFF=3600",
            "# MAX_RETRY_ATTEMPTS=3",
            "",
            "# Caching Configuration",
            "# CACHE_TTL=300",
            "# MAX_CACHE_SIZE=10000",
            "",
            "# Logging Configuration",
            "# LOG_LEVEL=INFO  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL",
            "# MAX_LOG_ENTRIES=1000",
            "",
            "# Resource Management",
            "# MEMORY_WARNING_THRESHOLD=80.0",
            "# MEMORY_CRITICAL_THRESHOLD=95.0"
        ]
        
        with open(env_path, 'w') as f:
            f.write('\n'.join(content))
            
    @staticmethod
    def get_configuration_help() -> str:
        """
        Get help text for configuration troubleshooting.
        
        Returns:
            str: Formatted help text with configuration guidance
        """
        return """
        StatsBot Configuration Guide
        ===========================
        
        Required Environment Variables:
        - BOT_TOKEN: Your Discord bot token
        - MEMBER_COUNT_CHANNEL_ID: Channel ID for member count updates
        - ONLINE_COUNT_CHANNEL_ID: Channel ID for online count updates
        - BAN_COUNT_CHANNEL_ID: Channel ID for ban count updates
        - HEARTBEAT_CHANNEL_ID: Channel ID for heartbeat messages
        - STATS_CHANNEL_ID: Channel ID for statistics reports
        
        Common Configuration Issues:
        
        1. Missing environment variables:
           - Ensure you have a config/.env file with all required variables
           - Check for typos in variable names
        
        2. Invalid channel IDs:
           - Channel IDs must be valid integers
           - Ensure the bot has access to all specified channels
        
        3. Invalid token:
           - Verify your bot token is correct and the bot is properly registered
        
        4. Permission issues:
           - Ensure the bot has proper permissions in all channels
           - Required permissions: VIEW_CHANNEL, SEND_MESSAGES, EMBED_LINKS
        
        For more help, run the troubleshooting command or check the documentation.
        """


# Global configuration manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def load_config() -> BotConfig:
    """Load configuration using the global configuration manager."""
    return get_config_manager().load_config()


def get_config() -> BotConfig:
    """Get the current configuration using the global configuration manager."""
    return get_config_manager().get_config()