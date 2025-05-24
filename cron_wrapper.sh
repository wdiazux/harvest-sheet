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

# Function to process a single user's data
process_user() {
    local user_prefix=$1
    log "INFO" "Processing user with prefix: ${user_prefix}"
    
    # Export the user prefix for the Python script
    export USER_PREFIX="${user_prefix}"
    
    # Get the current date in YYYY-MM-DD format
    local today=$(date +%Y-%m-%d)
    # Get the date 7 days ago in YYYY-MM-DD format
    local one_week_ago=$(date -v-7d +%Y-%m-%d)
    
    log "INFO" "Fetching time entries from ${one_week_ago} to ${today}"
    
    # Run the script with the date range
    if ! python3 "${SCRIPT_DIR}/convert_harvest_json_to_csv.py" \
        --from-date "${one_week_ago}" \
        --to-date "${today}" \
        --user "${user_prefix}" 2>> "${ERROR_LOG_FILE}"; then
        log "ERROR" "Failed to process user ${user_prefix}"
        return 1
    fi
    
    log "INFO" "Successfully processed user: ${user_prefix}"
    return 0
}

# Main execution
log "INFO" "Starting user processing"

# Process all users with HARVEST_ACCOUNT_ID in their environment variables
# This finds all environment variables that end with _HARVEST_ACCOUNT_ID
user_count=0
success_count=0

# Get all environment variables that end with _HARVEST_ACCOUNT_ID
while IFS= read -r var_name; do
    # Extract the prefix (everything before _HARVEST_ACCOUNT_ID)
    user_prefix="${var_name%_HARVEST_ACCOUNT_ID}"
    
    # Skip if no prefix found
    [ -z "${user_prefix}" ] && continue
    
    log "INFO" "Found user configuration: ${user_prefix}"
    
    # Process this user
    if process_user "${user_prefix}"; then
        ((success_count++))
    fi
    
    ((user_count++))
    
    # Add a small delay between users to avoid rate limiting
    sleep 2
    
done < <(env | grep -E '_HARVEST_ACCOUNT_ID=' | cut -d= -f1)

# Log summary
log "INFO" "Processed ${success_count} of ${user_count} users successfully"

if [ ${success_count} -eq 0 ] && [ ${user_count} -gt 0 ]; then
    error "Failed to process any users. Check ${ERROR_LOG_FILE} for details."
elif [ ${success_count} -lt ${user_count} ]; then
    log "WARNING" "Some users failed to process. Check ${ERROR_LOG_FILE} for details."
else
    log "INFO" "All users processed successfully"
fi

log "INFO" "Harvest sync completed at $(date)"

exit 0
