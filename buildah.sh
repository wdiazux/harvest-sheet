#!/usr/bin/env bash
set -e

# 1. Create container from python:3.11-slim
ctr=$(buildah from python:3.11-slim)
if [[ -z "$ctr" ]]; then
  echo "Failed to create container from python:3.11-slim" >&2
  exit 1
fi

# 2. Set working directory
buildah config --workingdir /app $ctr

# 3. Install cron and clean up apt cache
buildah run $ctr -- apt-get update
buildah run $ctr -- apt-get install -y --no-install-recommends cron
buildah run $ctr -- rm -rf /var/lib/apt/lists/*

# 4. Copy code, requirements, and crontab
buildah copy $ctr convert_harvest_json_to_csv.py /app/
buildah copy $ctr requirements.txt /app/
buildah copy $ctr crontab.txt /app/
# Copy only .env.example for documentation/reference (do NOT bake secrets into the image)
buildah copy $ctr .env.example /app/ || echo ".env.example not found, skipping."

# 5. Install Python dependencies (including optional dotenv)
buildah run $ctr -- pip install --no-cache-dir -r /app/requirements.txt
buildah run $ctr -- /bin/sh -c 'pip install --no-cache-dir python-dotenv || true'

# 6. Register crontab
buildah run $ctr -- crontab /app/crontab.txt

# 7. Set environment variables from .env (if present)
if [ -f .env ]; then
  echo "Adding environment variables from .env to the image..."
  while IFS= read -r line; do
    # Ignore comments and blank lines
    if [[ $line =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      buildah config --env "$line" $ctr
    fi
  done < .env
else
  echo ".env file not found; skipping environment variable injection."
fi
# Always set PYTHONUNBUFFERED=1
buildah config --env PYTHONUNBUFFERED=1 $ctr

# 8. Set CMD to start cron and tail the log
# Set CMD as an array (recommended for Buildah)
buildah config --cmd '["/bin/sh", "-c", "cron && tail -F /app/cron.log"]' $ctr

# 9. Add healthcheck (buildah doesn't support HEALTHCHECK natively, so document it)
echo '# Healthcheck: pgrep cron || exit 1 (interval=1m, timeout=3s)' > /dev/null

# 10. Commit the image
buildah commit $ctr harvest-sheet:latest

echo "Image built and tagged as harvest-sheet:latest."
