"""
Media File Matcher Module

Matches media files with their corresponding Google Takeout JSON metadata files.
Handles various naming conventions and edge cases.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Supported media file extensions
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
    '.webp', '.heic', '.heif', '.raw', '.cr2', '.nef', '.arw',
    '.dng', '.orf', '.rw2', '.pef', '.srw'
}

VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm',
    '.m4v', '.3gp', '.3g2', '.mts', '.m2ts', '.mpg', '.mpeg'
}

MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


@dataclass
class MatchResult:
    """Result of matching a media file with its JSON metadata."""
    media_path: Path
    json_path: Optional[Path]
    match_type: str  # 'exact', 'edited', 'truncated', 'numbered', 'none'
    confidence: float  # 0.0 to 1.0


class MediaFileMatcher:
    """Matches media files with their Google Takeout JSON metadata files."""
    
    # Google often truncates filenames at 47 characters (before extension)
    GOOGLE_FILENAME_LIMIT = 47
    
    # Pattern for edited files: original-edited.jpg, original-bearbeitet.jpg, etc.
    EDITED_PATTERNS = [
        r'-edited$',
        r'-bearbeitet$',  # German
        r'-modifié$',     # French
        r'-editado$',     # Spanish
        r'-modificato$',  # Italian
        r'-編集済み$',     # Japanese
    ]
    
    # Pattern for numbered duplicates: photo(1).jpg, photo(2).jpg
    NUMBERED_PATTERN = re.compile(r'^(.+?)(\(\d+\))(\.[^.]+)$')
    
    # Default Google Takeout JSON metadata file suffixes
    DEFAULT_JSON_SUFFIXES = [
        '.json',                      # Standard: photo.jpg.json
        '.supplemental-met.json',     # Supplemental: photo.jpg.supplemental-met.json
        '.supplemental-metadata.json', # Alternative supplemental format
    ]
    
    def __init__(self, json_suffixes: Optional[List[str]] = None):
        """
        Initialize the matcher.
        
        Args:
            json_suffixes: List of JSON file suffixes to look for.
                          Default: ['.json', '.supplemental-met.json', '.supplemental-metadata.json']
        """
        self.matched_count = 0
        self.unmatched_count = 0
        self._json_cache: Dict[Path, List[Path]] = {}
        self.json_suffixes = json_suffixes or self.DEFAULT_JSON_SUFFIXES
    
    def is_media_file(self, path: Path) -> bool:
        """Check if a file is a supported media file."""
        return path.suffix.lower() in MEDIA_EXTENSIONS
    
    def is_image_file(self, path: Path) -> bool:
        """Check if a file is an image."""
        return path.suffix.lower() in IMAGE_EXTENSIONS
    
    def is_video_file(self, path: Path) -> bool:
        """Check if a file is a video."""
        return path.suffix.lower() in VIDEO_EXTENSIONS
    
    def is_json_metadata_file(self, path: Path) -> bool:
        """
        Check if a JSON file is likely a Google Takeout metadata file.
        Metadata files have patterns like:
        - mediafile.ext.json
        - mediafile.ext.supplemental-met.json
        - mediafile.ext.supplemental-metadata.json
        """
        if path.suffix.lower() != '.json':
            return False
        
        filename = path.name.lower()
        
        # Check against all configured JSON suffixes
        for suffix in self.json_suffixes:
            if filename.endswith(suffix.lower()):
                # Extract media filename by removing the suffix
                media_name = path.name[:-len(suffix)]
                potential_ext = Path(media_name).suffix.lower()
                if potential_ext in MEDIA_EXTENSIONS:
                    return True
        
        return False
    
    def _get_json_files_in_directory(self, directory: Path) -> List[Path]:
        """Get cached list of JSON files in a directory."""
        if directory not in self._json_cache:
            try:
                self._json_cache[directory] = [
                    f for f in directory.iterdir()
                    if f.is_file() and f.suffix.lower() == '.json'
                ]
            except Exception as e:
                logger.warning(f"Error listing directory {directory}: {e}")
                self._json_cache[directory] = []
        
        return self._json_cache[directory]
    
    def find_json_for_media(self, media_path: Path) -> MatchResult:
        """
        Find the corresponding JSON metadata file for a media file.
        
        Args:
            media_path: Path to the media file
            
        Returns:
            MatchResult with the JSON path and match details
        """
        directory = media_path.parent
        filename = media_path.name
        
        # Strategy 1: Exact match with various JSON suffixes
        # (photo.jpg -> photo.jpg.json, photo.jpg.supplemental-met.json, etc.)
        for suffix in self.json_suffixes:
            exact_json = directory / f"{filename}{suffix}"
            if exact_json.exists():
                self.matched_count += 1
                match_type = 'exact' if suffix == '.json' else 'supplemental'
                return MatchResult(media_path, exact_json, match_type, 1.0)
        
        # Strategy 2: Handle edited files (photo-edited.jpg -> photo.jpg.json)
        json_path = self._try_edited_match(media_path)
        if json_path:
            self.matched_count += 1
            return MatchResult(media_path, json_path, 'edited', 0.9)
        
        # Strategy 3: Handle numbered duplicates (photo(1).jpg -> photo.jpg.json or photo(1).jpg.json)
        json_path = self._try_numbered_match(media_path)
        if json_path:
            self.matched_count += 1
            return MatchResult(media_path, json_path, 'numbered', 0.85)
        
        # Strategy 4: Handle truncated filenames
        json_path = self._try_truncated_match(media_path)
        if json_path:
            self.matched_count += 1
            return MatchResult(media_path, json_path, 'truncated', 0.8)
        
        # Strategy 5: Handle supplementary files like -EFFECTS, -ANIMATION, -COLLAGE
        json_path = self._try_supplementary_match(media_path)
        if json_path:
            self.matched_count += 1
            return MatchResult(media_path, json_path, 'supplementary', 0.75)
        
        # No match found
        self.unmatched_count += 1
        logger.debug(f"No JSON match found for: {media_path}")
        return MatchResult(media_path, None, 'none', 0.0)
    
    def _try_edited_match(self, media_path: Path) -> Optional[Path]:
        """Try to match edited file variants."""
        stem = media_path.stem
        ext = media_path.suffix
        directory = media_path.parent
        
        for pattern in self.EDITED_PATTERNS:
            if re.search(pattern, stem, re.IGNORECASE):
                # Remove the edited suffix
                original_stem = re.sub(pattern, '', stem, flags=re.IGNORECASE)
                # Try all JSON suffix patterns
                for json_suffix in self.json_suffixes:
                    original_json = directory / f"{original_stem}{ext}{json_suffix}"
                    if original_json.exists():
                        return original_json
        
        return None
    
    def _try_numbered_match(self, media_path: Path) -> Optional[Path]:
        """Try to match numbered duplicate files."""
        filename = media_path.name
        directory = media_path.parent
        
        match = self.NUMBERED_PATTERN.match(filename)
        if match:
            base_name = match.group(1)
            number = match.group(2)
            ext = match.group(3)
            
            # Try all JSON suffix patterns
            for json_suffix in self.json_suffixes:
                # Try: photo(1).jpg.json
                numbered_json = directory / f"{base_name}{number}{ext}{json_suffix}"
                if numbered_json.exists():
                    return numbered_json
                
                # Try: photo.jpg(1).json (Google sometimes does this)
                alt_json = directory / f"{base_name}{ext}{number}{json_suffix}"
                if alt_json.exists():
                    return alt_json
                
                # Try: photo.jpg.json (fall back to original without number)
                base_json = directory / f"{base_name}{ext}{json_suffix}"
                if base_json.exists():
                    return base_json
        
        return None
    
    def _try_truncated_match(self, media_path: Path) -> Optional[Path]:
        """Try to match files that may have been truncated by Google."""
        stem = media_path.stem
        ext = media_path.suffix
        directory = media_path.parent
        
        # If the filename (without extension) is exactly at the limit,
        # it might be truncated
        if len(stem) >= self.GOOGLE_FILENAME_LIMIT - 1:
            # Look for JSON files that start with the truncated name
            json_files = self._get_json_files_in_directory(directory)
            
            truncated_stem = stem[:self.GOOGLE_FILENAME_LIMIT - 5]  # Leave room for variation
            
            for json_file in json_files:
                json_stem = json_file.stem  # e.g., "verylongfilename.jpg" from "verylongfilename.jpg.json"
                
                # Check if the JSON file's media name starts with our truncated name
                if json_stem.startswith(truncated_stem):
                    # Verify the extension matches
                    potential_ext = Path(json_stem).suffix.lower()
                    if potential_ext == ext.lower():
                        return json_file
        
        return None
    
    def _try_supplementary_match(self, media_path: Path) -> Optional[Path]:
        """Try to match supplementary files (effects, animations, collages)."""
        stem = media_path.stem
        ext = media_path.suffix
        directory = media_path.parent
        
        # Common Google Photos supplementary suffixes
        suffixes = ['-EFFECTS', '-ANIMATION', '-COLLAGE', '-PANO', '-MOTION']
        
        for suffix in suffixes:
            if stem.upper().endswith(suffix):
                # Try to find the original file's JSON
                original_stem = stem[:-len(suffix)]
                for json_suffix in self.json_suffixes:
                    original_json = directory / f"{original_stem}{ext}{json_suffix}"
                    if original_json.exists():
                        return original_json
        
        return None
    
    def find_all_matches(self, directory: Path, recursive: bool = True) -> List[MatchResult]:
        """
        Find all media files and their JSON matches in a directory.
        
        Args:
            directory: Directory to search
            recursive: Whether to search recursively
            
        Returns:
            List of MatchResult objects
        """
        results = []
        
        if recursive:
            media_files = [
                f for f in directory.rglob("*")
                if f.is_file() and self.is_media_file(f)
            ]
        else:
            media_files = [
                f for f in directory.iterdir()
                if f.is_file() and self.is_media_file(f)
            ]
        
        logger.info(f"Found {len(media_files)} media files to process")
        
        for media_file in media_files:
            result = self.find_json_for_media(media_file)
            results.append(result)
        
        # Log statistics
        matched = sum(1 for r in results if r.json_path is not None)
        logger.info(f"Matched {matched}/{len(results)} media files with JSON metadata")
        
        return results
    
    def find_orphaned_json_files(self, directory: Path, recursive: bool = True) -> List[Path]:
        """
        Find JSON files that don't have a corresponding media file.
        These might be leftover after the media was deleted.
        
        Args:
            directory: Directory to search
            recursive: Whether to search recursively
            
        Returns:
            List of orphaned JSON file paths
        """
        orphaned = []
        
        if recursive:
            json_files = list(directory.rglob("*.json"))
        else:
            json_files = list(directory.glob("*.json"))
        
        for json_file in json_files:
            if not self.is_json_metadata_file(json_file):
                continue
            
            # Get the media filename from the JSON filename
            # Handle different patterns:
            # - photo.jpg.json -> photo.jpg
            # - photo.jpg.supplemental-met.json -> photo.jpg
            # - photo.jpg.supplemental-metadata.json -> photo.jpg
            json_name = json_file.name
            media_name = None
            
            for suffix in self.json_suffixes:
                if json_name.endswith(suffix):
                    media_name = json_name[:-len(suffix)]
                    break
            
            if media_name is None:
                continue
                
            media_path = json_file.parent / media_name
            
            if not media_path.exists():
                orphaned.append(json_file)
        
        logger.info(f"Found {len(orphaned)} orphaned JSON files")
        return orphaned
    
    def clear_cache(self):
        """Clear the internal JSON file cache."""
        self._json_cache.clear()


def find_media_json_pairs(
    directory: str,
    recursive: bool = True
) -> List[Tuple[Path, Optional[Path]]]:
    """
    Convenience function to find all media files and their JSON pairs.
    
    Args:
        directory: Directory to search
        recursive: Whether to search recursively
        
    Returns:
        List of (media_path, json_path) tuples
    """
    matcher = MediaFileMatcher()
    results = matcher.find_all_matches(Path(directory), recursive)
    return [(r.media_path, r.json_path) for r in results]
