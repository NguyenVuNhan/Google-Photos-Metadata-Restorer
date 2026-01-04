"""
Unit tests for the Media File Matcher module.

Tests various filename matching scenarios including:
- Exact matches (photo.jpg -> photo.jpg.json)
- Truncated filenames (Google's 51 char limit)
- Supplemental metadata files
- Edited files (-edited suffix)
- Numbered duplicates (photo(1).jpg)
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from src.matcher import MediaFileMatcher, MatchResult, MEDIA_EXTENSIONS


class TestMediaFileMatcher:
    """Test cases for MediaFileMatcher class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def matcher(self):
        """Create a fresh matcher instance."""
        return MediaFileMatcher()
    
    # ==========================================================================
    # Test: Exact Match
    # ==========================================================================
    
    def test_exact_match_jpg(self, temp_dir, matcher):
        """Test exact match: photo.jpg -> photo.jpg.json"""
        media_file = temp_dir / "photo.jpg"
        json_file = temp_dir / "photo.jpg.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'exact'
        assert result.confidence == 1.0
    
    def test_exact_match_png(self, temp_dir, matcher):
        """Test exact match: image.png -> image.png.json"""
        media_file = temp_dir / "image.png"
        json_file = temp_dir / "image.png.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'exact'
    
    def test_exact_match_mp4(self, temp_dir, matcher):
        """Test exact match: video.mp4 -> video.mp4.json"""
        media_file = temp_dir / "video.mp4"
        json_file = temp_dir / "video.mp4.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'exact'
    
    # ==========================================================================
    # Test: Truncated Filename - Extension Truncated
    # ==========================================================================
    
    def test_truncated_extension_jpg_to_j(self, temp_dir, matcher):
        """
        Test truncated extension: Google cuts .jpg to .j
        Screenshot_20210414-123045_Google Play Store.jpg -> 
        Screenshot_20210414-123045_Google Play Store.j.json
        """
        media_file = temp_dir / "Screenshot_20210414-123045_Google Play Store.jpg"
        json_file = temp_dir / "Screenshot_20210414-123045_Google Play Store.j.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'truncated'
        assert result.confidence >= 0.8
    
    def test_truncated_extension_jpg_to_jp(self, temp_dir, matcher):
        """Test truncated extension: .jpg truncated to .jp"""
        media_file = temp_dir / "VeryLongFilenameForTestingPurposes.jpg"
        json_file = temp_dir / "VeryLongFilenameForTestingPurposes.jp.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'truncated'
    
    def test_truncated_extension_jpeg_to_jpe(self, temp_dir, matcher):
        """Test truncated extension: .jpeg truncated to .jpe"""
        media_file = temp_dir / "LongFilename_With_Details.jpeg"
        json_file = temp_dir / "LongFilename_With_Details.jpe.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'truncated'
    
    # ==========================================================================
    # Test: Truncated Filename - Name Truncated Before Extension
    # ==========================================================================
    
    def test_truncated_before_extension_with_space(self, temp_dir, matcher):
        """
        Test truncated name with trailing space:
        Screenshot_20210608-182630_Samsung Experience H.jpg ->
        Screenshot_20210608-182630_Samsung Experience .json
        """
        media_file = temp_dir / "Screenshot_20210608-182630_Samsung Experience H.jpg"
        json_file = temp_dir / "Screenshot_20210608-182630_Samsung Experience .json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'truncated'
    
    def test_truncated_mid_filename(self, temp_dir, matcher):
        """Test filename truncated in the middle of the name."""
        media_file = temp_dir / "This_Is_A_Very_Long_Filename_That_Gets_Cut.jpg"
        json_file = temp_dir / "This_Is_A_Very_Long_Filename_That_Gets.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'truncated'
    
    # ==========================================================================
    # Test: Supplemental Metadata Files
    # ==========================================================================
    
    def test_supplemental_metadata_full(self, temp_dir, matcher):
        """Test full supplemental metadata suffix: .supplemental-metadata.json"""
        media_file = temp_dir / "photo.jpg"
        json_file = temp_dir / "photo.jpg.supplemental-metadata.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type in ('exact', 'truncated')
    
    def test_supplemental_metadata_truncated_supplem(self, temp_dir, matcher):
        """Test truncated supplemental: .supplem.json"""
        media_file = temp_dir / "LongScreenshotName_12345.jpg"
        json_file = temp_dir / "LongScreenshotName_12345.jpg.supplem.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'truncated'
    
    def test_supplemental_metadata_truncated_s(self, temp_dir, matcher):
        """Test truncated supplemental: .s.json (most truncated)"""
        media_file = temp_dir / "VeryVeryLongFilename.jpg"
        json_file = temp_dir / "VeryVeryLongFilename.jpg.s.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'truncated'
    
    # ==========================================================================
    # Test: Edited Files
    # ==========================================================================
    
    def test_edited_suffix_english(self, temp_dir, matcher):
        """Test edited file: photo-edited.jpg -> photo.jpg.json"""
        media_file = temp_dir / "photo-edited.jpg"
        json_file = temp_dir / "photo.jpg.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'edited'
    
    def test_edited_suffix_german(self, temp_dir, matcher):
        """Test German edited: photo-bearbeitet.jpg -> photo.jpg.json"""
        media_file = temp_dir / "photo-bearbeitet.jpg"
        json_file = temp_dir / "photo.jpg.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'edited'
    
    # ==========================================================================
    # Test: Numbered Duplicates
    # ==========================================================================
    
    def test_numbered_duplicate_with_own_json(self, temp_dir, matcher):
        """Test numbered file: photo(1).jpg -> photo(1).jpg.json"""
        media_file = temp_dir / "photo(1).jpg"
        json_file = temp_dir / "photo(1).jpg.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type in ('exact', 'numbered')
    
    def test_numbered_duplicate_fallback_to_original(self, temp_dir, matcher):
        """Test numbered file falls back: photo(1).jpg -> photo.jpg.json"""
        media_file = temp_dir / "photo(1).jpg"
        json_file = temp_dir / "photo.jpg.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'numbered'
    
    def test_numbered_duplicate_google_style(self, temp_dir, matcher):
        """Test Google's numbered style: photo.jpg(1).json"""
        media_file = temp_dir / "photo(1).jpg"
        json_file = temp_dir / "photo.jpg(1).json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.match_type == 'numbered'
    
    # ==========================================================================
    # Test: No Match
    # ==========================================================================
    
    def test_no_match_missing_json(self, temp_dir, matcher):
        """Test no match when JSON file doesn't exist."""
        media_file = temp_dir / "orphan_photo.jpg"
        media_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path is None
        assert result.match_type == 'none'
        assert result.confidence == 0.0
    
    # ==========================================================================
    # Test: Multiple JSON Files - Best Match Selection
    # ==========================================================================
    
    def test_prefers_exact_match_over_truncated(self, temp_dir, matcher):
        """When both exact and truncated exist, prefer exact."""
        media_file = temp_dir / "photo.jpg"
        exact_json = temp_dir / "photo.jpg.json"
        truncated_json = temp_dir / "photo.j.json"
        
        media_file.touch()
        exact_json.touch()
        truncated_json.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == exact_json
        assert result.match_type == 'exact'
    
    def test_prefers_longer_truncated_match(self, temp_dir, matcher):
        """When multiple truncated matches exist, prefer the longer one."""
        media_file = temp_dir / "LongFilename_Screenshot.jpg"
        short_json = temp_dir / "LongFilename.json"
        longer_json = temp_dir / "LongFilename_Screenshot.j.json"
        
        media_file.touch()
        short_json.touch()
        longer_json.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        # Should prefer the longer match
        assert result.json_path == longer_json
    
    # ==========================================================================
    # Test: Helper Methods
    # ==========================================================================
    
    def test_is_media_file_jpg(self, matcher):
        """Test is_media_file for JPG."""
        assert matcher.is_media_file(Path("photo.jpg")) is True
        assert matcher.is_media_file(Path("photo.JPG")) is True
    
    def test_is_media_file_png(self, matcher):
        """Test is_media_file for PNG."""
        assert matcher.is_media_file(Path("image.png")) is True
    
    def test_is_media_file_mp4(self, matcher):
        """Test is_media_file for MP4."""
        assert matcher.is_media_file(Path("video.mp4")) is True
    
    def test_is_media_file_non_media(self, matcher):
        """Test is_media_file for non-media files."""
        assert matcher.is_media_file(Path("document.pdf")) is False
        assert matcher.is_media_file(Path("data.json")) is False
        assert matcher.is_media_file(Path("script.py")) is False
    
    def test_is_image_file(self, matcher):
        """Test is_image_file method."""
        assert matcher.is_image_file(Path("photo.jpg")) is True
        assert matcher.is_image_file(Path("video.mp4")) is False
    
    def test_is_video_file(self, matcher):
        """Test is_video_file method."""
        assert matcher.is_video_file(Path("video.mp4")) is True
        assert matcher.is_video_file(Path("photo.jpg")) is False


class TestMatcherEdgeCases:
    """Test edge cases and real-world scenarios."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def matcher(self):
        """Create a fresh matcher instance."""
        return MediaFileMatcher()
    
    def test_real_world_google_play_store(self, temp_dir, matcher):
        """
        Real-world case from Google Takeout:
        Screenshot_20210414-123045_Google Play Store.jpg
        Screenshot_20210414-123045_Google Play Store.j.json
        """
        media_file = temp_dir / "Screenshot_20210414-123045_Google Play Store.jpg"
        json_file = temp_dir / "Screenshot_20210414-123045_Google Play Store.j.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.json_path is not None
    
    def test_real_world_samsung_experience(self, temp_dir, matcher):
        """
        Real-world case from Google Takeout:
        Screenshot_20210608-182630_Samsung Experience H.jpg
        Screenshot_20210608-182630_Samsung Experience .json
        """
        media_file = temp_dir / "Screenshot_20210608-182630_Samsung Experience H.jpg"
        json_file = temp_dir / "Screenshot_20210608-182630_Samsung Experience .json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
        assert result.json_path is not None
    
    def test_unicode_filename(self, temp_dir, matcher):
        """Test matching with unicode characters in filename."""
        media_file = temp_dir / "日本語ファイル名.jpg"
        json_file = temp_dir / "日本語ファイル名.jpg.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
    
    def test_spaces_in_filename(self, temp_dir, matcher):
        """Test matching with spaces in filename."""
        media_file = temp_dir / "My Vacation Photo 2021.jpg"
        json_file = temp_dir / "My Vacation Photo 2021.jpg.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
    
    def test_heic_file(self, temp_dir, matcher):
        """Test matching HEIC files (iPhone format)."""
        media_file = temp_dir / "IMG_1234.HEIC"
        json_file = temp_dir / "IMG_1234.HEIC.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file
    
    def test_mov_video(self, temp_dir, matcher):
        """Test matching MOV video files."""
        media_file = temp_dir / "video_clip.MOV"
        json_file = temp_dir / "video_clip.MOV.json"
        
        media_file.touch()
        json_file.touch()
        
        result = matcher.find_json_for_media(media_file)
        
        assert result.json_path == json_file


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
