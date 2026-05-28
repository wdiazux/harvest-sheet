# Secrets & Variables Configuration Guide

This document describes every secret and variable the Harvest Report project needs, split
across the three places they now live:

- **(a) Cloudflare Worker secrets** — verify sign-in, authorize callers, and trigger the
  workflow. Set with `wrangler secret put`; never committed.
- **(b) GitHub repository secrets** — used by the GitHub Actions export.
- **(c) GitHub repository variables** — non-sensitive config.

> **Why three places now?** The web interface no longer triggers the workflow from the
> browser. A static page cannot hold a secret or verify identity, so a Cloudflare Worker
> owns authentication and the GitHub credential. See
> [`docs/plans/2026-05-28-secure-web-trigger-design.md`](plans/2026-05-28-secure-web-trigger-design.md)
> and Phase E of
> [`docs/plans/2026-05-28-secure-web-trigger-implementation.md`](plans/2026-05-28-secure-web-trigger-implementation.md).

---

## (a) Cloudflare Worker Secrets

Set inside the `worker/` directory. These are **never** placed in `wrangler.toml` or any
committed file:

```bash
cd worker
npx wrangler secret put GOOGLE_CLIENT_ID
npx wrangler secret put GH_APP_ID
npx wrangler secret put GH_APP_INSTALLATION_ID
npx wrangler secret put GH_APP_PRIVATE_KEY      # paste full PKCS8 PEM
npx wrangler secret put ALLOWED_EMAILS          # comma-separated emails
```

Non-secret Worker config (owner, repo, workflow file/ref, allowed origin) lives in
`worker/wrangler.toml` under `[vars]` and is safe to commit.

### `GOOGLE_CLIENT_ID`
**Description:** Google OAuth 2.0 Client ID. The Worker uses it as the expected `aud`
(audience) when verifying the Google ID token.

**Where to get it:** [Google Cloud Console](https://console.cloud.google.com/) →
**APIs & Services → Credentials** → your OAuth 2.0 Client ID (format
`xxxxx.apps.googleusercontent.com`).

**Notes:** This is the same value as the `OAUTH_CLIENT_ID` repo secret (it is a public
identifier — the page ships it anyway). It is duplicated here because the Worker needs it
server-side to validate tokens.

### `GH_APP_ID`
**Description:** The numeric App ID of the GitHub App that triggers the workflow.

**Where to get it:** GitHub → Settings → Developer settings → GitHub Apps → your App
(shown as **App ID**).

### `GH_APP_INSTALLATION_ID`
**Description:** The installation ID for this App on the repository. The Worker uses it to
mint an installation access token.

**Where to get it:** From the install URL after installing the App on the repo:
`https://github.com/settings/installations/<INSTALLATION_ID>`.

### `GH_APP_PRIVATE_KEY`
**Description:** The GitHub App private key in **PKCS8 PEM** format (`BEGIN PRIVATE KEY`),
used to sign the App JWT.

**How to prepare it:** GitHub generates a PKCS1 `.pem`; convert it to PKCS8 for Web Crypto:
```bash
openssl pkcs8 -topk8 -inform PEM -outform PEM -nocrypt \
  -in app.private-key.pem -out app.pkcs8.pem
```
Paste the full contents of `app.pkcs8.pem` (including BEGIN/END lines) when prompted.

**Notes:** Never commit this key. It only exists as a Worker secret.

### `ALLOWED_EMAILS`
**Description:** Comma-separated list of Google account emails authorized to trigger the
export. **This is now the single source of authorization** — checked by the Worker after
the Google ID token is verified.

**Format:**
```
user1@example.com,user2@example.com,user3@example.com
```

**Notes:** Matching is case-insensitive and trimmed. Add/remove users by updating this
Worker secret (`wrangler secret put ALLOWED_EMAILS`).

---

## (b) GitHub Repository Secrets

**Location:** `https://github.com/YOUR_OWNER/YOUR_REPO/settings/secrets/actions`

These are consumed by the GitHub Actions export workflows.

### `OAUTH_CLIENT_ID`
**Description:** Google OAuth 2.0 Client ID, injected into the static page at deploy time
by `deploy-pages.yml` so the Google Sign-In button works.

**Format:**
```
123456789012-abcdefghijklmnopqrstuvwxyz123456.apps.googleusercontent.com
```

**Notes:** Public identifier (safe in client-side code). Same value as the Worker's
`GOOGLE_CLIENT_ID`. Do **not** use the Client *Secret* here.

---

### Google Service Account (5 secrets)

These authenticate the export to the Google Sheets API. Create a Service Account in
[Google Cloud Console](https://console.cloud.google.com/), enable the **Google Sheets
API**, and download the JSON key. Your JSON key looks like:

```json
{
  "type": "service_account",
  "project_id": "your-project-123456",
  "private_key_id": "abc123def456...",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEF...\n-----END PRIVATE KEY-----\n",
  "client_email": "your-service-account@your-project.iam.gserviceaccount.com",
  "client_id": "123456789012345678901"
}
```

#### `GOOGLE_SA_PROJECT_ID`
Google Cloud project ID — from `"project_id"`.

#### `GOOGLE_SA_PRIVATE_KEY_ID`
Service account private key identifier — from `"private_key_id"`.

#### `GOOGLE_SA_PRIVATE_KEY`
Service account private key (PEM) — from `"private_key"`.

**⚠️ IMPORTANT:** Copy the **entire value** including the `-----BEGIN PRIVATE KEY-----`
and `-----END PRIVATE KEY-----` markers, and keep the `\n` characters (they represent
newlines).

**Common mistakes:**
- ❌ Removing the `\n` characters → authentication fails
- ❌ Omitting the BEGIN/END markers → invalid key format
- ❌ Adding extra spaces or line breaks → key corruption

#### `GOOGLE_SA_CLIENT_EMAIL`
Service account email — from `"client_email"`. Share your Google Sheets with this address
(Editor permission).

#### `GOOGLE_SA_CLIENT_ID`
Service account numeric client ID — from `"client_id"`.

---

### `USER_CREDENTIALS`
**Description:** JSON object containing all user-specific Harvest and Google Sheets
credentials.

**Format:**
```json
{
  "users": [
    {
      "prefix": "USER_ONE",
      "harvest_account_id": "1234567",
      "harvest_auth_token": "1234567.pt.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "harvest_user_agent": "user1@example.com",
      "harvest_user_id": "9999999",
      "google_sheet_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz-EXAMPLE_ID_ONE",
      "google_sheet_tab_name": "User One"
    },
    {
      "prefix": "USER_TWO",
      "harvest_account_id": "1234567",
      "harvest_auth_token": "9876543.pt.yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
      "harvest_user_agent": "user2@example.com",
      "harvest_user_id": "8888888",
      "google_sheet_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz-EXAMPLE_ID_TWO",
      "google_sheet_tab_name": "User Two"
    }
  ]
}
```

**Field Descriptions:**

| Field | Description | Where to find |
|-------|-------------|---------------|
| `prefix` | User identifier (UPPERCASE_FORMAT) | Choose a unique identifier; must match `AVAILABLE_USERS` |
| `harvest_account_id` | Harvest account ID | Harvest Settings → Account |
| `harvest_auth_token` | Harvest Personal Access Token | Harvest Settings → Developers → Create New Token |
| `harvest_user_agent` | User email (for API identification) | User's email address |
| `harvest_user_id` | Harvest user ID (optional filter) | Harvest API or user profile |
| `google_sheet_id` | Target Google Sheet ID | From the Sheet URL |
| `google_sheet_tab_name` | Sheet tab/worksheet name | Tab name in Google Sheet |

**How to extract a Google Sheet ID:**
```
https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz-EXAMPLE_ID/edit
                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                      This is your google_sheet_id
```

**How to create a Harvest Personal Access Token:**
1. Log in to Harvest → **Settings → Developers → Personal Access Tokens**
2. Click **"Create New Personal Access Token"**, name it (e.g. `Harvest Report Export`)
3. Copy the token (format `USERID.pt.xxxxxxxxxxxx`)

**Adding a new user:**
1. Add a user object to this JSON and choose a unique `prefix`.
2. Add a matching entry to the `AVAILABLE_USERS` variable.
3. Add the user's email to the Worker's `ALLOWED_EMAILS` secret so they can sign in.

**Used by workflows:**
- `daily-harvest-export.yml` — processes ALL users in the JSON automatically.
- `web-trigger.yml` — processes the user selected in the web interface.

---

### `WORKFLOW_TRIGGER_TOKEN` (log cleanup only)
**Description:** A GitHub token consumed **only** by `cleanup-logs.yml` as `GH_TOKEN` to
delete old workflow run logs via the GitHub API.

**⚠️ It no longer triggers the export and is no longer injected into the web page.** The
old, insecure flow that embedded a `repo`-scoped PAT in `app.js` has been removed; the web
trigger now goes through the Cloudflare Worker + GitHub App. If you do not use the log
cleanup workflow, this secret can be removed and `cleanup-logs.yml` disabled. If you keep
it, scope it minimally to what the cleanup API calls require, and rotate it periodically.

---

#### Deprecated / removable: `ALLOWED_USERS`
The `ALLOWED_USERS` repo secret is **no longer referenced by any workflow.** Authorization
now happens in the Cloudflare Worker via `ALLOWED_EMAILS`. If it still exists in the repo,
it is safe to delete.

---

## (c) GitHub Repository Variables

**Location:** `https://github.com/YOUR_OWNER/YOUR_REPO/settings/variables/actions`

### `WORKER_URL`
**Description:** The base URL of the deployed Cloudflare Worker (e.g.
`https://harvest-web-trigger.<account>.workers.dev`). Injected into `docs/app.js` at deploy
time so the page can POST to `${WORKER_URL}/trigger`.

**Notes:**
- Non-sensitive (the endpoint is public; it only acts on a valid Google token).
- `deploy-pages.yml` requires it to be set and to start with `https://`.

```bash
gh variable set WORKER_URL --body "https://harvest-web-trigger.<account>.workers.dev" --repo YOUR_OWNER/YOUR_REPO
```

### `AVAILABLE_USERS`
**Description:** JSON object with the user options for the web interface dropdown. Written
to `docs/config.json` at deploy time.

**Format:**
```json
{
  "users": [
    { "value": "all", "label": "All Users" },
    { "value": "USER_ONE", "label": "John Smith" },
    { "value": "USER_TWO", "label": "Jane Doe" }
  ]
}
```

**Field Descriptions:**
- `value`: must match a `prefix` in `USER_CREDENTIALS` (or `"all"`).
- `label`: display name shown in the dropdown.
- The first entry should be `"all"` for processing all users.

### `AUTO_DELETE_LOGS` (optional)
**Description:** Enables/disables automatic workflow log deletion in `cleanup-logs.yml`.

**Default:** Enabled if unset.

**Allowed values:** `true`/`false` (or `1`/`0`).

**Behavior when enabled:**
- Deletes successful runs older than 1 hour for `web-trigger.yml` and
  `daily-harvest-export.yml`.
- Runs every 6 hours via cron; does not delete failed runs.

```bash
gh variable set AUTO_DELETE_LOGS --body "true" --repo YOUR_OWNER/YOUR_REPO
```

---

## 🔒 Security Features & Best Practices

### Where authorization happens now
1. The page obtains a Google ID token (proof of identity only).
2. The Cloudflare Worker verifies that token (signature, audience = `GOOGLE_CLIENT_ID`,
   issuer, expiry, `email_verified`).
3. The Worker checks the email against `ALLOWED_EMAILS` (the single allow-list).
4. The Worker mints a short-lived GitHub App installation token and calls
   `workflow_dispatch`.

There is no client-supplied "I am authorized" claim trusted by the workflow, and no GitHub
token in the browser.

### Secret masking & log hygiene
The export workflow masks credentials and suppresses script output:
```yaml
echo "::add-mask::$GOOGLE_SA_PRIVATE_KEY"
# ... and each user credential field
python convert_harvest_json_to_csv.py $ARGS > /dev/null 2>&1
```
`cleanup-logs.yml` deletes successful runs older than 1 hour as defense-in-depth.

### Secret rotation schedule
- **Harvest tokens** (`USER_CREDENTIALS`): every 90 days
- **GitHub App private key** (`GH_APP_PRIVATE_KEY`): periodically; regenerate in the App
  settings and update the Worker secret
- **`WORKFLOW_TRIGGER_TOKEN`** (if used for cleanup): every 90 days
- **Google Service Account** (`GOOGLE_SA_*`): annually or when compromised
- **OAuth Client ID**: only when compromised

### Access control
- Limit repository collaborators (any collaborator can read Actions secrets).
- The GitHub App has **Actions: write** on this one repo only — least privilege.
- Enable two-factor authentication on GitHub and Cloudflare accounts.
- Review `ALLOWED_EMAILS` regularly.

### Incident response
If a secret is compromised:
1. **Immediate:** rotate it (regenerate the App key / Harvest token / SA key as
   applicable, and run `wrangler secret put` again for Worker secrets).
2. **Update:** change it in both the source (Google/Harvest/GitHub) and where it is stored
   (Worker secret or GitHub secret).
3. **Audit:** review Actions runs and Worker logs for unauthorized activity.
4. **Document:** record the incident and response.

---

## 📋 Quick Setup Checklist

### Cloudflare Worker (a)
- [ ] Deploy the Worker (`npx wrangler deploy`); note the `*.workers.dev` URL
- [ ] `wrangler secret put GOOGLE_CLIENT_ID`
- [ ] `wrangler secret put GH_APP_ID`
- [ ] `wrangler secret put GH_APP_INSTALLATION_ID`
- [ ] `wrangler secret put GH_APP_PRIVATE_KEY` (PKCS8 PEM)
- [ ] `wrangler secret put ALLOWED_EMAILS` (comma-separated)

### GitHub repository secrets (b)
- [ ] `OAUTH_CLIENT_ID`
- [ ] `USER_CREDENTIALS`
- [ ] 5 × `GOOGLE_SA_*` (`PROJECT_ID`, `PRIVATE_KEY_ID`, `PRIVATE_KEY` with `\n`,
      `CLIENT_EMAIL`, `CLIENT_ID`)
- [ ] (optional) `WORKFLOW_TRIGGER_TOKEN` — only if using `cleanup-logs.yml`
- [ ] Delete `ALLOWED_USERS` if it still exists (deprecated)

### GitHub repository variables (c)
- [ ] `WORKER_URL`
- [ ] `AVAILABLE_USERS`
- [ ] (optional) `AUTO_DELETE_LOGS`

### Verification
- [ ] Allow-listed Google account signs in → workflow runs → Sheet updates
- [ ] Non-allow-listed account → 403, no run
- [ ] `gh secret list` / `gh variable list` show the expected names

---

## ❓ Troubleshooting

### "Sign-in could not be verified" (401)
- The Google ID token is missing/expired/invalid, or the audience does not match.
- Confirm the Worker's `GOOGLE_CLIENT_ID` equals the page's client ID
  (`OAUTH_CLIENT_ID`).

### "Your account is not authorized" (403)
- The verified email is not in the Worker's `ALLOWED_EMAILS`. Update that Worker secret.

### "Could not start the job" (502)
- The Worker failed to mint the GitHub App token or to dispatch the workflow.
- Check `GH_APP_ID`, `GH_APP_INSTALLATION_ID`, and `GH_APP_PRIVATE_KEY`, the App's
  installation, and that it has **Actions: write**. Inspect the Worker logs.

### "Invalid credentials" / Sheet not updated
- Verify `USER_CREDENTIALS` JSON is valid and tokens are current.
- Verify all 5 `GOOGLE_SA_*` secrets (keep `\n` in the private key); confirm the service
  account has Editor access to the Sheet.

---

## 📞 Support

For issues or questions:
1. Review the design and implementation plans under `docs/plans/`.
2. Check the GitHub Actions logs and the Cloudflare Worker logs.
3. Consult the [main README](../README.md).
