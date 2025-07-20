"""
Data validation and corruption detection utilities.

This module provides utilities for validating data integrity and
detecting corruption in critical files.
"""

import json
import hashlib
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Callable, Union
from datetime import datetime
import logging

from src.core.exceptions import DataPersistenceError, ValidationError


class DataValidator:
    """
    Data validation and corruption detection for critical files.
    
    This class provides methods for validating data integrity and
    detecting corruption in critical files, with support for custom
    validation rules and automatic repair.
    
    Attributes:
        logger (logging.Logger): Logger instance
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the data validator.
        
        Args:
            logger: Logger instance (optional)
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def validate_json_structure(
        self, 
        data: Dict[str, Any],
        required_keys: Optional[List[str]] = None,
        key_types: Optional[Dict[str, type]] = None,
        custom_validators: Optional[Dict[str, Callable[[Any], bool]]] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate JSON data structure.
        
        Args:
            data: Dictionary to validate
            required_keys: List of keys that must be present
            key_types: Dictionary mapping keys to expected types
            custom_validators: Dictionary mapping keys to custom validation functions
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Check required keys
        if required_keys:
            for key in required_keys:
                if key not in data:
                    errors.append(f"Missing required key: {key}")
        
        # Check key types
        if key_types:
            for key, expected_type in key_types.items():
                if key in data and not isinstance(data[key], expected_type):
                    errors.append(
                        f"Invalid type for key '{key}': "
                        f"expected {expected_type.__name__}, "
                        f"got {type(data[key]).__name__}"
                    )
        
        # Apply custom validators
        if custom_validators:
            for key, validator in custom_validators.items():
                if key in data and not validator(data[key]):
                    errors.append(f"Validation failed for key: {key}")
        
        return len(errors) == 0, errors
    
    def validate_date_format(self, date_str: str, format_str: str = "%Y-%m-%d") -> bool:
        """
        Validate a date string against a format.
        
        Args:
            date_str: Date string to validate
            format_str: Expected date format
            
        Returns:
            True if valid, False otherwise
        """
        try:
            datetime.strptime(date_str, format_str)
            return True
        except ValueError:
            return False
    
    def validate_stats_data(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate statistics data structure.
        
        Args:
            data: Statistics data to validate
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Check that data is a dictionary
        if not isinstance(data, dict):
            return False, ["Data must be a dictionary"]
        
        # Validate each date entry
        for date_key, date_data in data.items():
            # Validate date format
            if not self.validate_date_format(date_key):
                errors.append(f"Invalid date format: {date_key}")
            
            # Validate date data structure
            if not isinstance(date_data, dict):
                errors.append(f"Data for date {date_key} must be a dictionary")
                continue
            
            # Check required event types
            required_events = ["joins", "leaves"]
            for event_type in required_events:
                if event_type not in date_data:
                    errors.append(f"Missing required event type '{event_type}' for date {date_key}")
                elif not isinstance(date_data[event_type], list):
                    errors.append(f"Event type '{event_type}' for date {date_key} must be a list")
            
            # Validate event entries
            for event_type, events in date_data.items():
                if not isinstance(events, list):
                    continue  # Already reported above
                
                for i, event in enumerate(events):
                    if not isinstance(event, dict):
                        errors.append(f"Event {i} in '{event_type}' for date {date_key} must be a dictionary")
                        continue
                    
                    # Check required event fields
                    required_fields = ["id", "username", "timestamp"]
                    for field in required_fields:
                        if field not in event:
                            errors.append(
                                f"Missing required field '{field}' in event {i} "
                                f"of '{event_type}' for date {date_key}"
                            )
                    
                    # Validate ID field
                    if "id" in event and not isinstance(event["id"], (int, str)):
                        errors.append(
                            f"Field 'id' in event {i} of '{event_type}' for date {date_key} "
                            f"must be an integer or string"
                        )
                    
                    # Validate username field
                    if "username" in event and not isinstance(event["username"], str):
                        errors.append(
                            f"Field 'username' in event {i} of '{event_type}' for date {date_key} "
                            f"must be a string"
                        )
                    
                    # Validate timestamp field
                    if "timestamp" in event:
                        if not isinstance(event["timestamp"], str):
                            errors.append(
                                f"Field 'timestamp' in event {i} of '{event_type}' for date {date_key} "
                                f"must be a string"
                            )
                        else:
                            # Try to parse timestamp
                            try:
                                datetime.fromisoformat(event["timestamp"])
                            except ValueError:
                                errors.append(
                                    f"Invalid timestamp format in event {i} of '{event_type}' "
                                    f"for date {date_key}"
                                )
        
        return len(errors) == 0, errors
    
    def repair_stats_data(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, List[str]]:
        """
        Attempt to repair statistics data.
        
        Args:
            data: Statistics data to repair
            
        Returns:
            Tuple of (repaired_data, repairs_made, repair_messages)
        """
        repairs_made = False
        repair_messages = []
        repaired_data = {}
        
        # Check that data is a dictionary
        if not isinstance(data, dict):
            return {}, False, ["Cannot repair: data is not a dictionary"]
        
        # Process each date entry
        for date_key, date_data in data.items():
            # Validate and potentially fix date format
            if self.validate_date_format(date_key):
                valid_date_key = date_key
            else:
                # Try to extract a valid date
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_key)
                if date_match:
                    valid_date_key = date_match.group(1)
                    repairs_made = True
                    repair_messages.append(f"Fixed invalid date format: {date_key} -> {valid_date_key}")
                else:
                    # Skip this entry if we can't fix the date
                    repair_messages.append(f"Skipped invalid date entry: {date_key}")
                    continue
            
            # Initialize repaired date data
            if valid_date_key not in repaired_data:
                repaired_data[valid_date_key] = {}
            
            # Handle non-dictionary date data
            if not isinstance(date_data, dict):
                repaired_data[valid_date_key] = {
                    "joins": [],
                    "leaves": [],
                    "bans": [],
                    "unbans": []
                }
                repairs_made = True
                repair_messages.append(f"Initialized empty data for date: {valid_date_key}")
                continue
            
            # Ensure required event types exist
            for event_type in ["joins", "leaves", "bans", "unbans"]:
                if event_type not in date_data:
                    date_data[event_type] = []
                    repairs_made = True
                    repair_messages.append(f"Added missing event type '{event_type}' for date {valid_date_key}")
                elif not isinstance(date_data[event_type], list):
                    date_data[event_type] = []
                    repairs_made = True
                    repair_messages.append(
                        f"Reset invalid event type '{event_type}' to empty list for date {valid_date_key}"
                    )
            
            # Process each event type
            for event_type, events in date_data.items():
                repaired_events = []
                
                if not isinstance(events, list):
                    repaired_data[valid_date_key][event_type] = []
                    continue
                
                for event in events:
                    if not isinstance(event, dict):
                        # Skip invalid events
                        repairs_made = True
                        repair_messages.append(f"Skipped invalid event in '{event_type}' for date {valid_date_key}")
                        continue
                    
                    repaired_event = {}
                    
                    # Handle ID field
                    if "id" in event and isinstance(event["id"], (int, str)):
                        repaired_event["id"] = event["id"]
                    else:
                        repaired_event["id"] = 0  # Default ID
                        repairs_made = True
                        repair_messages.append(f"Set default ID for event in '{event_type}' for date {valid_date_key}")
                    
                    # Handle username field
                    if "username" in event and isinstance(event["username"], str):
                        repaired_event["username"] = event["username"]
                    else:
                        repaired_event["username"] = "unknown"  # Default username
                        repairs_made = True
                        repair_messages.append(
                            f"Set default username for event in '{event_type}' for date {valid_date_key}"
                        )
                    
                    # Handle timestamp field
                    if "timestamp" in event and isinstance(event["timestamp"], str):
                        try:
                            # Validate timestamp format
                            datetime.fromisoformat(event["timestamp"])
                            repaired_event["timestamp"] = event["timestamp"]
                        except ValueError:
                            # Set default timestamp
                            default_timestamp = datetime.now().isoformat()
                            repaired_event["timestamp"] = default_timestamp
                            repairs_made = True
                            repair_messages.append(
                                f"Set default timestamp for event in '{event_type}' for date {valid_date_key}"
                            )
                    else:
                        # Set default timestamp
                        default_timestamp = datetime.now().isoformat()
                        repaired_event["timestamp"] = default_timestamp
                        repairs_made = True
                        repair_messages.append(
                            f"Set default timestamp for event in '{event_type}' for date {valid_date_key}"
                        )
                    
                    # Add any additional fields from the original event
                    for key, value in event.items():
                        if key not in repaired_event:
                            repaired_event[key] = value
                    
                    repaired_events.append(repaired_event)
                
                repaired_data[valid_date_key][event_type] = repaired_events
        
        return repaired_data, repairs_made, repair_messages
    
    def validate_json_file(
        self, 
        file_path: Path,
        validation_func: Callable[[Dict[str, Any]], Tuple[bool, List[str]]],
        repair_func: Optional[Callable[[Dict[str, Any]], Tuple[Dict[str, Any], bool, List[str]]]] = None,
        auto_repair: bool = False
    ) -> Tuple[bool, List[str], Optional[Dict[str, Any]]]:
        """
        Validate a JSON file with custom validation and optional repair.
        
        Args:
            file_path: Path to the JSON file
            validation_func: Function to validate the data
            repair_func: Function to repair the data (optional)
            auto_repair: Whether to automatically repair and save the file
            
        Returns:
            Tuple of (is_valid, messages, repaired_data)
        """
        if not file_path.exists():
            return False, [f"File not found: {file_path}"], None
        
        try:
            # Read the JSON file
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as e:
                    error_msg = f"Invalid JSON in file: {str(e)}"
                    self.logger.error(error_msg)
                    
                    if repair_func and auto_repair:
                        # Try to repair with empty data
                        repaired_data, repairs_made, repair_messages = repair_func({})
                        if repairs_made:
                            # Save repaired data
                            with open(file_path, 'w', encoding='utf-8') as f_out:
                                json.dump(repaired_data, f_out, indent=4)
                            
                            return False, [error_msg] + repair_messages, repaired_data
                    
                    return False, [error_msg], None
            
            # Validate the data
            is_valid, validation_messages = validation_func(data)
            
            if not is_valid and repair_func:
                # Try to repair the data
                repaired_data, repairs_made, repair_messages = repair_func(data)
                
                if repairs_made:
                    # Validate the repaired data
                    repaired_valid, repaired_validation_messages = validation_func(repaired_data)
                    
                    if repaired_valid and auto_repair:
                        # Save repaired data
                        with open(file_path, 'w', encoding='utf-8') as f_out:
                            json.dump(repaired_data, f_out, indent=4)
                        
                        return True, repair_messages, repaired_data
                    
                    return repaired_valid, validation_messages + repair_messages, repaired_data
            
            return is_valid, validation_messages, None
        
        except Exception as e:
            error_msg = f"Error validating file: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return False, [error_msg], None
    
    def calculate_file_checksum(self, file_path: Path, algorithm: str = 'md5') -> str:
        """
        Calculate a checksum for a file.
        
        Args:
            file_path: Path to the file
            algorithm: Hash algorithm to use
            
        Returns:
            Checksum string
            
        Raises:
            DataPersistenceError: If the file cannot be read
        """
        if not file_path.exists():
            raise DataPersistenceError(
                f"File not found: {file_path}",
                file_path=str(file_path),
                operation="read"
            )
        
        try:
            hash_obj = hashlib.new(algorithm)
            
            with open(file_path, 'rb') as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(4096), b''):
                    hash_obj.update(chunk)
            
            return hash_obj.hexdigest()
        
        except Exception as e:
            raise DataPersistenceError(
                f"Failed to calculate checksum: {str(e)}",
                file_path=str(file_path),
                operation="checksum",
                original_error=e
            )
    
    def verify_file_checksum(self, file_path: Path, expected_checksum: str, algorithm: str = 'md5') -> bool:
        """
        Verify a file against an expected checksum.
        
        Args:
            file_path: Path to the file
            expected_checksum: Expected checksum
            algorithm: Hash algorithm to use
            
        Returns:
            True if the checksum matches, False otherwise
        """
        try:
            actual_checksum = self.calculate_file_checksum(file_path, algorithm)
            return actual_checksum == expected_checksum
        except Exception:
            return False