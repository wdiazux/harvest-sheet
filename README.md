# Harvest Sheet

Extract time-tracking data from Harvest API and convert to CSV, with optional Google Sheets upload. Features multiple users, scheduled execution, and a **secure web interface** for browser-based access.

## Features

### 🤖 Automated Daily Exports
✅ **Scheduled exports** - Runs daily at 6:00 AM UTC
✅ **Automatic date calculation** - Uses last week or current week (Fri-Sun)
✅ **Multi-user processing** - Handles all configured users
✅ **Direct Google Sheets upload** - No artifacts stored in GitHub
✅ **Enterprise security** - Credentials masked, minimal permissions

### 🌐 Secure Web Interface
✅ **Google OAuth 2.0 authentication**
✅ **Enterprise-grade security** - Safe for public repositories
✅ **Manual workflow triggering** - No hardcoded tokens
✅ **Multi-user support** - Individual access control
✅ **Complete audit trail** - Security logging

**Quick Start Web Interface:**
1. Visit your GitHub Pages URL: `https://yourusername.github.io/harvest-report`
2. Sign in with authorized Google account
3. Generate secure parameters and manually trigger via GitHub Actions
4. Download results from workflow artifacts

**Setup Guide**: [web-setup-instructions.md](web-setup-instructions.md)
**Security Details**: [SECURITY-ANALYSIS.md](SECURITY-ANALYSIS.md)

---

## GitHub Actions Workflows

Harvest Sheet includes **5 automated workflows** for complete automation and security:

### 1. 🤖 Daily Harvest Export (`daily-harvest-export.yml`)
- **Trigger**: Scheduled daily at 6:00 AM UTC, or manual via `workflow_dispatch`
- **Purpose**: Automated daily export of time entries to Google Sheets
- **Features**:
  - Automatic date range calculation (last week or current week Fri-Sun)
  - Processes all configured users in single run
  - Direct Google Sheets upload (no CSV artifacts stored)
  - Secure: credentials masked, output suppressed, minimal permissions
- **Setup**: Configure `USER_CREDENTIALS` JSON secret with all user details

### 2. 🌐 Web Interface Trigger (`web-trigger.yml`)
- **Trigger**: `repository_dispatch` from web UI, or manual
- **Purpose**: Handles secure export requests from the web interface
- **Features**:
  - Google OAuth 2.0 user authorization validation
  - Input sanitization and validation
  - Dynamic user credential loading from secrets
  - Parameterized date ranges and user selection
- **Security**: Email whitelist, token hashing, CSRF protection

### 3. 📦 Build and Push Container (`build-and-push.yml`)
- **Trigger**: Push to `main` branch (excluding docs), or manual
- **Purpose**: Builds and publishes container image to GitHub Container Registry
- **Features**:
  - Uses buildah for OCI-compatible images
  - Automatic versioning (date + commit hash)
  - Tags: `latest` and version-specific
  - Published to `ghcr.io/username/harvest-sheet`

### 4. 🚀 Deploy GitHub Pages (`deploy-pages.yml`)
- **Trigger**: Push to `main`, or manual
- **Purpose**: Deploys secure web interface to GitHub Pages
- **Features**:
  - Injects OAuth Client ID and GitHub token into static files
  - Loads user configuration from repository variables
  - Serves web UI at `https://username.github.io/harvest-sheet/`

### 5. 🧹 Cleanup Workflow Logs (`cleanup-logs.yml`)
- **Trigger**: Every 6 hours via cron, or manual
- **Purpose**: Auto-deletes old workflow logs for security
- **Features**:
  - Deletes successful web-trigger runs older than 1 hour
  - Configurable via `AUTO_DELETE_LOGS` variable (enabled by default)
  - Protects sensitive data in public repositories

---

## Table of Contents
- [Features](#features)
  - [Automated Daily Exports](#-automated-daily-exports)
  - [Secure Web Interface](#-secure-web-interface)
- [GitHub Actions Workflows](#github-actions-workflows)
- [General Use](#general-use)
  - [Harvest Sheet Workflow](#harvest-sheet-workflow)
- [Usage Guide: Harvest Sheet Docker Image](#usage-guide-harvest-sheet-docker-image)
  - [Quick Start: One-off Run](#quick-start-one-off-run)
  - [Automated Runs with Docker Compose](#automated-runs-with-docker-compose)
  - [Running on a Schedule (Cron)](#running-on-a-schedule-cron)
  - [Multi-User Support](#multi-user-support)
  - [Environment Variables](#environment-variables)
  - [Advanced: Buildah & NixOS](#advanced-buildah--nixos)
  - [Troubleshooting](#troubleshooting)
- [How to Obtain API Credentials](#how-to-obtain-api-credentials)
  - [Harvest API Credentials](#harvest-api-credentials)
  - [Google Service Account Credentials (for Sheets Upload)](#google-service-account-credentials-for-sheets-upload)

---

## General Use

Harvest Sheet automatically extracts time entries from Harvest and can upload them to Google Sheets. **Choose your preferred interface:**

### 🌐 **Web Interface** (Recommended)
- Browser-based with Google OAuth authentication
- Secure manual workflow triggering
- No local setup required
- Perfect for occasional use

### 🐳 **Container/CLI Interface**
- Docker containers with automated scheduling
- Command-line execution
- Local development support
- Perfect for automated workflows

### Harvest Sheet Workflow

1. **Authentication**: Google OAuth (web) or API credentials (container/CLI)
2. **Data Retrieval**: Fetches time entries from Harvest API for specified date range
3. **Data Validation**: Uses Pydantic models to ensure data integrity
4. **CSV Conversion**: Transforms data to CSV format with pandas
5. **Upload**: Optionally uploads CSV to Google Sheets
6. **Multi-User**: Processes all configured users in single execution

### Core Features

- **Full Harvest API Integration** - Access to all standard and advanced time entry fields
- **Data Validation** - Pydantic models ensure data integrity
- **Flexible Output** - Basic or advanced fields in exports
- **Rich Console Output** - Enhanced terminal feedback with progress indicators
- **Multi-User Support** - Process time entries for multiple Harvest accounts
- **Multiple Interfaces** - Web browser, Docker container, or direct Python execution

> **💡 Quick Start**: For browser-based access, use the [web interface](#-new-secure-web-interface). For automated workflows, use the [container approach](#usage-guide-harvest-sheet-docker-image).

---

## Usage Guide: Harvest Sheet Docker Image

This guide explains how to use the `ghcr.io/wdiazux/harvest-sheet:latest` image for both manual and scheduled (cron) runs, including advanced options and troubleshooting.

### Quick Start: One-off Run

You can run the image directly to fetch and convert Harvest data to CSV (and optionally upload to Google Sheets):

```sh
docker run --rm \
  --env-file .env \
  -v $(pwd)/output:/app/output \
  ghcr.io/wdiazux/harvest-sheet:latest
```
- Ensure your `.env` file is in the current directory.
- Output will be written to the `output` folder.

### Automated Runs with Docker Compose

You can also run the project using Docker Compose for easier management:

1. Make sure you have a `.env` file with your configuration in the project root.
2. Create a `docker-compose.yml` file in your project directory with the following content:

```yaml
version: '3.8'
services:
  harvest-sheet:
    image: ghcr.io/wdiazux/harvest-sheet:latest
    env_file:
      - .env
    volumes:
      - ./output:/app/output  # Optional: Mounts output directory
    restart: unless-stopped
```

This will start the service. Output files (if any) will be written to the `output` directory.

- To stop the service: `docker compose down`
- To apply updates after changes: `docker compose up`

### Running on a Schedule (Cron)

The Docker container comes with cron pre-configured to run the script on a regular schedule. The default schedule is defined in `crontab.txt`:

```
# Run the Harvest script at 6:00 AM and 6:00 PM every day
0 6,18 * * * /app/cron_wrapper.sh >> /app/logs/cron.log 2>> /app/logs/cron.error.log

# Run the Harvest script at 12:00 AM every Monday
0 0 * * 1 /app/cron_wrapper.sh >> /app/logs/cron.log 2>> /app/logs/cron.error.log
```

This configuration runs the script twice daily at 6:00 AM and 6:00 PM, and once weekly at midnight on Mondays.

All jobs use the `/app/cron_wrapper.sh` script which:
1. Sets up logging with timestamps
2. Loads environment variables from Docker (uses `/app/.env` as a fallback if available)
3. Counts all user prefixes in the environment
4. Runs the Python script to process all detected users in a single execution
5. Generates detailed logs in the `/app/logs/` directory

The wrapper script uses Rich for enhanced terminal output and provides detailed progress information during execution.

#### To customize the schedule:
1. Edit `crontab.txt` before building or mounting it into the container:
   - To mount a custom crontab:
     ```yaml
     volumes:
       - ./my-crontab.txt:/app/crontab.txt:ro
     ```
2. The container starts cron automatically and tails `/app/cron.log`.
3. Logs are available in the `cron.log` file inside the container (or mount `/app/cron.log` to your host).

### Multi-User Support

The application supports multiple users with different Harvest accounts and Google Sheets destinations. This is implemented through user-specific environment variables with prefixes.

#### How Multi-User Support Works:

1. Each user's variables are prefixed with their name (e.g., `FIRSTNAME_LASTNAME_HARVEST_ACCOUNT_ID`)
2. The `cron_wrapper.sh` script verifies that at least one user has Harvest credentials defined
3. The Python script is run once with the `--all-users` flag
4. The Python script automatically detects all user prefixes in the environment
5. For each detected user, the script uses the prefix to load the correct credentials

#### To Add a New User:

1. Add their environment variables to `.env` with an appropriate prefix:
   ```
   FIRSTNAME_LASTNAME_HARVEST_ACCOUNT_ID=1234567
   FIRSTNAME_LASTNAME_HARVEST_AUTH_TOKEN=your_token_here
   FIRSTNAME_LASTNAME_HARVEST_USER_AGENT=first.last@example.com
   FIRSTNAME_LASTNAME_HARVEST_USER_ID=7654321
   FIRSTNAME_LASTNAME_GOOGLE_SHEET_ID=your_sheet_id
   FIRSTNAME_LASTNAME_GOOGLE_SHEET_TAB_NAME=FirstName LastName
   ```

2. No other configuration is needed - the wrapper script will automatically detect and process the new user

### Environment Variables

The application uses two types of environment variables:

#### 1. User-Specific Variables (with prefix)

- `FIRSTNAME_LASTNAME_HARVEST_ACCOUNT_ID`: Harvest account ID
- `FIRSTNAME_LASTNAME_HARVEST_AUTH_TOKEN`: Authentication token
- `FIRSTNAME_LASTNAME_HARVEST_USER_AGENT`: User agent (usually your email)
- `FIRSTNAME_LASTNAME_HARVEST_USER_ID`: (Optional) User ID for filtering entries by user
- `FIRSTNAME_LASTNAME_GOOGLE_SHEET_ID`: Google Sheet ID for this user
- `FIRSTNAME_LASTNAME_GOOGLE_SHEET_TAB_NAME`: Tab name in the Google Sheet

#### 2. Global Variables

- `GOOGLE_SA_PROJECT_ID`: Google Service Account project ID
- `GOOGLE_SA_PRIVATE_KEY_ID`: Private key ID
- `GOOGLE_SA_PRIVATE_KEY`: Private key (replace newlines with `\n`)
- `GOOGLE_SA_CLIENT_EMAIL`: Service account email
- `GOOGLE_SA_CLIENT_ID`: Service account client ID
- `UPLOAD_TO_GOOGLE_SHEET`: Enable/disable Google Sheets upload (1=enable, 0=disable)
- `ENABLE_RAW_JSON`: Enable/disable raw JSON export (1=enable, 0=disable)
- `INCLUDE_ADVANCED_FIELDS`: Include additional fields from Harvest API in CSV export (1=enable, 0=disable)
- `FROM_DATE`: Optional start date in YYYY-MM-DD format
- `TO_DATE`: Optional end date in YYYY-MM-DD format
- `TZ`: Set the timezone for the container (default: UTC)

See `.env.example` for a complete template with explanations.

### Advanced: Buildah & NixOS

- Use `buildah.sh` for custom builds or to build on NixOS.
- The script ensures cron, python, and all dependencies are installed, and registers the crontab.

### Troubleshooting

- **No output?** Check the logs: `docker logs <container>` or inspect the log files in `/app/logs/`. The script generates timestamped log files for each run.
- **Google Sheets upload fails?** Double-check your service account credentials and ensure the sheet is shared with the service account email. The script provides detailed error messages with Rich output.
- **Environment not loading?** Make sure `.env` is present and correctly formatted. Check user prefixes and required variables.
- **Cron jobs not running?** Verify the container's timezone with `TZ` environment variable if your jobs appear to run at unexpected times.
- **Data validation errors?** The script uses Pydantic models to validate API data - check the error messages for details on fields that failed validation.

---

## Advanced Field Output

The script supports exporting additional fields from the Harvest API beyond the standard ones. This is useful for detailed reporting, billing verification, and advanced time tracking analysis.

### Available Additional Fields

When the `INCLUDE_ADVANCED_FIELDS` option is enabled, the following fields are added to the CSV output:

- **Rounded Hours**: Hours after rounding rules have been applied
- **Is Billed**: Whether the time entry has been billed on an invoice
- **Is Locked**: Whether the time entry is locked for editing
- **Started/Ended**: Start and end times for the entry (if available)
- **Created At/Updated At**: Timestamps for when the entry was created and last updated
- **Cost Rate**: The cost rate applied to the time entry (if available)

### Enabling Raw JSON and Advanced Fields

#### Raw JSON Export
To save the raw JSON response from the Harvest API:

1. Set `ENABLE_RAW_JSON=1` in your `.env` file, or
2. Use the `--json` command-line argument when running the script

#### Advanced Fields
To include additional fields in your CSV exports:

1. Set `INCLUDE_ADVANCED_FIELDS=1` in your `.env` file, or
2. Add `INCLUDE_ADVANCED_FIELDS=1` to your environment variables

In a multi-user setup, these settings apply globally to all users processed in that run.

## Running Locally Without Docker

You can run the script directly on your local machine without Docker. This is useful for development, testing, or if you prefer not to use containers.

### Prerequisites

1. Python 3.9 or higher installed on your system
2. Required Python packages installed

### Installation

1. Clone the repository or download the source code
2. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root with your configuration (see [Environment Variables](#environment-variables))

### Running the Script

Run the script directly with Python:

```bash
# Basic usage (will use last week as default date range)
python convert_harvest_json_to_csv.py

# Specify a date range
python convert_harvest_json_to_csv.py --from-date 2025-05-01 --to-date 2025-05-15

# Specify a custom output file
python convert_harvest_json_to_csv.py --output my_timesheet.csv

# Enable debug logging
python convert_harvest_json_to_csv.py --debug

# Specify a user prefix (for multi-user setups)
python convert_harvest_json_to_csv.py --user JOHN_DOE

# Save raw JSON output (or set ENABLE_RAW_JSON=1 in your .env file)
python convert_harvest_json_to_csv.py --json harvest_data.json
```

### Command-Line Arguments

- `--from-date`: Start date for time entries (YYYY-MM-DD)
- `--to-date`: End date for time entries (YYYY-MM-DD)
- `--output`: Custom output file path for the CSV
- `--json`: Save raw API response as JSON to the specified file
- `--user`: Override the user prefix for environment variables
- `--debug`: Enable debug logging

### Expected Output

When running successfully, the script will:

1. Display a header with the application name and version
2. Show user information and configuration details
3. Download time entries from Harvest with a progress indicator
4. Process and validate the data using Pydantic models
5. Write the processed data to a CSV file (in the `output/` subdirectory by default)
6. Optionally upload to Google Sheets if configured

### Output File Locations

By default, output files will be stored in the following locations:

- **CSV files**: `./output/harvest_export_[prefix].csv`
- **JSON files** (if enabled): `./output/harvest_export_[prefix].json`
- **Log files**: Created in the current directory or specified log directory

In a Docker environment, these paths would be inside the container at `/app/output/` and `/app/logs/` according to the container configuration. All file paths in the scripts use absolute paths relative to `/app`.

All output is enhanced with Rich formatting for better readability in the terminal.

---

## How to Obtain API Credentials

### Harvest API Credentials
You will need the following for Harvest API access:
- `HARVEST_ACCOUNT_ID`
- `HARVEST_AUTH_TOKEN`
- `HARVEST_USER_AGENT`

**Steps:**
1. Log in to your Harvest account at [https://id.getharvest.com/](https://id.getharvest.com/).
2. Go to **Settings** > **Developers** > **Personal Access Tokens**.
3. Click **Create New Personal Access Token**.
4. Copy your **Account ID** and **Personal Access Token**.
5. Set your **User Agent** to your email address or app name (e.g., `user@email.com`).
6. Add these values to your `.env` file with your prefix (replace FIRSTNAME_LASTNAME with your actual name):
   ```env
   FIRSTNAME_LASTNAME_HARVEST_ACCOUNT_ID=your_account_id
   FIRSTNAME_LASTNAME_HARVEST_AUTH_TOKEN=your_personal_access_token
   FIRSTNAME_LASTNAME_HARVEST_USER_AGENT=your_email_or_app
   ```

**Official Docs:** [Harvest API Authentication](https://help.getharvest.com/api-v2/authentication-api/authentication/authentication/)

### Google Service Account Credentials (for Sheets Upload)
To upload to Google Sheets, you **must** use a Google Cloud Service Account (not an API key or OAuth client ID). The Service Account provides secure, automated server-to-server access.

> **Note:** Do NOT use an "API key" or "OAuth client ID" for this workflow. You need a downloaded Service Account JSON file.

**Steps to obtain Service Account credentials:**
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or select an existing one).
3. Enable the **Google Sheets API** for your project (APIs & Services > Library > search for "Google Sheets API" > Enable).
4. Go to **APIs & Services > Credentials**.
5. Click **Create Credentials > Service account**.
6. Fill in the Service account details:
    - **Service account name**: Choose a descriptive name (e.g., `sheets-writer`).
    - **Description**: (Optional) e.g., "Writes data to Google Sheets from Harvest script".
    - Click **Create and Continue**.
7. Assign a role to the service account:
    - Recommended: **Editor** or **Writer** (to allow writing to Sheets).
    - Click **Continue** and then **Done**.
8. After creation, click on your new service account in the list to view its details.
9. Go to the **Keys** tab, click **Add Key > Create new key**, select **JSON**, and download the key file.
10. In the Service account details, find the **Email** field (e.g., `sheets-writer@your-project.iam.gserviceaccount.com`).
11. **Share your Google Sheet with this service account email:**
    - Open your Google Sheet in the browser.
    - Click the **Share** button.
    - Add the service account email as an editor (full access is usually required for writing).
    - Click **Send**.
12. Open the downloaded JSON key file and copy the following fields to your `.env` file:
    - `project_id` → `GOOGLE_SA_PROJECT_ID`
    - `private_key_id` → `GOOGLE_SA_PRIVATE_KEY_ID`
    - `private_key` → `GOOGLE_SA_PRIVATE_KEY` (**replace all newlines with `\n` so it is a single line**)
    - `client_email` → `GOOGLE_SA_CLIENT_EMAIL`
    - `client_id` → `GOOGLE_SA_CLIENT_ID`
    - Add your `GOOGLE_SHEET_ID` and `GOOGLE_SHEET_TAB_NAME` as well.
    - Set `UPLOAD_TO_GOOGLE_SHEET=1` to enable uploads.

    Example `.env` entries:
    ```env
    GOOGLE_SA_PROJECT_ID=your_project_id
    GOOGLE_SA_PRIVATE_KEY_ID=your_private_key_id
    GOOGLE_SA_PRIVATE_KEY=your_private_key
    GOOGLE_SA_CLIENT_EMAIL=your_service_account_email
    GOOGLE_SA_CLIENT_ID=your_client_id
    GOOGLE_SHEET_ID=your_sheet_id
    GOOGLE_SHEET_TAB_NAME=your_tab_name
    UPLOAD_TO_GOOGLE_SHEET=1
    ```