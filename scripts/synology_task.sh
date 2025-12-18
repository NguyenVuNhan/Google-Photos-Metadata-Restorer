#!/bin/bash
# =============================================================================
# Google Photos Metadata Restorer - Synology Scheduled Task Script
# =============================================================================
# This script is designed to run as a scheduled task on Synology DSM 7.x
#
# Setup Instructions:
# 1. Copy this script to your Synology NAS (e.g., /volume1/scripts/)
# 2. Make it executable: chmod +x /volume1/scripts/restore_metadata.sh
# 3. Create a scheduled task in DSM Control Panel
# 4. Modify the configuration variables below
# =============================================================================

# -----------------------------------------------------------------------------
# CONFIGURATION - Modify these variables for your setup
# -----------------------------------------------------------------------------

# Choose run mode: "executable" or "python"
RUN_MODE="executable"

# Path to the executable (if using executable mode)
EXECUTABLE_PATH="/volume1/scripts/gphotos-metadata-restorer"

# Path to Python (if using python mode)
PYTHON_PATH="/usr/local/bin/python3"
APP_PATH="/volume1/docker/metadata-restorer"

# Input folder - where you upload Google Takeout ZIP files
INPUT_FOLDER="/volume1/GoogleTakeout/incoming"

# Output folder - where processed photos will be saved
OUTPUT_FOLDER="/volume1/photo/GooglePhotos"

# Whether to extract ZIP files
EXTRACT_ZIPS="true"

# Whether to delete ZIP files after extraction
DELETE_ZIPS="false"

# Whether to delete JSON files after processing
DELETE_JSON="true"

# Log file location
LOG_FILE="/var/log/gphotos-metadata-restorer.log"

# -----------------------------------------------------------------------------
# SCRIPT LOGIC - Usually no need to modify below this line
# -----------------------------------------------------------------------------

# Timestamp for logging
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Log function
log() {
    echo "[$TIMESTAMP] $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Starting Google Photos Metadata Restorer"
log "=========================================="

# Check if input folder exists
if [ ! -d "$INPUT_FOLDER" ]; then
    log "ERROR: Input folder does not exist: $INPUT_FOLDER"
    exit 1
fi

# Check if there are any ZIP files to process
ZIP_COUNT=$(find "$INPUT_FOLDER" -maxdepth 1 -name "*.zip" -type f | wc -l)

if [ "$ZIP_COUNT" -eq 0 ]; then
    log "No ZIP files found in $INPUT_FOLDER. Nothing to do."
    exit 0
fi

log "Found $ZIP_COUNT ZIP file(s) to process"

# Create output folder if it doesn't exist
mkdir -p "$OUTPUT_FOLDER"

# Build command arguments
CMD_ARGS="--input $INPUT_FOLDER --output $OUTPUT_FOLDER"

if [ "$EXTRACT_ZIPS" = "true" ]; then
    CMD_ARGS="$CMD_ARGS --extract"
fi

if [ "$DELETE_ZIPS" = "true" ]; then
    CMD_ARGS="$CMD_ARGS --delete-zips"
fi

if [ "$DELETE_JSON" != "true" ]; then
    CMD_ARGS="$CMD_ARGS --keep-json"
fi

CMD_ARGS="$CMD_ARGS --log-file $LOG_FILE"

# Run the metadata restorer
if [ "$RUN_MODE" = "executable" ]; then
    log "Running: $EXECUTABLE_PATH $CMD_ARGS"
    $EXECUTABLE_PATH $CMD_ARGS
else
    log "Running: $PYTHON_PATH -m src.main $CMD_ARGS"
    cd "$APP_PATH"
    $PYTHON_PATH -m src.main $CMD_ARGS
fi

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log "Metadata restoration completed successfully"
    
    # Optional: Trigger Synology Photos re-indexing
    if command -v synoindex &> /dev/null; then
        log "Triggering Synology Photos re-indexing..."
        synoindex -R "$OUTPUT_FOLDER"
        log "Re-indexing triggered"
    fi
else
    log "ERROR: Metadata restoration failed with exit code $EXIT_CODE"
fi

log "=========================================="
log "Script completed"
log "=========================================="

exit $EXIT_CODE
