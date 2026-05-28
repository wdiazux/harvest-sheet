# Secure Web Interface for Harvest Sheet

This directory contains a secure web interface for the Harvest Sheet application.
The static frontend holds **no secrets**: it only proves who the user is (via Google
Sign-In) and hands that proof to a small backend that does the privileged work.

> **Architecture reference:** the authoritative design is
> [`docs/plans/2026-05-28-secure-web-trigger-design.md`](plans/2026-05-28-secure-web-trigger-design.md).
> Owner provisioning steps (GitHub App, Worker deploy, repo wiring) are in
> Phase E of [`docs/plans/2026-05-28-secure-web-trigger-implementation.md`](plans/2026-05-28-secure-web-trigger-implementation.md).

## Security Features

### 🔐 Authentication & Authorization
- **Google Sign-In**: Users sign in with a Google account; the page obtains a short-lived
  Google **ID token**.
- **Server-side token verification**: A Cloudflare Worker verifies the ID token's
  signature (Google JWKS), audience (`GOOGLE_CLIENT_ID`), issuer, expiry, and
  `email_verified` before doing anything.
- **Email allow-list**: The Worker checks the verified email against its `ALLOWED_EMAILS`
  secret. Unlisted users get a `403`.
- **Input validation**: Inputs are validated server-side in the Worker (date format,
  known user prefix) and again in the workflow.

### 🛡️ Data Protection
- **No secret in the browser**: The static page ships only the Google client ID and the
  Worker URL — both non-sensitive. There is **no GitHub token in `app.js`**.
- **Secrets live server-side**: The GitHub App private key and the email allow-list are
  Cloudflare Worker secrets; Harvest tokens and the Google service-account key are GitHub
  Actions secrets.
- **Short-lived GitHub credential**: The Worker mints a GitHub App **installation token**
  that auto-expires in ~1 hour; it is never tied to a personal account and never reaches
  the browser.
- **Audit / logging hygiene**: The export step masks credentials and suppresses output;
  the cleanup workflow deletes old run logs as defense-in-depth.

### 🚨 Attack Prevention
- **Not publicly triggerable**: The export runs via `workflow_dispatch`, which requires
  write access — a random visitor (or a fork) cannot fire it directly.
- **Injection prevention**: The workflow passes inputs via `env:` and references quoted
  shell variables, so no untrusted value is interpolated into a `run:` step.
- **Untrusted browser**: The browser is treated as fully untrusted; it carries only a
  Google ID token proving identity, nothing privileged.

## How It Works

### 1. Automated Daily Exports
```
Scheduled Trigger (6 AM UTC) → GitHub Actions → Harvest API → Google Sheets
```

1. Daily workflow (`daily-harvest-export.yml`) runs automatically at 6:00 AM UTC
2. Auto-calculates the date range
3. Processes all users from the `USER_CREDENTIALS` secret
4. Uploads directly to Google Sheets (no artifacts stored)

This path is independent of the web interface and uses only the export secrets.

### 2. Web Interface Exports
```
User → Google Sign-In → Static Page → POST {WORKER_URL}/trigger
     → Cloudflare Worker (verify + allow-list + GitHub App token)
     → workflow_dispatch → GitHub Actions → Harvest API → Google Sheets
```

1. User signs in with Google on the GitHub Pages site.
2. The page POSTs the Google ID token plus the form fields
   (`from_date`, `to_date`, `user_prefix`, `upload_to_sheets`, `include_advanced_fields`)
   to the Cloudflare Worker at `POST {WORKER_URL}/trigger`.
3. The Worker:
   - verifies the Google ID token,
   - checks the email against `ALLOWED_EMAILS`,
   - validates the inputs,
   - mints a GitHub App installation token, and
   - calls `workflow_dispatch` on `web-trigger.yml`.
4. The workflow loads the export secrets and runs the Python script, which uploads to
   Google Sheets.
5. The Worker returns `202` (triggered), or `400/401/403/502` on failure — never any
   secret or internal detail.

### 3. Validation Chain

#### Frontend (`docs/app.js`)
- Renders the Google Sign-In button and the report form.
- Collects the Google ID token (`response.credential`) and the form fields.
- POSTs them to the Worker. **It holds no GitHub token and never calls the GitHub API.**

#### Cloudflare Worker (`worker/`)
- Verifies the Google ID token (signature, audience, issuer, expiry, `email_verified`).
- Enforces the `ALLOWED_EMAILS` allow-list.
- Validates inputs server-side.
- Mints the GitHub App installation token and triggers `workflow_dispatch`.
- CORS restricted to the Pages origin.

#### Workflow (`.github/workflows/web-trigger.yml`)
- `workflow_dispatch` only (not browser-triggerable).
- Passes inputs via `env:` and validates them again.
- Loads `USER_CREDENTIALS` + `GOOGLE_SA_*` secrets, masks them, runs the export.

## Setup Instructions

The privileged pieces (GitHub App + Cloudflare Worker) are provisioned once by the repo
owner. Follow **Phase E** of the implementation plan for the exact click-by-click steps;
the summary below is orientation only.

### 1. Configure Google OAuth
1. In the [Google Cloud Console](https://console.cloud.google.com/), create an OAuth 2.0
   **Web application** Client ID.
2. Add your GitHub Pages origin (e.g. `https://yourusername.github.io`) to the authorized
   JavaScript origins.
3. The Client ID is used in two places: as the `OAUTH_CLIENT_ID` repo secret (injected
   into the page) and as the `GOOGLE_CLIENT_ID` Worker secret (used to verify tokens).

### 2. Create the GitHub App
1. GitHub → Settings → Developer settings → **GitHub Apps → New GitHub App**.
2. Permission: **Actions: Read and write** only. Disable the webhook.
3. Install it on this repository only.
4. Generate a private key, convert it to PKCS8, and note the **App ID** and
   **Installation ID**. (Exact steps: Phase E1 of the implementation plan.)

### 3. Deploy the Cloudflare Worker
1. From `worker/`: `npx wrangler login` then `npx wrangler deploy`; note the
   `*.workers.dev` URL.
2. Set the Worker secrets with `wrangler secret put` (never committed):
   `GOOGLE_CLIENT_ID`, `GH_APP_ID`, `GH_APP_INSTALLATION_ID`, `GH_APP_PRIVATE_KEY`
   (PKCS8 PEM), `ALLOWED_EMAILS` (comma-separated). (Phase E2.)

### 4. Configure the Repository
1. **Secrets**: `OAUTH_CLIENT_ID`, `USER_CREDENTIALS`, and the five `GOOGLE_SA_*`.
2. **Variables**: `WORKER_URL` (the workers.dev URL) and `AVAILABLE_USERS`.
3. See [`SECRETS-CONFIGURATION.md`](SECRETS-CONFIGURATION.md) for every value.

### 5. Enable GitHub Pages
```
Repository Settings → Pages → Source: GitHub Actions
```
Then run **Deploy to GitHub Pages**. The deploy injects only the Google client ID, the
Worker URL, and the available-users list — no token.

## File Structure

```
docs/
├── index.html                   # Main web interface
├── app.js                       # Frontend logic (Google Sign-In + POST to Worker)
├── config.json                  # User dropdown config (auto-generated at deploy)
├── README.md                    # This file
├── SECRETS-CONFIGURATION.md     # Secrets & variables setup guide
└── plans/                       # Design + implementation plans

worker/
├── src/                         # Cloudflare Worker source (logic only, no secrets)
├── test/                        # Worker unit tests
└── wrangler.toml                # Worker config (non-secret vars)

.github/workflows/
├── daily-harvest-export.yml     # Automated daily exports
├── web-trigger.yml              # Web interface export (workflow_dispatch only)
├── deploy-pages.yml             # GitHub Pages deployment (config injection, no token)
├── build-and-push.yml           # Container image builds
└── cleanup-logs.yml             # Automated log cleanup
```

## Security Considerations

### ✅ Safe for Public Repositories
- No secret in any committed file or in the served page.
- Identity is verified server-side (Google ID token), not trusted from the client.
- `workflow_dispatch` cannot be triggered by anonymous visitors or forks.
- The GitHub credential is a short-lived, single-repo App installation token.

### 🔒 Additional Security Measures
- Worker secrets are encrypted at Cloudflare (`wrangler secret put`); the GitHub App
  private key is never committed.
- Export secrets stay in GitHub Actions secrets and are masked in logs.
- Inputs are validated in the Worker and again in the workflow.
- The cleanup workflow removes old run logs to limit information disclosure.

### 📋 Security Testing
```
# Test checklist:
□ Allow-listed Google account → workflow runs and the Sheet updates
□ Non-allow-listed account → 403, no Actions run
□ Invalid date format → 400, no run
□ No GitHub token present in docs/ or deploy-pages.yml
□ web-trigger.yml is workflow_dispatch only
```

## Usage

1. **Visit the GitHub Pages URL**: `https://yourusername.github.io/yourrepo`
2. **Sign in with Google**: use an allow-listed Google account.
3. **Fill parameters**: select date range, user, and options.
4. **Generate Report**: the page sends your request to the Worker, which triggers the
   workflow.
5. **Check progress**: open the repository's Actions tab; results are uploaded to Google
   Sheets.

## Troubleshooting

### Common Issues
- **"Sign-in could not be verified" (401)**: token expired or invalid — sign in again.
  Confirm the Worker's `GOOGLE_CLIENT_ID` matches the page's client ID.
- **"Your account is not authorized" (403)**: email not in the Worker's `ALLOWED_EMAILS`.
- **"Could not start the job" (502)**: GitHub App token/dispatch failed — check the
  Worker logs and the App's installation/permissions.
- **Workflow runs but Sheet not updated**: verify `USER_CREDENTIALS` and the five
  `GOOGLE_SA_*` secrets, and that the service account has Editor access to the Sheet.

### Security Alerts
- **Never** commit any secret (Worker secrets, GitHub App key, service-account key).
- **Always** use HTTPS for the Worker URL and authentication flows.
- **Regularly** review the Worker's `ALLOWED_EMAILS` allow-list.
- **Monitor** Actions runs and Worker logs for unexpected activity.

## Architecture Benefits

This architecture provides:
- **Zero secrets in the browser**: safe for public repositories.
- **Real authentication**: the Google ID token is verified server-side.
- **Least privilege**: a single-repo GitHub App with a short-lived token.
- **Defense in depth**: allow-list + input validation + log hygiene.
- **Maintainability**: clear separation between the static page, the Worker, and the
  workflow.
