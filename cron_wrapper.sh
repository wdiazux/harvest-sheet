#!/bin/bash
# Script to run the Harvest script with environment variables

# Load environment variables needed by the Harvest script
if [ -f /proc/1/environ ]; then
    # Extract only the environment variables we need from the container process
    # This is safer than exporting all variables
    while IFS= read -r -d '' var; do
        # Only export variables that match our patterns
        if [[ $var =~ ^(HARVEST_|GOOGLE_|FROM_DATE|TO_DATE|OUTPUT_DIR|CSV_OUTPUT_FILE|UPLOAD_TO|ENABLE_RAW_JSON|HARVEST_RAW_JSON) ]]; then
            export "$var"
        fi
    done < /proc/1/environ
fi

# Source .env file if it exists (will override container environment variables)
if [ -f /app/.env ]; then
    set -a  # automatically export all variables
    source /app/.env
    set +a
fi

# Run the Python script with absolute paths and pass all arguments
/usr/local/bin/python /app/convert_harvest_json_to_csv.py "$@"
