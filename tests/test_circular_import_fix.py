"""
Test script to verify that circular import issues are fixed.
"""

import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_imports():
    """Test importing modules that previously had circular dependencies."""
    print("Testing imports...")
    
    # Import performance module
    print("Importing performance module...")
    from src.utils.performance import timing, performance_context
    print("✓ Successfully imported performance module")
    
    # Import cache_manager
    print("Importing cache_manager...")
    from src.utils.cache.cache_manager import CacheManager
    print("✓ Successfully imported CacheManager")
    
    # Import core exceptions
    print("Importing core exceptions...")
    from src.core.exceptions import CacheError
    print("✓ Successfully imported CacheError")
    
    # Import stats service
    print("Importing stats service...")
    from src.services.stats.service import OptimizedStatsService
    print("✓ Successfully imported OptimizedStatsService")
    
    # Import presence service
    print("Importing presence service...")
    from src.services.presence.service import RichPresenceService
    print("✓ Successfully imported RichPresenceService")
    
    print("All imports successful!")

if __name__ == "__main__":
    test_imports()