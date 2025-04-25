#!/usr/bin/env bash
# Harvest Sheet Container Image Builder
# Creates an OCI-compatible container image for the Harvest Sheet application

# Exit on any error
set -e

# 1. Create container from python:3.11-slim
echo "Creating container from python:3.11-slim..."
ctr=$(buildah from python:3.11-slim)
if [[ -z "$ctr" ]]; then
  echo "Failed to create container from python:3.11-slim" >&2
  exit 1
fi

# 2. Set working directory
buildah config --workingdir /app $ctr

# 3. Install dependencies and clean up in a single layer
echo "Installing system dependencies..."
buildah run $ctr -- sh -c 'apt-get update && \
  apt-get install -y --no-install-recommends cron procps && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*'

# 4. Copy application files
echo "Copying application files..."
for file in convert_harvest_json_to_csv.py requirements.txt crontab.txt; do
  if [ ! -f "$file" ]; then
    echo "Error: Required file $file not found" >&2
    exit 1
  fi
  buildah copy $ctr "$file" /app/
done

# Copy example env file if it exists (for documentation only)
buildah copy $ctr .env.example /app/ 2>/dev/null || echo ".env.example not found, skipping."

# 5. Create required directories and files
buildah run $ctr -- mkdir -p /app/output
buildah run $ctr -- touch /app/cron.log /app/cron.error.log

# 6. Install Python dependencies in a single layer
echo "Installing Python dependencies..."
buildah run $ctr -- pip install --no-cache-dir -r /app/requirements.txt python-dotenv

# 7. Register crontab
echo "Setting up cron jobs..."
buildah run $ctr -- crontab /app/crontab.txt

# 8. Set environment variables
# Always set PYTHONUNBUFFERED for better log output
buildah config --env PYTHONUNBUFFERED=1 $ctr

# Add variables from .env if present
if [ -f .env ]; then
  echo "Adding environment variables from .env..."
  grep -E '^[A-Za-z_][A-Za-z0-9_]*=' .env | while read -r line; do
    buildah config --env "$line" $ctr
  done
else
  echo ".env file not found; continuing without it."
  echo "Remember to mount a volume with environment variables or provide them at runtime."
fi

# 9. Configure container metadata
buildah config --cmd '["/bin/sh", "-c", "cron && tail -F /app/cron.log"]' $ctr
buildah config --author "Harvest Sheet Maintainer" $ctr
buildah config --label "description=Harvest Sheet data processor with scheduled jobs" $ctr

# 10. Commit the image
echo "Committing container to image..."
buildah commit $ctr harvest-sheet:latest

echo "✅ Image built and tagged as harvest-sheet:latest"
echo "Run with: podman run -d --name harvest-sheet harvest-sheet:latest"
