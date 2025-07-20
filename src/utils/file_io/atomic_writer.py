"""
Atomic file writing with backup mechanisms.

This module provides utilities for atomic file operations that ensure
data integrity even in case of system crashes or power failures.
"""

import os
import shutil
import tempfile
import asyncio
import glob
from pathlib import Path
from typing import Optional, List, Callable, Any
from datetime import datetime
import logging

from src.core.exceptions import DataPersistenceError


class AtomicWriter:
    """
    Atomic file writer with backup mechanisms.
    
    This class provides methods for safely writing files with atomic operations
    and automatic backup creation. It ensures that files are never left in a
    corrupted state even if the system crashes during a write operation.
    
    Attributes:
        backup_retention_count (int): Number of backup files to keep
        logger (logging.Logger): Logger instance
    """
    
    def __init__(
        self, 
        backup_retention_count: int = 3,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the atomic writer.
        
        Args:
            backup_retention_count: Number of backup files to keep
            logger: Logger instance (optional)
        """
        self.backup_retention_count = backup_retention_count
        self.logger = logger or logging.getLogger(__name__)
        
    async def write_atomic(
        self, 
        file_path: Path, 
        content: str,
        create_backup: bool = True,
        mode: str = 'w',
        encoding: str = 'utf-8'
    ) -> Path:
        """
        Write content to a file atomically.
        
        This method writes to a temporary file first, then renames it to the
        target file to ensure atomic updates. It also creates a backup of the
        original file if requested.
        
        Args:
            file_path: Path to the target file
            content: Content to write
            create_backup: Whether to create a backup of the original file
            mode: File open mode ('w' for write, 'a' for append)
            encoding: File encoding
            
        Returns:
            Path to the backup file if created, otherwise the target file path
            
        Raises:
            DataPersistenceError: If the write operation fails
        """
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create temporary file in the same directory for atomic move
        temp_file = file_path.with_suffix(f'{file_path.suffix}.tmp')
        
        # Create backup filename with timestamp
        backup_file = None
        if create_backup and file_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            backup_file = file_path.with_suffix(f'{file_path.suffix}.bak{timestamp}')
            
        try:
            # Write to temporary file first
            with open(temp_file, mode, encoding=encoding) as f:
                f.write(content)
                
            # Create backup of current file if it exists and backup is requested
            if backup_file and file_path.exists():
                shutil.copy2(file_path, backup_file)
                
            # Rename temporary file to target file (atomic operation)
            os.replace(temp_file, file_path)
            
            self.logger.debug(
                f"File written atomically: {file_path}",
                extra={
                    "file_path": str(file_path),
                    "backup_file": str(backup_file) if backup_file else None
                }
            )
            
            # Clean up old backups if needed
            if create_backup:
                await self.cleanup_old_backups(file_path)
                
            return backup_file if backup_file else file_path
            
        except Exception as e:
            self.logger.error(
                f"Failed to write file atomically: {file_path}",
                exc_info=True,
                extra={
                    "file_path": str(file_path),
                    "error": str(e)
                }
            )
            
            # Clean up temporary file if it exists
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
                
            raise DataPersistenceError(
                f"Failed to write file atomically: {str(e)}",
                file_path=str(file_path),
                operation="write",
                original_error=e
            )
    
    async def write_atomic_with_validation(
        self, 
        file_path: Path, 
        content: str,
        validation_func: Callable[[str], bool],
        create_backup: bool = True,
        mode: str = 'w',
        encoding: str = 'utf-8'
    ) -> Path:
        """
        Write content to a file atomically with validation.
        
        This method extends write_atomic by validating the content before
        committing the changes to the target file.
        
        Args:
            file_path: Path to the target file
            content: Content to write
            validation_func: Function to validate the content
            create_backup: Whether to create a backup of the original file
            mode: File open mode ('w' for write, 'a' for append)
            encoding: File encoding
            
        Returns:
            Path to the backup file if created, otherwise the target file path
            
        Raises:
            DataPersistenceError: If the write operation fails or validation fails
        """
        # Validate content before writing
        if not validation_func(content):
            raise DataPersistenceError(
                "Content validation failed",
                file_path=str(file_path),
                operation="validate"
            )
            
        # Proceed with atomic write
        return await self.write_atomic(file_path, content, create_backup, mode, encoding)
    
    async def cleanup_old_backups(self, file_path: Path) -> None:
        """
        Clean up old backup files, keeping only the most recent ones.
        
        Args:
            file_path: Path to the original file
        """
        try:
            # Find all backup files
            backup_pattern = f"{file_path.stem}{file_path.suffix}.bak*"
            backup_files = sorted(
                file_path.parent.glob(backup_pattern),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            # Keep only the most recent backups
            if len(backup_files) > self.backup_retention_count:
                for old_backup in backup_files[self.backup_retention_count:]:
                    try:
                        old_backup.unlink()
                        self.logger.debug(f"Removed old backup: {old_backup}")
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to remove old backup: {old_backup}",
                            exc_info=True,
                            extra={"error": str(e)}
                        )
        except Exception as e:
            self.logger.warning(
                "Error during backup cleanup",
                exc_info=True,
                extra={"error": str(e)}
            )
    
    async def restore_from_backup(self, file_path: Path) -> Optional[Path]:
        """
        Attempt to restore a file from the most recent valid backup.
        
        Args:
            file_path: Path to the file to restore
            
        Returns:
            Path to the backup file used for restoration, or None if no valid backup found
            
        Raises:
            DataPersistenceError: If restoration fails
        """
        self.logger.warning(f"Attempting to restore {file_path} from backup")
        
        # Look for backup files
        backup_pattern = f"{file_path.stem}{file_path.suffix}.bak*"
        backup_files = sorted(
            file_path.parent.glob(backup_pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        if not backup_files:
            self.logger.error(f"No backup files found for {file_path}")
            return None
            
        for backup_file in backup_files:
            try:
                self.logger.info(f"Trying backup file: {backup_file}")
                
                # Copy backup to original file
                shutil.copy2(backup_file, file_path)
                
                self.logger.info(f"Successfully restored from backup: {backup_file}")
                return backup_file
                
            except Exception as e:
                self.logger.error(
                    f"Failed to restore from backup: {backup_file}",
                    exc_info=True,
                    extra={"error": str(e)}
                )
                
        # If we get here, all backups failed
        self.logger.error("All backup restoration attempts failed")
        return None
    
    def get_backup_files(self, file_path: Path) -> List[Path]:
        """
        Get a list of backup files for a given file.
        
        Args:
            file_path: Path to the original file
            
        Returns:
            List of backup file paths sorted by modification time (newest first)
        """
        backup_pattern = f"{file_path.stem}{file_path.suffix}.bak*"
        return sorted(
            file_path.parent.glob(backup_pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )