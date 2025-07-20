"""
File I/O utilities for optimized data persistence.

This package provides utilities for efficient file operations including:
- Atomic writes with backup mechanisms
- Streaming JSON serialization and deserialization
- Data validation and corruption detection
"""

from src.utils.file_io.atomic_writer import AtomicWriter
from src.utils.file_io.json_utils import (
    stream_json_to_file,
    stream_json_from_file,
    validate_json_file
)
from src.utils.file_io.data_validator import DataValidator