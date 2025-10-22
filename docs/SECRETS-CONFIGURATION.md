# GitHub Secrets Configuration Guide

This document provides detailed instructions for configuring all required GitHub Secrets for the Harvest Report project.

---

## 📍 Where to Add Secrets

**GitHub Repository Settings:**
```
https://github.com/YOUR_OWNER/YOUR_REPO/settings/secrets/actions
```

Click **"New repository secret"** for each secret below.

---

## 🔐 Required Secrets (9 Total)

### 1. Authentication & Authorization

#### `ALLOWED_USERS`
**Description:** Comma-separated list of authorized email addresses that can access the web interface

**Format:**
```
email1@domain.com,email2@domain.com,email3@domain.com
```

**Example:**
```
user1@example.com,user2@example.com,user3@example.com
```

**Notes:**
- No spaces between emails
- Must match the Google accounts used to sign in
- Case-sensitive
- Add/remove users by updating this secret

---

#### `OAUTH_CLIENT_ID`
**Description:** Google OAuth 2.0 Client ID for web interface authentication

**Where to get it:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to: **APIs & Services → Credentials**
3. Find your OAuth 2.0 Client ID
4. Copy the **Client ID** (format: `xxxxx.apps.googleusercontent.com`)

**Format:**
```
123456789012-abcdefghijklmnopqrstuvwxyz123456.apps.googleusercontent.com
```

**Notes:**
- This is a **public identifier** (safe to expose in client-side code)
- Do NOT use the Client Secret here
- Must match the Client ID configured in your Google Cloud project

---

#### `WORKFLOW_TRIGGER_TOKEN`
**Description:** GitHub Personal Access Token (PAT) for triggering workflows from the web interface

**How to create:**
1. Go to [GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)](https://github.com/settings/tokens)
2. Click **"Generate new token (classic)"**
3. Name: `Harvest Sheet Workflow Trigger`
4. Expiration: Choose your preferred duration
5. Select scopes:
   - ✅ `repo` (Full control of private repositories)
   - ✅ `workflow` (Update GitHub Action workflows)
6. Click **"Generate token"**
7. Copy the token (starts with `ghp_`)

**Format:**
```
ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Security Notes:**
- Store this token securely - you can't view it again
- Regenerate periodically (recommended: every 90 days)
- If compromised, revoke immediately and generate a new one

---

### 2. Google Service Account (5 secrets)

These secrets authenticate your application to Google Sheets API.

#### Prerequisites:
1. Create a Service Account in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable **Google Sheets API** for your project
3. Download the JSON key file

#### How to extract values from JSON key file:

**Your JSON key looks like:**
```json
{
  "type": "service_account",
  "project_id": "your-project-123456",
  "private_key_id": "abc123def456...",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEF...\n-----END PRIVATE KEY-----\n",
  "client_email": "your-service-account@your-project.iam.gserviceaccount.com",
  "client_id": "123456789012345678901",
  ...
}
```

---

#### `GOOGLE_SA_PROJECT_ID`
**Description:** Google Cloud project ID

**Extract from JSON:**
```json
"project_id": "your-project-123456"
```

**Value to set:** `your-project-123456`

---

#### `GOOGLE_SA_PRIVATE_KEY_ID`
**Description:** Service account private key identifier

**Extract from JSON:**
```json
"private_key_id": "abc123def456ghi789jkl012mno345pqr678stu9"
```

**Value to set:** `abc123def456ghi789jkl012mno345pqr678stu9`

---

#### `GOOGLE_SA_PRIVATE_KEY`
**Description:** Service account private key (PEM format)

**Extract from JSON:**
```json
"private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEF...\n-----END PRIVATE KEY-----\n"
```

**⚠️ IMPORTANT:** Copy the **entire value** including:
- `-----BEGIN PRIVATE KEY-----`
- All the encoded key content
- `-----END PRIVATE KEY-----`
- Keep the `\n` characters (they represent newlines)

**Example value:**
```
-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...\n-----END PRIVATE KEY-----\n
```

**Common mistakes:**
- ❌ Removing the `\n` characters → Will cause authentication to fail
- ❌ Copying without BEGIN/END markers → Invalid key format
- ❌ Adding extra spaces or line breaks → Key corruption

---

#### `GOOGLE_SA_CLIENT_EMAIL`
**Description:** Service account email address

**Extract from JSON:**
```json
"client_email": "service-account-name@your-project.iam.gserviceaccount.com"
```

**Value to set:** `service-account-name@your-project.iam.gserviceaccount.com`

**Notes:**
- Share your Google Sheets with this email address (Editor permission)
- Format: `name@project-id.iam.gserviceaccount.com`

---

#### `GOOGLE_SA_CLIENT_ID`
**Description:** Service account client ID (numeric)

**Extract from JSON:**
```json
"client_id": "123456789012345678901"
```

**Value to set:** `123456789012345678901`

---

### 3. User Credentials (Consolidated)

#### `USER_CREDENTIALS`
**Description:** JSON object containing all user-specific Harvest and Google Sheets credentials

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
| `prefix` | User identifier (UPPERCASE_FORMAT) | Choose a unique identifier |
| `harvest_account_id` | Harvest account ID | Harvest Settings → Account |
| `harvest_auth_token` | Harvest Personal Access Token | Harvest Settings → Developers → Create New Token |
| `harvest_user_agent` | User email (for API identification) | User's email address |
| `harvest_user_id` | Harvest user ID (optional filter) | Harvest API or user profile |
| `google_sheet_id` | Target Google Sheet ID | From Sheet URL |
| `google_sheet_tab_name` | Sheet tab/worksheet name | Tab name in Google Sheet |

**How to extract Google Sheet ID:**
```
https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz-EXAMPLE_ID/edit
                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                      This is your google_sheet_id
```

**How to create Harvest Personal Access Token:**
1. Log in to Harvest
2. Go to: **Settings → Developers → Personal Access Tokens**
3. Click **"Create New Personal Access Token"**
4. Name: `Harvest Report Export`
5. Copy the token (format: `USERID.pt.xxxxxxxxxxxx`)

**Adding a new user:**
1. Copy an existing user object in the JSON
2. Update all fields with the new user's information
3. Choose a unique `prefix` (e.g., `USER_THREE`)
4. Update the secret in GitHub
5. Add the user's email to `ALLOWED_USERS` secret

**Notes:**
- JSON must be valid (use [JSONLint](https://jsonlint.com/) to validate)
- All users in the same Harvest account share the same `harvest_account_id`
- Each user needs their own Personal Access Token
- Multiple users can write to the same Google Sheet (different tabs)

**Used by workflows:**
- `daily-harvest-export.yml` - Processes ALL users in the JSON automatically
- `web-trigger.yml` - Processes users based on web interface selection

---

## 📊 GitHub Variables (Repository Variables)

**Location:** `https://github.com/YOUR_OWNER/YOUR_REPO/settings/variables/actions`

### `AVAILABLE_USERS`
**Description:** JSON object with user options for the web interface dropdown

**Format:**
```json
{
  "users": [
    { "value": "all", "label": "All Users" },
    { "value": "USER_ONE", "label": "John Smith" },
    { "value": "USER_TWO", "label": "Jane Doe" },
    { "value": "USER_THREE", "label": "Bob Johnson" }
  ]
}
```

**Field Descriptions:**
- `value`: Must match the `prefix` in `USER_CREDENTIALS` secret
- `label`: Display name shown in the web interface dropdown
- First entry should always be `"all"` for processing all users

**Notes:**
- This is a **variable**, not a secret (non-sensitive)
- Used to populate the user dropdown in the web interface
- Add new entries when adding users to `USER_CREDENTIALS`

---

### `AUTO_DELETE_LOGS` (Optional)
**Description:** Enable/disable automatic workflow log deletion

**Default:** Enabled (if not set, defaults to `true`)

**Allowed values:**
- `true` - Enable automatic log deletion (recommended for public repos)
- `false` - Disable automatic log deletion
- `1` - Enable (numeric format)
- `0` - Disable (numeric format)

**Behavior when enabled:**
- Deletes successful workflow logs older than 1 hour
- Runs automatically every 6 hours via scheduled workflow
- Preserves artifacts (CSV/JSON files) for 30 days
- Only affects `web-trigger.yml` workflow logs
- Does not delete failed runs (for debugging)

**Why use this:**
- **Public repositories**: Prevents potential information disclosure in logs
- **Privacy**: Removes execution history while preserving output files
- **Compliance**: Helps meet data retention policies

**How to set:**
```bash
# Enable (recommended)
gh variable set AUTO_DELETE_LOGS --body "true" --repo YOUR_OWNER/YOUR_REPO

# Disable
gh variable set AUTO_DELETE_LOGS --body "false" --repo YOUR_OWNER/YOUR_REPO
```

---

## 🔒 Security Features & Best Practices

### Security Implementation

This project implements **defense-in-depth** security for public repositories:

#### 1. Secret Masking
All workflows use GitHub Actions secret masking to prevent accidental exposure:
```yaml
echo "::add-mask::$USER_EMAIL"
echo "::add-mask::$TOKEN_HASH"
echo "::add-mask::$GOOGLE_CLIENT_ID"
```
- Automatically replaces masked values with `***` in logs
- Prevents secrets from appearing in workflow output
- Applied to emails, tokens, and OAuth credentials

#### 2. Minimal Logging
Workflows minimize information disclosure in public logs:
- Generic error messages (e.g., "Validation failed" instead of specific details)
- No echoing of user emails, dates, or parameters
- Script output redirected to artifacts (not console)
- Job summaries show only completion status

#### 3. Automatic Log Cleanup
The `cleanup-logs.yml` workflow provides automated log deletion:
- Runs every 6 hours via cron schedule
- Deletes successful runs older than 1 hour
- Preserves artifacts (CSV/JSON files) for 30 days
- Controlled by `AUTO_DELETE_LOGS` variable (enabled by default)
- Separate workflow to avoid self-deletion conflicts

#### 4. Server-Side Authorization
All requests are validated on GitHub's servers:
- Email validated against `ALLOWED_USERS` secret
- Validation in GitHub Actions (not client-side)
- OAuth token hash verified (never plain text)
- CSRF protection included

#### 5. Consolidated Secrets
Single `USER_CREDENTIALS` JSON secret:
- All user credentials in one encrypted secret
- Reduces secret sprawl
- Easier to manage and rotate
- Dynamic loading per workflow run

### Security Best Practices

#### 1. Secret Rotation Schedule
- **Harvest tokens**: Every 90 days
- **GitHub PAT**: Every 90 days
- **Google Service Account**: Annually or when compromised
- **OAuth Client ID**: Only when compromised

#### 2. Access Control
- Limit GitHub repository access to authorized personnel only
- Use GitHub's **secret scanning** feature (enabled by default)
- Enable **two-factor authentication** for all GitHub accounts
- Regularly audit `ALLOWED_USERS` list

#### 3. Validation & Testing
After setting all secrets, verify they work:

```bash
# Check secret names are set
gh secret list --repo YOUR_OWNER/YOUR_REPO

# Trigger a test workflow via the web interface
# Go to: https://YOUR_OWNER.github.io/YOUR_REPO/
# Sign in and run a test report
```

#### 4. Backup & Recovery
- Keep a secure backup of all secrets in a password manager (e.g., 1Password, LastPass)
- Store the Google Service Account JSON key file securely
- Document who has access to secrets
- Test recovery process periodically

#### 5. Incident Response
If a secret is compromised:
1. **Immediate**: Rotate the compromised secret
2. **Update**: Change secret in both GitHub and source (Google/Harvest)
3. **Audit**: Check logs for unauthorized access
4. **Review**: Verify no other secrets were exposed
5. **Document**: Record incident and response actions

---

## 🛠️ Helper Scripts

### Generate secrets from .env file:
```bash
bash scripts/generate-gh-secrets.sh > add-secrets.sh
bash add-secrets.sh
```

### Verify secret configuration:
```bash
bash scripts/check-secrets.sh
```

---

## 📋 Quick Setup Checklist

### Initial Setup
- [ ] Create Google OAuth Client ID
- [ ] Create GitHub Personal Access Token (with `repo` scope)
- [ ] Create Google Service Account and download JSON key
- [ ] Enable Google Sheets API
- [ ] Share Google Sheets with service account email (Editor permission)

### Configure Secrets
- [ ] Set `OAUTH_CLIENT_ID` secret
- [ ] Set `WORKFLOW_TRIGGER_TOKEN` secret
- [ ] Set `ALLOWED_USERS` secret (comma-separated emails)
- [ ] Set 5 `GOOGLE_SA_*` secrets from JSON key:
  - [ ] `GOOGLE_SA_PROJECT_ID`
  - [ ] `GOOGLE_SA_PRIVATE_KEY_ID`
  - [ ] `GOOGLE_SA_PRIVATE_KEY` (keep `\n` characters!)
  - [ ] `GOOGLE_SA_CLIENT_EMAIL`
  - [ ] `GOOGLE_SA_CLIENT_ID`
- [ ] Set `USER_CREDENTIALS` secret with all users

### Configure Variables
- [ ] Set `AVAILABLE_USERS` variable (with `"users"` wrapper object)
- [ ] (Optional) Set `AUTO_DELETE_LOGS` variable (defaults to enabled)

### Testing & Verification
- [ ] Test web interface authentication (OAuth sign-in)
- [ ] Test workflow trigger and report generation
- [ ] Verify Google Sheets are updated
- [ ] Verify artifacts are available for download
- [ ] (Optional) Verify log cleanup runs after 6 hours

---

## ❓ Troubleshooting

### "Access denied" error
- Check that user's email is in `ALLOWED_USERS` secret
- Verify email matches exactly (case-sensitive)
- Ensure no extra spaces in comma-separated list

### "Invalid credentials" error
- Verify `USER_CREDENTIALS` JSON is valid
- Check Harvest token hasn't expired
- Confirm `harvest_account_id` is correct

### "Google Sheets authentication failed"
- Verify all 5 `GOOGLE_SA_*` secrets are set correctly
- Check `GOOGLE_SA_PRIVATE_KEY` includes `\n` characters
- Ensure service account has Editor access to the sheet

### "Workflow not triggering"
- Check `WORKFLOW_TRIGGER_TOKEN` has correct scopes (`repo`, `workflow`)
- Verify token hasn't expired
- Confirm GitHub Actions are enabled for the repository

---

## 📞 Support

For issues or questions:
1. Check the [Security Audit Report](../SECURITY-AUDIT.md)
2. Review GitHub Actions logs
3. Consult the [main README](../README.md)
