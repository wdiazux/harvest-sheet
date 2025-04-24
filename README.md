# Harvest Script: Buildah & NixOS Ready

This project provides a script to convert Harvest time-tracking data to CSV, with optional Google Sheets upload. The environment is designed to be reproducible and secure, leveraging Buildah for container builds and NixOS for development.

---

## Table of Contents
- [Features](#features)
- [Requirements](#requirements)
- [Setup](#setup)
  - [Environment Variables](#environment-variables)
  - [Nix-shell Setup (Optional)](#nix-shell-setup-optional)
- [Building the Image with Buildah](#building-the-image-with-buildah)
- [Running the Container](#running-the-container)
- [Google Sheets Integration](#google-sheets-integration)
- [Security Notes](#security-notes)

---

## Features
- Converts Harvest JSON data to CSV
- Optionally uploads to Google Sheets
- Uses Buildah for rootless, Dockerless builds
- NixOS-compatible development shell

---

## Requirements
- [Buildah](https://buildah.io/) and [Podman](https://podman.io/) **must be installed on your system** (not just in a nix-shell)
    - On NixOS: `nix-env -iA nixos.buildah nixos.podman`
    - On Ubuntu: `sudo apt install buildah podman`
    - On Fedora: `sudo dnf install buildah podman`
    - Or use your distro's package manager
- [Nix](https://nixos.org/download.html) (optional, for reproducible Python/dev environment)
- Harvest API credentials
- (Optional) Google Service Account credentials for Sheets upload

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
12. Open the downloaded JSON key file and copy the following fields to your `.env`:
    - `project_id` → `GOOGLE_SA_PROJECT_ID`
    - `private_key_id` → `GOOGLE_SA_PRIVATE_KEY_ID`
    - `private_key` → `GOOGLE_SA_PRIVATE_KEY` (**replace all newlines with `\n`** so it is a single line)
    - `client_email` → `GOOGLE_SA_CLIENT_EMAIL`
    - `client_id` → `GOOGLE_SA_CLIENT_ID`
13. Add these to your `.env`:
   ```env
   GOOGLE_SA_PROJECT_ID=...
   GOOGLE_SA_PRIVATE_KEY_ID=...
   GOOGLE_SA_PRIVATE_KEY=...
   GOOGLE_SA_CLIENT_EMAIL=...
   GOOGLE_SA_CLIENT_ID=...
   GOOGLE_SHEET_ID=your_sheet_id
   GOOGLE_SHEET_TAB_NAME=your_tab_name
   UPLOAD_TO_GOOGLE_SHEET=1
   ```

**Official Docs:**
- [Google Cloud: Creating and Managing Service Accounts](https://cloud.google.com/iam/docs/creating-managing-service-accounts)
- [Google Sheets API Python Quickstart](https://developers.google.com/sheets/api/quickstart/python)

---

## Setup

### 1. Clone the repository
```sh
git clone https://github.com/wdiaz/harvest-sheet.git
cd harvest-sheet
```

### 2. (Optional) Enter the Nix Shell for Python/Dev Dependencies
This ensures all Python and development dependencies are available (but does NOT provide buildah/podman):
```sh
nix-shell
```

### 3. Configure Environment Variables
- Copy `.env.example` to `.env` and fill in your credentials:

```sh
cp .env.example .env
# Edit .env with your favorite editor
```

- **Required variables:**
  - `HARVEST_ACCOUNT_ID`, `HARVEST_AUTH_TOKEN`, `HARVEST_USER_AGENT`
  - (Optional) `FROM_DATE`, `TO_DATE`, `CSV_OUTPUT_FILE`
  - For Google Sheets: `GOOGLE_SA_PROJECT_ID`, `GOOGLE_SA_PRIVATE_KEY_ID`, `GOOGLE_SA_PRIVATE_KEY`, `GOOGLE_SA_CLIENT_EMAIL`, `GOOGLE_SA_CLIENT_ID`, `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_TAB_NAME`, `UPLOAD_TO_GOOGLE_SHEET`

---

## Building the Image with Buildah

1. Ensure `buildah` and `podman` are installed and available on your system (see Requirements).
2. (Optional) Activate the Nix shell if you want Python/dev dependencies available:
   ```sh
   nix-shell
   ```
3. Run the build script:
   ```sh
   ./buildah.sh
   ```
   This will:
   - Build a container image from `python:3.11-slim`
   - Install dependencies
   - Copy your code and `.env.example` (not `.env`)
   - Inject all variables from your `.env` file as environment variables in the image
   - Commit the image as `harvest-sheet:latest`

---

## Running the Container

You can run the image with Podman (or Docker, if you export the image):

```sh
podman run --rm harvest-sheet:latest
```

- If you did **not** bake secrets into the image, use:
  ```sh
  podman run --rm --env-file .env harvest-sheet:latest
  ```

---

## Google Sheets Integration
To enable Google Sheets upload, fill in the required Google Service Account variables in `.env` and set `UPLOAD_TO_GOOGLE_SHEET=1`.

---

## Security Notes
- **Never commit your real `.env` file to version control.**
- By default, the build script injects all `.env` variables into the image. For production or shared images, avoid this and use `--env-file` at runtime instead.
- `.env.example` is provided as a template only.

---

## Troubleshooting
- If you see errors about missing `buildah` or `podman`, ensure you are running inside the Nix shell (`nix-shell`).
- For more info, see the comments in `buildah.sh` and `shell.nix`.

---

## License
MIT or your project license here.
