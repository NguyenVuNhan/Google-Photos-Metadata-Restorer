# Synology DSM 7.2 Setup Guide

This guide explains how to set up the Google Photos Metadata Restorer on your Synology NAS with DSM 7.2.2.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation Methods](#installation-methods)
3. [Method A: Direct Python Installation (Recommended)](#method-a-direct-python-installation-recommended)
4. [Method B: Docker Installation](#method-b-docker-installation)
5. [Setting Up Scheduled Tasks](#setting-up-scheduled-tasks)
6. [Folder Structure Recommendations](#folder-structure-recommendations)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before starting, ensure you have:

- Synology DSM 7.2.x installed
- SSH access enabled (Control Panel → Terminal & SNMP → Enable SSH)
- Administrator access to your NAS
- Basic familiarity with command line

---

## Installation Methods

There are three ways to install the Metadata Restorer:

| Method | Pros | Cons |
|--------|------|------|
| **Pre-built Executable** | Easiest, no Python needed | Still requires ExifTool |
| **Direct Python** | Full control, easy debugging | Requires Python setup |
| **Docker** | Isolated environment | Requires Docker package, more resources |

We recommend **Pre-built Executable** for most users.

---

## Method A: Pre-built Executable (Easiest)

The pre-built executable includes ExifTool bundled inside - **no additional dependencies required!**

### Step 1: Download the Linux Executable

1. Go to the [Releases page](https://github.com/yourusername/Google-Photos-Metadata-Restorer/releases)
2. Download `gphotos-metadata-restorer-linux.zip`
3. Extract and upload `gphotos-metadata-restorer` to your NAS (e.g., `/volume1/scripts/`)

### Step 2: Make it Executable

```bash
ssh admin@your-nas-ip
chmod +x /volume1/scripts/gphotos-metadata-restorer
```

### Step 3: Test

```bash
/volume1/scripts/gphotos-metadata-restorer --version
/volume1/scripts/gphotos-metadata-restorer --input /volume1/GoogleTakeout --dry-run
```

That's it! No need to install ExifTool separately - it's bundled in the executable.

---

## Method B: Direct Python Installation

### Step 1: Install Required Packages

1. Open **Package Center** in DSM
2. Install **Python 3.9** (or latest available)
3. Install **SynoCli File Tools** from SynoCommunity (contains exiftool)
   - If SynoCommunity is not added, go to Package Center → Settings → Package Sources → Add
   - Name: `SynoCommunity`
   - Location: `https://packages.synocommunity.com`

### Step 2: SSH into Your NAS

```bash
ssh admin@your-nas-ip
```

Replace `admin` with your username and `your-nas-ip` with your NAS IP address.

### Step 3: Create Application Directory

```bash
# Create directory for the application
sudo mkdir -p /volume1/docker/metadata-restorer
cd /volume1/docker/metadata-restorer

# Create a Python virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
```

### Step 4: Copy Application Files

Transfer the application files to your NAS using File Station or SCP:

```bash
# From your local machine (Windows PowerShell)
scp -r src/ admin@your-nas-ip:/volume1/docker/metadata-restorer/
scp requirements.txt admin@your-nas-ip:/volume1/docker/metadata-restorer/
scp -r scripts/ admin@your-nas-ip:/volume1/docker/metadata-restorer/
scp -r config/ admin@your-nas-ip:/volume1/docker/metadata-restorer/
```

### Step 5: Install Python Dependencies

```bash
# On the NAS via SSH
cd /volume1/docker/metadata-restorer
source venv/bin/activate
pip install -r requirements.txt
```

### Step 6: Install ExifTool

If not installed via SynoCommunity:

```bash
# Download ExifTool
cd /tmp
wget https://exiftool.org/Image-ExifTool-12.70.tar.gz
tar -xzf Image-ExifTool-12.70.tar.gz
cd Image-ExifTool-12.70

# Install
sudo cp -r exiftool lib /usr/local/bin/
sudo chmod +x /usr/local/bin/exiftool

# Verify installation
exiftool -ver
```

### Step 7: Test the Installation

```bash
cd /volume1/docker/metadata-restorer
source venv/bin/activate

# Run a dry-run test
python3 -m src.main --input /volume1/GoogleTakeout --dry-run
```

---

## Method B: Docker Installation

### Step 1: Install Docker

1. Open **Package Center**
2. Search for and install **Container Manager** (Docker)

### Step 2: Create Dockerfile

Create a file named `Dockerfile` in the application directory:

```dockerfile
FROM python:3.11-slim

# Install ExifTool
RUN apt-get update && apt-get install -y \
    exiftool \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Default command
ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--help"]
```

### Step 3: Build and Run

```bash
# SSH into NAS
cd /volume1/docker/metadata-restorer

# Build the image
sudo docker build -t metadata-restorer .

# Test run
sudo docker run --rm \
    -v /volume1/GoogleTakeout:/input \
    -v /volume1/photo:/output \
    metadata-restorer \
    --input /input --output /output --extract --dry-run
```

---

## Setting Up Scheduled Tasks

### Step 1: Configure the Script

1. Copy the example script:
   ```bash
   cp /volume1/docker/metadata-restorer/scripts/synology_task.sh /volume1/scripts/restore_metadata.sh
   ```

2. Edit the configuration variables in the script:
   ```bash
   sudo nano /volume1/scripts/restore_metadata.sh
   ```

3. Make it executable:
   ```bash
   chmod +x /volume1/scripts/restore_metadata.sh
   ```

### Step 2: Create Scheduled Task in DSM

1. Open **Control Panel** → **Task Scheduler**

2. Click **Create** → **Scheduled Task** → **User-defined script**

3. Configure the **General** tab:
   - **Task**: `Google Photos Metadata Restorer`
   - **User**: `root` (required for full file access)
   - **Enabled**: ✓

4. Configure the **Schedule** tab:
   - **Run on the following days**: Select days (e.g., Daily)
   - **Time**: Choose a time when NAS is less busy (e.g., 3:00 AM)
   - **Frequency**: Once a day (or as needed)

5. Configure the **Task Settings** tab:
   - **User-defined script**:
     ```bash
     /volume1/scripts/restore_metadata.sh
     ```
   - **Send run details by email**: (optional, enter your email)

6. Click **OK** to save

### Step 3: Test the Scheduled Task

1. In Task Scheduler, right-click your task
2. Select **Run**
3. Check the log file: `cat /var/log/metadata-restorer.log`

---

## Folder Structure Recommendations

Here's a recommended folder structure for your NAS:

```
/volume1/
├── GoogleTakeout/
│   ├── incoming/          ← Upload Google Takeout ZIPs here
│   ├── completed/         ← (Optional) Processed ZIPs moved here
│   └── extracted/         ← (Optional) Temporary extraction folder
│
├── photo/                  ← Synology Photos folder
│   └── GooglePhotos/       ← Restored photos go here
│
├── docker/
│   └── metadata-restorer/  ← Application installation
│
└── scripts/
    └── restore_metadata.sh ← Scheduled task script
```

### Configure Synology Photos

1. Open **Synology Photos**
2. Go to **Settings** → **Shared Space**
3. Ensure `/photo` folder is included in your library

After running the metadata restorer, Synology Photos will automatically index the new files with their correct dates.

---

## Workflow

Here's your typical workflow:

1. **Export from Google Photos**:
   - Go to [Google Takeout](https://takeout.google.com/)
   - Select only **Google Photos**
   - Choose `.zip` format
   - Download the ZIP file(s)

2. **Upload to NAS**:
   - Use File Station or SMB to upload ZIPs to `/volume1/GoogleTakeout/incoming/`

3. **Processing** (happens automatically via scheduled task):
   - ZIP files are extracted
   - Metadata is restored to photos
   - JSON files are deleted
   - Files appear in `/volume1/photo/GooglePhotos/`

4. **View in Synology Photos**:
   - Open Synology Photos app
   - Photos appear with correct dates and locations

---

## Troubleshooting

### ExifTool Not Found

```bash
# Check if ExifTool is installed
which exiftool

# If not found, install manually (see Step 6 above)
```

### Python Module Not Found

```bash
# Make sure you're using the virtual environment
cd /volume1/docker/metadata-restorer
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Permission Denied Errors

```bash
# Ensure scripts are executable
chmod +x /volume1/scripts/restore_metadata.sh

# For scheduled tasks, run as root user
```

### Checking Logs

```bash
# View the metadata restorer log
cat /var/log/metadata-restorer.log

# View the last 50 lines
tail -50 /var/log/metadata-restorer.log

# Follow log in real-time
tail -f /var/log/metadata-restorer.log
```

### Synology Photos Not Showing New Files

```bash
# Manually trigger re-indexing
synoindex -R /volume1/photo/GooglePhotos

# Or restart Synology Photos service
synopkg restart SynologyPhotos
```

### Insufficient Space During Extraction

- Ensure you have enough free space (at least 2x the size of your ZIP files)
- Consider processing ZIPs in batches
- Use `--delete-zips` flag to remove ZIPs after extraction

---

## Getting Help

If you encounter issues:

1. Run with debug logging:
   ```bash
   python3 -m src.main --input /path --log-level DEBUG
   ```

2. Check all logs for errors

3. Ensure all prerequisites are installed correctly

4. Verify file permissions
