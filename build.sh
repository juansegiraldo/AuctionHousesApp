#!/usr/bin/env bash
# Render build script

set -e  # Exit on error

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Build completed successfully!"