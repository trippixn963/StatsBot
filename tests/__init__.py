"""
StatsBot Testing Package.

This package provides comprehensive testing infrastructure including:
- Unit tests with Discord API mocking
- Integration tests for service interactions
- Performance tests for memory and response time validation
- Test fixtures and utilities for consistent testing

Test Organization:
    unit/: Unit tests for individual components
    integration/: Integration tests for service interactions
    performance/: Performance and load testing
    fixtures/: Test data and mock configurations
    utils/: Testing utilities and helpers
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to Python path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Disable logging during tests unless explicitly enabled
if not sys.argv[0].endswith('pytest'):
    logging.disable(logging.CRITICAL)

__version__ = "1.0.0"
__all__ = []