import os
import json
import requests
import argparse
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Any, Dict, List, Optional, Tuple

# Rich for better logging and output
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress
from rich.panel import Panel

# Pydantic for data validation
from pydantic import BaseModel, field_validator

# Create console for rich output
console = Console()

# Configure rich logging - only needed for compatibility with existing code
# Eventually we'll transition everything to use console directly
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False)]
)

# Application metadata
APP_NAME = "Harvest to Google Sheets Exporter"
APP_VERSION = "1.1.0"

# Show application banner
console.print(Panel.fit(
    f"[bold green]{APP_NAME}[/bold green] [dim]v{APP_VERSION}[/dim]", 
    subtitle="[dim]Running in Docker[/dim]" if os.path.exists('/.dockerenv') or os.path.isdir('/app') else ""
))

# Google Sheets API imports - try/except for graceful failure if deps missing
try:
    from google.oauth2 import service_account
    import gspread
except ImportError:
    console.print("[yellow]Warning: Google Sheets API dependencies not installed[/yellow]")
    console.print("[dim]Install with: pip install gspread google-auth[/dim]")
    service_account = None
    gspread = None

# Security helper functions for masking personal information in logs
def mask_email(email: str) -> str:
    """Mask email address for secure logging.

    Args:
        email: Email address to mask

    Returns:
        Masked email (e.g., wi***@***.com)
    """
    if not email or '@' not in email:
        return '***'

    try:
        local, domain = email.split('@', 1)
        # Show first 2 chars of local part, mask the rest
        masked_local = local[:2] + '***' if len(local) > 2 else '***'
        # Mask domain but show TLD
        domain_parts = domain.split('.')
        if len(domain_parts) > 1:
            masked_domain = '***.' + domain_parts[-1]
        else:
            masked_domain = '***'
        return f"{masked_local}@{masked_domain}"
    except Exception:
        return '***'


def mask_user_prefix(prefix: str) -> str:
    """Mask user prefix for secure logging.

    Args:
        prefix: User prefix (e.g., 'WILLIAM_DIAZ_')

    Returns:
        Hashed identifier (e.g., 'USER_a1b2c3d4')
    """
    if not prefix or prefix == '':
        return 'default'

    try:
        import hashlib
        # Create a short hash of the prefix for logging
        hash_obj = hashlib.sha256(prefix.encode())
        short_hash = hash_obj.hexdigest()[:8]
        return f"USER_{short_hash}"
    except Exception:
        return 'USER_unknown'


# Define Pydantic models for Harvest API data
class HarvestUser(BaseModel):
    id: int
    name: str
    
    @property
    def first_name(self) -> str:
        parts = self.name.split()
        return parts[0] if parts else ''
    
    @property
    def last_name(self) -> str:
        parts = self.name.split()
        return ' '.join(parts[1:]) if len(parts) > 1 else ''

class HarvestClient(BaseModel):
    id: int
    name: str
    currency: Optional[str] = None

class HarvestProject(BaseModel):
    id: int
    name: str
    code: Optional[str] = None

class HarvestTask(BaseModel):
    id: int
    name: str

class HarvestTimeEntry(BaseModel):
    id: int
    spent_date: str
    hours: float
    hours_without_timer: Optional[float] = None
    rounded_hours: Optional[float] = None
    notes: Optional[str] = ''
    billable: bool = False
    billable_rate: Optional[float] = None
    cost_rate: Optional[float] = None
    is_locked: Optional[bool] = None
    locked_reason: Optional[str] = None
    is_closed: Optional[bool] = None
    is_billed: Optional[bool] = None
    is_running: Optional[bool] = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_time: Optional[str] = None
    ended_time: Optional[str] = None
    user: HarvestUser
    client: HarvestClient
    project: HarvestProject
    task: HarvestTask
    
    @field_validator('notes', mode='before')
    def empty_string_for_none(cls, v):
        return v or ''
        
    @property
    def billable_amount(self) -> Optional[float]:
        if self.billable and self.billable_rate and self.hours:
            return self.billable_rate * self.hours
        return None
        
    @property
    def billable_text(self) -> str:
        return 'Yes' if self.billable else 'No'
        
    @property
    def billed_text(self) -> str:
        return 'Yes' if self.is_billed else 'No'
        
    @property
    def locked_text(self) -> str:
        return 'Yes' if self.is_locked else 'No'
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for DataFrame creation"""
        base_dict = {
            'Date': self.spent_date,
            'Client': self.client.name,
            'Project': self.project.name,
            'Project Code': self.project.code or '',
            'Task': self.task.name,
            'Notes': self.notes,
            'Hours': float(self.hours),
            'Billable?': self.billable_text,
            'Billable Amount': self.billable_amount if self.billable_amount else '',
            'First Name': self.user.first_name,
            'Last Name': self.user.last_name,
        }
        
        # Add advanced fields if requested through environment variable
        include_advanced = get_env_variable('INCLUDE_ADVANCED_FIELDS', '0').lower() in ('1', 'true', 'yes')
        if include_advanced:
            advanced_fields = {
                'Rounded Hours': self.rounded_hours or self.hours,
                'Is Billed': self.billed_text,
                'Is Locked': self.locked_text,
                'Started': self.started_time or '',
                'Ended': self.ended_time or '',
                'Created At': self.created_at or '',
                'Updated At': self.updated_at or '',
                'Cost Rate': self.cost_rate or '',
            }
            base_dict.update(advanced_fields)
            
        return base_dict

class HarvestResponse(BaseModel):
    time_entries: List[HarvestTimeEntry] = []

def detect_all_user_prefixes() -> list:
    """Detect all user prefixes from environment variables.
    
    Searches for environment variables matching the pattern *_HARVEST_ACCOUNT_ID
    to identify all user prefixes in the system.
    
    Returns:
        list: List of user prefixes (e.g., ['WILLIAM_DIAZ_', 'JOHN_DOE_'])
    """
    prefixes = []
    
    # Look for all user-specific environment variables
    for key in os.environ:
        if key.endswith('_HARVEST_ACCOUNT_ID') and not key.startswith('USER_'):
            prefix = key.replace('_HARVEST_ACCOUNT_ID', '') + '_'
            prefixes.append(prefix)
    
    # Remove duplicates while preserving order
    unique_prefixes = []
    for prefix in prefixes:
        if prefix not in unique_prefixes:
            unique_prefixes.append(prefix)
    
    return unique_prefixes


def load_environment() -> None:
    """Load environment variables from .env file.
    
    In Docker, looks for .env at /app/.env
    Otherwise, looks for .env in script directory or parent directories.
    
    Also detects user prefix from environment variables pattern.
    """
    try:
        from dotenv import load_dotenv, find_dotenv
        
        # Check if we're running in a Docker container
        in_docker = os.path.exists('/.dockerenv') or os.path.isdir('/app')
        docker_env_path = '/app/.env'
        
        if in_docker and os.path.isfile(docker_env_path):
            # In Docker, use /app/.env path
            load_dotenv(docker_env_path)
            console.print("[green]Loaded environment variables from .env file[/green]")
            console.print("[dim]Running in Docker container environment[/dim]")
        else:
            # Look for .env in script directory first
            script_dir = os.path.dirname(os.path.abspath(__file__))
            local_env = os.path.join(script_dir, '.env')

            if os.path.isfile(local_env):
                # Use script directory's .env
                load_dotenv(local_env)
                console.print("[green]Loaded environment variables from .env file[/green]")
            else:
                # Look for .env in parent directories
                found = find_dotenv(usecwd=True)
                if found:
                    load_dotenv(found)
                    console.print("[green]Loaded environment variables from .env file[/green]")
                else:
                    console.print("[yellow]No .env file found, using only OS environment variables[/yellow]")
        
        # Try to detect the user prefix
        global USER_PREFIX
        
        # First look for explicitly set USER_PREFIX
        if os.environ.get('USER_PREFIX'):
            USER_PREFIX = os.environ.get('USER_PREFIX', '')
            masked_prefix = mask_user_prefix(USER_PREFIX)
            console.print(f"[blue]Using explicitly set user prefix: {masked_prefix}[/blue]")
        else:
            # Check for any already-set user-specific environment variables
            for key in os.environ:
                if key.endswith('_HARVEST_ACCOUNT_ID') and not key.startswith('USER_'):
                    prefix = key.replace('_HARVEST_ACCOUNT_ID', '')
                    USER_PREFIX = prefix + '_'
                    masked_prefix = mask_user_prefix(USER_PREFIX)
                    console.print(f"[green]Automatically detected user prefix: {masked_prefix}[/green]")
                    break
        
        # Verify critical environment variables for Google Sheets
        gs_vars_present = all(os.environ.get(var) for var in [
            'GOOGLE_SA_PROJECT_ID',
            'GOOGLE_SA_PRIVATE_KEY_ID',
            'GOOGLE_SA_PRIVATE_KEY',
            'GOOGLE_SA_CLIENT_EMAIL',
            'GOOGLE_SA_CLIENT_ID'
        ])
        
        if not gs_vars_present:
            console.print("[yellow]Warning: Some Google Service Account variables are missing[/yellow]")
            console.print("[dim]Google Sheets upload may not work properly[/dim]")
    
    except ImportError:
        console.print("[yellow]python-dotenv not installed. Using only OS environment variables.[/yellow]")
        console.print("[dim]Install with: pip install python-dotenv[/dim]")
    except Exception as e:
        console.print(f"[bold red]Error loading .env file: {e}[/bold red]")
        console.print_exception()

# Configure file logging if running in Docker
in_docker = os.path.exists('/.dockerenv') or os.path.isdir('/app')

if in_docker:
    # In Docker, set up file logging in addition to console
    log_dir = '/app/logs'
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'harvest_export.log')
    
    # Add a file handler to the root logger
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(file_handler)
    
    console.print(f"[dim]Logging to file: {log_file}[/dim]")


def get_absolute_path(relative_path: str) -> str:
    """Convert a relative path to an absolute path, respecting Docker environment.
    
    If running in Docker, paths will be rooted at /app.
    Otherwise, they'll be relative to the script's directory.
    
    Args:
        relative_path: A path relative to the application root
        
    Returns:
        An absolute path appropriate for the current environment
    """
    # Check if we're running in a Docker container
    in_docker = os.path.exists('/.dockerenv') or os.path.isdir('/app')
    
    if in_docker:
        # In Docker, root at /app
        return os.path.join('/app', relative_path)
    else:
        # In development, use script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, relative_path)

def get_env_variable(var_name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Return an environment variable, with support for user prefixes.
    
    Args:
        var_name: The base name of the environment variable
        default: Default value if variable is not found
        required: Whether to raise an error if the variable is not found
        
    Returns:
        The value of the environment variable, or the default
        
    Raises:
        RuntimeError: If required is True and variable is not found
    """
    # Initialize USER_PREFIX if it hasn't been set yet
    if 'USER_PREFIX' not in globals():
        global USER_PREFIX
        USER_PREFIX = os.environ.get('USER_PREFIX', '')
    
    # First, try with user prefix if it exists
    value = None
    source = None
    
    if USER_PREFIX:
        prefixed_var = f"{USER_PREFIX}{var_name}"
        value = os.environ.get(prefixed_var)
        
        if value is not None:
            source = f"user-prefixed variable {prefixed_var}"
    
    # Then try without prefix
    if value is None:
        value = os.environ.get(var_name)
        if value is not None:
            source = f"global variable {var_name}"
    
    # Return default or raise error if required
    if value is None:
        if required and default is None:
            console.print(f"[bold red]Error: Required environment variable not found: {var_name}[/bold red]")
            console.print(f"[dim]Tried with prefix: {USER_PREFIX}{var_name} and without prefix: {var_name}[/dim]")
            raise RuntimeError(f"Required environment variable not found: {var_name}")
        
        if default is not None:
            source = "default value"
            value = default
        else:
            source = "None (not found)"
    
    # For sensitive variables, don't log the actual value
    sensitive_vars = ['TOKEN', 'KEY', 'SECRET', 'PASSWORD', 'AUTH']
    is_sensitive = any(s in var_name.upper() for s in sensitive_vars)
    
    if is_sensitive and value:
        display_value = f"{'*' * min(len(value), 10)}{' (redacted)'}" 
    else:
        display_value = value
        
    # Only log for required variables or those that were found
    if required or value is not default:
        console.print(f"[dim]Using {var_name}: {display_value} (from {source})[/dim]")
        
    return value


def download_time_entries(account_id: str, auth_token: str, user_agent: str, from_date: str, to_date: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Fetch all Harvest time entries for the given date range, handling pagination.
    When user_id is provided, time entries will be filtered for that specific user.
    
    Args:
        account_id: Harvest account ID (required)
        auth_token: Harvest API token (required)
        user_agent: User agent string to identify your app to Harvest API
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
        user_id: Optional Harvest user ID to filter entries by
        
    Returns:
        Dictionary containing all time entries
        
    Raises:
        requests.RequestException: If there's an error with the API request
        ValueError: If required parameters are missing
    """
    # Validate required parameters
    if not all([account_id, auth_token, user_agent, from_date, to_date]):
        console.print("[bold red]Error: Missing required parameters for Harvest API request[/bold red]")
        raise ValueError("Missing required parameters for Harvest API request")
    
    # Prepare headers
    headers = {
        'Harvest-Account-ID': account_id,
        'Authorization': f'Bearer {auth_token}',
        'User-Agent': user_agent,
        'Content-Type': 'application/json',
    }
    
    # Base URL for the Harvest Time Entries API
    base_url = 'https://api.harvestapp.com/v2/time_entries'
    
    # Set up query parameters
    params = {
        'from': from_date,
        'to': to_date,
        'page': 1,
        'per_page': 100  # Maximum allowed by Harvest API
    }
    
    # Add user_id filter if provided as parameter or from environment
    if not user_id:
        user_id = get_env_variable('HARVEST_USER_ID')
    
    if user_id:
        params['user_id'] = user_id
        console.print(f"[blue]Filtering time entries for user ID: {user_id}[/blue]")
    
    console.print(f"[blue]Fetching time entries from {from_date} to {to_date}[/blue]")
    
    # Fetch first page to get total pages
    try:
        with console.status("[bold green]Contacting Harvest API...") as status:
            response = requests.get(base_url, headers=headers, params=params)
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
            
            # Parse response data
            data = response.json()
            
            # Get pagination info
            total_pages = data.get('total_pages', 1)
            total_entries = data.get('total_entries', 0)
            
            # Extract time entries from first page
            all_entries = data.get('time_entries', [])
            
            console.print(f"[green]Found {total_entries} time entries across {total_pages} pages[/green]")
    
    except requests.RequestException as e:
        console.print(f"[bold red]Error connecting to Harvest API: {e}[/bold red]")
        console.print_exception()
        raise
    
    # If we have more than one page, fetch the rest with a progress bar
    if total_pages > 1:
        with Progress() as progress:
            # Create a task in the progress bar
            task = progress.add_task("[cyan]Downloading time entries...", total=total_pages-1)
            
            # Start from page 2 since we already got page 1
            for page in range(2, total_pages + 1):
                try:
                    params['page'] = page
                    response = requests.get(base_url, headers=headers, params=params)
                    response.raise_for_status()
                    
                    # Add entries from this page
                    page_data = response.json()
                    all_entries.extend(page_data.get('time_entries', []))
                    
                    # Update progress bar
                    progress.update(task, advance=1, description=f"[cyan]Downloading page {page}/{total_pages}...")
                    
                except requests.RequestException as e:
                    console.print(f"[yellow]Warning: Error fetching page {page}: {e}[/yellow]")
                    # Continue with next page instead of failing completely
    
    console.print(f"[green]Successfully downloaded {len(all_entries)} time entries[/green]")
    
    # Return data in same format as the Harvest API response
    return {
        'time_entries': all_entries,
        'total_entries': len(all_entries)
    }


def parse_time_entries(data: Dict[str, Any]) -> pd.DataFrame:
    """Convert Harvest API time entries into a pandas DataFrame for export with correct field mapping.
    
    Using Pydantic models for validation and pandas for data manipulation.
    """
    # Define output columns - these will be the columns in our final DataFrame
    output_columns = [
        "Date", "Client", "Project", "Project Code", "Task", "Notes", "Hours", 
        "Billable?", "Billable Amount", "First Name", "Last Name"
    ]
    
    # Handle empty data case
    if not data.get("time_entries"):
        console.print("[yellow]No time entries found in the data[/yellow]")
        return pd.DataFrame(columns=output_columns)
    
    try:
        # Use Pydantic to parse and validate the Harvest data
        harvest_data = HarvestResponse.model_validate(data)
        
        if not harvest_data.time_entries:
            console.print("[yellow]Time entries list is empty[/yellow]")
            return pd.DataFrame(columns=output_columns)
        
        # Process entries with a Rich progress bar
        with console.status("[bold green]Processing time entries...") as status:
            # Convert Pydantic models to dictionaries for DataFrame creation
            processed_entries = [entry.to_dict() for entry in harvest_data.time_entries]
        
        # Create DataFrame from processed entries
        if processed_entries:
            df = pd.DataFrame(processed_entries)
            # Ensure all output columns exist, even if empty
            for col in output_columns:
                if col not in df.columns:
                    df[col] = ''
            # Return only the columns we want, in the right order
            df = df[output_columns]
            console.print(f"[green]Successfully parsed {len(df)} time entries using Pydantic models[/green]")
            return df
        else:
            console.print("[yellow]No entries were processed successfully[/yellow]")
            return pd.DataFrame(columns=output_columns)
            
    except Exception as e:
        console.print(f"[bold red]Error parsing time entries: {e}[/bold red]")
        # Print a more detailed traceback with Rich
        console.print_exception()
        # Return an empty DataFrame with the correct columns
        return pd.DataFrame(columns=output_columns)


def add_summary_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Add summary rows to the DataFrame with totals for billable, non-billable, and specific tasks.

    Args:
        df: DataFrame containing time entries

    Returns:
        DataFrame with summary rows appended (if data exists)
    """
    # Only add summary rows if there are data rows
    if df.empty:
        return df

    # Get all columns to create empty summary rows
    all_columns = df.columns.tolist()

    # Create a base summary row with empty values for all columns
    def create_summary_row(notes_text: str, hours_value: float) -> Dict[str, Any]:
        row = {col: '' for col in all_columns}
        row['Notes'] = notes_text
        row['Hours'] = hours_value
        return row

    summary_rows = []

    # 1. Total Billable Hours
    billable_hours = df[df['Billable?'] == 'Yes']['Hours'].sum()
    if billable_hours > 0:
        summary_rows.append(create_summary_row('TOTAL BILLABLE', billable_hours))

    # 2. Total Non-Billable Hours
    non_billable_hours = df[df['Billable?'] == 'No']['Hours'].sum()
    if non_billable_hours > 0:
        summary_rows.append(create_summary_row('TOTAL NON BILLABLE', non_billable_hours))

    # 3. Total OKR's & PDP's Hours
    okr_hours = df[df['Task'] == "OKR's & PDP's"]['Hours'].sum()
    if okr_hours > 0:
        summary_rows.append(create_summary_row("TOTAL OKR's & PDP's", okr_hours))

    # 4. Total Learning & Development Hours
    learning_hours = df[df['Task'] == "Learning & Development"]['Hours'].sum()
    if learning_hours > 0:
        summary_rows.append(create_summary_row("TOTAL Learning & Development", learning_hours))

    # 5. Total Hours (sum of all time entries)
    total_hours = df['Hours'].sum()
    if total_hours > 0:
        summary_rows.append(create_summary_row('TOTAL HOURS', total_hours))

    # Add summary rows to the DataFrame if any exist
    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        df = pd.concat([df, summary_df], ignore_index=True)
        console.print(f"[green]Added {len(summary_rows)} summary row(s) to the report[/green]")

    return df


def add_resume_section(df: pd.DataFrame, original_df: pd.DataFrame) -> pd.DataFrame:
    """Add a resume section after the summary rows with formatted entry details.

    Args:
        df: DataFrame with summary rows already added
        original_df: Original DataFrame with time entries (without summary rows)

    Returns:
        DataFrame with resume section appended
    """
    if original_df.empty:
        return df

    all_columns = df.columns.tolist()

    def create_row(text: str) -> Dict[str, Any]:
        """Create a row with text only in the first column (Date/A)."""
        row = {col: '' for col in all_columns}
        row['Date'] = text
        return row

    rows_to_add = []

    # Add 3 empty separator rows
    for _ in range(3):
        rows_to_add.append(create_row(''))

    # Add RESUME title row
    rows_to_add.append(create_row('RESUME'))

    # Build all resume content as a single string with newlines
    resume_lines = []

    # Group entries by date and format them
    # Sort by date first
    sorted_df = original_df.sort_values('Date')

    # Group by date
    grouped = sorted_df.groupby('Date')

    previous_date = None
    for date, group in grouped:
        # Add blank line between different dates (except before first)
        if previous_date is not None:
            resume_lines.append('')

        # Format date as "jan 26" style
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%b %d').lower()
        except (ValueError, TypeError):
            formatted_date = str(date).lower()

        # Add each entry for this date
        for _, entry in group.iterrows():
            project_code = entry.get('Project Code', '') or ''
            project_name = entry.get('Project', '') or ''
            client_name = entry.get('Client', '') or ''
            task_name = entry.get('Task', '') or ''
            notes = entry.get('Notes', '') or ''
            hours = entry.get('Hours', 0)

            # Format hours with HOUR/HOURS
            hours_str = f"{hours} HOUR" if hours == 1 else f"{hours} HOURS"

            # Build the formatted line
            # Format: {date} >>> [{project_code}] {project_name} ( {client} ) {task} ({notes}) - {hours}
            parts = [f"{formatted_date}     >>> "]

            if project_code:
                parts.append(f"[{project_code}] ")

            parts.append(f"{project_name}")

            if client_name:
                parts.append(f" ( {client_name} )")

            parts.append(f" {task_name}")

            if notes:
                parts.append(f" ({notes})")

            parts.append(f" - {hours_str}")

            line = ''.join(parts)
            resume_lines.append(line)

        previous_date = date

    # Add single cell with all resume content joined by newlines
    if resume_lines:
        resume_content = '\n'.join(resume_lines)
        rows_to_add.append(create_row(resume_content))
        console.print(f"[green]Added resume section with {len(resume_lines)} entries[/green]")

    # Append rows to the DataFrame
    if rows_to_add:
        resume_df = pd.DataFrame(rows_to_add)
        df = pd.concat([df, resume_df], ignore_index=True)

    return df


def write_csv(data: pd.DataFrame, output_file: str) -> None:
    """Write the pandas DataFrame to a CSV file with the specified output filename.
    
    Args:
        data: Pandas DataFrame containing the data to write
        output_file: Path to the output CSV file. If not absolute, will be created in ./output/
    """
    # If output_file is not an absolute path, create it in the appropriate output directory
    if not os.path.isabs(output_file):
        # Use the Docker-aware path function to determine the output directory
        output_dir = get_absolute_path('output')
        logging.debug(f"Using output directory: {output_dir}")
        
        # Create the output directory if it doesn't exist
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            logging.warning(f"Could not create directory {output_dir}, using current directory: {e}")
            output_dir = '.'
            
        # Update the output file path
        output_file = os.path.join(output_dir, output_file)
    else:
        # Ensure the directory exists if it's an absolute path
        dir_path = os.path.dirname(output_file) or '.'
        try:
            os.makedirs(dir_path, exist_ok=True)
        except OSError as e:
            logging.warning(f"Could not create directory {dir_path}, output may fail: {e}")
            raise
    
    try:
        # Use pandas to_csv for more efficient writing
        # Add index=False to avoid adding an index column
        data.to_csv(output_file, index=False)
        logging.info(f"Successfully wrote {len(data)} rows to {output_file}")
    except Exception as e:
        logging.error(f"Error writing CSV: {e}")
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
        today = datetime.now()
        current_weekday = today.weekday()  # 0=Monday, 6=Sunday
        
        # Using dateutil for better date manipulation
        # If it's Friday(4), Saturday(5), or Sunday(6), use the current week
        if current_weekday >= 4:  # Fri-Sun: current week
            # Start date is Monday of current week
            start_date = today - relativedelta(days=current_weekday)
            end_date = start_date + relativedelta(days=6)  # Sunday
        else:  # Mon-Thu: previous week
            # Go back to previous week's Monday
            start_date = today - relativedelta(days=current_weekday, weeks=1)
            end_date = start_date + relativedelta(days=6)  # Sunday
        
        # Format and log
        result = (start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        console.print(f"[blue]Date range: {result[0]} to {result[1]}[/blue]")
        return result
        
    except Exception as e:
        console.print(f"[bold red]Error calculating date range: {e}[/bold red]")
        console.print_exception()
        
        # Fallback: Last 7 days
        today = datetime.now()
        start_date = today - relativedelta(days=7)
        result = (start_date.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'))
        console.print(f"[yellow]Fallback date range: {result[0]} to {result[1]}[/yellow]")
        return result


def get_google_private_key():
    """Get the Google private key, handling both Docker and local environments.
    
    In Docker, prioritizes environment variables passed with -e parameter.
    In local environments, reads from .env file if environment variables aren't working.
    
    Returns:
        The properly formatted private key or an empty string if not found
    """
    try:
        # Check if we're running in a Docker container
        in_docker = os.path.exists('/.dockerenv') or os.path.isdir('/app')
        
        # In Docker, environment variables are typically passed with -e parameter
        # So we prioritize direct environment variable access
        if in_docker:
            logging.debug("Docker environment detected, using passed environment variables")
            # Directly access the environment variable
            raw_key = os.environ.get('GOOGLE_SA_PRIVATE_KEY', '')
            
            if raw_key and len(raw_key) > 50:
                logging.info("Successfully read private key from Docker environment variable")
                # Process the key as needed
                if (raw_key.startswith('\'') and raw_key.endswith('\'')) or \
                   (raw_key.startswith('"') and raw_key.endswith('"')):
                    raw_key = raw_key[1:-1]
                return raw_key.replace('\\n', '\n')
            
            logging.warning("Private key not found in Docker environment variables")
            return ''
        
        # For local environments, try environment variable first, then fall back to .env file
        raw_key = os.environ.get('GOOGLE_SA_PRIVATE_KEY', '')
        if raw_key and len(raw_key) > 50:
            logging.debug("Using private key from environment variable")
            if (raw_key.startswith('\'') and raw_key.endswith('\'')) or \
               (raw_key.startswith('"') and raw_key.endswith('"')):
                raw_key = raw_key[1:-1]
            return raw_key.replace('\\n', '\n')
        
        # Local fallback: read from .env file
        logging.debug("Env variable not working, trying direct file read")
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        if not os.path.exists(env_path):
            logging.error(f".env file not found at {env_path}")
            return ''
            
        with open(env_path, 'r') as f:
            for line in f:
                if line.strip().startswith('GOOGLE_SA_PRIVATE_KEY='):
                    # Extract everything after the equals sign
                    key_part = line.strip()[len('GOOGLE_SA_PRIVATE_KEY='):]
                    
                    # If quoted, remove the quotes
                    if (key_part.startswith('\'') and key_part.endswith('\'')) or \
                       (key_part.startswith('"') and key_part.endswith('"')):
                        key_part = key_part[1:-1]
                        
                    # Replace escaped newlines with actual newlines
                    key_part = key_part.replace('\\n', '\n')
                    
                    logging.debug(f"Key successfully read from .env file: {len(key_part)} characters")
                    return key_part
                    
        logging.error("GOOGLE_SA_PRIVATE_KEY not found in environment or .env file")
        return ''
    except Exception as e:
        logging.error(f"Error getting private key: {e}")
        return ''


def upload_csv_to_google_sheet(csv_file: str, spreadsheet_id: str, sheet_name: str):
    """Upload a CSV file to a Google Sheet.
    
    Args:
        csv_file: Path to the CSV file to upload
        spreadsheet_id: ID of the Google Sheet
        sheet_name: Name of the tab/worksheet
        
    Raises:
        FileNotFoundError: If CSV file not found
        RuntimeError: If Google credentials are missing or invalid
    """
    # Check if gspread is available
    if gspread is None:
        console.print("[bold red]Error: gspread is not installed. Install with pip install gspread[/bold red]")
        raise RuntimeError("gspread is not installed. Install with pip install gspread")
    
    # Prepare Google credentials
    try:
        with console.status("[bold green]Preparing Google credentials...") as status:
            # Get the private key
            private_key = get_google_private_key()
            console.print(f"[green]Successfully loaded private key ({len(private_key)} characters)[/green]")
            
            # Load Google Service Account credentials
            credentials_info = {
                "type": "service_account",
                "project_id": os.environ.get("GOOGLE_SA_PROJECT_ID"),
                "private_key_id": os.environ.get("GOOGLE_SA_PRIVATE_KEY_ID"),
                "private_key": private_key,
                "client_email": os.environ.get("GOOGLE_SA_CLIENT_EMAIL"),
                "client_id": os.environ.get("GOOGLE_SA_CLIENT_ID"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.environ.get('GOOGLE_SA_CLIENT_EMAIL')}",
                "universe_domain": os.environ.get("GOOGLE_SA_UNIVERSE_DOMAIN", "googleapis.com")
            }
            
            # Create credentials object
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # Use gspread instead of direct Google API
            client = gspread.authorize(credentials)
            console.print("[green]Successfully authenticated with Google Sheets API[/green]")
        
        # Check if CSV file exists and is readable
        if not os.path.exists(csv_file):
            console.print(f"[bold red]Error: CSV file not found: {csv_file}[/bold red]")
            raise FileNotFoundError(f"Cannot read CSV file: {csv_file}")
        
        if not os.access(csv_file, os.R_OK):
            console.print(f"[bold red]Error: Cannot read CSV file (permission denied): {csv_file}[/bold red]")
            raise PermissionError(f"Cannot read CSV file: {csv_file}")
        
        # Read CSV file
        with console.status("[bold blue]Reading CSV data...") as status:
            try:
                df = pd.read_csv(csv_file)
                values = [df.columns.tolist()] + df.values.tolist()
                console.print(f"[green]Loaded {len(df)} rows from CSV file for upload[/green]")
            except pd.errors.EmptyDataError:
                console.print("[yellow]CSV file is empty, creating default structure[/yellow]")
                # Use default headers for empty file
                default_headers = ["Date", "Client", "Project", "Project Code", "Task", "Notes", "Hours", 
                                 "Billable?", "Billable Amount", "First Name", "Last Name"]
                values = [default_headers, ['No data available']]
        
        # Open spreadsheet and prepare worksheet
        with console.status(f"[bold blue]Connecting to Google Sheet...") as status:
            spreadsheet = client.open_by_key(spreadsheet_id)
            
            # Try to get the worksheet by name, create it if it doesn't exist
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                console.print(f"[green]Found existing worksheet: {sheet_name}[/green]")
            except gspread.exceptions.WorksheetNotFound:
                console.print(f"[yellow]Worksheet '{sheet_name}' not found, creating it...[/yellow]")
                worksheet = spreadsheet.add_worksheet(
                    title=sheet_name, 
                    rows=max(1000, len(values)+10), 
                    cols=max(26, len(values[0]) if values else 0)
                )
                console.print(f"[green]Created new worksheet: {sheet_name}[/green]")
        
        # Handle NaN values that are not JSON compliant
        with console.status("[bold blue]Processing data for upload...") as status:
            # Convert any NaN or infinity values to empty strings
            clean_values = []
            for row in values:
                clean_row = []
                for value in row:
                    # Check if it's a float and if it's NaN or infinity
                    if isinstance(value, float) and (pd.isna(value) or (value == float('inf') or value == float('-inf'))):
                        clean_row.append('')  # Convert NaN/inf to empty string
                    else:
                        clean_row.append(value)
                clean_values.append(clean_row)
            
            # Now upload the clean values
            console.print(f"[bold blue]Uploading data to worksheet '{sheet_name}'...[/bold blue]")
            worksheet.clear()  # Clear existing content
            
            if clean_values and len(clean_values) > 1:  # Only update if we have header + data
                worksheet.update(clean_values)
                console.print(f"[bold green]Successfully uploaded {len(clean_values)-1} rows to Google Sheet![/bold green]")
            else:
                # Just update with headers if available
                if clean_values:
                    worksheet.update([clean_values[0], ['No data available']])  # At least keep the headers
                    console.print("[yellow]CSV file had headers but no data, uploaded empty sheet with headers[/yellow]")
                else:
                    # Fallback to default headers
                    default_headers = ["Date", "Client", "Project", "Project Code", "Task", "Notes", "Hours", 
                                     "Billable?", "Billable Amount", "First Name", "Last Name"]
                    worksheet.update([default_headers, ['No data available']])
                    console.print("[yellow]Created empty sheet with default headers[/yellow]")
            
    except FileNotFoundError as e:
        console.print(f"[bold red]Error: CSV file not found: {csv_file}[/bold red]")
        raise
    except Exception as e:
        console.print(f"[bold red]Error uploading to Google Sheets: {e}[/bold red]")
        console.print_exception()  # Rich traceback
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
    
    # Enable debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        console.print("[dim]Debug logging enabled[/dim]")
    
    # If --user argument is provided, process only that specific user
    # Otherwise, find and process all users
    user_prefixes = []
    if args.user:
        # Ensure the prefix ends with underscore
        user_prefix = args.user if args.user.endswith('_') else f"{args.user}_"
        user_prefixes = [user_prefix]
        console.print(f"[blue]Processing single user with prefix: {user_prefix}[/blue]")
    else:
        # Find all user prefixes in environment variables
        user_prefixes = detect_all_user_prefixes()
        if not user_prefixes:
            # If no user prefixes found, try with empty prefix (for backward compatibility)
            user_prefixes = ['']
            console.print("[yellow]No user prefixes found. Attempting to process with default settings.[/yellow]")
        else:
            console.print(f"[green]Found {len(user_prefixes)} users to process: {', '.join(user_prefixes)}[/green]")
    
    # Determine common date range for all users
    # Priority:    # Date range from environment or command-line arguments
    env_from = get_env_variable('FROM_DATE')
    env_to = get_env_variable('TO_DATE')
    
    # Set date range with priority: 1) command-line args, 2) env vars, 3) auto-calculate
    if args.from_date and args.to_date:
        from_date = args.from_date
        to_date = args.to_date
        console.print(f"[blue]Using command-line date range: {from_date} to {to_date}[/blue]")
    elif env_from and env_to:
        from_date = env_from
        to_date = env_to
        console.print(f"[blue]Using environment date range: {from_date} to {to_date}[/blue]")
    else:
        console.print("[yellow]No date range provided, using last week[/yellow]")
        from_date, to_date = get_last_week_range()
    
    # Create output directory if it doesn't exist
    output_dir = get_absolute_path("output")
    os.makedirs(output_dir, exist_ok=True)
    
    # Process each user
    for user_prefix in user_prefixes:
        # Set the current user prefix for the environment
        os.environ['USER_PREFIX'] = user_prefix
        
        # Get the current user info for logging
        user_email = get_env_variable('HARVEST_USER_AGENT', 'unknown user')
        masked_email = mask_email(user_email)
        masked_prefix = mask_user_prefix(user_prefix)
        console.print(f"\n[bold blue]{'='*80}[/bold blue]")
        console.print(f"[bold blue]Processing time entries for user: {masked_prefix}[/bold blue]")
        console.print(f"[bold blue]{'='*80}[/bold blue]")
        logging.info(f"Processing time entries for user: {masked_prefix}")
        
        # Determine output file path for this user
        if args.output and len(user_prefixes) == 1:
            # Only use explicitly specified output file if processing a single user
            output_file = args.output
        else:
            # Generate user-specific filename
            prefix = user_prefix.lower().replace('_', '') if user_prefix else 'default'
            output_file = get_absolute_path(f"output/harvest_export_{prefix}.csv")
        
        console.print(f"[blue]Using output file: {output_file}[/blue]")
        
        # Optionally prepare JSON output path for this user
        json_file = None
        enable_raw_json = get_env_variable('ENABLE_RAW_JSON', '0').lower() in ('1', 'true', 'yes')
        
        if args.json or enable_raw_json:
            if args.json and len(user_prefixes) == 1:
                # Only use explicitly specified JSON file if processing a single user
                json_file = args.json
            else:
                # Generate user-specific JSON filename
                json_file = output_file.replace('.csv', '.json')
                if json_file == output_file:  # No .csv extension to replace
                    json_file = f"{output_file}.json"
                    
            console.print(f"[dim]Will save raw JSON to: {json_file}[/dim]")
    
        # Step 1: Get Harvest API credentials specific to this user
        try:
            with console.status("[bold blue]Setting up Harvest API authentication...") as status:
                # Force refresh of the USER_PREFIX in the global scope to ensure we get the right variables
                global USER_PREFIX
                USER_PREFIX = user_prefix
                
                # Get user-specific Harvest credentials
                account_id = get_env_variable('HARVEST_ACCOUNT_ID', required=True)
                auth_token = get_env_variable('HARVEST_AUTH_TOKEN', required=True)
                user_agent = get_env_variable('HARVEST_USER_AGENT', 'Harvest API Script')
                user_id = get_env_variable('HARVEST_USER_ID')
                
                # Log the credentials being used (without showing sensitive information)
                console.print(f"[blue]Using credentials for user: {masked_prefix}[/blue]")
                logging.debug("Auth Token: (redacted)")
                logging.debug(f"User Agent: {masked_email}")
        except RuntimeError as e:
            console.print(f"[bold red]Configuration error for user {masked_prefix}: {e}[/bold red]")
            console.print("[yellow]Skipping this user and continuing with others[/yellow]")
            continue
    
        # Step 2: Download time entries for this user
        try:
            data = download_time_entries(account_id, auth_token, user_agent, from_date, to_date, user_id)
        except Exception as e:
            console.print(f"[bold red]Failed to download time entries for user {masked_prefix}: {e}[/bold red]")
            console.print_exception()
            console.print("[yellow]Skipping this user and continuing with others[/yellow]")
            continue
    
        # Step 3: Optionally save raw JSON for this user
        if json_file and (enable_raw_json or args.json):
            try:
                # Ensure the directory exists
                json_dir = os.path.dirname(json_file) or output_dir
                os.makedirs(json_dir, exist_ok=True)
                
                with console.status(f"[bold blue]Saving raw JSON to {json_file}...") as status:
                    with open(json_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                        
                console.print(f"[green]Saved raw JSON to {json_file}[/green]")
            except (IOError, OSError) as e:
                console.print(f"[yellow]Warning: Error saving JSON to {json_file}: {e}[/yellow]")
                # Continue even if JSON save fails
    
        # Step 4: Process data and write CSV for this user
        try:
            # Convert the JSON data to a pandas DataFrame
            df = parse_time_entries(data)

            # Keep a copy of original data for resume section
            original_df = df.copy()

            # Add summary rows to the DataFrame
            df = add_summary_rows(df)

            # Add resume section after summary rows
            df = add_resume_section(df, original_df)

            # Write the DataFrame to CSV file
            with console.status(f"[bold blue]Writing CSV to {output_file}...") as status:
                write_csv(df, output_file)
                
            if not df.empty:
                console.print(f"[green]Successfully wrote {len(df)} rows to {output_file}[/green]")
            else:
                console.print("[yellow]No time entries found for the specified period[/yellow]")
        except Exception as e:
            console.print(f"[bold red]Failed to process or write CSV for user {masked_prefix}: {e}[/bold red]")
            console.print_exception()
            console.print("[yellow]Skipping Google Sheets upload for this user and continuing[/yellow]")
            continue
    
        # Step 5: Google Sheets upload (optional) for this user
        spreadsheet_id = get_env_variable('GOOGLE_SHEET_ID')
        sheet_name = get_env_variable('GOOGLE_SHEET_TAB_NAME')
        upload_flag = get_env_variable('UPLOAD_TO_GOOGLE_SHEET', '0')
        
        # Determine if upload is enabled
        upload_enabled = upload_flag.lower() in ('1', 'true', 'yes')
        sheets_configured = bool(spreadsheet_id and sheet_name)
        
        if upload_enabled:
            console.print("[blue]Google Sheets upload: enabled[/blue]")
            
            if not sheets_configured:
                console.print("[yellow]Warning: Missing Google Sheet ID or Tab Name for user {user_prefix}.[/yellow]")
                console.print("[yellow]Skipping Google Sheets upload for this user and continuing[/yellow]")
                continue
            
            if not gspread or not service_account:
                console.print("[bold red]Error: Google Sheets API dependencies not installed.[/bold red]")
                console.print("[dim]Install with: pip install gspread google-auth[/dim]")
                continue
                
            try:
                # Upload CSV to Google Sheets
                upload_csv_to_google_sheet(output_file, spreadsheet_id, sheet_name)
                console.print(f"[green]Successfully uploaded to Google Sheet![/green]")
            except Exception as e:
                console.print(f"[bold red]Failed to upload to Google Sheets for user {masked_prefix}: {e}[/bold red]")
                console.print_exception()
        else:
            console.print("[dim]Google Sheets upload: disabled (set UPLOAD_TO_GOOGLE_SHEET=1 to enable)[/dim]")
    
    # Final summary
    console.print(f"\n[bold green]Completed processing for {len(user_prefixes)} user(s)[/bold green]")


if __name__ == "__main__":
    # Usage: python convert_harvest_json_to_csv.py [--from-date YYYY-MM-DD] [--to-date YYYY-MM-DD] [--output FILE] [--json FILE] [--user USER_PREFIX]
    # Note: Processing all users is the default behavior unless --user is specified
    main()
