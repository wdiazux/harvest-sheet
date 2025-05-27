#!/bin/bash
# Script to run the Harvest script for multiple users in a container
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

# Function to safely write environment variables to a file
save_env_vars() {
    local target_file=$1
    local source=${2:-"env"}
    local temp_file="${target_file}.tmp"
    
    # Create a clean temp file
    touch "${temp_file}"
    
    # Process each environment variable safely with proper quoting
    if [ "$source" = "env" ]; then
        # From current environment
        while IFS='=' read -r name value; do
            # Skip internal variables
            if [[ $name == "_"* ]] || [[ $name == "SHLVL" ]] || [[ $name == "PWD" ]] || [[ $name == "OLDPWD" ]]; then
                continue
            fi
            # Properly quote the value to preserve spaces and special characters
            printf "export %s=%q\n" "$name" "$value" >> "${temp_file}"
        done < <(env)
    else
        # From container environment
        while IFS='=' read -r name value; do
            # Skip internal variables
            if [[ $name == "_"* ]] || [[ $name == "SHLVL" ]] || [[ $name == "PWD" ]] || [[ $name == "OLDPWD" ]]; then
                continue
            fi
            # Properly quote the value to preserve spaces and special characters
            printf "export %s=%q\n" "$name" "$value" >> "${temp_file}"
        done <<< "$source"
    fi
    
    # Replace the old file with the new one
    mv "${temp_file}" "${target_file}"
}

# Set up environment variables
ENV_FILE="/app/.env"

# Step 1: Try to load from existing .env file
if [ -f "${ENV_FILE}" ]; then
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
    log "INFO" "Loaded environment variables from ${ENV_FILE}"
else
    log "INFO" "No .env file found at ${ENV_FILE}, using container environment variables"
    # Create .env from current environment
    save_env_vars "${ENV_FILE}"
    log "INFO" "Created ${ENV_FILE} from current environment"
    # Source the new file
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
fi

# Step 2: Check if we have what we need; if not, try container process
if ! env | grep -q -E '_HARVEST_ACCOUNT_ID='; then
    if [ -f "/proc/1/environ" ]; then
        log "INFO" "Attempting to load environment variables from container process"
        # Read environment variables from container's process
        CONTAINER_ENV=$(tr '\0' '\n' < /proc/1/environ | grep -v "^_=")
        
        # Save to .env file and update current environment
        save_env_vars "${ENV_FILE}" "${CONTAINER_ENV}"
        log "INFO" "Updated ${ENV_FILE} with container process environment"
        
        # Export to current process
        # shellcheck source=/dev/null
        source "${ENV_FILE}"
        
        # Final check
        if ! env | grep -q -E '_HARVEST_ACCOUNT_ID='; then
            error "No Harvest account IDs found in environment variables. Make sure container environment variables are properly configured."
        else
            log "INFO" "Successfully loaded environment variables from container process"
        fi
    else
        error "No Harvest account IDs found in environment variables. Make sure container environment variables are properly configured."
    fi
fi

# Log the number of Harvest account IDs found
HARVEST_ACCOUNT_IDS=$(env | grep -E '_HARVEST_ACCOUNT_ID=' | wc -l)
log "INFO" "Found ${HARVEST_ACCOUNT_IDS} Harvest account IDs in environment variables"

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
