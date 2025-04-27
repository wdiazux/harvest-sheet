# Harvest Sheet

This project provides a script to convert Harvest time-tracking data to CSV, with optional Google Sheets upload. The environment is designed to be reproducible and secure, leveraging Buildah for container builds and NixOS for development.

---

## Table of Contents
- [General Use](#general-use)
  - [How to Obtain API Credentials](#how-to-obtain-api-credentials)
  - [Google Service Account Credentials (for Sheets Upload)](#google-service-account-credentials-for-sheets-upload)

---

## General Use

Below is an example of the workflow:

### Harvest Sheet Workflow

- Converts time-tracking data to CSV
- Optionally uploads results to Google Sheets
- Supports both one-off and scheduled (cron) runs

> **Tip:** For most users, simply configure your `.env` file and run the container as shown below. For advanced usage, scheduling, and troubleshooting, see the detailed guide below.

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

The image includes cron support for scheduled automation. By default, the container uses `/app/crontab.txt` with the following schedule:

```
# Set essential PATH and SHELL for cron jobs
PATH=/usr/local/bin:/usr/bin:/bin
SHELL=/bin/bash

# Run the Harvest script at 6:00 AM and 6:00 PM every day
0 6,18 * * * /app/cron_wrapper.sh >> /app/cron.log 2>&1 || echo "[ERROR] Harvest script failed at $(date)" >> /app/cron.error.log

# Run the Harvest script at 12:00 AM every Monday
0 0 * * 1 /app/cron_wrapper.sh >> /app/cron.log 2>&1 || echo "[ERROR] Harvest script failed at $(date)" >> /app/cron.error.log
```

This configuration runs the script:
- At 6:00 AM and 6:00 PM every day
- At 12:00 AM every Monday (weekly run)

All jobs use the `/app/cron_wrapper.sh` script which sets up the environment properly before executing the Python script. The jobs log their output to `/app/cron.log` and any errors to `/app/cron.error.log`.

#### To customize the schedule:
1. Edit `crontab.txt` before building or mounting it into the container:
   - To mount a custom crontab:
     ```yaml
     volumes:
       - ./my-crontab.txt:/app/crontab.txt:ro
     ```
2. The container starts cron automatically and tails `/app/cron.log`.
3. Logs are available in the `cron.log` file inside the container (or mount `/app/cron.log` to your host).

### Environment Variables

- See `.env.example` for all supported variables.
- You can override variables at runtime with `-e VAR=value` or in your Compose file.
- Docker-specific variables are available for customizing container behavior:
  - `TZ`: Set the timezone for the container (default: UTC)
  - `OUTPUT_DIR`: Directory for output files (default: /app/output)
  - `ENABLE_RAW_JSON`: Enable/disable raw JSON export (1=enable, 0=disable)
  - `HARVEST_RAW_JSON`: Location to store raw JSON if enabled
  - `FROM_DATE`: Optional start date in YYYY-MM-DD format (if not using command-line args)
  - `TO_DATE`: Optional end date in YYYY-MM-DD format (if not using command-line args)
  - `CSV_OUTPUT_FILE`: Optional custom filename for the CSV output

### Advanced: Buildah & NixOS

- Use `buildah.sh` for custom builds or to build on NixOS.
- The script ensures cron, python, and all dependencies are installed, and registers the crontab.

### Troubleshooting

- **No output?** Check the logs: `docker logs <container>` or inspect `/app/cron.log`. For error details, check `/app/cron.error.log`.
- **Google Sheets upload fails?** Double-check your service account credentials and sharing permissions.
- **Environment not loading?** Make sure `.env` is present and correctly formatted.
- **Cron jobs not running?** Verify the container's timezone with `TZ` environment variable if your jobs appear to run at unexpected times.

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
6. Add these values to your `.env` file:
   ```env
   HARVEST_ACCOUNT_ID=your_account_id
   HARVEST_AUTH_TOKEN=your_personal_access_token
   HARVEST_USER_AGENT=your_email_or_app
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