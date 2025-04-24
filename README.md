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

![Harvest Sheet Workflow](docs/harvest-sheet-workflow.png)

- Converts time-tracking data to CSV
- Optionally uploads results to Google Sheets

> **Tip:** For most users, simply configure your `.env` file and run the container as shown below.

---

### Using Docker Compose

You can also run the project using Docker Compose for easier management:

1. Make sure you have a `.env` file with your configuration in the project root.
2. Create a `docker-compose.yml` file in your project directory with the following content:

```yaml
version: '3.8'
services:
  harvest-sheet:
    image: ghcr.io/wdiazux/harvest-sheet:latest
    build:
      context: .
      dockerfile: Dockerfile
    env_file:
      - .env
    volumes:
      - ./output:/app/output  # Optional: Mounts output directory
    restart: unless-stopped
```

**Example usage:**

```sh
docker compose up -d
```

This will start the service. Output files (if any) will be written to the `output` directory.

**Note:**
- The `.env` file is required for configuration; see `.env.example` for all available variables.
- The Buildah script (`buildah.sh`) is provided for advanced/custom builds, and ensures all required files and directories are present in the image.

- To stop the service: `docker compose down`
- To apply updates after changes: `docker compose up`

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