"""
Utilities Module

Common utility functions for the metadata restorer.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    log_format: Optional[str] = None
):
    """
    Set up logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file to write logs to
        log_format: Optional custom log format
    """
    if log_format is None:
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
    
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(logging.Formatter(log_format))
    handlers.append(console_handler)
    
    # File handler (if specified)
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(logging.Formatter(log_format))
            handlers.append(file_handler)
        except Exception as e:
            print(f"Warning: Could not create log file {log_file}: {e}")
    
    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        handlers=handlers
    )


def format_size(size_bytes: int) -> str:
    """
    Format a file size in bytes to a human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def format_duration(seconds: float) -> str:
    """
    Format a duration in seconds to a human-readable string.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string (e.g., "1h 23m 45s")
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}h {minutes}m {secs}s"


def count_files_by_extension(directory: Path, recursive: bool = True) -> dict:
    """
    Count files by extension in a directory.
    
    Args:
        directory: Directory to scan
        recursive: Whether to scan recursively
        
    Returns:
        Dictionary mapping extensions to counts
    """
    counts = {}
    
    if recursive:
        files = directory.rglob("*")
    else:
        files = directory.glob("*")
    
    for file in files:
        if file.is_file():
            ext = file.suffix.lower()
            counts[ext] = counts.get(ext, 0) + 1
    
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


def get_total_size(paths: List[Path]) -> int:
    """
    Get total size of files.
    
    Args:
        paths: List of file paths
        
    Returns:
        Total size in bytes
    """
    total = 0
    for path in paths:
        try:
            if path.is_file():
                total += path.stat().st_size
        except Exception:
            pass
    return total


def safe_delete(path: Path, dry_run: bool = False) -> bool:
    """
    Safely delete a file.
    
    Args:
        path: Path to delete
        dry_run: If True, don't actually delete
        
    Returns:
        True if deleted (or would be deleted in dry_run), False otherwise
    """
    try:
        if path.exists():
            if dry_run:
                logger.debug(f"Would delete: {path}")
                return True
            else:
                path.unlink()
                logger.debug(f"Deleted: {path}")
                return True
        return False
    except Exception as e:
        logger.warning(f"Could not delete {path}: {e}")
        return False


def create_backup(path: Path, backup_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Create a backup copy of a file.
    
    Args:
        path: File to backup
        backup_dir: Optional directory for backups (default: same directory)
        
    Returns:
        Path to backup file, or None if failed
    """
    import shutil
    
    try:
        if not path.exists():
            return None
        
        if backup_dir:
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{path.name}.backup"
        else:
            backup_path = path.parent / f"{path.name}.backup"
        
        # Add timestamp if backup already exists
        if backup_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_path.with_suffix(f".{timestamp}.backup")
        
        shutil.copy2(path, backup_path)
        logger.debug(f"Created backup: {backup_path}")
        return backup_path
        
    except Exception as e:
        logger.warning(f"Could not create backup of {path}: {e}")
        return None


def is_synology() -> bool:
    """Check if running on a Synology NAS."""
    return os.path.exists('/etc/synoinfo.conf')


def get_synology_volume() -> Optional[str]:
    """Get the main volume path on Synology."""
    if is_synology():
        for volume in ['/volume1', '/volume2', '/volume3', '/volume4']:
            if os.path.exists(volume):
                return volume
    return None


def ensure_directory(path: Path) -> Path:
    """
    Ensure a directory exists.
    
    Args:
        path: Directory path
        
    Returns:
        The path (created if needed)
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
