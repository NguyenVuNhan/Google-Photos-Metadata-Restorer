"""
Unit tests for the Main module.

Tests the MetadataRestorer class including:
- ZIP extraction and delayed deletion
- Metadata injection workflow
- Cleanup behavior
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import zipfile

from src.main import MetadataRestorer


class TestMetadataRestorerZipDeletion:
    """Test ZIP deletion behavior - only delete after successful processing."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        shutil.rmtree(temp_path)
    
    def _create_test_zip(self, zip_path: Path, files: dict) -> Path:
        """
        Create a test ZIP file with specified contents.
        
        Args:
            zip_path: Path for the ZIP file
            files: Dict of {filename: content} to include in ZIP
            
        Returns:
            Path to created ZIP
        """
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for filename, content in files.items():
                zf.writestr(filename, content)
        return zip_path
    
    def _create_sample_json_metadata(self) -> str:
        """Create sample Google Takeout JSON metadata."""
        return json.dumps({
            "title": "test_photo.jpg",
            "description": "Test photo",
            "photoTakenTime": {
                "timestamp": "1609459200",
                "formatted": "Jan 1, 2021, 12:00:00 AM UTC"
            },
            "geoData": {
                "latitude": 40.7128,
                "longitude": -74.0060,
                "altitude": 10.0
            }
        })
    
    def test_zip_files_tracked_after_extraction(self, temp_dir):
        """Test that extracted ZIP files are tracked for later deletion."""
        # Create a test ZIP
        zip_path = temp_dir / "test_takeout.zip"
        self._create_test_zip(zip_path, {
            "Takeout/Google Photos/test_photo.jpg": b"fake image data",
            "Takeout/Google Photos/test_photo.jpg.json": self._create_sample_json_metadata()
        })
        
        output_dir = temp_dir / "output"
        
        restorer = MetadataRestorer(
            input_path=temp_dir,
            output_path=output_dir,
            extract_zips=True,
            delete_zips=True,
            delete_json=False,
            dry_run=True  # Don't actually modify files
        )
        
        # Run extraction step only
        with patch.object(restorer, '_find_and_match_files', return_value=[]):
            restorer.run()
        
        # Verify ZIP file was tracked
        assert len(restorer._extracted_zip_files) == 1
        assert restorer._extracted_zip_files[0] == zip_path
    
    def test_zip_not_deleted_immediately_after_extraction(self, temp_dir):
        """Test that ZIP is NOT deleted immediately after extraction."""
        # Create a test ZIP
        zip_path = temp_dir / "test_takeout.zip"
        self._create_test_zip(zip_path, {
            "Takeout/Google Photos/test_photo.jpg": b"fake image data",
            "Takeout/Google Photos/test_photo.jpg.json": self._create_sample_json_metadata()
        })
        
        output_dir = temp_dir / "output"
        
        restorer = MetadataRestorer(
            input_path=temp_dir,
            output_path=output_dir,
            extract_zips=True,
            delete_zips=True,
            delete_json=False,
            dry_run=False
        )
        
        # Run only extraction step
        restorer._extract_zips()
        
        # ZIP should still exist after extraction (not deleted yet)
        assert zip_path.exists(), "ZIP should NOT be deleted immediately after extraction"
    
    def test_zip_deleted_after_successful_injection(self, temp_dir):
        """Test that ZIP is deleted after all metadata is successfully injected."""
        # Create a test ZIP with a simple structure
        zip_path = temp_dir / "test_takeout.zip"
        self._create_test_zip(zip_path, {
            "test_photo.jpg": b"fake image data",
            "test_photo.jpg.json": self._create_sample_json_metadata()
        })
        
        output_dir = temp_dir / "output"
        
        restorer = MetadataRestorer(
            input_path=temp_dir,
            output_path=output_dir,
            extract_zips=True,
            delete_zips=True,
            delete_json=False,
            dry_run=False
        )
        
        # Mock the injector to simulate successful injection
        with patch('src.main.create_injector') as mock_create_injector:
            mock_injector = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_injector.inject_metadata.return_value = mock_result
            mock_create_injector.return_value = mock_injector
            
            restorer.run()
        
        # ZIP should be deleted after successful processing
        assert not zip_path.exists(), "ZIP should be deleted after successful metadata injection"
        assert restorer.stats["zips_deleted"] == 1
    
    def test_zip_not_deleted_when_injection_fails(self, temp_dir):
        """Test that ZIP is NOT deleted if any metadata injection fails."""
        # Create a test ZIP
        zip_path = temp_dir / "test_takeout.zip"
        self._create_test_zip(zip_path, {
            "test_photo.jpg": b"fake image data",
            "test_photo.jpg.json": self._create_sample_json_metadata()
        })
        
        output_dir = temp_dir / "output"
        
        restorer = MetadataRestorer(
            input_path=temp_dir,
            output_path=output_dir,
            extract_zips=True,
            delete_zips=True,
            delete_json=False,
            dry_run=False
        )
        
        # Mock the injector to simulate failed injection
        with patch('src.main.create_injector') as mock_create_injector:
            mock_injector = MagicMock()
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.message = "Injection failed"
            mock_injector.inject_metadata.return_value = mock_result
            mock_create_injector.return_value = mock_injector
            
            restorer.run()
        
        # ZIP should NOT be deleted because injection failed
        assert zip_path.exists(), "ZIP should NOT be deleted when injection fails"
        assert restorer.stats["zips_deleted"] == 0
        assert restorer.stats["injection_failed"] > 0
    
    def test_zip_not_deleted_when_media_unmatched(self, temp_dir):
        """Test that ZIP is NOT deleted if some media files have no matching JSON."""
        # Create a test ZIP with unmatched media file
        zip_path = temp_dir / "test_takeout.zip"
        self._create_test_zip(zip_path, {
            "photo_with_json.jpg": b"fake image data",
            "photo_with_json.jpg.json": self._create_sample_json_metadata(),
            "photo_without_json.jpg": b"another image without metadata"
        })
        
        output_dir = temp_dir / "output"
        
        restorer = MetadataRestorer(
            input_path=temp_dir,
            output_path=output_dir,
            extract_zips=True,
            delete_zips=True,
            delete_json=False,
            dry_run=False
        )
        
        # Mock successful injection for matched files
        with patch('src.main.create_injector') as mock_create_injector:
            mock_injector = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_injector.inject_metadata.return_value = mock_result
            mock_create_injector.return_value = mock_injector
            
            restorer.run()
        
        # ZIP should NOT be deleted because not all media files had matching JSON
        assert zip_path.exists(), "ZIP should NOT be deleted when some media files are unmatched"
        assert restorer.stats["zips_deleted"] == 0
        # Verify there were unmatched files
        assert restorer.stats["media_files_found"] > restorer.stats["media_files_matched"]
    
    def test_zip_not_deleted_in_dry_run_mode(self, temp_dir):
        """Test that ZIP is not actually deleted in dry run mode."""
        # Create a test ZIP
        zip_path = temp_dir / "test_takeout.zip"
        self._create_test_zip(zip_path, {
            "test_photo.jpg": b"fake image data",
            "test_photo.jpg.json": self._create_sample_json_metadata()
        })
        
        output_dir = temp_dir / "output"
        
        restorer = MetadataRestorer(
            input_path=temp_dir,
            output_path=output_dir,
            extract_zips=True,
            delete_zips=True,
            delete_json=False,
            dry_run=True  # Dry run mode
        )
        
        restorer.run()
        
        # ZIP should still exist in dry run mode
        assert zip_path.exists(), "ZIP should NOT be deleted in dry run mode"
        # But stats should show it would be deleted
        assert restorer.stats["zips_deleted"] == 1
    
    def test_zip_not_deleted_when_delete_zips_false(self, temp_dir):
        """Test that ZIP is not deleted when delete_zips is False."""
        # Create a test ZIP
        zip_path = temp_dir / "test_takeout.zip"
        self._create_test_zip(zip_path, {
            "test_photo.jpg": b"fake image data",
            "test_photo.jpg.json": self._create_sample_json_metadata()
        })
        
        output_dir = temp_dir / "output"
        
        restorer = MetadataRestorer(
            input_path=temp_dir,
            output_path=output_dir,
            extract_zips=True,
            delete_zips=False,  # Don't delete ZIPs
            delete_json=False,
            dry_run=False
        )
        
        # Mock successful injection
        with patch('src.main.create_injector') as mock_create_injector:
            mock_injector = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_injector.inject_metadata.return_value = mock_result
            mock_create_injector.return_value = mock_injector
            
            restorer.run()
        
        # ZIP should still exist
        assert zip_path.exists(), "ZIP should not be deleted when delete_zips=False"
        assert restorer.stats["zips_deleted"] == 0


class TestMetadataRestorerMultipleZips:
    """Test behavior with multiple ZIP files."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        shutil.rmtree(temp_path)
    
    def _create_test_zip(self, zip_path: Path, files: dict) -> Path:
        """Create a test ZIP file with specified contents."""
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for filename, content in files.items():
                if isinstance(content, str):
                    content = content.encode('utf-8')
                zf.writestr(filename, content)
        return zip_path
    
    def _create_sample_json_metadata(self, title: str = "test.jpg") -> str:
        """Create sample Google Takeout JSON metadata."""
        return json.dumps({
            "title": title,
            "photoTakenTime": {"timestamp": "1609459200"}
        })
    
    def test_all_zips_tracked(self, temp_dir):
        """Test that all extracted ZIP files are tracked."""
        # Create multiple test ZIPs
        zip1 = self._create_test_zip(temp_dir / "takeout1.zip", {
            "photo1.jpg": b"image1",
            "photo1.jpg.json": self._create_sample_json_metadata("photo1.jpg")
        })
        zip2 = self._create_test_zip(temp_dir / "takeout2.zip", {
            "photo2.jpg": b"image2",
            "photo2.jpg.json": self._create_sample_json_metadata("photo2.jpg")
        })
        zip3 = self._create_test_zip(temp_dir / "takeout3.zip", {
            "photo3.jpg": b"image3",
            "photo3.jpg.json": self._create_sample_json_metadata("photo3.jpg")
        })
        
        output_dir = temp_dir / "output"
        
        restorer = MetadataRestorer(
            input_path=temp_dir,
            output_path=output_dir,
            extract_zips=True,
            delete_zips=True,
            dry_run=True
        )
        
        restorer.run()
        
        # All ZIPs should be tracked
        assert len(restorer._extracted_zip_files) == 3
        assert restorer.stats["zips_extracted"] == 3
    
    def test_all_zips_deleted_on_success(self, temp_dir):
        """Test that all ZIP files are deleted after successful processing."""
        # Create multiple test ZIPs
        zip1 = self._create_test_zip(temp_dir / "takeout1.zip", {
            "photo1.jpg": b"image1",
            "photo1.jpg.json": self._create_sample_json_metadata("photo1.jpg")
        })
        zip2 = self._create_test_zip(temp_dir / "takeout2.zip", {
            "photo2.jpg": b"image2",
            "photo2.jpg.json": self._create_sample_json_metadata("photo2.jpg")
        })
        
        output_dir = temp_dir / "output"
        
        restorer = MetadataRestorer(
            input_path=temp_dir,
            output_path=output_dir,
            extract_zips=True,
            delete_zips=True,
            dry_run=False
        )
        
        # Mock successful injection
        with patch('src.main.create_injector') as mock_create_injector:
            mock_injector = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_injector.inject_metadata.return_value = mock_result
            mock_create_injector.return_value = mock_injector
            
            restorer.run()
        
        # All ZIPs should be deleted
        assert not zip1.exists()
        assert not zip2.exists()
        assert restorer.stats["zips_deleted"] == 2


class TestMetadataRestorerInitialization:
    """Test MetadataRestorer initialization and configuration."""
    
    def test_default_values(self, tmp_path):
        """Test default initialization values."""
        restorer = MetadataRestorer(input_path=tmp_path)
        
        assert restorer.input_path == tmp_path
        assert restorer.output_path == tmp_path
        assert restorer.extract_zips is False
        assert restorer.delete_zips is False
        assert restorer.delete_json is True
        assert restorer.update_file_dates is True
        assert restorer.dry_run is False
        assert restorer._extracted_zip_files == []
    
    def test_custom_values(self, tmp_path):
        """Test custom initialization values."""
        output = tmp_path / "output"
        
        restorer = MetadataRestorer(
            input_path=tmp_path,
            output_path=output,
            extract_zips=True,
            delete_zips=True,
            delete_json=False,
            update_file_dates=False,
            dry_run=True,
            exiftool_path="/custom/exiftool"
        )
        
        assert restorer.input_path == tmp_path
        assert restorer.output_path == output
        assert restorer.extract_zips is True
        assert restorer.delete_zips is True
        assert restorer.delete_json is False
        assert restorer.update_file_dates is False
        assert restorer.dry_run is True
        assert restorer.exiftool_path == "/custom/exiftool"
    
    def test_stats_initialized(self, tmp_path):
        """Test that stats dictionary is properly initialized."""
        restorer = MetadataRestorer(input_path=tmp_path)
        
        assert "zips_extracted" in restorer.stats
        assert "zips_deleted" in restorer.stats
        assert "media_files_found" in restorer.stats
        assert "metadata_injected" in restorer.stats
        assert "injection_failed" in restorer.stats
        assert "json_files_deleted" in restorer.stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
