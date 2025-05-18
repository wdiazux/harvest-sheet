import os
import json
import logging
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_env_variable(var_name: str, default: Optional[str] = None, required: bool = False) -> str:
    """Retrieve an environment variable with optional default and required flag.
    
    Args:
        var_name: Name of the environment variable
        default: Default value if variable is not set
        required: If True, raises an error if variable is not set
        
    Returns:
        The value of the environment variable
        
    Raises:
        RuntimeError: If required is True and variable is not set
    """
    value = os.environ.get(var_name, default)
    if required and not value:
        raise RuntimeError(f"Environment variable '{var_name}' is required but not set.")
    return value

def ensure_directory_exists(directory: Path) -> None:
    """Ensure that the specified directory exists, creating it if necessary.
    
    Args:
        directory: Path to the directory to check/create
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create directory {directory}: {e}")
        raise

def fetch_harvest_data(from_date: str, to_date: str, output_file: str) -> Dict[str, Any]:
    """Fetch time entries from Harvest API and save raw JSON to a file.
    
    Args:
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
        output_file: Path to the output JSON file
        
    Returns:
        Dictionary containing the API response data
        
    Raises:
        requests.RequestException: If there's an error with the API request
        OSError: If there's an error writing to the output file
        RuntimeError: If required environment variables are missing
    """
    try:
        # Load environment variables from the root directory
        env_path = Path(__file__).parent.parent / '.env'
        load_dotenv(env_path)
        
        # Get required environment variables with user-specific prefix
        prefix = os.environ.get('USER_PREFIX', '')
        
        def get_prefixed_var(name, default=None, required=False):
            # Try prefixed version first, then fall back to unprefixed
            prefixed_name = f"{prefix}{name}" if prefix else name
            value = os.environ.get(prefixed_name, os.environ.get(name, default))
            if required and not value:
                raise RuntimeError(f"Required environment variable not found: {prefixed_name} or {name}")
            return value
        
        # Get required environment variables
        account_id = get_prefixed_var('HARVEST_ACCOUNT_ID', required=True)
        auth_token = get_prefixed_var('HARVEST_AUTH_TOKEN', required=True)
        user_agent = get_prefixed_var('HARVEST_USER_AGENT', 'Harvest-Script/1.0')
        user_id = get_prefixed_var('HARVEST_USER_ID')
        
        # Log which user we're processing
        logger.info(f"Processing data for user: {user_agent} (User ID: {user_id or 'All users'})")
        
        # Set up API request
        base_url = "https://api.harvestapp.com/v2/time_entries"
        params = {
            "from": from_date,
            "to": to_date,
            "per_page": 100
        }
        
        # Add user filter if user_id is available
        if user_id:
            params["user_id"] = user_id
            logger.info(f"Filtering time entries for user ID: {user_id}")
            
        headers = {
            'Harvest-Account-ID': account_id,
            'Authorization': f'Bearer {auth_token}',
            'User-Agent': user_agent,
        }
        
        # Make the API request
        logger.info(f"Fetching data from {from_date} to {to_date}...")
        response = requests.get(base_url, headers=headers, params=params)
        response.raise_for_status()
        
        # Get all pages of results
        data = response.json()
        all_entries = data.get('time_entries', [])
        
        # Handle pagination if needed
        while 'next' in response.links:
            next_url = response.links['next']['url']
            response = requests.get(next_url, headers=headers)
            response.raise_for_status()
            page_data = response.json()
            all_entries.extend(page_data.get('time_entries', []))
        
        result = {'time_entries': all_entries}
        
        # Ensure output directory exists
        output_path = Path(output_file)
        ensure_directory_exists(output_path.parent)
        
        # Save the raw JSON data
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)
        
        logger.info(f"Successfully saved {len(all_entries)} time entries to {output_file}")
        return result
        
    except requests.RequestException as e:
        logger.error(f"API request failed: {e}")
        raise
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to process response: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise

def main() -> None:
    """Main entry point for the script.
    
    This script can be run in two modes:
    1. Directly with environment variables (HARVEST_*)
    2. With user prefix (USER_PREFIX=USERNAME_)
    
    In the second mode, it will look for environment variables with the prefix.
    """
    import argparse
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Fetch time entries from Harvest API')
    parser.add_argument('--from-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to-date', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--output', default='harvest_data.json', 
                       help='Output JSON file name (saved in current directory)')
    parser.add_argument('--user', help='User prefix for environment variables (e.g., JOHN_DOE_)')
    
    args = parser.parse_args()
    
    # Set user prefix if provided
    if args.user:
        os.environ['USER_PREFIX'] = args.user
    
    try:
        # Use the output filename as provided (or default) in the current directory
        result = fetch_harvest_data(args.from_date, args.to_date, args.output)
        logger.info(f"Successfully fetched {len(result.get('time_entries', []))} time entries")
    except RuntimeError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except requests.RequestException as e:
        logger.error(f"API request failed: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())