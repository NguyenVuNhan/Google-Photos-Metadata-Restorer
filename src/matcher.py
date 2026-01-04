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
    
    # Google often truncates filenames at around 51 characters (total including extension)
    GOOGLE_FILENAME_LIMIT = 51
    
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
    
    def __init__(self):
        """Initialize the matcher."""
        self.matched_count = 0
        self.unmatched_count = 0
        self._json_cache: Dict[Path, List[Path]] = {}
    
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
        Handles truncated filenames where Google cuts off part of the name.
        """
        if path.suffix.lower() != '.json':
            return False
        
        filename = path.name
        
        # Remove .json suffix to get the base
        base = filename[:-5]  # Remove '.json'
        
        # Check if it looks like a media filename (possibly truncated)
        # Look for common image/video extension patterns anywhere in the name
        # because Google may truncate: "photo.jpg" -> "photo.j" or "photo.jp"
        ext_patterns = [ext.lstrip('.') for ext in MEDIA_EXTENSIONS]
        
        for ext in ext_patterns:
            # Check for full extension
            if base.lower().endswith(f'.{ext}'):
                return True
            # Check for truncated extensions (at least 1 char after the dot)
            for i in range(1, len(ext)):
                if base.lower().endswith(f'.{ext[:i]}'):
                    return True
        
        # Also check for supplemental metadata patterns
        # e.g., "photo.jpg.supplemental-met" or "photo.jpg.supplem"
        if '.supplemental' in base.lower() or '.supplem' in base.lower():
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
        
        # Strategy 1: Exact match (photo.jpg -> photo.jpg.json)
        exact_json = directory / f"{filename}.json"
        if exact_json.exists():
            self.matched_count += 1
            return MatchResult(media_path, exact_json, 'exact', 1.0)
        
        # Strategy 2: Truncated filename match
        # Google truncates long filenames, so we look for JSON files that 
        # start with a truncated version of our media filename
        json_path = self._try_truncated_match(media_path)
        if json_path:
            self.matched_count += 1
            return MatchResult(media_path, json_path, 'truncated', 0.95)
        
        # Strategy 3: Handle edited files (photo-edited.jpg -> photo.jpg.json)
        json_path = self._try_edited_match(media_path)
        if json_path:
            self.matched_count += 1
            return MatchResult(media_path, json_path, 'edited', 0.9)
        
        # Strategy 4: Handle numbered duplicates (photo(1).jpg -> photo.jpg.json or photo(1).jpg.json)
        json_path = self._try_numbered_match(media_path)
        if json_path:
            self.matched_count += 1
            return MatchResult(media_path, json_path, 'numbered', 0.85)
        
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
                original_json = directory / f"{original_stem}{ext}.json"
                if original_json.exists():
                    return original_json
                # Also try truncated match for the original
                original_media = directory / f"{original_stem}{ext}"
                if not original_media.exists():
                    # Create a fake path for truncated matching
                    original_media = media_path.parent / f"{original_stem}{ext}"
                return self._try_truncated_match(original_media)
        
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
            
            # Try: photo(1).jpg.json
            numbered_json = directory / f"{base_name}{number}{ext}.json"
            if numbered_json.exists():
                return numbered_json
            
            # Try: photo.jpg(1).json (Google sometimes does this)
            alt_json = directory / f"{base_name}{ext}{number}.json"
            if alt_json.exists():
                return alt_json
            
            # Try: photo.jpg.json (fall back to original without number)
            base_json = directory / f"{base_name}{ext}.json"
            if base_json.exists():
                return base_json
            
            # Try truncated matching for numbered files
            return self._try_truncated_match(media_path)
        
        return None
    
    def _try_truncated_match(self, media_path: Path) -> Optional[Path]:
        """
        Try to match files where Google has truncated the JSON filename.
        
        Google Takeout truncates long filenames at around 51 characters total.
        Examples:
        - "Screenshot_20210414-123045_Google Play Store.jpg" 
          -> "Screenshot_20210414-123045_Google Play Store.j.json" (truncated .jpg to .j)
        - "Screenshot_20210608-182630_Samsung Experience H.jpg"
          -> "Screenshot_20210608-182630_Samsung Experience .json" (truncated before extension)
        """
        directory = media_path.parent
        media_filename = media_path.name  # e.g., "Screenshot_20210414-123045_Google Play Store.jpg"
        
        # Get all JSON files in the directory
        json_files = self._get_json_files_in_directory(directory)
        
        if not json_files:
            return None
        
        # For each JSON file, check if the media filename starts with 
        # what the JSON filename represents (minus .json suffix)
        best_match = None
        best_match_len = 0
        
        for json_file in json_files:
            json_name = json_file.name  # e.g., "Screenshot_20210414-123045_Google Play Store.j.json"
            
            # Remove .json suffix to get the truncated media name
            if not json_name.lower().endswith('.json'):
                continue
            
            truncated_name = json_name[:-5]  # Remove '.json'
            
            # Handle supplemental metadata patterns
            # e.g., "photo.jpg.supplem" should match "photo.jpg"
            supplem_patterns = ['.supplemental-metadata', '.supplemental-met', '.supplemental', '.supplem', '.supple', '.suppl', '.supp', '.sup', '.su', '.s']
            for pattern in supplem_patterns:
                if truncated_name.lower().endswith(pattern):
                    truncated_name = truncated_name[:-len(pattern)]
                    break
            
            # Check if our media filename starts with the truncated name
            # The truncated name might be missing part of the extension or filename
            if len(truncated_name) < 5:  # Too short to be meaningful
                continue
            
            # Check if media filename starts with the truncated JSON base
            if media_filename.lower().startswith(truncated_name.lower()):
                # This is a potential match - prefer longer matches
                if len(truncated_name) > best_match_len:
                    best_match = json_file
                    best_match_len = len(truncated_name)
            
            # Also check if the truncated name is a prefix of our full filename
            # Handle case: "photo.j" matches "photo.jpg"
            elif truncated_name.lower().rstrip() == media_filename[:len(truncated_name.rstrip())].lower():
                if len(truncated_name) > best_match_len:
                    best_match = json_file
                    best_match_len = len(truncated_name)
        
        return best_match
    
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
                original_json = directory / f"{original_stem}{ext}.json"
                if original_json.exists():
                    return original_json
                # Also try truncated match
                original_media = directory / f"{original_stem}{ext}"
                return self._try_truncated_match(original_media)
        
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
            # Handle truncated names by extracting the base
            json_name = json_file.name
            
            if not json_name.lower().endswith('.json'):
                continue
            
            # Remove .json suffix
            base = json_name[:-5]
            
            # Remove supplemental metadata suffix if present
            supplem_patterns = ['.supplemental-metadata', '.supplemental-met', '.supplemental', 
                              '.supplem', '.supple', '.suppl', '.supp', '.sup', '.su', '.s']
            for pattern in supplem_patterns:
                if base.lower().endswith(pattern):
                    base = base[:-len(pattern)]
                    break
            
            # Check if any media file in the directory starts with this base
            # (to handle truncated filenames)
            has_match = False
            for media_file in json_file.parent.iterdir():
                if media_file.is_file() and self.is_media_file(media_file):
                    if media_file.name.lower().startswith(base.lower().rstrip()):
                        has_match = True
                        break
            
            if not has_match:
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
