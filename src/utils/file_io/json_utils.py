"""
Efficient JSON serialization and deserialization utilities.

This module provides utilities for efficient JSON operations including:
- Streaming JSON serialization for large datasets
- Streaming JSON deserialization for memory efficiency
- JSON validation and schema checking
"""

import json
import os
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Iterator, Union, List, Callable, TypeVar, Generic
import logging
import io

from src.core.exceptions import DataPersistenceError

# Try to import optional dependencies for better performance
try:
    import orjson  # Faster JSON serialization/deserialization
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

try:
    import ijson  # Streaming JSON parser
    HAS_IJSON = True
except ImportError:
    HAS_IJSON = False

# Type variable for generic functions
T = TypeVar('T')

# Set up logger
logger = logging.getLogger(__name__)


def calculate_json_hash(data: Dict[str, Any]) -> str:
    """
    Calculate a deterministic hash of JSON data.
    
    Args:
        data: Dictionary to hash
        
    Returns:
        String hash of the data
    """
    # Use a deterministic JSON serialization for consistent hashing
    if HAS_ORJSON:
        serialized = orjson.dumps(data, option=orjson.OPT_SORT_KEYS).decode('utf-8')
    else:
        serialized = json.dumps(data, sort_keys=True)
    
    return hashlib.md5(serialized.encode()).hexdigest()


def has_json_changed(data: Dict[str, Any], previous_hash: str) -> bool:
    """
    Check if JSON data has changed compared to a previous hash.
    
    Args:
        data: Current data
        previous_hash: Previous hash to compare against
        
    Returns:
        True if data has changed, False otherwise
    """
    current_hash = calculate_json_hash(data)
    return current_hash != previous_hash


async def stream_json_to_file(
    file_path: Path, 
    data: Dict[str, Any], 
    indent: Optional[int] = None,
    atomic: bool = True,
    create_backup: bool = True
) -> None:
    """
    Stream JSON data to a file with memory efficiency.
    
    This function writes JSON data to a file in a memory-efficient way,
    optionally using atomic operations and creating backups.
    
    Args:
        file_path: Path to the output file
        data: Dictionary to serialize to JSON
        indent: Number of spaces for indentation (None for compact JSON)
        atomic: Whether to use atomic write operations
        create_backup: Whether to create a backup of the original file
        
    Raises:
        DataPersistenceError: If the write operation fails
    """
    try:
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use faster orjson if available
        if HAS_ORJSON and not indent:
            json_bytes = orjson.dumps(
                data,
                option=orjson.OPT_INDENT_2 if indent else 0
            )
            
            if atomic:
                # Create temporary file for atomic write
                temp_file = file_path.with_suffix('.tmp')
                
                # Create backup if requested
                if create_backup and file_path.exists():
                    backup_file = file_path.with_suffix(f'.bak')
                    import shutil
                    shutil.copy2(file_path, backup_file)
                
                # Write to temporary file
                with open(temp_file, 'wb') as f:
                    f.write(json_bytes)
                
                # Atomic rename
                os.replace(temp_file, file_path)
            else:
                # Direct write
                with open(file_path, 'wb') as f:
                    f.write(json_bytes)
        else:
            # Standard JSON module with streaming for large objects
            if atomic:
                # Create temporary file for atomic write
                temp_file = file_path.with_suffix('.tmp')
                
                # Create backup if requested
                if create_backup and file_path.exists():
                    backup_file = file_path.with_suffix(f'.bak')
                    import shutil
                    shutil.copy2(file_path, backup_file)
                
                # Stream to temporary file
                with open(temp_file, 'w', encoding='utf-8') as f:
                    # For very large objects, stream the JSON output
                    f.write('{')
                    
                    # Stream each key-value pair
                    for i, (key, value) in enumerate(data.items()):
                        if i > 0:
                            f.write(',')
                        
                        # Write key
                        json_key = json.dumps(key)
                        f.write(f'\n{" " * (indent or 0)}{json_key}: ')
                        
                        # Write value
                        json_value = json.dumps(value, indent=indent)
                        f.write(json_value)
                    
                    f.write('\n}')
                
                # Atomic rename
                os.replace(temp_file, file_path)
            else:
                # Direct write with standard JSON
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=indent)
    
    except Exception as e:
        # Clean up temporary file if it exists
        temp_file = file_path.with_suffix('.tmp')
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        
        logger.error(
            f"Failed to write JSON to file: {file_path}",
            exc_info=True,
            extra={"error": str(e)}
        )
        
        raise DataPersistenceError(
            f"Failed to write JSON to file: {str(e)}",
            file_path=str(file_path),
            operation="write",
            original_error=e
        )


def stream_json_from_file(file_path: Path) -> Dict[str, Any]:
    """
    Stream JSON data from a file with memory efficiency.
    
    This function reads JSON data from a file in a memory-efficient way,
    using streaming parsers for large files when available.
    
    Args:
        file_path: Path to the input file
        
    Returns:
        Dictionary containing the parsed JSON data
        
    Raises:
        DataPersistenceError: If the read operation fails or JSON is invalid
    """
    if not file_path.exists():
        raise DataPersistenceError(
            f"File not found: {file_path}",
            file_path=str(file_path),
            operation="read"
        )
    
    try:
        # For small files, use direct loading (faster)
        if file_path.stat().st_size < 1024 * 1024:  # Less than 1MB
            if HAS_ORJSON:
                with open(file_path, 'rb') as f:
                    return orjson.loads(f.read())
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        
        # For larger files, use streaming approach if ijson is available
        if HAS_IJSON:
            result = {}
            with open(file_path, 'rb') as f:
                # Use ijson for true streaming
                for prefix, event, value in ijson.parse(f):
                    if prefix == '' and event == 'map_key':
                        current_key = value
                        result[current_key] = {}
                    elif '.' not in prefix and event == 'map_key':
                        current_subkey = value
                        if isinstance(result[prefix], dict):
                            result[prefix][current_subkey] = None
                    elif event == 'string' or event == 'number' or event == 'boolean' or event == 'null':
                        parts = prefix.split('.')
                        if len(parts) == 1:
                            result[parts[0]] = value
                        elif len(parts) == 2:
                            result[parts[0]][parts[1]] = value
            
            return result
        else:
            # Fallback to regular json for larger files
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    except json.JSONDecodeError as e:
        logger.error(
            f"JSON decode error when reading file: {file_path}",
            exc_info=True,
            extra={"error": str(e)}
        )
        
        raise DataPersistenceError(
            f"Invalid JSON in file: {str(e)}",
            file_path=str(file_path),
            operation="read",
            original_error=e
        )
    except Exception as e:
        logger.error(
            f"Failed to read JSON from file: {file_path}",
            exc_info=True,
            extra={"error": str(e)}
        )
        
        raise DataPersistenceError(
            f"Failed to read JSON from file: {str(e)}",
            file_path=str(file_path),
            operation="read",
            original_error=e
        )


def validate_json_file(
    file_path: Path,
    schema: Optional[Dict[str, Any]] = None,
    custom_validator: Optional[Callable[[Dict[str, Any]], List[str]]] = None
) -> Tuple[bool, List[str]]:
    """
    Validate a JSON file against a schema or custom validator.
    
    Args:
        file_path: Path to the JSON file
        schema: JSON schema to validate against (optional)
        custom_validator: Custom validation function (optional)
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    if not file_path.exists():
        return False, [f"File not found: {file_path}"]
    
    try:
        # Read the JSON file
        data = stream_json_from_file(file_path)
        
        errors = []
        
        # Validate against schema if provided
        if schema:
            try:
                import jsonschema
                try:
                    jsonschema.validate(instance=data, schema=schema)
                except jsonschema.exceptions.ValidationError as e:
                    errors.append(f"Schema validation error: {e}")
            except ImportError:
                errors.append("jsonschema package not available for schema validation")
        
        # Apply custom validator if provided
        if custom_validator and callable(custom_validator):
            custom_errors = custom_validator(data)
            if custom_errors:
                errors.extend(custom_errors)
        
        return len(errors) == 0, errors
    
    except Exception as e:
        return False, [f"Validation error: {str(e)}"]


def stream_json_items(file_path: Path, items_path: str) -> Iterator[Any]:
    """
    Stream items from a JSON array in a file.
    
    This function allows processing large JSON arrays without loading
    the entire file into memory.
    
    Args:
        file_path: Path to the JSON file
        items_path: Path to the array within the JSON structure (e.g., 'data.items')
        
    Yields:
        Items from the JSON array
        
    Raises:
        DataPersistenceError: If the read operation fails or JSON is invalid
    """
    if not file_path.exists():
        raise DataPersistenceError(
            f"File not found: {file_path}",
            file_path=str(file_path),
            operation="read"
        )
    
    try:
        if HAS_IJSON:
            with open(file_path, 'rb') as f:
                # Use ijson for true streaming
                for item in ijson.items(f, items_path + '.item'):
                    yield item
        else:
            # Fallback to regular json
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Navigate to the specified path
                parts = items_path.split('.')
                current = data
                for part in parts:
                    if part in current:
                        current = current[part]
                    else:
                        raise DataPersistenceError(
                            f"Path '{items_path}' not found in JSON",
                            file_path=str(file_path),
                            operation="read"
                        )
                
                # Yield items from the array
                if isinstance(current, list):
                    for item in current:
                        yield item
                else:
                    raise DataPersistenceError(
                        f"Path '{items_path}' does not point to an array",
                        file_path=str(file_path),
                        operation="read"
                    )
    
    except Exception as e:
        logger.error(
            f"Failed to stream JSON items from file: {file_path}",
            exc_info=True,
            extra={"error": str(e)}
        )
        
        raise DataPersistenceError(
            f"Failed to stream JSON items: {str(e)}",
            file_path=str(file_path),
            operation="read",
            original_error=e
        )