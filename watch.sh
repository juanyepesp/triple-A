#!/bin/bash

SOURCE="/Users/juan/Local/research-projects/triple-A"
DEST="aaagent@192.168.64.3:/Users/aaagent/Documents/sync/"

sync_now() {
    echo "[$(date '+%H:%M:%S')] Syncing..."

    rsync -az \
        --delete \
        --exclude='.git/' \
        --exclude='.git' \
        --exclude='venv/' \
        --exclude='node_modules/' \
        --exclude='vision_outputs/' \
        --exclude='screenshots/' \
        --exclude='.venv/' \
        --exclude='__pycache__/' \
        --exclude='.pytest_cache/' \
        --exclude='.mypy_cache/' \
        --exclude='.DS_Store' \
        "$SOURCE" \
        "$DEST"

    echo "[$(date '+%H:%M:%S')] rsync exit code: $?"
}

echo "Watching $SOURCE"
echo "Press Ctrl+C to stop."

sync_now

fswatch -o "$SOURCE" | while read -r _; do
    sleep 0.25
    sync_now
done