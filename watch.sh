#!/bin/bash

SOURCE="/Users/juan/Local/research-projects/triple-A"
DEST="aaagent@192.168.64.3:/Users/aaagent/Documents/sync/"

echo "Watching $SOURCE"
echo "Press Ctrl+C to stop."

fswatch -o "$SOURCE" | while read -r _; do
    sleep 0.25

    rsync -az \
        --delete \
        --exclude='.git/' \
        --exclude='venv/' \
        --exclude='vision_outputs/' \
        --exclude='screenshots/' \
        --exclude='.venv/' \
        --exclude='__pycache__/' \
        --exclude='.pytest_cache/' \
        --exclude='.mypy_cache/' \
        --exclude='.DS_Store' \
        "$SOURCE" \
        "$DEST"
done
