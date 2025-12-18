"""
Main Entry Point

CLI interface for the Google Photos Metadata Restorer.
Supports both command-line arguments and YAML configuration files.
"""

import os
import sys
import time
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import yaml
from tqdm import tqdm

from .extractor import ZipExtractor
from .parser import GoogleTakeoutParser
from .matcher import MediaFileMatcher
from .injector import MetadataInjector, ExifToolNotFoundError, create_injector
from .cleaner import JsonCleaner
from .utils import (
    setup_logging, format_duration, format_size,
    count_files_by_extension, is_synology
)

# Version info
__version__ = "1.0.0"

logger = logging.getLogger(__name__)


class MetadataRestorer:
    """Main class for restoring Google Photos metadata."""
    
    def __init__(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
        extract_zips: bool = False,
        delete_zips: bool = False,
        delete_json: bool = True,
        update_file_dates: bool = True,
        dry_run: bool = False,
        exiftool_path: Optional[str] = None
    ):
        """
        Initialize the metadata restorer.
        
        Args:
            input_path: Path to Google Takeout folder or ZIP files
            output_path: Path for extracted files (if extracting ZIPs)
            extract_zips: Whether to extract ZIP files first
            delete_zips: Whether to delete ZIPs after extraction
            delete_json: Whether to delete JSON files after processing
            update_file_dates: Whether to update file system dates
            dry_run: If True, don't make any changes
            exiftool_path: Custom path to ExifTool
        """
        self.input_path = input_path
        self.output_path = output_path or input_path
        self.extract_zips = extract_zips
        self.delete_zips = delete_zips
        self.delete_json = delete_json
        self.update_file_dates = update_file_dates
        self.dry_run = dry_run
        self.exiftool_path = exiftool_path
        
        # Statistics
        self.stats = {
            "start_time": None,
            "end_time": None,
            "zips_extracted": 0,
            "media_files_found": 0,
            "media_files_matched": 0,
            "metadata_injected": 0,
            "injection_failed": 0,
            "json_files_deleted": 0,
        }
    
    def run(self) -> dict:
        """
        Run the full metadata restoration process.
        
        Returns:
            Dictionary with statistics and results
        """
        self.stats["start_time"] = time.time()
        
        logger.info("=" * 60)
        logger.info("Google Photos Metadata Restorer")
        logger.info("=" * 60)
        
        if self.dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
        
        working_path = self.input_path
        
        # Step 1: Extract ZIPs if requested
        if self.extract_zips:
            working_path = self._extract_zips()
            if working_path is None:
                logger.error("ZIP extraction failed")
                return self.stats
        
        # Step 2: Find and match media files with JSON
        matches = self._find_and_match_files(working_path)
        
        if not matches:
            logger.warning("No media files found to process")
            return self.stats
        
        # Step 3: Inject metadata
        processed_json_files = self._inject_metadata(matches)
        
        # Step 4: Clean up JSON files
        if self.delete_json and processed_json_files:
            self._cleanup_json_files(processed_json_files)
        
        # Final statistics
        self.stats["end_time"] = time.time()
        self._print_summary()
        
        return self.stats
    
    def _extract_zips(self) -> Optional[Path]:
        """Extract ZIP files."""
        logger.info("-" * 40)
        logger.info("Step 1: Extracting ZIP files")
        logger.info("-" * 40)
        
        extractor = ZipExtractor(delete_after_extraction=self.delete_zips)
        
        # Preserve folder structure as requested
        results = extractor.extract_all(
            self.input_path,
            self.output_path,
            preserve_structure=True
        )
        
        self.stats["zips_extracted"] = results["successful"]
        
        if results["successful"] == 0 and results["total"] > 0:
            return None
        
        return self.output_path
    
    def _find_and_match_files(self, path: Path) -> list:
        """Find media files and match with JSON."""
        logger.info("-" * 40)
        logger.info("Step 2: Finding and matching files")
        logger.info("-" * 40)
        
        matcher = MediaFileMatcher()
        matches = matcher.find_all_matches(path, recursive=True)
        
        self.stats["media_files_found"] = len(matches)
        self.stats["media_files_matched"] = sum(
            1 for m in matches if m.json_path is not None
        )
        
        logger.info(f"Found {self.stats['media_files_found']} media files")
        logger.info(f"Matched {self.stats['media_files_matched']} with JSON metadata")
        
        # Show file type breakdown
        ext_counts = count_files_by_extension(path)
        media_exts = {k: v for k, v in ext_counts.items() 
                      if k in {'.jpg', '.jpeg', '.png', '.heic', '.mp4', '.mov', '.gif'}}
        if media_exts:
            logger.info("Media file breakdown:")
            for ext, count in list(media_exts.items())[:5]:
                logger.info(f"  {ext}: {count}")
        
        return matches
    
    def _inject_metadata(self, matches: list) -> list:
        """Inject metadata into media files."""
        logger.info("-" * 40)
        logger.info("Step 3: Injecting metadata")
        logger.info("-" * 40)
        
        # Create injector
        try:
            injector = create_injector(
                exiftool_path=self.exiftool_path,
                update_file_dates=self.update_file_dates,
                fallback_to_basic=True
            )
        except ExifToolNotFoundError as e:
            logger.error(str(e))
            return []
        
        parser = GoogleTakeoutParser()
        processed_json_files = []
        
        # Filter to only matched files
        matched_items = [m for m in matches if m.json_path is not None]
        
        if not matched_items:
            logger.info("No files with JSON metadata to process")
            return []
        
        # Process with progress bar
        for match in tqdm(matched_items, desc="Injecting metadata", unit="files"):
            try:
                # Parse the JSON metadata
                metadata = parser.parse_json_file(match.json_path)
                
                if metadata is None:
                    logger.warning(f"Could not parse: {match.json_path}")
                    continue
                
                if not metadata.has_useful_metadata():
                    logger.debug(f"No useful metadata in: {match.json_path}")
                    processed_json_files.append(match.json_path)
                    continue
                
                # Inject metadata (unless dry run)
                if self.dry_run:
                    logger.debug(f"Would inject metadata into: {match.media_path}")
                    self.stats["metadata_injected"] += 1
                else:
                    result = injector.inject_metadata(match.media_path, metadata)
                    
                    if result.success:
                        self.stats["metadata_injected"] += 1
                    else:
                        self.stats["injection_failed"] += 1
                        logger.warning(f"Failed: {match.media_path} - {result.message}")
                
                processed_json_files.append(match.json_path)
                
            except Exception as e:
                logger.error(f"Error processing {match.media_path}: {e}")
                self.stats["injection_failed"] += 1
        
        logger.info(f"Successfully injected metadata into {self.stats['metadata_injected']} files")
        
        if self.stats["injection_failed"] > 0:
            logger.warning(f"Failed to inject metadata into {self.stats['injection_failed']} files")
        
        return processed_json_files
    
    def _cleanup_json_files(self, json_files: list):
        """Clean up JSON files after processing."""
        logger.info("-" * 40)
        logger.info("Step 4: Cleaning up JSON files")
        logger.info("-" * 40)
        
        cleaner = JsonCleaner(dry_run=self.dry_run)
        result = cleaner.delete_json_files(json_files)
        
        self.stats["json_files_deleted"] = result.deleted_count
        
        if self.dry_run:
            logger.info(f"Would delete {result.deleted_count} JSON files")
        else:
            logger.info(f"Deleted {result.deleted_count} JSON files")
    
    def _print_summary(self):
        """Print final summary."""
        duration = self.stats["end_time"] - self.stats["start_time"]
        
        logger.info("=" * 60)
        logger.info("SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Duration: {format_duration(duration)}")
        
        if self.extract_zips:
            logger.info(f"ZIP files extracted: {self.stats['zips_extracted']}")
        
        logger.info(f"Media files found: {self.stats['media_files_found']}")
        logger.info(f"Media files with metadata: {self.stats['media_files_matched']}")
        logger.info(f"Metadata successfully injected: {self.stats['metadata_injected']}")
        
        if self.stats["injection_failed"] > 0:
            logger.info(f"Metadata injection failed: {self.stats['injection_failed']}")
        
        if self.delete_json:
            logger.info(f"JSON files {'would be ' if self.dry_run else ''}deleted: {self.stats['json_files_deleted']}")
        
        logger.info("=" * 60)


def load_config_file(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from a YAML file.
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        Dictionary with configuration values
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config or {}
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in configuration file: {e}")


def merge_args_with_config(args: argparse.Namespace, config: Dict[str, Any]) -> argparse.Namespace:
    """
    Merge command-line arguments with config file values.
    Command-line arguments take precedence.
    
    Args:
        args: Parsed command-line arguments
        config: Configuration dictionary from file
        
    Returns:
        Merged argparse.Namespace
    """
    # Mapping from config file keys to argparse attribute names
    config_mapping = {
        'input_folder': 'input',
        'output_folder': 'output',
        'extract_zips': 'extract',
        'delete_zips_after_extraction': 'delete_zips',
        'delete_json_after_processing': 'delete_json',
        'update_file_dates': 'update_file_dates',
        'dry_run': 'dry_run',
        'exiftool_path': 'exiftool',
        'log_level': 'log_level',
        'log_file': 'log_file',
    }
    
    for config_key, arg_key in config_mapping.items():
        if config_key in config:
            config_value = config[config_key]
            current_value = getattr(args, arg_key, None)
            
            # Only use config value if arg wasn't explicitly set
            # For boolean flags, check if they're False (default)
            # For strings, check if they're None (default)
            if current_value is None or (isinstance(current_value, bool) and not current_value):
                setattr(args, arg_key, config_value)
    
    # Handle inverted flags
    if 'delete_json_after_processing' in config:
        args.keep_json = not config['delete_json_after_processing']
    if 'update_file_dates' in config:
        args.no_file_dates = not config['update_file_dates']
    
    return args


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Restore metadata from Google Takeout JSON files to media files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a Google Takeout folder
  metadata-restorer --input /path/to/Takeout

  # Use a configuration file
  metadata-restorer --config /path/to/config.yaml

  # Extract ZIPs first, then process
  metadata-restorer --input /path/to/zips --extract --output /path/to/extracted

  # Dry run to see what would happen
  metadata-restorer --input /path/to/Takeout --dry-run

  # Keep JSON files after processing
  metadata-restorer --input /path/to/Takeout --keep-json

  # Synology example
  metadata-restorer --input /volume1/GoogleTakeout --output /volume1/photo
        """
    )
    
    parser.add_argument(
        '--version', '-v',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        help='Path to YAML configuration file'
    )
    
    parser.add_argument(
        '--input', '-i',
        type=str,
        default=None,
        help='Input path (Google Takeout folder or directory with ZIP files)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='Output path for extracted files (default: same as input)'
    )
    
    parser.add_argument(
        '--extract', '-e',
        action='store_true',
        help='Extract ZIP files before processing'
    )
    
    parser.add_argument(
        '--delete-zips',
        action='store_true',
        help='Delete ZIP files after extraction'
    )
    
    parser.add_argument(
        '--keep-json', '-k',
        action='store_true',
        help='Keep JSON files after processing (default: delete them)'
    )
    
    parser.add_argument(
        '--no-file-dates',
        action='store_true',
        help='Do not update file system dates'
    )
    
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would be done without making changes'
    )
    
    parser.add_argument(
        '--exiftool',
        type=str,
        default=None,
        help='Path to ExifTool executable'
    )
    
    parser.add_argument(
        '--log-level', '-l',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    parser.add_argument(
        '--log-file',
        type=str,
        default=None,
        help='Log file path'
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    # Load config file if specified
    config = {}
    if args.config:
        try:
            config = load_config_file(args.config)
            args = merge_args_with_config(args, config)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Validate that input is provided (either via args or config)
    if not args.input:
        print("Error: --input is required (or specify in config file)", file=sys.stderr)
        sys.exit(1)
    
    # Setup logging
    setup_logging(
        level=args.log_level,
        log_file=args.log_file
    )
    
    logger.info(f"Google Photos Metadata Restorer v{__version__}")
    
    # Validate input path
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input path does not exist: {input_path}")
        sys.exit(1)
    
    # Setup output path
    output_path = Path(args.output) if args.output else None
    
    # Check if running on Synology
    if is_synology():
        logger.info("Detected Synology NAS environment")
    
    # Create and run restorer
    try:
        restorer = MetadataRestorer(
            input_path=input_path,
            output_path=output_path,
            extract_zips=args.extract,
            delete_zips=args.delete_zips,
            delete_json=not args.keep_json,
            update_file_dates=not args.no_file_dates,
            dry_run=args.dry_run,
            exiftool_path=args.exiftool
        )
        
        stats = restorer.run()
        
        # Exit with error if there were failures
        if stats.get("injection_failed", 0) > 0:
            sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if args.log_level == 'DEBUG':
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
