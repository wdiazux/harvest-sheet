import os
import csv
import json
import requests
import argparse
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import logging

# Google Sheets API imports
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except ImportError:
    service_account = None
    build = None
    # Will raise error if upload is attempted without dependencies

def load_environment():
    """Load environment variables from .env file.
    
    Looks for .env file in the script directory or parent directories.
    """
    try:
        from dotenv import load_dotenv, find_dotenv
        
        # First try looking for a specific .env file in the current directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        local_env = os.path.join(script_dir, '.env')
        
        if os.path.isfile(local_env):
            load_dotenv(local_env)
            logging.info(f"Loaded environment variables from {local_env}")
        else:
            # Use find_dotenv to look in parent directories
            env_path = find_dotenv()
            if env_path:
                load_dotenv(env_path)
                logging.info(f"Loaded environment variables from {env_path}")
            else:
                logging.warning("No .env file found, using system environment variables")
                
        # Automatically set USER_PREFIX if WILLIAM_DIAZ_ prefixed variables exist
        if os.environ.get('WILLIAM_DIAZ_HARVEST_ACCOUNT_ID'):
            os.environ['USER_PREFIX'] = 'WILLIAM_DIAZ_'
            logging.info("Automatically set USER_PREFIX to WILLIAM_DIAZ_")
            
    except ImportError:
        logging.warning("python-dotenv not installed, using system environment variables")
    except Exception as e:
        logging.error(f"Error loading .env file: {e}")

# Set up logging
def setup_logging(debug=False):
    """Configure logging with the specified debug level."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format='[%(levelname)s] %(message)s')
    return logging.getLogger(__name__)

# Initialize logging with default level
logger = setup_logging()

def get_env_variable(var_name: str, default: Optional[str] = None, required: bool = False) -> str:
    """Return an environment variable, with support for user prefixes.
    
    Args:
        var_name: The base name of the environment variable
        default: Default value if variable is not found
        required: If True, raises an error if variable is not found
        
    Returns:
        The value of the environment variable, or the default
        
    Raises:
        RuntimeError: If required is True and variable is not found
    """
    # Get the current user prefix if set
    prefix = os.environ.get('USER_PREFIX', '')
    
    # Try to get the prefixed version first, then fall back to unprefixed
    prefixed_name = f"{prefix}{var_name}" if prefix else var_name
    value = os.environ.get(prefixed_name, os.environ.get(var_name, default))
    
    if required and not value:
        raise RuntimeError(
            f"Required environment variable not found: {prefixed_name} or {var_name}"
        )
    return value


def download_time_entries(account_id: str, auth_token: str, user_agent: str, from_date: str, to_date: str) -> Dict[str, Any]:
    """Fetch all Harvest time entries for the given date range, handling pagination.
    When a HARVEST_USER_ID is set, time entries will be filtered for that specific user.
    
    Args:
        account_id: Harvest account ID (required)
        auth_token: Harvest authentication token (required)
        user_agent: User agent string for the API request (required)
        from_date: Start date in YYYY-MM-DD format (required)
        to_date: End date in YYYY-MM-DD format (required)
        
    Returns:
        Dictionary containing the time entries data
        
    Raises:
        requests.RequestException: If there's an error with the API request
        ValueError: If required parameters are missing
    """
    if not all([account_id, auth_token, user_agent, from_date, to_date]):
        raise ValueError("Missing required parameters for download_time_entries")
    
    base_url = "https://api.harvestapp.com/v2/time_entries"
    
    # Get user ID using the same prefixing logic as other environment variables
    user_id = get_env_variable('HARVEST_USER_ID', default='')
    
    params = {
        "from": from_date,
        "to": to_date,
        "per_page": 100,
    }
    
    # Only add user_id to params if it's provided
    if user_id:
        try:
            # Make sure the user_id is a number before sending to API
            params["user_id"] = str(int(user_id))
            logging.info(f"Filtering time entries for user ID: {user_id}")
        except ValueError:
            logging.error(f"Invalid HARVEST_USER_ID value: {user_id}. Must be a numeric ID.")
            logging.warning("Continuing without user_id filter")
    
    logging.info(f"Fetching time entries from {from_date} to {to_date}")
    headers = {
        'Harvest-Account-ID': account_id,
        'Authorization': f'Bearer {auth_token}',
        'User-Agent': user_agent,
    }
    all_entries = []
    
    # Use a session for connection pooling efficiency
    with requests.Session() as session:
        session.headers.update(headers)
        
        page = 1
        while True:
            params["page"] = page
            try:
                response = session.get(base_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                logging.error(f"Harvest API request failed on page {page}: {e}")
                raise
            except Exception as e:
                logging.error(f"Unexpected error on page {page}: {e}")
                raise
                
            entries = data.get("time_entries", [])
            all_entries.extend(entries)
            
            if not data.get("next_page"):
                break
            page = data["next_page"]
            
    return {"time_entries": all_entries}


def parse_time_entries(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert Harvest API time entries into rows for CSV export with correct field mapping."""
    rows = []
    
    for entry in data.get("time_entries", []):
        try:
            # Safely extract user name parts
            full_name = entry.get("user", {}).get("name", "")
            name_parts = full_name.split()
            first_name = name_parts[0] if name_parts else ""
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
            
            # Safely get employee status from user_assignment
            is_employee = entry.get("user_assignment", {}).get("is_active", False)
            
            # Get project code safely
            project = entry.get("project", {})
            project_code = project.get("code") or ""
            
            row = {
                "Date": entry.get("spent_date", ""),
                "Client": entry.get("client", {}).get("name", ""),
                "Project": project.get("name", ""),
                "Project Code": project_code,
                "Task": entry.get("task", {}).get("name", ""),
                "Notes": entry.get("notes") or "",
                "Hours": entry.get("hours", 0.0),
                "Billable?": "Yes" if entry.get("billable") else "No",
                "Invoiced?": "Yes" if entry.get("is_billed") else "No",
                "First Name": first_name,
                "Last Name": last_name,
                "Roles": "Developer",  # Default role
                "Employee?": "Yes" if is_employee else "No",
                "External Reference URL": entry.get("external_reference", {}).get("permalink", "") 
                                         if entry.get("external_reference") else "",
                "Harvest ID": str(entry.get("id", "")),  # Ensure ID is a string
                "Approved": "Yes" if entry.get("is_locked") else "No",  # Assuming locked means approved
                "Department": ""  # Not provided by Harvest API
            }
            rows.append(row)
            
        except Exception as e:
            logging.error(f"Error processing entry {entry.get('id')}: {str(e)}")
            continue
            
    return rows


def write_csv(rows: List[Dict[str, Any]], output_file: str) -> None:
    """Write the parsed rows to a CSV file with the specified output filename.
    
    Args:
        rows: List of dictionaries containing the data to write
        output_file: Path to the output CSV file. If not absolute, will be created in ./output/
    """
    # If output_file is not an absolute path, create it in ./output/
    if not os.path.isabs(output_file):
        output_dir = 'output'  # Default to local output directory when not in Docker
        # Check if we're running in a Docker container
        if os.path.exists('/.env') or os.path.isfile('/app/.env'):
            output_dir = '/app/output'
        
        # Create the output directory if it doesn't exist
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            # If we can't create the directory, fall back to current directory
            logging.warning(f"Could not create directory {output_dir}, using current directory: {e}")
            output_dir = '.'
            
        output_file = os.path.join(output_dir, os.path.basename(output_file))
    else:
        # Ensure the directory exists if it's an absolute path
        dir_path = os.path.dirname(output_file) or '.'
        try:
            os.makedirs(dir_path, exist_ok=True)
        except OSError as e:
            logging.error(f"Could not create directory {dir_path}: {e}")
            raise
    
    fieldnames = [
        'Date', 'Client', 'Project', 'Project Code', 'Task', 'Notes', 'Hours',
        'Billable?', 'Invoiced?', 'First Name', 'Last Name', 'Roles', 'Employee?',
        'External Reference URL', 'Harvest ID', 'Approved', 'Department'
    ]
    
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logging.info(f"Successfully wrote {len(rows)} rows to {output_file}")
    except IOError as e:
        logging.error(f"Error writing to {output_file}: {e}")
        raise


def get_last_week_range() -> Tuple[str, str]:
    """Return the date range for the weekly report based on the current day.
    
    Returns:
        Tuple[str, str]: A tuple of (start_date, end_date) in 'YYYY-MM-DD' format
        - If today is Friday, Saturday, or Sunday: returns current week (Monday-Sunday)
        - Otherwise: returns previous week (Monday-Sunday)
        
    Note:
        - Week is considered to start on Monday and end on Sunday
        - All dates are in the system's local timezone
    """
    try:
        # Use datetime.now() with timezone awareness if available (Python 3.3+)
        today = datetime.now()
        
        # Get the current weekday (Monday=0, Sunday=6)
        current_weekday = today.weekday()
        
        # Calculate days to go back to most recent Monday
        days_to_monday = current_weekday  # 0 for Monday, 1 for Tuesday, etc.
        
        # Determine if we're in the current week (Fri-Sun) or previous week (Mon-Thu)
        is_current_week = current_weekday >= 4  # Friday, Saturday, or Sunday
        
        if is_current_week:
            # Current week
            start_date = today - timedelta(days=days_to_monday)
            end_date = start_date + timedelta(days=6)
        else:
            # Previous week
            start_date = today - timedelta(days=days_to_monday + 7)  # Go back to previous Monday
            end_date = start_date + timedelta(days=6)
        
        # Ensure we're working with dates (not datetimes) at midnight
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        return (
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        
    except Exception as e:
        logging.error(f"Error calculating date range: {e}")
        # Fallback to a safe default (previous week) if there's an error
        fallback_date = (datetime.now() - timedelta(weeks=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        fallback_start = fallback_date - timedelta(days=fallback_date.weekday())
        fallback_end = fallback_start + timedelta(days=6)
        return (
            fallback_start.strftime('%Y-%m-%d'),
            fallback_end.strftime('%Y-%m-%d')
        )


def upload_csv_to_google_sheet(csv_file: str, spreadsheet_id: str, sheet_name: str):
    """Upload a CSV file to a specific Google Sheet tab, replacing its contents.

    Uses Google Service Account credentials from environment variables.
    """
    if not service_account or not build:
        raise ImportError("Google API dependencies not installed. Run: pip install google-api-python-client google-auth")
    
    try:
        # Load Google credentials from Environment Variables
        project_id = get_env_variable('GOOGLE_SA_PROJECT_ID', required=True)
        private_key_id = get_env_variable('GOOGLE_SA_PRIVATE_KEY_ID', required=True)
        client_email = get_env_variable('GOOGLE_SA_CLIENT_EMAIL', required=True)
        client_id = get_env_variable('GOOGLE_SA_CLIENT_ID', required=True)
        universe_domain = get_env_variable('GOOGLE_SA_UNIVERSE_DOMAIN', default="googleapis.com")
        
        # Read GOOGLE_SA_PRIVATE_KEY directly from environment
        # The issue was that get_env_variable wasn't working well with the private key
        # because it contains special characters
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), 'r') as env_file:
            env_content = env_file.read()
            
        # Extract the private key using a more direct method
        import re
        private_key_match = re.search(r'GOOGLE_SA_PRIVATE_KEY=(["\'])(.+?)\1', env_content, re.DOTALL)
        
        if private_key_match:
            # Get the raw key (without quotes)
            private_key = private_key_match.group(2)
            # Replace \n with actual newlines
            private_key = private_key.replace('\\n', '\n')
            logging.info(f"Successfully loaded private key from .env ({len(private_key)} characters)")
        else:
            # Fallback - try reading directly from environment
            logging.warning("Could not extract private key from .env file, trying environment variables")
            private_key = os.environ.get('GOOGLE_SA_PRIVATE_KEY', '')
            private_key = private_key.replace('\\n', '\n')
            
            if len(private_key) < 100:  # A valid key should be much longer
                logging.error(f"Private key appears too short: {len(private_key)} characters")
                raise ValueError("Invalid or missing private key")
                
        # Validate the key format
        if not private_key.startswith("-----BEGIN PRIVATE KEY-----"):
            logging.error("Private key has incorrect format")
            raise ValueError("Invalid private key format")
        
        # Create credentials dictionary for service account auth
        credentials_dict = {
            "type": "service_account",
            "project_id": project_id,
            "private_key_id": private_key_id,
            "private_key": private_key,
            "client_email": client_email,
            "client_id": client_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{client_email}",
            "universe_domain": universe_domain
        }
        
        # Generate credentials from the dictionary
        credentials = service_account.Credentials.from_service_account_info(
            credentials_dict, 
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        
        # Build the Sheets service
        service = build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logging.error(f"Failed to initialize Google Sheets API: {e}")
        raise

    try:
        # Read CSV file as 2D array of values
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            values = list(reader)
        
        # Get the spreadsheet and clear values in the specified tab
        sheet = service.spreadsheets()
        
        # Clear existing values
        clear_request = sheet.values().clear(
            spreadsheetId=spreadsheet_id,
            range=sheet_name,
            body={}
        )
        clear_request.execute()
        
        # Update with new values
        update_request = sheet.values().update(
            spreadsheetId=spreadsheet_id,
            range=sheet_name,
            valueInputOption='USER_ENTERED',
            body={
                'values': values
            }
        )
        update_request.execute()
        logging.info(f"Successfully uploaded {csv_file} to Google Sheet ID: {spreadsheet_id}, Tab: {sheet_name}")
    except FileNotFoundError:
        logging.error(f"CSV file not found: {csv_file}")
        raise
    except Exception as e:
        logging.error(f"Error uploading to Google Sheets: {e}")
        raise


def main() -> None:
    """Main entry point for the script: parses arguments, fetches data, writes CSV, and optionally uploads to Google Sheets."""
    # Load environment variables first, so they're available throughout the function
    load_environment()
    
    parser = argparse.ArgumentParser(description="Convert Harvest time entries to CSV format")
    parser.add_argument('--from-date', default=None, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to-date', default=None, help='End date (YYYY-MM-DD)')
    parser.add_argument('--output', default=None, help='Output CSV file name (overrides env var)')
    parser.add_argument('--json', default=None, help='(Optional) Save raw JSON to this file')
    parser.add_argument('--user', help='User prefix for environment variables (e.g., WILLIAM_DIAZ_)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()
    
    # If --user argument is provided, override the automatically set USER_PREFIX
    if args.user:
        os.environ['USER_PREFIX'] = args.user
        logging.info(f"Set USER_PREFIX to {args.user} from command line argument")
    
    # Reconfigure logging if debug flag is set
    global logger
    logger = setup_logging(debug=args.debug)
    
    # Set user prefix if provided via command line
    if args.user:
        os.environ['USER_PREFIX'] = args.user.upper()
    # Otherwise, try to find a user prefix in the environment variables
    elif 'USER_PREFIX' not in os.environ:
        # Look for any environment variable that ends with _HARVEST_USER_AGENT
        for key in os.environ:
            if key.endswith('_HARVEST_USER_AGENT'):
                prefix = key.replace('_HARVEST_USER_AGENT', '_')
                os.environ['USER_PREFIX'] = prefix
                logging.info(f"Auto-detected user prefix from environment: {prefix}")
                break
    
    # Get the current user prefix for logging
    prefix = os.environ.get('USER_PREFIX', '')
    user_email = get_env_variable('HARVEST_USER_AGENT', 'unknown user')
    logging.info(f"Processing time entries for: {user_email} (Prefix: {prefix or 'none'})")
    

    # Determine date range
    # Priority: CLI arguments > environment variables > last week
    env_from = os.environ.get('FROM_DATE')
    env_to = os.environ.get('TO_DATE')
    
    if args.from_date and args.to_date:
        from_date = args.from_date
        to_date = args.to_date
        logging.info(f"Using --from-date and --to-date arguments: {from_date} to {to_date}")
    elif args.from_date:
        from_dt = datetime.strptime(args.from_date, '%Y-%m-%d')
        from_date, to_date = get_last_week_range()
        logging.info(f"Only --from-date provided, using range: {from_date} to {to_date}")
    elif args.to_date:
        to_dt = datetime.strptime(args.to_date, '%Y-%m-%d')
        from_date, to_date = get_last_week_range()
        logging.info(f"Only --to-date provided, using range: {from_date} to {to_date}")
    elif env_from and env_to:
        from_date = env_from
        to_date = env_to
        logging.info(f"Using FROM_DATE and TO_DATE from environment: {from_date} to {to_date}")
    elif env_from:
        from_date_dt = datetime.strptime(env_from, '%Y-%m-%d')
        from_date, to_date = get_last_week_range()
        logging.info(f"Only FROM_DATE from environment, using range: {from_date} to {to_date}")
    elif env_to:
        to_date_dt = datetime.strptime(env_to, '%Y-%m-%d')
        from_date, to_date = get_last_week_range()
        logging.info(f"Only TO_DATE from environment, using range: {from_date} to {to_date}")
    else:
        from_date, to_date = get_last_week_range()
        logging.info(f"No date range provided, using last week: {from_date} to {to_date}")

    # Determine output paths
    output_name = args.output or get_env_variable('CSV_OUTPUT_FILE', 'harvest_export.csv')
    
    # Set default output directory based on environment
    default_output_dir = 'output'  # Default to local output directory
    if os.path.exists('/.env') or os.path.isfile('/app/.env'):
        default_output_dir = '/app/output'  # Use Docker path if in container
    
    output_dir = os.environ.get('OUTPUT_DIR', default_output_dir)
    
    # If output file doesn't have a path, put it in the output directory
    if not os.path.dirname(output_name):
        output_file = os.path.join(output_dir, output_name)
    else:
        output_file = output_name
        
    # Ensure output directory exists
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_file)) or '.', exist_ok=True)
    except OSError as e:
        logging.error(f"Could not create output directory: {e}")
        # Fall back to current directory
        output_file = os.path.join('.', os.path.basename(output_file))
        
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    logging.info(f"Using output file: {output_file}")
    
    # JSON export settings
    default_json_path = os.path.join(output_dir, 'harvest_raw.json')
    json_file = args.json or default_json_path
    enable_raw_json = os.environ.get('ENABLE_RAW_JSON') == '1'

    # Get Harvest API credentials with support for user prefixes
    try:
        account_id = get_env_variable('HARVEST_ACCOUNT_ID', required=True)
        auth_token = get_env_variable('HARVEST_AUTH_TOKEN', required=True)
        user_agent = get_env_variable('HARVEST_USER_AGENT', 'Harvest API Script')
        
        logging.info(f"Using Harvest account: {account_id}")
        logging.info(f"Authenticated as: {user_agent}")
        
    except RuntimeError as e:
        logging.critical(f"Configuration error: {e}")
        logging.info("Make sure to set the required environment variables with or without a user prefix")
        return

    # Download data
    try:
        # Download time entries
        data = download_time_entries(account_id, auth_token, user_agent, from_date, to_date)
    except ValueError as e:
        logging.critical(f"Validation error: {e}")
        return
    except requests.RequestException as e:
        logging.critical(f"Failed to download time entries: {e}")
        return
    except Exception as e:
        logging.critical(f"Failed to download time entries: {e}")
        return

    # Optionally save raw JSON
    if json_file and (enable_raw_json or args.json):
        try:
            # Ensure the directory exists
            json_dir = os.path.dirname(json_file) or output_dir
            os.makedirs(json_dir, exist_ok=True)
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logging.info(f"Saved raw JSON to {json_file}")
        except (IOError, OSError) as e:
            logging.error(f"Error saving JSON to {json_file}: {e}")
            # Don't fail the whole process if JSON save fails

    # Parse and write CSV
    try:
        rows = parse_time_entries(data)
        write_csv(rows, output_file)
    except Exception as e:
        logging.critical(f"Failed to process or write CSV: {e}")
        return

    # Google Sheets upload configuration
    # These variables should be prefixed with the user's name (handled by get_env_variable)
    spreadsheet_id = get_env_variable('GOOGLE_SHEET_ID')
    sheet_name = get_env_variable('GOOGLE_SHEET_TAB_NAME')
    upload_flag = get_env_variable('UPLOAD_TO_GOOGLE_SHEET', '0')
    
    # Check for required Google Sheets credentials (these are global variables)
    creds_env_present = all(
        os.environ.get(var) for var in [
            'GOOGLE_SA_PROJECT_ID',
            'GOOGLE_SA_PRIVATE_KEY_ID', 
            'GOOGLE_SA_PRIVATE_KEY',
            'GOOGLE_SA_CLIENT_EMAIL',
            'GOOGLE_SA_CLIENT_ID'
        ]
    )
    
    # Determine if upload is enabled and required credentials are present
    upload_enabled = upload_flag.lower() in ('1', 'true', 'yes')
    sheets_configured = bool(spreadsheet_id and sheet_name)
    
    if upload_enabled:
        logging.info("Google Sheets upload: enabled")
        if not sheets_configured:
            logging.error("Missing Google Sheet ID or Tab Name. Check your environment variables.")
            return
        
        if not creds_env_present:
            logging.error("Missing Google Service Account credentials. Check your environment variables.")
            return
            
        try:
            upload_csv_to_google_sheet(output_file, spreadsheet_id, sheet_name)
            logging.info(f"Successfully uploaded to Google Sheet ID: {spreadsheet_id}, Tab: {sheet_name}")
        except Exception as e:
            logging.error(f"Failed to upload to Google Sheets: {e}")
    else:
        logging.info("Google Sheets upload: disabled (set UPLOAD_TO_GOOGLE_SHEET=1 to enable)")


if __name__ == "__main__":
    # Usage: python convert_harvest_json_to_csv.py [--from-date YYYY-MM-DD] [--to-date YYYY-MM-DD] [--output FILE] [--json FILE]
    main()
