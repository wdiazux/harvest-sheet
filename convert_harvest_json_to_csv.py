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

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, ignore

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

def get_env_variable(var_name: str, default: Optional[str] = None, required: bool = False) -> str:
    """Return an environment variable, or raise a clear error if required and missing."""
    value = os.environ.get(var_name, default)
    if required and not value:
        raise RuntimeError(f"Environment variable '{var_name}' is required but not set.")
    return value


def download_time_entries(account_id: str, auth_token: str, user_agent: str, from_date: str, to_date: str) -> Dict[str, Any]:
    """Fetch all Harvest time entries for the given date range, handling pagination."""
    url = f"https://api.harvestapp.com/v2/time_entries?from={from_date}&to={to_date}&per_page=100"
    headers = {
        'Harvest-Account-ID': account_id,
        'Authorization': f'Bearer {auth_token}',
        'User-Agent': user_agent,
    }
    all_entries = []
    page = 1
    while True:
        paged_url = f"{url}&page={page}"
        try:
            response = requests.get(paged_url, headers=headers, timeout=30)
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
        rows.append({
            "Date": entry.get("spent_date", ""),
            "Client": entry.get("client", {}).get("name", ""),
            "Project": entry.get("project", {}).get("name", ""),
            "Project Code": entry.get("project", {}).get("code", ""),
            "Task": entry.get("task", {}).get("name", ""),
            "Notes": entry.get("notes") or "",
            "Hours": entry.get("hours", 0),
            "Billable?": "Yes" if entry.get("billable") else "No",
            "Invoiced?": "Yes" if entry.get("is_billed") else "No",
        })
    return rows


def write_csv(rows: List[Dict[str, Any]], output_file: str) -> None:
    """Write the parsed rows to a CSV file with the specified output filename."""
    fieldnames = [
        "Date", "Client", "Project", "Project Code", "Task", "Notes", "Hours",
        "Billable?", "Invoiced?"
    ]
    try:
        with open(output_file, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logging.info(f"CSV export completed: {output_file}")
    except Exception as e:
        logging.error(f"Failed to write CSV: {e}")
        raise


def get_last_week_range() -> Tuple[str, str]:
    """Return the previous week's Monday and Sunday date strings (YYYY-MM-DD)."""
    today = datetime.now()
    # Always get the previous full week (Monday to Sunday)
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday.strftime('%Y-%m-%d'), last_sunday.strftime('%Y-%m-%d')

def upload_csv_to_google_sheet(csv_file: str, spreadsheet_id: str, sheet_name: str):
    """Upload a CSV file to a specific Google Sheet tab, replacing its contents.

    Supports credentials from split environment variables.
    """
    if not (service_account and build):
        raise ImportError("Google Sheets dependencies are not installed. Please install google-api-python-client and google-auth.")
    try:
        creds = None
        # Only support split env variables for credentials
        split_vars = [
            'GOOGLE_SA_PROJECT_ID',
            'GOOGLE_SA_PRIVATE_KEY_ID',
            'GOOGLE_SA_PRIVATE_KEY',
            'GOOGLE_SA_CLIENT_EMAIL',
            'GOOGLE_SA_CLIENT_ID',
        ]
        if all(os.environ.get(var) for var in split_vars):
            # Compose the credentials dict
            creds_dict = {
                "type": "service_account",
                "project_id": os.environ['GOOGLE_SA_PROJECT_ID'],
                "private_key_id": os.environ['GOOGLE_SA_PRIVATE_KEY_ID'],
                "private_key": os.environ['GOOGLE_SA_PRIVATE_KEY'].replace('\\n', '\n'),
                "client_email": os.environ['GOOGLE_SA_CLIENT_EMAIL'],
                "client_id": os.environ['GOOGLE_SA_CLIENT_ID'],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.environ['GOOGLE_SA_CLIENT_EMAIL'].replace('@', '%40')}",
                # Optional universe_domain
            }
            if os.environ.get('GOOGLE_SA_UNIVERSE_DOMAIN'):
                creds_dict["universe_domain"] = os.environ['GOOGLE_SA_UNIVERSE_DOMAIN']
            creds = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
        else:
            raise RuntimeError("No Google service account credentials provided via split environment variables.")
        service = build('sheets', 'v4', credentials=creds)
        sheet = service.spreadsheets()
        # Read CSV data
        with open(csv_file, newline='') as f:
            reader = csv.reader(f)
            data = list(reader)
        # Clear the existing sheet content
        sheet.values().clear(
            spreadsheetId=spreadsheet_id,
            range=sheet_name
        ).execute()
        # Write new data
        sheet.values().update(
            spreadsheetId=spreadsheet_id,
            range=sheet_name,
            valueInputOption="RAW",
            body={"values": data}
        ).execute()
        logging.info(f"Uploaded {csv_file} to Google Sheet '{sheet_name}' in spreadsheet '{spreadsheet_id}'")
    except Exception as e:
        logging.error(f"Failed to upload CSV to Google Sheets: {e}")
        raise

def main() -> None:
    """Main entry point for the script: parses arguments, fetches data, writes CSV, and optionally uploads to Google Sheets."""
    parser = argparse.ArgumentParser(description="Download Harvest time entries and convert to CSV.")
    parser.add_argument('--from-date', default=None, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to-date', default=None, help='End date (YYYY-MM-DD)')
    parser.add_argument('--output', default=None, help='CSV output filename (default: /output/harvest_export.csv)')
    parser.add_argument('--json', default=None, help='(Optional) Save raw JSON to this file')
    args = parser.parse_args()

    # --- Docker/ENV-first config ---
    # Dates: ENV > CLI > fallback

    # Determine output file location
    output_arg = args.output or os.environ.get('CSV_OUTPUT_FILE')
    if output_arg:
        if not os.path.isabs(output_arg):
            output_file = os.path.join(os.getcwd(), 'output', output_arg)
        else:
            output_file = output_arg
    else:
        output_file = os.path.join(os.getcwd(), 'output', 'harvest_export.csv')

    env_from = os.environ.get('FROM_DATE')
    env_to = os.environ.get('TO_DATE')
    from_date = None
    to_date = None
    if env_from and env_to:
        from_date = env_from
        to_date = env_to
        logging.info(f"Using FROM_DATE and TO_DATE from environment: {from_date} to {to_date}")
    elif env_from:
        from_date = env_from
        from_date_dt = datetime.strptime(from_date, '%Y-%m-%d')
        to_date_dt = from_date_dt + timedelta(days=(6 - from_date_dt.weekday()))
        to_date = to_date_dt.strftime('%Y-%m-%d')
        logging.info(f"Only FROM_DATE from environment, using range: {from_date} to {to_date}")
    elif env_to:
        to_date = env_to
        to_date_dt = datetime.strptime(to_date, '%Y-%m-%d')
        from_date_dt = to_date_dt - timedelta(days=to_date_dt.weekday())
        from_date = from_date_dt.strftime('%Y-%m-%d')
        logging.info(f"Only TO_DATE from environment, using range: {from_date} to {to_date}")
    elif args.from_date and args.to_date:
        from_date = args.from_date
        to_date = args.to_date
        logging.info(f"Using --from-date and --to-date arguments: {from_date} to {to_date}")
    elif args.from_date:
        from_date = args.from_date
        from_date_dt = datetime.strptime(from_date, '%Y-%m-%d')
        to_date_dt = from_date_dt + timedelta(days=(6 - from_date_dt.weekday()))
        to_date = to_date_dt.strftime('%Y-%m-%d')
        logging.info(f"Only --from-date provided, using range: {from_date} to {to_date}")
    elif args.to_date:
        to_date = args.to_date
        to_date_dt = datetime.strptime(to_date, '%Y-%m-%d')
        from_date_dt = to_date_dt - timedelta(days=to_date_dt.weekday())
        from_date = from_date_dt.strftime('%Y-%m-%d')
        logging.info(f"Only --to-date provided, using range: {from_date} to {to_date}")
    else:
        # Use last full week (Mon-Sun) before today (2025-04-23)
        today = datetime(2025, 4, 23)
        last_monday = today - timedelta(days=today.weekday() + 7)
        last_sunday = last_monday + timedelta(days=6)
        from_date = last_monday.strftime('%Y-%m-%d')
        to_date = last_sunday.strftime('%Y-%m-%d')
        logging.info(f"No date range provided, using last week: {from_date} to {to_date}")

    # Output file: ENV > CLI > default
    output_arg = os.environ.get('CSV_OUTPUT_FILE') or args.output or 'harvest_export.csv'
    if os.path.isabs(output_arg):
        output_file = output_arg
    else:
        output_file = os.path.join('output', output_arg)
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    json_file = os.environ.get('HARVEST_RAW_JSON') or args.json

    # Get Harvest API credentials (ENV-first)
    try:
        account_id = get_env_variable('HARVEST_ACCOUNT_ID', required=True)
        auth_token = get_env_variable('HARVEST_AUTH_TOKEN', required=True)
        user_agent = get_env_variable('HARVEST_USER_AGENT', default='Harvest API Script')
    except RuntimeError as e:
        logging.critical(str(e))
        return

    # Download data
    try:
        data = download_time_entries(account_id, auth_token, user_agent, from_date, to_date)
    except Exception as e:
        logging.critical(f"Failed to download time entries: {e}")
        return

    # Optionally save raw JSON
    if json_file:
        try:
            with open(json_file, "w") as jf:
                json.dump(data, jf, indent=2)
            logging.info(f"Raw JSON saved to: {json_file}")
        except Exception as e:
            logging.error(f"Failed to save JSON: {e}")

    # Parse and write CSV
    try:
        rows = parse_time_entries(data)
        write_csv(rows, output_file)
    except Exception as e:
        logging.critical(f"Failed to process or write CSV: {e}")
        return

    # Google Sheets upload if env vars present
    spreadsheet_id = os.environ.get('GOOGLE_SHEET_ID')
    sheet_name = os.environ.get('GOOGLE_SHEET_TAB_NAME')
    upload_flag = os.environ.get('UPLOAD_TO_GOOGLE_SHEET', '1')  # Default to upload if vars present
    # Only attempt upload if split env or JSON env is present
    creds_env_present = all(os.environ.get(var) for var in [
        'GOOGLE_SA_PROJECT_ID',
        'GOOGLE_SA_PRIVATE_KEY_ID',
        'GOOGLE_SA_PRIVATE_KEY',
        'GOOGLE_SA_CLIENT_EMAIL',
        'GOOGLE_SA_CLIENT_ID',
    ])
    if spreadsheet_id and sheet_name and upload_flag == '1' and creds_env_present:
        try:
            upload_csv_to_google_sheet(output_file, spreadsheet_id, sheet_name)
        except Exception as e:
            logging.error(f"Failed to upload to Google Sheets: {e}")
    else:
        logging.info("Skipping Google Sheets upload (env vars not set, credentials missing, or upload disabled)")


if __name__ == "__main__":
    # Usage: python convert_harvest_json_to_csv.py [--from-date YYYY-MM-DD] [--to-date YYYY-MM-DD] [--output FILE] [--json FILE]
    # Or via Docker: set ENV vars (see .env.example)
    # Requires: requests, python-dotenv (optional, for .env support)
    main()

