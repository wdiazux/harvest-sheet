import os
import json
import logging
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# Rich for better logging and output (if available)
try:
    from rich.console import Console
    from rich.logging import RichHandler
    # Create console for rich output
    console = Console()
    # Configure rich logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_time=False)]
    )
    # Define logger
    logger = logging.getLogger(__name__)
except ImportError:
    # Fallback to standard logging if rich is not available
    console = None
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    
    # Simple print function to mimic rich console
    class SimplePrint:
        def print(self, message, **kwargs):
            print(message)
    
    if console is None:
        console = SimplePrint()

def load_environment() -> Optional[str]:
    """Load environment variables from .env file.
    
    In Docker, looks for .env at /app/.env
    Otherwise, looks for .env in script directory or parent directories.
    
    Also detects user prefix from environment variables pattern.
    
    Returns:
        The detected user prefix, if any
    """
    user_prefix = os.environ.get('USER_PREFIX', '')
    
    # Check if running in Docker
    in_docker = os.path.exists('/.dockerenv') or os.path.isdir('/app')
    
    if in_docker:
        # In Docker, load from /app/.env
        env_path = '/app/.env'
        if os.path.exists(env_path):
            logger.info(f"Loading environment from Docker path: {env_path}")
            # We're not using python-dotenv directly to avoid the dependency
            # Instead, manually read the file and set environment variables
            try:
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ.setdefault(key, value)
            except Exception as e:
                logger.warning(f"Failed to load .env file: {e}")
    else:
        # Not in Docker, try to find .env in current or parent directories
        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).parent.parent / '.env'
            if env_path.exists():
                logger.info(f"Loading environment from: {env_path}")
                load_dotenv(env_path)
            else:
                logger.warning(f".env file not found at {env_path}")
        except ImportError:
            logger.warning("python-dotenv not installed, skipping .env loading")
    
    # Detect user prefix from environment variables if not explicitly set
    if not user_prefix:
        # Look for common patterns in environment variables to detect user prefix
        for key in os.environ:
            if key.endswith('_HARVEST_ACCOUNT_ID') or key.endswith('_GOOGLE_SHEET_ID'):
                user_prefix = key.rsplit('_', 3)[0] + '_'
                logger.info(f"Detected user prefix: {user_prefix}")
                break
    
    return user_prefix

def get_env_variable(var_name: str, default: Optional[str] = None, required: bool = False) -> str:
    """Return an environment variable, with support for user prefixes.
    
    Args:
        var_name: The base name of the environment variable
        default: Default value if variable is not found
        required: If True, raises error when variable is not found
        
    Returns:
        The value of the environment variable, or the default
        
    Raises:
        RuntimeError: If required is True and variable is not found
    """
    # Get current user prefix - either from global or detect from environment
    user_prefix = os.environ.get('USER_PREFIX', '')
    
    # Try with user prefix first, then without
    # Make sure we add an underscore between prefix and var_name only if prefix doesn't end with underscore
    prefixed_name = None
    if user_prefix:
        if user_prefix.endswith('_'):
            prefixed_name = f"{user_prefix}{var_name}"
        else:
            prefixed_name = f"{user_prefix}_{var_name}"
    value = None
    
    # Look for prefixed version first
    if prefixed_name:
        value = os.environ.get(prefixed_name)
        if value:
            logger.debug(f"Using prefixed environment variable: {prefixed_name}={value}")
            return value
    
    # Fall back to unprefixed version
    value = os.environ.get(var_name, default)
    
    if required and not value:
        error_msg = f"Required environment variable not found: "
        if prefixed_name:
            error_msg += f"{prefixed_name} or {var_name}"
        else:
            error_msg += f"{var_name}"
        raise RuntimeError(error_msg)
    
    return value

def get_absolute_path(relative_path: str) -> str:
    """Convert a relative path to an absolute path, respecting Docker environment.
    
    If running in Docker, paths will be rooted at /app.
    Otherwise, they'll be relative to the script's directory.
    
    Args:
        relative_path: A path relative to the application root
        
    Returns:
        An absolute path appropriate for the current environment
    """
    # Check if we're running in Docker
    in_docker = os.path.exists('/.dockerenv') or os.path.isdir('/app')
    
    # If path is already absolute, return it
    if os.path.isabs(relative_path):
        return relative_path
        
    if in_docker:
        # In Docker, root at /app
        return os.path.join('/app', relative_path)
    else:
        # Not in Docker, root at script directory's parent (project root)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(project_root, relative_path)

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
        # Load environment variables and detect user prefix
        user_prefix = load_environment()
        
        # Set user prefix if detected but not already set
        if user_prefix and not os.environ.get('USER_PREFIX'):
            os.environ['USER_PREFIX'] = user_prefix
            logger.info(f"Set USER_PREFIX to: {user_prefix}")
        
        # Get required environment variables
        account_id = get_env_variable('HARVEST_ACCOUNT_ID', required=True)
        auth_token = get_env_variable('HARVEST_AUTH_TOKEN', required=True)
        user_agent = get_env_variable('HARVEST_USER_AGENT', 'Harvest-Script/1.0')
        user_id = get_env_variable('HARVEST_USER_ID')
        
        # Check if raw JSON output is enabled
        enable_raw_json = get_env_variable('ENABLE_RAW_JSON', '0').lower() in ('1', 'true', 'yes')
        
        # Log configuration
        if console:
            console.print(f"[blue]Harvest API Configuration:[/blue]")
            console.print(f"  Account ID: {account_id}")
            console.print(f"  User Agent: {user_agent}")
            console.print(f"  User ID Filter: {user_id or 'None (all users)'}")
            console.print(f"  Date Range: {from_date} to {to_date}")
            console.print(f"  Raw JSON: {'Enabled' if enable_raw_json else 'Disabled'}")
            console.print(f"  Output File: {output_file}")
        else:
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
        if console:
            console.print(f"[bold blue]Fetching data from Harvest API...[/bold blue]")
        else:
            logger.info(f"Fetching data from {from_date} to {to_date}...")
        
        response = requests.get(base_url, headers=headers, params=params)
        response.raise_for_status()
        
        # Get all pages of results
        data = response.json()
        all_entries = data.get('time_entries', [])
        
        # Handle pagination if needed
        total_pages = 1
        current_page = 1
        
        while 'next' in response.links:
            total_pages += 1
            current_page += 1
            
            if console:
                console.print(f"[dim]Processing page {current_page}...[/dim]")
            else:
                logger.info(f"Processing page {current_page}...")
                
            next_url = response.links['next']['url']
            response = requests.get(next_url, headers=headers)
            response.raise_for_status()
            page_data = response.json()
            all_entries.extend(page_data.get('time_entries', []))
        
        result = {'time_entries': all_entries}
        
        # Only save if raw JSON is enabled or this is a debug script
        if enable_raw_json or __name__ == "__main__":
            # Convert output_file to absolute path if needed
            if not os.path.isabs(output_file):
                output_file = get_absolute_path(output_file)
            
            # Ensure output directory exists
            output_path = Path(output_file)
            ensure_directory_exists(output_path.parent)
            
            # Save the raw JSON data
            with open(output_path, 'w') as f:
                json.dump(result, f, indent=2)
            
            if console:
                console.print(f"[green]Successfully saved {len(all_entries)} time entries to {output_file}[/green]")
            else:
                logger.info(f"Successfully saved {len(all_entries)} time entries to {output_file}")
        else:
            if console:
                console.print(f"[yellow]Raw JSON saving is disabled. Set ENABLE_RAW_JSON=1 to enable.[/yellow]")
            else:
                logger.info("Raw JSON saving is disabled")
        
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
    from datetime import datetime, timedelta
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Fetch time entries from Harvest API')
    parser.add_argument('--from-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to-date', help='End date (YYYY-MM-DD)')
    parser.add_argument('--output', help='Output JSON file name')
    parser.add_argument('--user', help='User prefix for environment variables (e.g., JOHN_DOE_)')
    parser.add_argument('--last-month', action='store_true', help='Fetch data for the last complete month')
    
    args = parser.parse_args()
    
    # Set user prefix if provided
    if args.user:
        os.environ['USER_PREFIX'] = args.user
    
    # Default dates if not provided
    if args.last_month:
        # Get the last complete month
        today = datetime.now()
        first_of_this_month = today.replace(day=1)
        last_of_prev_month = first_of_this_month - timedelta(days=1)
        first_of_prev_month = last_of_prev_month.replace(day=1)
        
        from_date = first_of_prev_month.strftime('%Y-%m-%d')
        to_date = last_of_prev_month.strftime('%Y-%m-%d')
        
        if console:
            console.print(f"[blue]Using last month: {from_date} to {to_date}[/blue]")
        else:
            logger.info(f"Using last month: {from_date} to {to_date}")
    else:
        # Use provided dates or defaults
        from_date = args.from_date or (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        to_date = args.to_date or datetime.now().strftime('%Y-%m-%d')
    
    # Use output filename as provided or generate a default based on date range
    if not args.output:
        # Generate default filename
        user_prefix = os.environ.get('USER_PREFIX', '')
        user_part = user_prefix.rstrip('_').lower() if user_prefix else 'harvest'
        output_file = f"{user_part}_data_{from_date}_to_{to_date}.json"
        
        # Store in output directory
        output_dir = get_absolute_path('output')
        output_file = os.path.join(output_dir, output_file)
    else:
        output_file = args.output
    
    try:
        # Get environment variables and fetch data
        result = fetch_harvest_data(from_date, to_date, output_file)
        entry_count = len(result.get('time_entries', []))
        
        # Show summary
        if console:
            if entry_count > 0:
                console.print(f"[bold green]Successfully fetched {entry_count} time entries[/bold green]")
            else:
                console.print(f"[yellow]No time entries found for the specified period[/yellow]")
        else:
            logger.info(f"Successfully fetched {entry_count} time entries")
            
        return 0
    except RuntimeError as e:
        if console:
            console.print(f"[bold red]Configuration error: {e}[/bold red]")
        else:
            logger.error(f"Configuration error: {e}")
        return 1
    except requests.RequestException as e:
        if console:
            console.print(f"[bold red]API request failed: {e}[/bold red]")
        else:
            logger.error(f"API request failed: {e}")
        return 1
    except Exception as e:
        if console:
            console.print(f"[bold red]Unexpected error: {e}[/bold red]")
            import traceback
            console.print(traceback.format_exc())
        else:
            logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())