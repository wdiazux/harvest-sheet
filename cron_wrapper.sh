#!/bin/bash
# Script to run the Harvest script for multiple users in a Docker container
# This script runs inside a container where the working directory is /app

# Exit on error
set -e

# Set container paths
CONTAINER_HOME="/app"
SCRIPT_DIR="${CONTAINER_HOME}"
cd "${CONTAINER_HOME}"  # Ensure we're in the correct directory

# Set up logging
LOG_DIR="${CONTAINER_HOME}/logs"
LOG_FILE="${LOG_DIR}/harvest_sync_$(date +%Y%m%d_%H%M%S).log"
ERROR_LOG_FILE="${LOG_DIR}/harvest_sync_errors_$(date +%Y%m%d_%H%M%S).log"

# Create necessary directories
mkdir -p "${LOG_DIR}" "${CONTAINER_HOME}/output"

# Function to log messages
log() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${message}" | tee -a "${LOG_FILE}"
}

# Function to handle errors
error() {
    log "ERROR" "$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1" >> "${ERROR_LOG_FILE}"
    exit 1
}

# Log script start
log "INFO" "Starting Harvest sync process"

# Load environment variables (if available, but not required)
ENV_FILE="/app/.env"
if [ -f "${ENV_FILE}" ]; then
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
    log "INFO" "Loaded environment variables from ${ENV_FILE}"
else
    log "INFO" "No .env file found at ${ENV_FILE}, using Docker environment variables instead"
fi

# Verify required environment variables are set
if ! env | grep -q -E '_HARVEST_ACCOUNT_ID='; then
    error "No Harvest account IDs found in environment variables. Make sure Docker environment variables are properly configured."
fi

# Main execution
log "INFO" "Starting Harvest data processing for all users"

# Count how many users have HARVEST_ACCOUNT_ID environment variables
user_count=$(env | grep -E '_HARVEST_ACCOUNT_ID=' | wc -l)
log "INFO" "Found ${user_count} user configurations in environment variables"

# Run the script once for all users
# Python script will automatically calculate the appropriate date range
log "INFO" "Running Python script with automatic date range calculation"

if python3 "${SCRIPT_DIR}/convert_harvest_json_to_csv.py" \
    --all-users 2>> "${ERROR_LOG_FILE}"; then
    
    log "INFO" "Successfully processed all users"
    success=true
else
    log "ERROR" "Failed to process all users. Check ${ERROR_LOG_FILE} for details."
    success=false
fi

# Log summary
if [ "${success}" = true ]; then
    log "INFO" "All users processed successfully"
else
    error "Failed to process users. Check ${ERROR_LOG_FILE} for details."
fi

log "INFO" "Harvest sync completed at $(date)"

exit 0
