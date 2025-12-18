# Google Photos Metadata Restorer

Restore metadata (dates, GPS locations, descriptions) from Google Takeout JSON files back into your photos and videos.

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Build Status](https://github.com/NguyenVuNhan/Google-Photos-Metadata-Restorer/actions/workflows/build.yml/badge.svg)

## The Problem

When you export your photos from Google Photos using [Google Takeout](https://takeout.google.com/), the metadata (dates, GPS coordinates, descriptions) is **not embedded in the media files**. Instead, it's stored in separate `.json` files alongside each photo/video.

This means:
- Photos show the wrong date in your photo library
- GPS location data is lost
- Descriptions and captions are not visible

## The Solution

This tool:
1. **Extracts** Google Takeout ZIP files (optional)
2. **Matches** each media file with its corresponding JSON metadata file
3. **Injects** the metadata back into the media files using ExifTool
4. **Cleans up** the JSON files after processing

## Features

- ✅ Supports **images** (JPEG, PNG, HEIC, GIF, RAW, etc.)
- ✅ Supports **videos** (MP4, MOV, AVI, MKV, etc.)
- ✅ Restores **dates** (DateTimeOriginal, CreateDate)
- ✅ Restores **GPS coordinates** (latitude, longitude, altitude)
- ✅ Restores **descriptions/captions**
- ✅ Updates **file system dates** (modification time)
- ✅ Handles Google's **naming quirks** (truncated names, duplicates, edited versions)
- ✅ **Synology NAS** integration with scheduled tasks
- ✅ **Dry-run mode** to preview changes
- ✅ Preserves **original folder structure**
- ✅ **Standalone executables** - No Python installation required

## Quick Start

### Option 1: Download Pre-built Executable (Easiest)

Download the latest release for your platform from the [Releases page](https://github.com/NguyenVuNhan/Google-Photos-Metadata-Restorer/releases):

| Platform | Download |
|----------|----------|
| Windows | `gphotos-metadata-restorer-windows.zip` |
| Linux | `gphotos-metadata-restorer-linux.zip` |
| macOS | `gphotos-metadata-restorer-macos.zip` |

Each ZIP contains `gphotos-metadata-restorer` (or `.exe` on Windows).

> **✅ ExifTool is bundled** - No additional dependencies required! Just download and run.

### Option 2: Run from Source

#### Prerequisites

1. **Python 3.8+**
2. **ExifTool** - Required for metadata manipulation

#### Installing ExifTool

**Windows:**
```powershell
# Download from https://exiftool.org/
# Extract and add to PATH, or specify path with --exiftool flag
```

**macOS:**
```bash
brew install exiftool
```

**Linux/Synology:**
```bash
sudo apt-get install exiftool
# or
sudo yum install perl-Image-ExifTool
```

#### Installation

```bash
# Clone or download this repository
cd Google-Photos-Metadata-Restorer

# Install Python dependencies
pip install -r requirements.txt
```

### Basic Usage

```bash
# Using the executable
gphotos-metadata-restorer --input /path/to/Takeout

# Using a config file
gphotos-metadata-restorer --config /path/to/config.yaml

# Or using Python directly
python -m src.main --input /path/to/Takeout

# Extract ZIPs first, then process
gphotos-metadata-restorer --input /path/to/zips --extract --output /path/to/extracted

# Dry run (see what would happen without making changes)
gphotos-metadata-restorer --input /path/to/Takeout --dry-run

# Keep JSON files after processing
gphotos-metadata-restorer --input /path/to/Takeout --keep-json
```

## Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--config` | `-c` | Path to YAML configuration file |
| `--input` | `-i` | Input path (Google Takeout folder or ZIP files) |
| `--output` | `-o` | Output path for extracted files |
| `--extract` | `-e` | Extract ZIP files before processing |
| `--delete-zips` | | Delete ZIP files after extraction |
| `--keep-json` | `-k` | Keep JSON files after processing |
| `--no-file-dates` | | Don't update file system dates |
| `--dry-run` | `-n` | Preview changes without modifying files |
| `--exiftool` | | Custom path to ExifTool executable (not needed for pre-built executables) |
| `--log-level` | `-l` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `--log-file` | | Path to log file |
| `--version` | `-v` | Show version number |

> **Note:** Either `--input` or `--config` (with `input_folder` set) is required.

## Using a Configuration File

Instead of passing all options via command line, you can use a YAML configuration file:

```bash
# Use a config file
gphotos-metadata-restorer --config /path/to/config.yaml

# Config file with command-line overrides (CLI takes precedence)
gphotos-metadata-restorer --config /path/to/config.yaml --dry-run
```

See `config/config.example.yaml` for all available options.

## Examples

### Example 1: Process Downloaded Takeout

You've downloaded Google Takeout and extracted it to `C:\Users\Me\Takeout`:

```bash
gphotos-metadata-restorer --input "C:\Users\Me\Takeout"
```

### Example 2: Extract and Process ZIPs

You have multiple ZIP files from Google Takeout in a folder:

```bash
gphotos-metadata-restorer --input "D:\Downloads\GoogleTakeout" --extract --output "D:\Photos\Restored"
```

### Example 3: Synology NAS

Process files on your Synology NAS:

```bash
gphotos-metadata-restorer --input /volume1/GoogleTakeout --output /volume1/photo/GooglePhotos --extract
```

## Synology NAS Setup

For detailed instructions on setting up automated processing on Synology DSM 7.2, see:

📖 **[Synology Setup Guide](docs/SYNOLOGY_SETUP.md)**

Key features for Synology:
- Scheduled task automation
- Automatic Synology Photos indexing
- Step-by-step installation guide

## How It Works

### 1. Google Takeout Structure

Google Takeout exports photos with this structure:
```
Takeout/
└── Google Photos/
    └── 2023-Album/
        ├── photo.jpg
        ├── photo.jpg.json    ← Metadata for photo.jpg
        ├── video.mp4
        └── video.mp4.json    ← Metadata for video.mp4
```

### 2. JSON Metadata Format

Each `.json` file contains:
```json
{
  "title": "photo.jpg",
  "description": "My vacation photo",
  "photoTakenTime": {
    "timestamp": "1609459200",
    "formatted": "Jan 1, 2021, 12:00:00 AM UTC"
  },
  "geoData": {
    "latitude": 48.8584,
    "longitude": 2.2945,
    "altitude": 0.0
  }
}
```

### 3. Metadata Injection

The tool uses ExifTool to write this metadata into the actual photo/video files:
- EXIF: DateTimeOriginal, CreateDate, GPSLatitude, GPSLongitude
- IPTC: DateCreated, Caption-Abstract
- XMP: Description

## File Matching

The tool handles Google's various naming conventions:

| Media File | JSON File |
|------------|-----------|
| `photo.jpg` | `photo.jpg.json` |
| `photo(1).jpg` | `photo(1).jpg.json` or `photo.jpg.json` |
| `photo-edited.jpg` | `photo.jpg.json` |
| `very_long_name_truncated.jpg` | `very_long_name_truncated_original.jpg.json` |

## Troubleshooting

### ExifTool not found

```
ExifToolNotFoundError: ExifTool not found
```

**Solution:** Install ExifTool and ensure it's in your PATH, or use `--exiftool /path/to/exiftool`

### Permission denied

**Solution:** Run with administrator/root privileges, or check file permissions

### No files processed

**Solution:** Ensure you're pointing to the correct Takeout folder (should contain `Google Photos` subfolder)

### JSON files not matching

Run with `--log-level DEBUG` to see detailed matching information:
```bash
gphotos-metadata-restorer --input /path/to/Takeout --log-level DEBUG --dry-run
```

## Building from Source

To build the executable yourself:

```bash
# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build
pyinstaller --onefile --name gphotos-metadata-restorer --console run.py

# The executable will be in the dist/ folder
```

## Project Structure

```
Google-Photos-Metadata-Restorer/
├── .github/
│   └── workflows/
│       └── build.yml         # GitHub Actions CI/CD
├── src/
│   ├── __init__.py           # Package initialization
│   ├── main.py               # CLI entry point
│   ├── extractor.py          # ZIP extraction
│   ├── parser.py             # JSON metadata parsing
│   ├── matcher.py            # Media-JSON file matching
│   ├── injector.py           # Metadata injection via ExifTool
│   ├── cleaner.py            # JSON cleanup
│   └── utils.py              # Utility functions
├── config/
│   └── config.example.yaml   # Example configuration
├── scripts/
│   └── synology_task.sh      # Synology scheduled task script
├── docs/
│   └── SYNOLOGY_SETUP.md     # Synology setup guide
├── run.py                    # Entry point for executable
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [ExifTool by Phil Harvey](https://exiftool.org/) - The backbone of metadata manipulation
- Google Takeout for providing data export functionality

## Related Projects

- [google-photos-exif](https://github.com/mattwilson1024/google-photos-exif) - Similar tool in Node.js
- [gphotos-takeout](https://github.com/TheLastGimbus/GooglePhotosTakeoutHelper) - Python helper for Google Takeout
