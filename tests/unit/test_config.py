#!/usr/bin/env python3
"""
Test script for the centralized configuration management system.

This script tests the functionality of the ConfigManager class and BotConfig
dataclass to ensure they work correctly with environment variables and
provide proper validation and error messages.
"""

import os
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.core.config import ConfigManager
from src.core.exceptions import ConfigurationError


def test_config_loading():
    """Test basic configuration loading."""
    print("Testing basic configuration loading...")
    
    try:
        config_manager = ConfigManager()
        config = config_manager.load_config()
        print("✅ Configuration loaded successfully")
        print(f"Environment: {config.environment}")
        print(f"Debug mode: {config.debug_mode}")
        print(f"Log level: {config.log_level}")
    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}")
        print(e.get_troubleshooting_message())
        return False
        
    return True


def test_environment_specific_defaults():
    """Test environment-specific defaults."""
    print("\nTesting environment-specific defaults...")
    
    # Save original environment
    original_env = os.environ.get('ENVIRONMENT')
    
    try:
        # Test development environment
        os.environ['ENVIRONMENT'] = 'development'
        config_manager = ConfigManager()
        config = config_manager.load_config()
        print(f"✅ Development environment loaded: debug_mode={config.debug_mode}, log_level={config.log_level}")
        
        # Test production environment
        os.environ['ENVIRONMENT'] = 'production'
        config_manager = ConfigManager()
        config = config_manager.load_config()
        print(f"✅ Production environment loaded: debug_mode={config.debug_mode}, log_level={config.log_level}")
        
    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}")
        return False
    finally:
        # Restore original environment
        if original_env:
            os.environ['ENVIRONMENT'] = original_env
        else:
            os.environ.pop('ENVIRONMENT', None)
            
    return True


def test_validation():
    """Test configuration validation."""
    print("\nTesting configuration validation...")
    
    # Save original values
    original_update_interval = os.environ.get('UPDATE_INTERVAL')
    
    try:
        # Test invalid update interval
        os.environ['UPDATE_INTERVAL'] = '10'  # Too low
        config_manager = ConfigManager()
        
        try:
            config = config_manager.load_config()
            print("❌ Validation failed: should have rejected update_interval=10")
            return False
        except ConfigurationError as e:
            print(f"✅ Correctly rejected invalid configuration: {e}")
            
    finally:
        # Restore original values
        if original_update_interval:
            os.environ['UPDATE_INTERVAL'] = original_update_interval
        else:
            os.environ.pop('UPDATE_INTERVAL', None)
            
    return True


def test_troubleshooting_info():
    """Test troubleshooting information."""
    print("\nTesting troubleshooting information...")
    
    config_manager = ConfigManager()
    
    try:
        config = config_manager.load_config()
        info = config_manager.get_troubleshooting_info()
        
        print("✅ Troubleshooting info generated:")
        print(f"  Required variables: {len(info['required_variables'])}")
        print(f"  Optional variables: {len(info['optional_variables'])}")
        print(f"  Missing required: {info['missing_required']}")
        print(f"  Config loaded: {info['config_loaded']}")
        print(f"  Environment: {info['environment']}")
        
    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}")
        return False
            
    return True


def main():
    """Run all tests."""
    print("Testing centralized configuration management system...\n")
    
    tests = [
        test_config_loading,
        test_environment_specific_defaults,
        test_validation,
        test_troubleshooting_info
    ]
    
    success_count = 0
    
    for test_func in tests:
        if test_func():
            success_count += 1
            
    print(f"\nTests completed: {success_count}/{len(tests)} successful")
    
    # Create example .env file
    print("\nCreating example .env file...")
    ConfigManager.create_example_env_file()
    print("✅ Example .env file created at config/.env.example")
    
    return 0 if success_count == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())