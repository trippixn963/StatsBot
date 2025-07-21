#!/usr/bin/env python3
"""
Bot diagnostic script to identify startup issues.
"""

import sys
import os
import traceback
from pathlib import Path

def check_python_version():
    """Check Python version compatibility."""
    print(f"Python version: {sys.version}")
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required")
        return False
    print("✅ Python version OK")
    return True

def check_dependencies():
    """Check if required dependencies are installed."""
    required_packages = [
        'discord.py',
        'python-dotenv',
        'aiohttp'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('.py', '').replace('-', '_'))
            print(f"✅ {package} installed")
        except ImportError:
            print(f"❌ {package} missing")
            missing.append(package)
    
    return len(missing) == 0

def check_config_files():
    """Check if configuration files exist."""
    config_files = [
        'config/.env',
        'main.py'
    ]
    
    all_exist = True
    for file_path in config_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} missing")
            all_exist = False
    
    return all_exist

def check_env_variables():
    """Check if required environment variables are set."""
    from dotenv import load_dotenv
    load_dotenv("config/.env")
    
    required_vars = [
        'BOT_TOKEN',
        'MEMBER_COUNT_CHANNEL_ID',
        'ONLINE_COUNT_CHANNEL_ID',
        'BAN_COUNT_CHANNEL_ID',
        'HEARTBEAT_CHANNEL_ID',
        'STATS_CHANNEL_ID'
    ]
    
    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var} set")
        else:
            print(f"❌ {var} missing")
            missing.append(var)
    
    return len(missing) == 0

def test_imports():
    """Test importing the main bot modules."""
    try:
        print("Testing imports...")
        
        # Test core imports
        from src.core.bot import OptimizedStatsBot
        print("✅ OptimizedStatsBot import OK")
        
        from src.core.config import load_config
        print("✅ load_config import OK")
        
        # Test service imports
        from src.services.stats.service import OptimizedStatsService
        print("✅ OptimizedStatsService import OK")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {str(e)}")
        print(f"Full traceback:\n{traceback.format_exc()}")
        return False

def test_config_loading():
    """Test loading configuration."""
    try:
        from src.core.config import load_config
        config = load_config()
        print("✅ Configuration loaded successfully")
        return True
    except Exception as e:
        print(f"❌ Configuration error: {str(e)}")
        print(f"Full traceback:\n{traceback.format_exc()}")
        return False

def main():
    """Run all diagnostic checks."""
    print("🔍 StatsBot Diagnostic Tool")
    print("=" * 40)
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Config Files", check_config_files),
        ("Environment Variables", check_env_variables),
        ("Module Imports", test_imports),
        ("Configuration Loading", test_config_loading)
    ]
    
    all_passed = True
    for check_name, check_func in checks:
        print(f"\n🔍 Checking {check_name}...")
        try:
            if not check_func():
                all_passed = False
        except Exception as e:
            print(f"❌ {check_name} failed with error: {str(e)}")
            print(f"Traceback:\n{traceback.format_exc()}")
            all_passed = False
    
    print("\n" + "=" * 40)
    if all_passed:
        print("✅ All checks passed! Bot should start normally.")
    else:
        print("❌ Some checks failed. Fix the issues above before starting the bot.")
    
    return all_passed

if __name__ == "__main__":
    main()