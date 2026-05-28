# Harvest Sheet

Extract time-tracking data from the Harvest API, convert it to CSV, and optionally upload it to Google Sheets. It supports multiple users, runs on a schedule, and offers a secure web interface for triggering exports from the browser.

## How it works

1. **Fetch** time entries from the Harvest API for a date range (defaults to the previous week).
2. **Validate** the response with Pydantic models.
3. **Convert** to CSV with pandas.
4. **Upload** to Google Sheets (optional).

A single run processes every configured user. You can run it three ways: the web interface, a Docker container (one-off or scheduled), or directly with Python.

## Interfaces

| Interface | Best for | Auth |
|-----------|----------|------|
| **Web** | Occasional, browser-based runs | Google Sign-In (allow-listed emails) |
| **Container** | Automated/scheduled runs | Harvest + Google service-account credentials |
| **CLI (Python)** | Local development and testing | Same as container |

---

## Web interface

A static GitHub Pages site lets allow-listed users trigger an export from the browser. It holds **no secrets**: the page sends a Google ID token to a Cloudflare Worker, which verifies the token, checks an email allow-list, and triggers the export workflow through a GitHub App. See the [design doc](docs/plans/2026-05-28-secure-web-trigger-design.md) for the full architecture.

**Using it:**

1. Visit `https://wdiazux.github.io/harvest-sheet/`.
2. Sign in with an authorized Google account.
3. Pick a date range and options, then choose **Generate Report**.
4. Follow progress in the repository's **Actions** tab.

**Setup:** see [docs/SECRETS-CONFIGURATION.md](docs/SECRETS-CONFIGURATION.md) for the secrets/variables, and the [implementation plan](docs/plans/2026-05-28-secure-web-trigger-implementation.md) (Phase E) for the GitHub App and Cloudflare Worker steps.

---

## GitHub Actions workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `daily-harvest-export.yml` | Daily 06:00 UTC, or manual | Automated daily export of all users to Google Sheets |
| `web-trigger.yml` | `workflow_dispatch` (called by the Worker) | Runs an export requested from the web interface |
| `build-and-push.yml` | Push to `main`, or manual | Builds the container image and pushes to GHCR |
| `deploy-pages.yml` | Push to `main`, or manual | Deploys the web interface, injecting the (public) Google client ID and Worker URL — never a token |
| `cleanup-logs.yml` | Every 6 hours, or manual | Deletes old successful workflow runs (uses the built-in `GITHUB_TOKEN`) |

Dependency updates are tracked by Dependabot (`.github/dependabot.yml`) for pip, GitHub Actions, and the Worker's npm packages.

---

## Running with Docker

The published image is `ghcr.io/wdiazux/harvest-sheet:latest`.

### One-off run

```sh
docker run --rm \
  --env-file .env \
  -v $(pwd)/output:/app/output \
  ghcr.io/wdiazux/harvest-sheet:latest
```

Output is written to `./output`.

### Docker Compose

```yaml
services:
  harvest-sheet:
    image: ghcr.io/wdiazux/harvest-sheet:latest
    env_file:
      - .env
    volumes:
      - ./output:/app/output
    restart: unless-stopped
```

Start with `docker compose up`; stop with `docker compose down`.

### Scheduled runs (cron)

The image ships with cron configured in `crontab.txt` (06:00 and 18:00 daily, plus midnight Mondays). Each run goes through `cron_wrapper.sh`, which sets up timestamped logging, loads the environment, and runs the script once for all detected users. Logs land in `/app/logs/`.

To customize the schedule, edit `crontab.txt` or mount your own:

```yaml
volumes:
  - ./my-crontab.txt:/app/crontab.txt:ro
```

---

## Running locally with Python

**Prerequisites:** Python 3.11+ (matching the container; pandas 3.x requires 3.10+).

```bash
pip install -r requirements.txt          # install dependencies
python convert_harvest_json_to_csv.py    # run (defaults to last week)
```

On NixOS, `nix-shell` provides Python with all dependencies preinstalled.

### Common commands

```bash
# Specific date range
python convert_harvest_json_to_csv.py --from-date 2025-05-01 --to-date 2025-05-15

# A single user (multi-user setups)
python convert_harvest_json_to_csv.py --user JOHN_DOE

# Custom CSV output, raw JSON, debug logging
python convert_harvest_json_to_csv.py --output my_timesheet.csv
python convert_harvest_json_to_csv.py --json harvest_data.json
python convert_harvest_json_to_csv.py --debug
```

| Flag | Description |
|------|-------------|
| `--from-date` | Start date (YYYY-MM-DD) |
| `--to-date` | End date (YYYY-MM-DD) |
| `--output` | Custom CSV path |
| `--json` | Save the raw API response as JSON |
| `--user` | Process a single user prefix |
| `--debug` | Verbose logging |

Output defaults to `./output/harvest_export_[prefix].csv` (and `.json` if raw JSON is enabled). In the container these are under `/app/output/` and `/app/logs/`.

---

## Multi-user support

Each user's settings are environment variables prefixed with their name. The script auto-detects every prefix present and processes them in one run — no flag needed.

```env
JOHN_DOE_HARVEST_ACCOUNT_ID=1234567
JOHN_DOE_HARVEST_AUTH_TOKEN=your_token_here
JOHN_DOE_HARVEST_USER_AGENT=john.doe@example.com
JOHN_DOE_HARVEST_USER_ID=7654321          # optional, filters to this user
JOHN_DOE_GOOGLE_SHEET_ID=your_sheet_id
JOHN_DOE_GOOGLE_SHEET_TAB_NAME=John Doe
```

Add another user by adding another prefixed block — nothing else to configure.

## Environment variables

**Per user** (prefixed): `_HARVEST_ACCOUNT_ID`, `_HARVEST_AUTH_TOKEN`, `_HARVEST_USER_AGENT`, `_HARVEST_USER_ID` (optional), `_GOOGLE_SHEET_ID`, `_GOOGLE_SHEET_TAB_NAME`.

**Global:**

| Variable | Purpose |
|----------|---------|
| `GOOGLE_SA_PROJECT_ID` | Service-account project ID |
| `GOOGLE_SA_PRIVATE_KEY_ID` | Private key ID |
| `GOOGLE_SA_PRIVATE_KEY` | Private key (newlines as `\n`) |
| `GOOGLE_SA_CLIENT_EMAIL` | Service-account email |
| `GOOGLE_SA_CLIENT_ID` | Service-account client ID |
| `UPLOAD_TO_GOOGLE_SHEET` | Upload to Sheets (`1`/`0`) |
| `INCLUDE_ADVANCED_FIELDS` | Add extended Harvest fields (`1`/`0`) |
| `ENABLE_RAW_JSON` | Also save the raw API response (`1`/`0`) |
| `FROM_DATE` / `TO_DATE` | Optional date range (YYYY-MM-DD) |
| `TZ` | Container timezone (default UTC) |

See `.env.example` for a complete, annotated template.

## Advanced fields

With `INCLUDE_ADVANCED_FIELDS=1`, the CSV also includes rounded hours, billed/locked status, start/end times, created/updated timestamps, and cost rate (when available). This applies to all users in the run.

---

## Obtaining credentials

### Harvest

1. Sign in at [id.getharvest.com](https://id.getharvest.com/).
2. Go to **Settings → Developers → Personal Access Tokens** and create a token.
3. Copy your **Account ID** and **token**; set the user agent to your email.
4. Add them to `.env` with your prefix:
   ```env
   FIRSTNAME_LASTNAME_HARVEST_ACCOUNT_ID=your_account_id
   FIRSTNAME_LASTNAME_HARVEST_AUTH_TOKEN=your_personal_access_token
   FIRSTNAME_LASTNAME_HARVEST_USER_AGENT=your_email
   ```

Docs: [Harvest API authentication](https://help.getharvest.com/api-v2/authentication-api/authentication/authentication/).

### Google service account (for Sheets upload)

Uploading requires a Google Cloud **service account** (not an API key or OAuth client).

1. In the [Google Cloud Console](https://console.cloud.google.com/), create or select a project and enable the **Google Sheets API**.
2. Under **APIs & Services → Credentials**, create a **Service account**.
3. On the service account's **Keys** tab, add a **JSON** key and download it.
4. **Share your Google Sheet** with the service account's email as an editor.
5. Copy the JSON fields into `.env` (keep the private key on one line with `\n` for newlines):
   ```env
   GOOGLE_SA_PROJECT_ID=your_project_id
   GOOGLE_SA_PRIVATE_KEY_ID=your_private_key_id
   GOOGLE_SA_PRIVATE_KEY=your_private_key
   GOOGLE_SA_CLIENT_EMAIL=your_service_account_email
   GOOGLE_SA_CLIENT_ID=your_client_id
   UPLOAD_TO_GOOGLE_SHEET=1
   ```

> The web interface's Google **Sign-In** (the OAuth *client ID*) is separate from this service account — see [docs/SECRETS-CONFIGURATION.md](docs/SECRETS-CONFIGURATION.md).

---

## Troubleshooting

- **No output:** check `docker logs <container>` or `/app/logs/`.
- **Sheets upload fails:** confirm the sheet is shared with the service-account email and the credentials are correct.
- **Environment not loading:** ensure `.env` exists and prefixes/required variables are correct.
- **Cron runs at odd times:** set the `TZ` variable.
- **Validation errors:** the Pydantic error message names the offending field.
