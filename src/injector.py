"""
Metadata Injector Module

Injects metadata from Google Takeout JSON files back into media files.
Uses ExifTool for reliable cross-format metadata writing.
Supports bundled ExifTool for standalone executable distribution.
"""

import os
import sys
import subprocess
import shutil
import logging
import platform
import tempfile
import stat
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from .parser import MediaMetadata
from .matcher import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

logger = logging.getLogger(__name__)


def get_bundled_exiftool_path() -> Optional[str]:
    """
    Get the path to the bundled ExifTool executable.
    When running as a PyInstaller bundle, ExifTool is extracted to a temp directory.
    
    Returns:
        Path to bundled ExifTool or None if not bundled
    """
    # Check if running as a PyInstaller bundle
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        bundle_dir = sys._MEIPASS
    else:
        # Running as script - check if exiftool is in the project
        bundle_dir = Path(__file__).parent.parent / 'exiftool'
        if not bundle_dir.exists():
            return None
    
    # Determine the ExifTool executable name based on platform
    if platform.system() == 'Windows':
        exiftool_name = 'exiftool.exe'
    else:
        exiftool_name = 'exiftool'
    
    exiftool_path = Path(bundle_dir) / exiftool_name
    
    if exiftool_path.exists():
        # Ensure it's executable on Unix systems
        if platform.system() != 'Windows':
            try:
                exiftool_path.chmod(exiftool_path.stat().st_mode | stat.S_IEXEC)
            except Exception:
                pass
        return str(exiftool_path)
    
    # Check for Perl-based ExifTool (exiftool script + lib folder)
    exiftool_script = Path(bundle_dir) / 'exiftool'
    exiftool_lib = Path(bundle_dir) / 'lib'
    
    if exiftool_script.exists() and exiftool_lib.exists():
        if platform.system() != 'Windows':
            try:
                exiftool_script.chmod(exiftool_script.stat().st_mode | stat.S_IEXEC)
            except Exception:
                pass
        return str(exiftool_script)
    
    return None


@dataclass
class InjectionResult:
    """Result of metadata injection."""
    media_path: Path
    success: bool
    message: str
    metadata_applied: Dict[str, Any]


class ExifToolNotFoundError(Exception):
    """Raised when ExifTool is not found on the system."""
    pass


class MetadataInjector:
    """Injects metadata into media files using ExifTool."""
    
    def __init__(
        self,
        exiftool_path: Optional[str] = None,
        update_file_dates: bool = True,
        overwrite_existing: bool = False
    ):
        """
        Initialize the metadata injector.
        
        Args:
            exiftool_path: Custom path to ExifTool executable
            update_file_dates: Whether to update file system dates
            overwrite_existing: Whether to overwrite existing metadata
        """
        self.exiftool_path = exiftool_path or self._find_exiftool()
        self.update_file_dates = update_file_dates
        self.overwrite_existing = overwrite_existing
        self.success_count = 0
        self.failure_count = 0
        
        # Verify ExifTool is available
        if not self._verify_exiftool():
            raise ExifToolNotFoundError(
                "ExifTool not found. Please install it:\n"
                "  - Windows: Download from https://exiftool.org/ and add to PATH\n"
                "  - Linux: sudo apt-get install exiftool\n"
                "  - macOS: brew install exiftool\n"
                "  - Synology: Install via package or Docker"
            )
    
    def _find_exiftool(self) -> str:
        """Find ExifTool executable on the system."""
        # First, check for bundled ExifTool
        bundled_path = get_bundled_exiftool_path()
        if bundled_path:
            logger.debug(f"Found bundled ExifTool at: {bundled_path}")
            return bundled_path
        
        # Common names for the executable
        names = ['exiftool', 'exiftool.exe']
        
        # Check if it's in PATH
        for name in names:
            path = shutil.which(name)
            if path:
                return path
        
        # Check common installation locations
        common_paths = []
        
        if platform.system() == 'Windows':
            common_paths = [
                r'C:\Windows\exiftool.exe',
                r'C:\Program Files\exiftool\exiftool.exe',
                r'C:\exiftool\exiftool.exe',
                os.path.expanduser(r'~\exiftool\exiftool.exe'),
            ]
        elif platform.system() == 'Darwin':  # macOS
            common_paths = [
                '/usr/local/bin/exiftool',
                '/opt/homebrew/bin/exiftool',
            ]
        else:  # Linux/Synology
            common_paths = [
                '/usr/bin/exiftool',
                '/usr/local/bin/exiftool',
                '/opt/bin/exiftool',
                '/volume1/@appstore/exiftool/exiftool',  # Synology
            ]
        
        for path in common_paths:
            if os.path.isfile(path):
                return path
        
        return 'exiftool'  # Hope it's in PATH
    
    def _verify_exiftool(self) -> bool:
        """Verify that ExifTool is available and working."""
        try:
            result = subprocess.run(
                [self.exiftool_path, '-ver'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                logger.info(f"ExifTool version {version} found at {self.exiftool_path}")
                return True
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            logger.warning("ExifTool verification timed out")
        except Exception as e:
            logger.warning(f"Error verifying ExifTool: {e}")
        
        return False
    
    def inject_metadata(
        self,
        media_path: Path,
        metadata: MediaMetadata
    ) -> InjectionResult:
        """
        Inject metadata into a media file.
        
        Args:
            media_path: Path to the media file
            metadata: MediaMetadata object with values to inject
            
        Returns:
            InjectionResult with details of the operation
        """
        if not media_path.exists():
            return InjectionResult(
                media_path, False, "File does not exist", {}
            )
        
        if not metadata.has_useful_metadata():
            return InjectionResult(
                media_path, True, "No useful metadata to inject", {}
            )
        
        try:
            # Build ExifTool arguments
            args = self._build_exiftool_args(media_path, metadata)
            
            if not args:
                return InjectionResult(
                    media_path, True, "No metadata arguments generated", {}
                )
            
            # Run ExifTool
            cmd = [self.exiftool_path] + args + [str(media_path)]
            
            logger.debug(f"Running: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                # Update file system dates if requested
                if self.update_file_dates and metadata.best_date:
                    self._update_file_dates(media_path, metadata.best_date)
                
                self.success_count += 1
                
                return InjectionResult(
                    media_path,
                    True,
                    f"Successfully updated metadata",
                    metadata.to_exif_dict()
                )
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.warning(f"ExifTool error for {media_path}: {error_msg}")
                self.failure_count += 1
                
                return InjectionResult(
                    media_path, False, f"ExifTool error: {error_msg}", {}
                )
                
        except subprocess.TimeoutExpired:
            self.failure_count += 1
            return InjectionResult(
                media_path, False, "ExifTool operation timed out", {}
            )
        except Exception as e:
            self.failure_count += 1
            logger.error(f"Error injecting metadata into {media_path}: {e}")
            return InjectionResult(
                media_path, False, f"Error: {str(e)}", {}
            )
    
    def _build_exiftool_args(
        self,
        media_path: Path,
        metadata: MediaMetadata
    ) -> List[str]:
        """
        Build ExifTool command-line arguments.
        
        Args:
            media_path: Path to the media file
            metadata: Metadata to inject
            
        Returns:
            List of command-line arguments
        """
        args = [
            '-overwrite_original',  # Don't create backup files
            '-ignoreMinorErrors',   # Continue on minor errors
        ]
        
        is_video = media_path.suffix.lower() in VIDEO_EXTENSIONS
        
        # Date/Time
        if metadata.best_date:
            date_str = metadata.best_date.strftime("%Y:%m:%d %H:%M:%S")
            
            if is_video:
                # Video date tags
                args.extend([
                    f'-CreateDate={date_str}',
                    f'-ModifyDate={date_str}',
                    f'-MediaCreateDate={date_str}',
                    f'-MediaModifyDate={date_str}',
                    f'-TrackCreateDate={date_str}',
                    f'-TrackModifyDate={date_str}',
                ])
                
                # QuickTime-specific (MP4, MOV)
                if media_path.suffix.lower() in {'.mp4', '.mov', '.m4v'}:
                    args.extend([
                        f'-QuickTime:CreateDate={date_str}',
                        f'-QuickTime:ModifyDate={date_str}',
                    ])
            else:
                # Image date tags
                args.extend([
                    f'-DateTimeOriginal={date_str}',
                    f'-CreateDate={date_str}',
                    f'-ModifyDate={date_str}',
                ])
                
                # IPTC date (for compatibility)
                iptc_date = metadata.best_date.strftime("%Y%m%d")
                iptc_time = metadata.best_date.strftime("%H%M%S")
                args.extend([
                    f'-IPTC:DateCreated={iptc_date}',
                    f'-IPTC:TimeCreated={iptc_time}',
                ])
        
        # GPS Location
        geo = metadata.best_geo_location
        if geo.is_valid():
            lat_ref = "N" if geo.latitude >= 0 else "S"
            lon_ref = "E" if geo.longitude >= 0 else "W"
            
            args.extend([
                f'-GPSLatitude={abs(geo.latitude)}',
                f'-GPSLatitudeRef={lat_ref}',
                f'-GPSLongitude={abs(geo.longitude)}',
                f'-GPSLongitudeRef={lon_ref}',
            ])
            
            if geo.altitude != 0:
                alt_ref = 0 if geo.altitude >= 0 else 1
                args.extend([
                    f'-GPSAltitude={abs(geo.altitude)}',
                    f'-GPSAltitudeRef={alt_ref}',
                ])
        
        # Description
        if metadata.description:
            # Escape special characters
            desc = metadata.description.replace('"', '\\"')
            args.extend([
                f'-ImageDescription={desc}',
                f'-Description={desc}',
                f'-Caption-Abstract={desc}',
            ])
            
            # XPComment for Windows
            if not is_video:
                args.append(f'-XPComment={desc}')
        
        return args
    
    def _update_file_dates(self, file_path: Path, date: datetime):
        """
        Update file system creation and modification dates.
        
        Args:
            file_path: Path to the file
            date: Date to set
        """
        try:
            timestamp = date.timestamp()
            os.utime(file_path, (timestamp, timestamp))
            logger.debug(f"Updated file dates for {file_path}")
        except Exception as e:
            logger.warning(f"Could not update file dates for {file_path}: {e}")
    
    def inject_metadata_batch(
        self,
        media_metadata_pairs: List[tuple]
    ) -> List[InjectionResult]:
        """
        Inject metadata into multiple files.
        
        Args:
            media_metadata_pairs: List of (media_path, metadata) tuples
            
        Returns:
            List of InjectionResult objects
        """
        results = []
        
        for media_path, metadata in media_metadata_pairs:
            result = self.inject_metadata(media_path, metadata)
            results.append(result)
        
        return results


class FallbackMetadataInjector:
    """
    Fallback metadata injector using Pillow for images.
    Used when ExifTool is not available.
    Limited functionality compared to ExifTool.
    """
    
    def __init__(self, update_file_dates: bool = True):
        """Initialize the fallback injector."""
        self.update_file_dates = update_file_dates
        self.success_count = 0
        self.failure_count = 0
    
    def inject_metadata(
        self,
        media_path: Path,
        metadata: MediaMetadata
    ) -> InjectionResult:
        """
        Inject metadata using Pillow (limited to file dates only).
        
        Args:
            media_path: Path to the media file
            metadata: MediaMetadata object
            
        Returns:
            InjectionResult with details
        """
        if not media_path.exists():
            return InjectionResult(
                media_path, False, "File does not exist", {}
            )
        
        # Fallback can only update file dates
        if self.update_file_dates and metadata.best_date:
            try:
                timestamp = metadata.best_date.timestamp()
                os.utime(media_path, (timestamp, timestamp))
                self.success_count += 1
                
                return InjectionResult(
                    media_path,
                    True,
                    "Updated file dates only (ExifTool not available)",
                    {"file_date": str(metadata.best_date)}
                )
            except Exception as e:
                self.failure_count += 1
                return InjectionResult(
                    media_path, False, f"Error: {str(e)}", {}
                )
        
        return InjectionResult(
            media_path,
            False,
            "No metadata injection possible without ExifTool",
            {}
        )


def create_injector(
    exiftool_path: Optional[str] = None,
    update_file_dates: bool = True,
    overwrite_existing: bool = False,
    fallback_to_basic: bool = True
) -> MetadataInjector:
    """
    Create the best available metadata injector.
    
    Args:
        exiftool_path: Custom path to ExifTool
        update_file_dates: Whether to update file system dates
        overwrite_existing: Whether to overwrite existing metadata
        fallback_to_basic: Whether to use fallback injector if ExifTool not found
        
    Returns:
        MetadataInjector or FallbackMetadataInjector
    """
    try:
        return MetadataInjector(
            exiftool_path=exiftool_path,
            update_file_dates=update_file_dates,
            overwrite_existing=overwrite_existing
        )
    except ExifToolNotFoundError:
        if fallback_to_basic:
            logger.warning("ExifTool not found, using fallback injector (limited functionality)")
            return FallbackMetadataInjector(update_file_dates=update_file_dates)
        raise
