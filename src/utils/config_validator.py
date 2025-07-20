"""
Configuration Validation and Environment Management Module.

This module provides comprehensive validation for bot configuration including:
- Startup validation with descriptive error messages
- Environment-specific configuration support with clear documentation
- Configuration troubleshooting guidance and validation helpers
- Type safety and consistency checking
"""

# Standard library imports
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple, Type
from dataclasses import dataclass, field
from enum import Enum

# Third-party imports
from dotenv import load_dotenv

# Local imports
from .performance import timing, performance_context
from .tree_log import log_perfect_tree_section, log_error_with_traceback

class ConfigError(Exception):
    """Custom exception for configuration validation errors."""
    pass

class EnvironmentType(Enum):
    """Supported environment types."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"

@dataclass
class ValidationRule:
    """Configuration validation rule definition."""
    name: str
    description: str
    validator: callable
    error_message: str
    required: bool = True
    default_value: Optional[Any] = None

@dataclass
class ConfigField:
    """Configuration field definition with validation."""
    name: str
    description: str
    field_type: Type
    required: bool = True
    default_value: Optional[Any] = None
    validation_rules: List[ValidationRule] = field(default_factory=list)
    environment_specific: bool = False
    sensitive: bool = False

class ConfigValidator:
    """
    Comprehensive configuration validator.
    
    This class validates bot configuration with detailed error reporting,
    environment-specific support, and troubleshooting guidance.
    
    Attributes:
        config_fields (Dict[str, ConfigField]): Defined configuration fields
        environment (EnvironmentType): Current environment type
        config_path (Path): Path to configuration file
        validation_errors (List[str]): Collected validation errors
    """
    
    def __init__(self, 
                 config_path: Optional[Union[str, Path]] = None,
                 environment: Optional[EnvironmentType] = None):
        """
        Initialize configuration validator.
        
        Args:
            config_path: Path to configuration file (default: config/.env)
            environment: Environment type (auto-detected if None)
        """
        self.config_path = Path(config_path or "config/.env")
        self.environment = environment or self._detect_environment()
        self.validation_errors: List[str] = []
        self.config_values: Dict[str, Any] = {}
        
        # Define configuration fields
        self.config_fields = self._define_config_fields()
        
        log_perfect_tree_section(
            "Configuration Validator",
            [
                ("config_path", str(self.config_path)),
                ("environment", self.environment.value),
                ("fields_count", len(self.config_fields))
            ],
            emoji="⚙️"
        )
    
    def _detect_environment(self) -> EnvironmentType:
        """Detect current environment type."""
        env_var = os.getenv('ENVIRONMENT', '').lower()
        
        if env_var in ['prod', 'production']:
            return EnvironmentType.PRODUCTION
        elif env_var in ['test', 'testing']:
            return EnvironmentType.TESTING
        else:
            return EnvironmentType.DEVELOPMENT
    
    def _define_config_fields(self) -> Dict[str, ConfigField]:
        """Define all configuration fields with validation rules."""
        fields = {}
        
        # Bot token field
        fields['BOT_TOKEN'] = ConfigField(
            name='BOT_TOKEN',
            description='Discord bot authentication token',
            field_type=str,
            required=True,
            sensitive=True,
            validation_rules=[
                ValidationRule(
                    name='token_format',
                    description='Valid Discord bot token format',
                    validator=self._validate_discord_token,
                    error_message='Invalid Discord bot token format. Expected format: MTxxxxxxxxx.xxxxxx.xxxxxxxxxxxxxxxxxxxxxxx'
                ),
                ValidationRule(
                    name='token_length',
                    description='Token length validation',
                    validator=lambda x: len(x) > 50,
                    error_message='Discord bot token appears too short'
                )
            ]
        )
        
        # Channel ID fields
        channel_fields = [
            ('MEMBER_COUNT_CHANNEL_ID', 'Member count display channel'),
            ('ONLINE_COUNT_CHANNEL_ID', 'Online count display channel'),
            ('BAN_COUNT_CHANNEL_ID', 'Ban count display channel'),
            ('HEARTBEAT_CHANNEL_ID', 'Bot heartbeat monitoring channel'),
            ('STATS_CHANNEL_ID', 'Daily statistics channel')
        ]
        
        for field_name, description in channel_fields:
            fields[field_name] = ConfigField(
                name=field_name,
                description=description,
                field_type=int,
                required=True,
                validation_rules=[
                    ValidationRule(
                        name='channel_id_format',
                        description='Valid Discord channel ID',
                        validator=self._validate_discord_id,
                        error_message=f'Invalid {field_name}: Must be a valid Discord channel ID (17-19 digits)'
                    )
                ]
            )
        
        # Guild ID field
        fields['GUILD_ID'] = ConfigField(
            name='GUILD_ID',
            description='Discord server (guild) ID',
            field_type=int,
            required=True,
            validation_rules=[
                ValidationRule(
                    name='guild_id_format',
                    description='Valid Discord guild ID',
                    validator=self._validate_discord_id,
                    error_message='Invalid GUILD_ID: Must be a valid Discord guild ID (17-19 digits)'
                )
            ]
        )
        
        # Environment-specific fields
        if self.environment == EnvironmentType.DEVELOPMENT:
            fields['LOG_LEVEL'] = ConfigField(
                name='LOG_LEVEL',
                description='Logging level for development',
                field_type=str,
                required=False,
                default_value='DEBUG',
                environment_specific=True,
                validation_rules=[
                    ValidationRule(
                        name='log_level_valid',
                        description='Valid logging level',
                        validator=lambda x: x.upper() in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        error_message='LOG_LEVEL must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL'
                    )
                ]
            )
        
        return fields
    
    def _validate_discord_token(self, token: str) -> bool:
        """Validate Discord bot token format."""
        if not token:
            return False
        
        # Discord bot tokens have a specific format
        # MTxxxxxxxxx.xxxxxx.xxxxxxxxxxxxxxxxxxxxxxx
        pattern = r'^[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,39}$'
        return bool(re.match(pattern, token))
    
    def _validate_discord_id(self, id_value: Union[str, int]) -> bool:
        """Validate Discord ID format (snowflake)."""
        try:
            id_int = int(id_value)
            # Discord IDs are 17-19 digits long
            return 10**16 <= id_int <= 10**19
        except (ValueError, TypeError):
            return False
    
    @timing(category="config")
    def load_and_validate(self) -> Dict[str, Any]:
        """
        Load and validate configuration from file.
        
        Returns:
            Dictionary of validated configuration values
            
        Raises:
            ConfigError: If validation fails
        """
        with performance_context("config_validation"):
            # Load environment file
            self._load_env_file()
            
            # Validate all fields
            self._validate_all_fields()
            
            # Check for validation errors
            if self.validation_errors:
                self._raise_validation_error()
            
            # Log successful validation
            log_perfect_tree_section(
                "Configuration Validated",
                [
                    ("fields_validated", len(self.config_values)),
                    ("environment", self.environment.value),
                    ("errors", len(self.validation_errors))
                ],
                emoji="✅"
            )
            
            return self.config_values.copy()
    
    def _load_env_file(self):
        """Load environment variables from file."""
        if not self.config_path.exists():
            raise ConfigError(
                f"Configuration file not found: {self.config_path}\n"
                f"Expected location: {self.config_path.absolute()}\n"
                f"Please create the configuration file with required environment variables."
            )
        
        try:
            load_dotenv(dotenv_path=self.config_path)
        except Exception as e:
            raise ConfigError(
                f"Failed to load configuration file: {self.config_path}\n"
                f"Error: {str(e)}\n"
                f"Please check file format and permissions."
            )
    
    def _validate_all_fields(self):
        """Validate all defined configuration fields."""
        for field_name, field_config in self.config_fields.items():
            try:
                self._validate_field(field_name, field_config)
            except Exception as e:
                self.validation_errors.append(
                    f"Unexpected error validating {field_name}: {str(e)}"
                )
    
    def _validate_field(self, field_name: str, field_config: ConfigField):
        """
        Validate a single configuration field.
        
        Args:
            field_name: Name of the field to validate
            field_config: Configuration field definition
        """
        # Get raw value from environment
        raw_value = os.getenv(field_name)
        
        # Handle missing values
        if raw_value is None:
            if field_config.required:
                self.validation_errors.append(
                    f"Missing required configuration: {field_name}\n"
                    f"Description: {field_config.description}\n"
                    f"Please add {field_name}=<value> to your configuration file."
                )
                return
            else:
                # Use default value
                self.config_values[field_name] = field_config.default_value
                return
        
        # Convert to appropriate type
        try:
            if field_config.field_type == int:
                converted_value = int(raw_value)
            elif field_config.field_type == float:
                converted_value = float(raw_value)
            elif field_config.field_type == bool:
                converted_value = raw_value.lower() in ['true', '1', 'yes', 'on']
            else:
                converted_value = str(raw_value)
        except (ValueError, TypeError) as e:
            self.validation_errors.append(
                f"Invalid type for {field_name}: Expected {field_config.field_type.__name__}, got '{raw_value}'\n"
                f"Description: {field_config.description}"
            )
            return
        
        # Run validation rules
        for rule in field_config.validation_rules:
            try:
                if not rule.validator(converted_value):
                    self.validation_errors.append(
                        f"{field_name}: {rule.error_message}\n"
                        f"Current value: {'[HIDDEN]' if field_config.sensitive else converted_value}\n"
                        f"Rule: {rule.description}"
                    )
            except Exception as e:
                self.validation_errors.append(
                    f"Validation rule error for {field_name}: {str(e)}"
                )
        
        # Store validated value
        self.config_values[field_name] = converted_value
    
    def _raise_validation_error(self):
        """Raise comprehensive validation error with troubleshooting info."""
        error_sections = [
            "❌ Configuration Validation Failed",
            "=" * 50,
            "",
            f"Environment: {self.environment.value}",
            f"Config file: {self.config_path}",
            "",
            "Validation Errors:",
            "-" * 20
        ]
        
        for i, error in enumerate(self.validation_errors, 1):
            error_sections.append(f"{i}. {error}")
            error_sections.append("")
        
        # Add troubleshooting section
        error_sections.extend([
            "Troubleshooting Guide:",
            "-" * 20,
            "1. Check that your config/.env file exists and is readable",
            "2. Verify all required fields are present and correctly formatted",
            "3. Ensure Discord IDs are valid (copy from Discord with Developer Mode enabled)",
            "4. Verify bot token is correct and not expired",
            "5. Check file permissions and encoding (should be UTF-8)",
            "",
            "For help, visit: https://discord.py.readthedocs.io/"
        ])
        
        raise ConfigError("\n".join(error_sections))
    
    def validate_runtime_config(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate configuration at runtime.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        runtime_errors = []
        
        # Check for unknown configuration keys
        known_keys = set(self.config_fields.keys())
        config_keys = set(config.keys())
        unknown_keys = config_keys - known_keys
        
        if unknown_keys:
            runtime_errors.append(
                f"Unknown configuration keys: {', '.join(unknown_keys)}"
            )
        
        # Validate types and values
        for key, value in config.items():
            if key in self.config_fields:
                field_config = self.config_fields[key]
                
                # Type check
                if not isinstance(value, field_config.field_type):
                    runtime_errors.append(
                        f"{key}: Expected {field_config.field_type.__name__}, got {type(value).__name__}"
                    )
                
                # Validation rules
                for rule in field_config.validation_rules:
                    try:
                        if not rule.validator(value):
                            runtime_errors.append(f"{key}: {rule.error_message}")
                    except Exception as e:
                        runtime_errors.append(f"{key}: Validation error - {str(e)}")
        
        return runtime_errors
    
    def get_config_documentation(self) -> str:
        """
        Generate comprehensive configuration documentation.
        
        Returns:
            Formatted documentation string
        """
        doc_sections = [
            "📋 Configuration Documentation",
            "=" * 40,
            "",
            f"Environment: {self.environment.value}",
            f"Config file: {self.config_path}",
            "",
            "Required Configuration Fields:",
            "-" * 30
        ]
        
        # Required fields
        for field_name, field_config in self.config_fields.items():
            if field_config.required:
                doc_sections.append(f"• {field_name}")
                doc_sections.append(f"  Description: {field_config.description}")
                doc_sections.append(f"  Type: {field_config.field_type.__name__}")
                if field_config.validation_rules:
                    doc_sections.append("  Validation:")
                    for rule in field_config.validation_rules:
                        doc_sections.append(f"    - {rule.description}")
                doc_sections.append("")
        
        # Optional fields
        optional_fields = [f for f in self.config_fields.values() if not f.required]
        if optional_fields:
            doc_sections.extend([
                "Optional Configuration Fields:",
                "-" * 30
            ])
            
            for field_config in optional_fields:
                doc_sections.append(f"• {field_config.name}")
                doc_sections.append(f"  Description: {field_config.description}")
                doc_sections.append(f"  Type: {field_config.field_type.__name__}")
                doc_sections.append(f"  Default: {field_config.default_value}")
                doc_sections.append("")
        
        return "\n".join(doc_sections)

# Global validator instance
config_validator = ConfigValidator()

def validate_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to validate configuration.
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        Validated configuration dictionary
        
    Raises:
        ConfigError: If validation fails
    """
    if config_path:
        validator = ConfigValidator(config_path)
    else:
        validator = config_validator
    
    return validator.load_and_validate()

def get_config_help() -> str:
    """Get configuration help documentation."""
    return config_validator.get_config_documentation() 