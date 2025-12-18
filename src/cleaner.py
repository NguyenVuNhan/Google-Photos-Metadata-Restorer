"""
Cleaner Module

Handles cleanup of JSON metadata files after processing.
"""

import logging
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from .utils import safe_delete, create_backup

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    """Result of cleanup operation."""
    total_files: int
    deleted_count: int
    failed_count: int
    skipped_count: int
    deleted_files: List[str]
    failed_files: List[tuple]  # (path, error)


class JsonCleaner:
    """Handles cleanup of JSON metadata files."""
    
    def __init__(
        self,
        create_backups: bool = False,
        backup_dir: Optional[Path] = None,
        dry_run: bool = False
    ):
        """
        Initialize the cleaner.
        
        Args:
            create_backups: Whether to backup files before deleting
            backup_dir: Directory for backups
            dry_run: If True, don't actually delete files
        """
        self.create_backups = create_backups
        self.backup_dir = backup_dir
        self.dry_run = dry_run
        
        self.deleted_files: List[Path] = []
        self.failed_files: List[tuple] = []
        self.skipped_files: List[Path] = []
    
    def delete_json_file(self, json_path: Path) -> bool:
        """
        Delete a single JSON file.
        
        Args:
            json_path: Path to the JSON file
            
        Returns:
            True if deleted successfully
        """
        try:
            if not json_path.exists():
                logger.debug(f"File does not exist: {json_path}")
                return True
            
            if json_path.suffix.lower() != '.json':
                logger.warning(f"Not a JSON file, skipping: {json_path}")
                self.skipped_files.append(json_path)
                return False
            
            # Create backup if requested
            if self.create_backups and not self.dry_run:
                backup_path = create_backup(json_path, self.backup_dir)
                if backup_path:
                    logger.debug(f"Backed up to: {backup_path}")
            
            # Delete the file
            if safe_delete(json_path, self.dry_run):
                self.deleted_files.append(json_path)
                if self.dry_run:
                    logger.debug(f"Would delete: {json_path}")
                else:
                    logger.debug(f"Deleted: {json_path}")
                return True
            else:
                self.failed_files.append((json_path, "Delete failed"))
                return False
                
        except Exception as e:
            logger.warning(f"Error deleting {json_path}: {e}")
            self.failed_files.append((json_path, str(e)))
            return False
    
    def delete_json_files(self, json_paths: List[Path]) -> CleanupResult:
        """
        Delete multiple JSON files.
        
        Args:
            json_paths: List of paths to delete
            
        Returns:
            CleanupResult with details
        """
        logger.info(f"{'Would delete' if self.dry_run else 'Deleting'} {len(json_paths)} JSON file(s)")
        
        for path in json_paths:
            self.delete_json_file(path)
        
        result = CleanupResult(
            total_files=len(json_paths),
            deleted_count=len(self.deleted_files),
            failed_count=len(self.failed_files),
            skipped_count=len(self.skipped_files),
            deleted_files=[str(p) for p in self.deleted_files],
            failed_files=[(str(p), e) for p, e in self.failed_files]
        )
        
        logger.info(
            f"Cleanup complete: {result.deleted_count} deleted, "
            f"{result.failed_count} failed, {result.skipped_count} skipped"
        )
        
        return result
    
    def find_and_delete_orphaned_json(
        self,
        directory: Path,
        recursive: bool = True
    ) -> CleanupResult:
        """
        Find and delete JSON files that have no corresponding media file.
        
        Args:
            directory: Directory to search
            recursive: Whether to search recursively
            
        Returns:
            CleanupResult with details
        """
        from .matcher import MediaFileMatcher
        
        matcher = MediaFileMatcher()
        orphaned = matcher.find_orphaned_json_files(directory, recursive)
        
        logger.info(f"Found {len(orphaned)} orphaned JSON files")
        
        return self.delete_json_files(orphaned)
    
    def reset_counters(self):
        """Reset all counters and lists."""
        self.deleted_files.clear()
        self.failed_files.clear()
        self.skipped_files.clear()


def cleanup_json_files(
    json_paths: List[str],
    dry_run: bool = False,
    create_backups: bool = False
) -> CleanupResult:
    """
    Convenience function to clean up JSON files.
    
    Args:
        json_paths: List of JSON file paths to delete
        dry_run: If True, don't actually delete
        create_backups: Whether to create backups before deleting
        
    Returns:
        CleanupResult with details
    """
    cleaner = JsonCleaner(
        create_backups=create_backups,
        dry_run=dry_run
    )
    return cleaner.delete_json_files([Path(p) for p in json_paths])
