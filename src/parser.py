"""
JSON Metadata Parser Module

Parses Google Takeout JSON metadata files and extracts relevant information.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GeoLocation:
    """Geographic location data."""
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    
    def is_valid(self) -> bool:
        """Check if location has valid coordinates."""
        return not (self.latitude == 0.0 and self.longitude == 0.0)
    
    def to_exif_format(self) -> Dict[str, Any]:
        """Convert to EXIF-compatible format."""
        if not self.is_valid():
            return {}
        
        # Determine reference directions
        lat_ref = "N" if self.latitude >= 0 else "S"
        lon_ref = "E" if self.longitude >= 0 else "W"
        
        return {
            "GPSLatitude": abs(self.latitude),
            "GPSLatitudeRef": lat_ref,
            "GPSLongitude": abs(self.longitude),
            "GPSLongitudeRef": lon_ref,
            "GPSAltitude": abs(self.altitude) if self.altitude else None,
            "GPSAltitudeRef": 0 if self.altitude >= 0 else 1  # 0 = above sea level
        }


@dataclass
class MediaMetadata:
    """Parsed metadata from Google Takeout JSON."""
    title: str = ""
    description: str = ""
    creation_time: Optional[datetime] = None
    photo_taken_time: Optional[datetime] = None
    geo_location: GeoLocation = field(default_factory=GeoLocation)
    geo_location_exif: GeoLocation = field(default_factory=GeoLocation)
    people: list = field(default_factory=list)
    url: str = ""
    original_json: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def best_date(self) -> Optional[datetime]:
        """Get the best available date (photo taken time preferred)."""
        return self.photo_taken_time or self.creation_time
    
    @property
    def best_geo_location(self) -> GeoLocation:
        """Get the best available geo location (EXIF preferred)."""
        if self.geo_location_exif.is_valid():
            return self.geo_location_exif
        return self.geo_location
    
    def has_useful_metadata(self) -> bool:
        """Check if there's any useful metadata to restore."""
        return (
            self.best_date is not None or
            self.best_geo_location.is_valid() or
            bool(self.description)
        )
    
    def to_exif_dict(self) -> Dict[str, Any]:
        """Convert metadata to ExifTool-compatible dictionary."""
        exif_data = {}
        
        # Date/Time fields
        if self.best_date:
            date_str = self.best_date.strftime("%Y:%m:%d %H:%M:%S")
            exif_data["DateTimeOriginal"] = date_str
            exif_data["CreateDate"] = date_str
            exif_data["ModifyDate"] = date_str
            
            # For video files
            exif_data["MediaCreateDate"] = date_str
            exif_data["MediaModifyDate"] = date_str
            exif_data["TrackCreateDate"] = date_str
            exif_data["TrackModifyDate"] = date_str
        
        # GPS data
        geo = self.best_geo_location
        if geo.is_valid():
            exif_data.update(geo.to_exif_format())
        
        # Description
        if self.description:
            exif_data["ImageDescription"] = self.description
            exif_data["Description"] = self.description
            exif_data["Caption-Abstract"] = self.description  # IPTC
            exif_data["XPComment"] = self.description  # Windows
        
        return exif_data


class GoogleTakeoutParser:
    """Parser for Google Takeout JSON metadata files."""
    
    def __init__(self):
        """Initialize the parser."""
        self.parsed_count = 0
        self.failed_count = 0
    
    def parse_timestamp(self, timestamp_data: Dict[str, Any]) -> Optional[datetime]:
        """
        Parse a Google Takeout timestamp object.
        
        Args:
            timestamp_data: Dictionary with 'timestamp' and/or 'formatted' keys
            
        Returns:
            datetime object or None
        """
        if not timestamp_data:
            return None
        
        try:
            # Try to use the Unix timestamp first (most reliable)
            if "timestamp" in timestamp_data:
                ts = int(timestamp_data["timestamp"])
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            
            # Fallback to parsing the formatted string
            if "formatted" in timestamp_data:
                # Google uses format like "Jan 1, 2021, 12:00:00 AM UTC"
                formatted = timestamp_data["formatted"]
                try:
                    return datetime.strptime(formatted, "%b %d, %Y, %I:%M:%S %p %Z")
                except ValueError:
                    # Try alternative formats
                    for fmt in [
                        "%b %d, %Y, %I:%M:%S %p",
                        "%Y-%m-%d %H:%M:%S",
                        "%d/%m/%Y %H:%M:%S"
                    ]:
                        try:
                            return datetime.strptime(formatted, fmt)
                        except ValueError:
                            continue
                            
        except Exception as e:
            logger.debug(f"Failed to parse timestamp: {timestamp_data}, error: {e}")
        
        return None
    
    def parse_geo_data(self, geo_data: Dict[str, Any]) -> GeoLocation:
        """
        Parse geographic location data.
        
        Args:
            geo_data: Dictionary with latitude, longitude, altitude
            
        Returns:
            GeoLocation object
        """
        if not geo_data:
            return GeoLocation()
        
        try:
            return GeoLocation(
                latitude=float(geo_data.get("latitude", 0.0)),
                longitude=float(geo_data.get("longitude", 0.0)),
                altitude=float(geo_data.get("altitude", 0.0))
            )
        except (ValueError, TypeError) as e:
            logger.debug(f"Failed to parse geo data: {geo_data}, error: {e}")
            return GeoLocation()
    
    def parse_json_file(self, json_path: Path) -> Optional[MediaMetadata]:
        """
        Parse a Google Takeout JSON metadata file.
        
        Args:
            json_path: Path to the JSON file
            
        Returns:
            MediaMetadata object or None if parsing failed
        """
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            metadata = MediaMetadata(
                title=data.get("title", ""),
                description=data.get("description", ""),
                creation_time=self.parse_timestamp(data.get("creationTime", {})),
                photo_taken_time=self.parse_timestamp(data.get("photoTakenTime", {})),
                geo_location=self.parse_geo_data(data.get("geoData", {})),
                geo_location_exif=self.parse_geo_data(data.get("geoDataExif", {})),
                people=data.get("people", []),
                url=data.get("url", ""),
                original_json=data
            )
            
            self.parsed_count += 1
            logger.debug(f"Parsed metadata for: {metadata.title}")
            
            return metadata
            
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in {json_path}: {e}")
            self.failed_count += 1
            return None
        except Exception as e:
            logger.warning(f"Error parsing {json_path}: {e}")
            self.failed_count += 1
            return None
    
    def parse_json_string(self, json_string: str) -> Optional[MediaMetadata]:
        """
        Parse JSON metadata from a string.
        
        Args:
            json_string: JSON string content
            
        Returns:
            MediaMetadata object or None if parsing failed
        """
        try:
            data = json.loads(json_string)
            
            metadata = MediaMetadata(
                title=data.get("title", ""),
                description=data.get("description", ""),
                creation_time=self.parse_timestamp(data.get("creationTime", {})),
                photo_taken_time=self.parse_timestamp(data.get("photoTakenTime", {})),
                geo_location=self.parse_geo_data(data.get("geoData", {})),
                geo_location_exif=self.parse_geo_data(data.get("geoDataExif", {})),
                people=data.get("people", []),
                url=data.get("url", ""),
                original_json=data
            )
            
            self.parsed_count += 1
            return metadata
            
        except Exception as e:
            logger.warning(f"Error parsing JSON string: {e}")
            self.failed_count += 1
            return None


def parse_google_takeout_json(json_path: str) -> Optional[MediaMetadata]:
    """
    Convenience function to parse a Google Takeout JSON file.
    
    Args:
        json_path: Path to the JSON file
        
    Returns:
        MediaMetadata object or None
    """
    parser = GoogleTakeoutParser()
    return parser.parse_json_file(Path(json_path))
