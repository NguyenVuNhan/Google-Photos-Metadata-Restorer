"""
ZIP Extractor Module

Handles extraction of Google Takeout ZIP files while preserving folder structure.
"""

import os
import zipfile
import logging
from pathlib import Path
from typing import List, Optional
from tqdm import tqdm

logger = logging.getLogger(__name__)


class ZipExtractor:
    """Handles extraction of Google Takeout ZIP files."""
    
    # Common Google Takeout folder patterns
    TAKEOUT_PATTERNS = ["Takeout", "Google Photos"]
    
    def __init__(self, delete_after_extraction: bool = False):
        """
        Initialize the ZIP extractor.
        
        Args:
            delete_after_extraction: Whether to delete ZIP files after successful extraction
        """
        self.delete_after_extraction = delete_after_extraction
        self.extracted_files: List[Path] = []
        self.failed_files: List[tuple] = []  # (path, error)
    
    def find_zip_files(self, input_path: Path) -> List[Path]:
        """
        Find all ZIP files in the given path.
        
        Args:
            input_path: Path to search for ZIP files
            
        Returns:
            List of paths to ZIP files
        """
        zip_files = []
        
        if input_path.is_file() and input_path.suffix.lower() == '.zip':
            zip_files.append(input_path)
        elif input_path.is_dir():
            # Find all ZIP files in the directory (non-recursive by default for safety)
            for item in input_path.iterdir():
                if item.is_file() and item.suffix.lower() == '.zip':
                    zip_files.append(item)
        
        logger.info(f"Found {len(zip_files)} ZIP file(s) to process")
        return sorted(zip_files)
    
    def find_zip_files_recursive(self, input_path: Path) -> List[Path]:
        """
        Recursively find all ZIP files in the given path.
        
        Args:
            input_path: Path to search for ZIP files
            
        Returns:
            List of paths to ZIP files
        """
        zip_files = []
        
        if input_path.is_file() and input_path.suffix.lower() == '.zip':
            zip_files.append(input_path)
        elif input_path.is_dir():
            for item in input_path.rglob("*.zip"):
                zip_files.append(item)
        
        logger.info(f"Found {len(zip_files)} ZIP file(s) to process (recursive)")
        return sorted(zip_files)
    
    def extract_zip(
        self, 
        zip_path: Path, 
        output_dir: Path,
        preserve_structure: bool = True
    ) -> bool:
        """
        Extract a single ZIP file.
        
        Args:
            zip_path: Path to the ZIP file
            output_dir: Directory to extract to
            preserve_structure: Whether to preserve the internal folder structure
            
        Returns:
            True if extraction was successful, False otherwise
        """
        try:
            logger.info(f"Extracting: {zip_path.name}")
            
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Get list of files for progress bar
                file_list = zf.namelist()
                total_files = len(file_list)
                
                logger.info(f"  Contains {total_files} files/folders")
                
                # Extract with progress bar
                for member in tqdm(file_list, desc=f"  Extracting {zip_path.name}", unit="files"):
                    try:
                        # Skip Mac OS X metadata files
                        if '__MACOSX' in member or member.startswith('._'):
                            continue
                        
                        if preserve_structure:
                            # Extract maintaining full path structure
                            zf.extract(member, output_dir)
                        else:
                            # Flatten structure - extract only Google Photos content
                            # This handles the "Takeout/Google Photos/..." structure
                            extracted_path = self._extract_with_simplified_structure(
                                zf, member, output_dir
                            )
                            
                    except Exception as e:
                        logger.warning(f"  Failed to extract {member}: {e}")
                        continue
                
                self.extracted_files.append(zip_path)
                logger.info(f"  Successfully extracted: {zip_path.name}")
                
                # Delete ZIP if configured
                if self.delete_after_extraction:
                    try:
                        zip_path.unlink()
                        logger.info(f"  Deleted ZIP file: {zip_path.name}")
                    except Exception as e:
                        logger.warning(f"  Failed to delete ZIP file: {e}")
                
                return True
                
        except zipfile.BadZipFile:
            error_msg = f"Invalid or corrupted ZIP file: {zip_path}"
            logger.error(error_msg)
            self.failed_files.append((zip_path, error_msg))
            return False
        except Exception as e:
            error_msg = f"Error extracting {zip_path}: {e}"
            logger.error(error_msg)
            self.failed_files.append((zip_path, str(e)))
            return False
    
    def _extract_with_simplified_structure(
        self, 
        zf: zipfile.ZipFile, 
        member: str, 
        output_dir: Path
    ) -> Optional[Path]:
        """
        Extract a member with simplified folder structure.
        Removes "Takeout/Google Photos/" prefix if present.
        
        Args:
            zf: ZipFile object
            member: Member path within ZIP
            output_dir: Output directory
            
        Returns:
            Path to extracted file or None
        """
        # Find and remove Google Takeout prefix
        parts = Path(member).parts
        
        # Look for "Google Photos" in the path and start from there
        start_idx = 0
        for i, part in enumerate(parts):
            if part == "Google Photos":
                start_idx = i + 1
                break
        
        if start_idx > 0 and start_idx < len(parts):
            # Create new path without the prefix
            new_path = Path(*parts[start_idx:])
            target_path = output_dir / new_path
        else:
            # Keep original structure
            target_path = output_dir / member
        
        # Create parent directories
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Extract if it's a file (not a directory)
        if not member.endswith('/'):
            with zf.open(member) as source:
                with open(target_path, 'wb') as target:
                    target.write(source.read())
            return target_path
        
        return None
    
    def extract_all(
        self, 
        input_path: Path, 
        output_dir: Path,
        preserve_structure: bool = True,
        recursive: bool = False
    ) -> dict:
        """
        Extract all ZIP files from input path.
        
        Args:
            input_path: Path containing ZIP files
            output_dir: Directory to extract to
            preserve_structure: Whether to preserve folder structure
            recursive: Whether to search for ZIPs recursively
            
        Returns:
            Dictionary with extraction results
        """
        # Find ZIP files
        if recursive:
            zip_files = self.find_zip_files_recursive(input_path)
        else:
            zip_files = self.find_zip_files(input_path)
        
        if not zip_files:
            logger.warning("No ZIP files found to extract")
            return {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "extracted_files": [],
                "failed_files": []
            }
        
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract each ZIP
        successful = 0
        for zip_path in zip_files:
            if self.extract_zip(zip_path, output_dir, preserve_structure):
                successful += 1
        
        results = {
            "total": len(zip_files),
            "successful": successful,
            "failed": len(zip_files) - successful,
            "extracted_files": [str(p) for p in self.extracted_files],
            "failed_files": [(str(p), e) for p, e in self.failed_files]
        }
        
        logger.info(f"Extraction complete: {successful}/{len(zip_files)} successful")
        
        return results


def extract_google_takeout(
    input_path: str,
    output_dir: str,
    delete_after: bool = False,
    preserve_structure: bool = True
) -> dict:
    """
    Convenience function to extract Google Takeout ZIP files.
    
    Args:
        input_path: Path to ZIP file(s) or directory containing ZIPs
        output_dir: Directory to extract to
        delete_after: Whether to delete ZIPs after extraction
        preserve_structure: Whether to preserve folder structure
        
    Returns:
        Dictionary with extraction results
    """
    extractor = ZipExtractor(delete_after_extraction=delete_after)
    return extractor.extract_all(
        Path(input_path),
        Path(output_dir),
        preserve_structure=preserve_structure
    )
