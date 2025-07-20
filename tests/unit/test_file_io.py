"""
Tests for the optimized file I/O operations and data persistence.

This module contains tests for atomic writes, efficient JSON serialization,
and data validation utilities.
"""

import unittest
import asyncio
import json
import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import hashlib

from src.utils.file_io.atomic_writer import AtomicWriter
from src.utils.file_io.json_utils import (
    calculate_json_hash,
    has_json_changed,
    stream_json_to_file,
    stream_json_from_file,
    validate_json_file
)
from src.utils.file_io.data_validator import DataValidator
from src.core.exceptions import DataPersistenceError


class TestAtomicWriter(unittest.IsolatedAsyncioTestCase):
    """Test cases for the AtomicWriter class."""
    
    async def asyncSetUp(self):
        """Set up test environment with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = Path(self.temp_dir) / "test_file.txt"
        self.writer = AtomicWriter(backup_retention_count=3)
    
    async def asyncTearDown(self):
        """Clean up temporary directory after tests."""
        shutil.rmtree(self.temp_dir)
    
    async def test_write_atomic(self):
        """Test atomic write operation."""
        # Write content atomically
        content = "Test content"
        await self.writer.write_atomic(self.test_file, content)
        
        # Verify file was created
        self.assertTrue(self.test_file.exists())
        
        # Verify content was written correctly
        with open(self.test_file, 'r') as f:
            self.assertEqual(content, f.read())
    
    async def test_write_with_backup(self):
        """Test atomic write with backup creation."""
        # Write initial content
        initial_content = "Initial content"
        await self.writer.write_atomic(self.test_file, initial_content)
        
        # Write new content with backup
        new_content = "New content"
        await self.writer.write_atomic(self.test_file, new_content, create_backup=True)
        
        # Verify new content was written
        with open(self.test_file, 'r') as f:
            self.assertEqual(new_content, f.read())
        
        # Verify backup was created
        backup_files = list(self.test_file.parent.glob(f"{self.test_file.stem}{self.test_file.suffix}.bak*"))
        self.assertEqual(1, len(backup_files))
        
        # Verify backup content
        with open(backup_files[0], 'r') as f:
            self.assertEqual(initial_content, f.read())
    
    async def test_backup_rotation(self):
        """Test backup rotation to limit the number of backups."""
        # Write multiple versions to create multiple backups
        for i in range(5):
            content = f"Content version {i}"
            await self.writer.write_atomic(self.test_file, content, create_backup=True)
        
        # Verify backup count is limited
        backup_files = list(self.test_file.parent.glob(f"{self.test_file.stem}{self.test_file.suffix}.bak*"))
        self.assertLessEqual(len(backup_files), self.writer.backup_retention_count)
    
    async def test_restore_from_backup(self):
        """Test restoring from backup."""
        # Write initial content
        initial_content = "Initial content"
        await self.writer.write_atomic(self.test_file, initial_content)
        
        # Write new content with backup
        new_content = "New content"
        await self.writer.write_atomic(self.test_file, new_content, create_backup=True)
        
        # Delete the file
        self.test_file.unlink()
        
        # Restore from backup
        restored_file = await self.writer.restore_from_backup(self.test_file)
        
        # Verify file was restored
        self.assertTrue(self.test_file.exists())
        self.assertIsNotNone(restored_file)
        
        # Verify content was restored
        with open(self.test_file, 'r') as f:
            self.assertEqual(initial_content, f.read())
    
    async def test_write_with_validation(self):
        """Test atomic write with validation."""
        # Define validation function
        def validate_content(content):
            return len(content) > 0
        
        # Write valid content
        valid_content = "Valid content"
        await self.writer.write_atomic_with_validation(
            self.test_file, valid_content, validate_content
        )
        
        # Verify file was created
        self.assertTrue(self.test_file.exists())
        
        # Try to write invalid content
        invalid_content = ""
        with self.assertRaises(DataPersistenceError):
            await self.writer.write_atomic_with_validation(
                self.test_file, invalid_content, validate_content
            )


class TestJsonUtils(unittest.IsolatedAsyncioTestCase):
    """Test cases for the JSON utilities."""
    
    async def asyncSetUp(self):
        """Set up test environment with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = Path(self.temp_dir) / "test_data.json"
    
    async def asyncTearDown(self):
        """Clean up temporary directory after tests."""
        shutil.rmtree(self.temp_dir)
    
    def test_calculate_json_hash(self):
        """Test calculating a deterministic hash of JSON data."""
        # Create test data
        data = {
            "key1": "value1",
            "key2": 123,
            "key3": [1, 2, 3],
            "key4": {"nested": "value"}
        }
        
        # Calculate hash
        hash1 = calculate_json_hash(data)
        
        # Verify hash is a string
        self.assertIsInstance(hash1, str)
        
        # Verify same data produces same hash
        hash2 = calculate_json_hash(data)
        self.assertEqual(hash1, hash2)
        
        # Verify different data produces different hash
        data["key1"] = "changed"
        hash3 = calculate_json_hash(data)
        self.assertNotEqual(hash1, hash3)
    
    def test_has_json_changed(self):
        """Test detecting changes in JSON data."""
        # Create test data
        data = {
            "key1": "value1",
            "key2": 123
        }
        
        # Calculate initial hash
        initial_hash = calculate_json_hash(data)
        
        # Verify no change is detected
        self.assertFalse(has_json_changed(data, initial_hash))
        
        # Modify data
        data["key1"] = "changed"
        
        # Verify change is detected
        self.assertTrue(has_json_changed(data, initial_hash))
    
    async def test_stream_json_to_file(self):
        """Test streaming JSON to a file."""
        # Create test data
        data = {
            "key1": "value1",
            "key2": 123,
            "key3": [1, 2, 3],
            "key4": {"nested": "value"}
        }
        
        # Stream to file
        await stream_json_to_file(self.test_file, data, indent=4)
        
        # Verify file was created
        self.assertTrue(self.test_file.exists())
        
        # Verify content was written correctly
        with open(self.test_file, 'r') as f:
            loaded_data = json.load(f)
            self.assertEqual(data, loaded_data)
    
    async def test_stream_json_from_file(self):
        """Test streaming JSON from a file."""
        # Create test data
        data = {
            "key1": "value1",
            "key2": 123,
            "key3": [1, 2, 3],
            "key4": {"nested": "value"}
        }
        
        # Write to file
        with open(self.test_file, 'w') as f:
            json.dump(data, f)
        
        # Stream from file
        loaded_data = stream_json_from_file(self.test_file)
        
        # Verify data was loaded correctly
        self.assertEqual(data, loaded_data)
    
    async def test_validate_json_file(self):
        """Test validating a JSON file."""
        # Create valid test data
        valid_data = {
            "name": "Test",
            "value": 123
        }
        
        # Write to file
        with open(self.test_file, 'w') as f:
            json.dump(valid_data, f)
        
        # Define schema
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "value": {"type": "number"}
            },
            "required": ["name", "value"]
        }
        
        # Validate file
        is_valid, errors = validate_json_file(self.test_file, schema)
        
        # Verify validation passed
        self.assertTrue(is_valid)
        self.assertEqual(0, len(errors))
        
        # Create invalid test data
        invalid_data = {
            "name": 123,  # Should be string
            "extra": "value"  # Missing required "value"
        }
        
        # Write to file
        with open(self.test_file, 'w') as f:
            json.dump(invalid_data, f)
        
        # Validate file
        is_valid, errors = validate_json_file(self.test_file, schema)
        
        # Verify validation failed
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)


class TestDataValidator(unittest.TestCase):
    """Test cases for the DataValidator class."""
    
    def setUp(self):
        """Set up test environment."""
        self.validator = DataValidator()
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = Path(self.temp_dir) / "test_data.json"
    
    def tearDown(self):
        """Clean up temporary directory after tests."""
        shutil.rmtree(self.temp_dir)
    
    def test_validate_json_structure(self):
        """Test validating JSON structure."""
        # Create valid test data
        valid_data = {
            "name": "Test",
            "value": 123,
            "items": [1, 2, 3]
        }
        
        # Define validation parameters
        required_keys = ["name", "value"]
        key_types = {
            "name": str,
            "value": int,
            "items": list
        }
        custom_validators = {
            "value": lambda x: x > 0,
            "items": lambda x: len(x) > 0
        }
        
        # Validate structure
        is_valid, errors = self.validator.validate_json_structure(
            valid_data, required_keys, key_types, custom_validators
        )
        
        # Verify validation passed
        self.assertTrue(is_valid)
        self.assertEqual(0, len(errors))
        
        # Create invalid test data
        invalid_data = {
            "name": 123,  # Wrong type
            "value": -1,  # Fails custom validation
            "items": []  # Fails custom validation
        }
        
        # Validate structure
        is_valid, errors = self.validator.validate_json_structure(
            invalid_data, required_keys, key_types, custom_validators
        )
        
        # Verify validation failed
        self.assertFalse(is_valid)
        self.assertEqual(3, len(errors))
    
    def test_validate_date_format(self):
        """Test validating date format."""
        # Test valid date
        self.assertTrue(self.validator.validate_date_format("2025-07-20"))
        
        # Test invalid dates
        self.assertFalse(self.validator.validate_date_format("2025/07/20"))
        self.assertFalse(self.validator.validate_date_format("20-07-2025"))
        self.assertFalse(self.validator.validate_date_format("not a date"))
    
    def test_validate_stats_data(self):
        """Test validating statistics data."""
        # Create valid stats data
        valid_data = {
            "2025-07-20": {
                "joins": [
                    {
                        "id": 123,
                        "username": "test_user",
                        "timestamp": "2025-07-20T12:00:00+00:00"
                    }
                ],
                "leaves": [],
                "bans": []
            }
        }
        
        # Validate data
        is_valid, errors = self.validator.validate_stats_data(valid_data)
        
        # Verify validation passed
        self.assertTrue(is_valid)
        self.assertEqual(0, len(errors))
        
        # Create invalid stats data
        invalid_data = {
            "invalid-date": {  # Invalid date format
                "joins": [
                    {
                        "id": "not an int",  # ID should be int or string
                        "timestamp": "invalid"  # Invalid timestamp
                    }
                ],
                "leaves": "not a list"  # Should be a list
            }
        }
        
        # Validate data
        is_valid, errors = self.validator.validate_stats_data(invalid_data)
        
        # Verify validation failed
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
    
    def test_repair_stats_data(self):
        """Test repairing statistics data."""
        # Create invalid stats data
        invalid_data = {
            "invalid-date": {  # Invalid date format
                "joins": [
                    {
                        "id": "not an int",  # ID should be int or string
                        "username": 123,  # Should be string
                        "timestamp": "invalid"  # Invalid timestamp
                    }
                ],
                "leaves": "not a list"  # Should be a list
            }
        }
        
        # Repair data
        repaired_data, repairs_made, messages = self.validator.repair_stats_data(invalid_data)
        
        # Verify repairs were made
        self.assertTrue(repairs_made)
        self.assertGreater(len(messages), 0)
        
        # Validate repaired data
        is_valid, errors = self.validator.validate_stats_data(repaired_data)
        
        # Verify repaired data is valid
        self.assertTrue(is_valid)
        self.assertEqual(0, len(errors))
    
    def test_calculate_file_checksum(self):
        """Test calculating file checksum."""
        # Create test file
        content = "Test content"
        with open(self.test_file, 'w') as f:
            f.write(content)
        
        # Calculate checksum
        checksum = self.validator.calculate_file_checksum(self.test_file)
        
        # Verify checksum is correct
        expected_checksum = hashlib.md5(content.encode()).hexdigest()
        self.assertEqual(expected_checksum, checksum)
    
    def test_verify_file_checksum(self):
        """Test verifying file checksum."""
        # Create test file
        content = "Test content"
        with open(self.test_file, 'w') as f:
            f.write(content)
        
        # Calculate expected checksum
        expected_checksum = hashlib.md5(content.encode()).hexdigest()
        
        # Verify correct checksum
        self.assertTrue(self.validator.verify_file_checksum(self.test_file, expected_checksum))
        
        # Verify incorrect checksum
        self.assertFalse(self.validator.verify_file_checksum(self.test_file, "wrong_checksum"))


if __name__ == '__main__':
    # Use asyncio to run async tests
    asyncio.run(unittest.main())