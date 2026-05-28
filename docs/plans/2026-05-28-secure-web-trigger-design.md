# Secure Web Trigger — Design

**Date:** 2026-05-28
**Repo:** `wdiazux/harvest-sheet` (PUBLIC)
**Status:** Approved design, pending implementation

## Goal

Let an allow-list of people sign in on the web and run the GitHub Action that
updates/generates the Google spreadsheet — in the most secure way achievable on
free infrastructure (no credit card).

## Problem with the current approach

The current web interface is a static GitHub Pages site that triggers the export
directly from the browser. This has three structural flaws that cannot be patched
in place:

- **C1 — Secret in public JS.** `deploy-pages.yml` injects a `repo`-scoped Personal
  Access Token into `docs/app.js`, which Pages then serves publicly. Anyone can read
  it (the repo is public) and gain full write access to the repo → can exfiltrate
  every other secret via a workflow.
- **C2 — Fake authentication.** `web-trigger.yml` trusts a client-supplied email
  against `ALLOWED_USERS`; the Google sign-in is never verified server-side, and the
  token hash / CSRF values are never validated.
- **H1 — Script injection.** `${{ github.event.client_payload.* }}` is interpolated
  directly into `run:` shell, allowing command execution on the runner.

Root cause: **a static site cannot hold a secret or verify identity.** The fix is a
tiny backend the user controls.

## Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Backend host | **Cloudflare Workers** | Free, no credit card, ~100k req/day, commercial OK, single-file deploy, encrypted secrets, easy CORS |
| Sign-in | **Google Sign-In** | Already wired; allowed people need only a Google account, not GitHub; token is server-verifiable |
| GitHub credential | **GitHub App** (Actions: write, one repo) | Max security: installation token auto-expires in 1h, auto-rotating, not tied to a personal account |
| Trigger mechanism | **`workflow_dispatch`** | Not publicly triggerable (requires write access); replaces browser `repository_dispatch` |

## Architecture & data flow

```
GitHub Pages (static, PUBLIC) — no secrets
  • "Sign in with Google" (Google Identity Services)
  • Form: date range, user, options → "Generate Report"
        │ POST {WORKER_URL}/trigger
        │   { google_id_token, from_date, to_date, user_prefix, upload_to_sheets, include_advanced_fields }
        ▼
Cloudflare Worker (holds all secrets)
  1. Verify Google ID token: signature via Google JWKS (cached),
     aud == GOOGLE_CLIENT_ID, iss == accounts.google.com, exp valid, email_verified == true
  2. Check email ∈ ALLOWED_EMAILS (Worker secret) — else 403
  3. Validate inputs server-side (dates YYYY-MM-DD, known user prefix)
  4. Mint GitHub App installation token (RS256 JWT via Web Crypto → installation token, 1h)
  5. POST /repos/wdiazux/harvest-sheet/actions/workflows/web-trigger.yml/dispatches
  6. Return 202 / 400 / 401 / 403 / 502 — no secrets, no internal detail
        │ GitHub REST
        ▼
web-trigger.yml (workflow_dispatch only)
  → reads Harvest + Google SA secrets → updates Google Sheet
```

**Trust boundary:** the browser is fully untrusted and holds nothing sensitive — only
a short-lived Google ID token proving who the user is. Every secret (GitHub App key,
Harvest tokens, Google service-account key) lives server-side.

## Components

### 1. Frontend (`docs/`, GitHub Pages — stays static)
- Keep the Google Sign-In button and the form.
- Remove from `app.js`: `GITHUB_TOKEN`, `GITHUB_OWNER/REPO`, and the direct
  `api.github.com/.../dispatches` call.
- On submit: POST the Google ID token (`response.credential`) + form fields to the Worker.
- `deploy-pages.yml` injects only non-secret config: the Google client ID and the
  Worker URL. No token injection.

### 2. Cloudflare Worker (`worker/`)
- `worker.js` + `wrangler.toml`. Single route: `POST /trigger`.
- Verifies the Google ID token (JWKS cached in memory / Cache API).
- Enforces the allow-list; validates inputs again server-side.
- Mints the GitHub App installation token and calls `workflow_dispatch`.
- CORS restricted to the Pages origin; lightweight rate limiting.
- **Worker secrets** (via `wrangler secret put`, never in `wrangler.toml`):
  `GH_APP_ID`, `GH_APP_PRIVATE_KEY`, `GH_APP_INSTALLATION_ID`, `GOOGLE_CLIENT_ID`,
  `ALLOWED_EMAILS`.

### 3. GitHub App
- New App, permission **Actions: write** only, installed on `wdiazux/harvest-sheet`.
- Owner creates it and generates the private key (exact steps in the implementation plan).

### 4. Workflow (`web-trigger.yml`)
- Drop the `repository_dispatch` trigger → **`workflow_dispatch` only**.
- Pass all inputs via `env:` and reference quoted `"$VAR"` (fixes H1 script injection).
- Delete the client-side email / token-hash / CSRF logic (the Worker already authenticated).

## Security model & error handling

**Failure modes (Worker):**
- Missing/expired/invalid Google token, wrong `aud`, or `email_verified == false` → **401**.
- Valid token but email not allow-listed → **403**.
- Malformed inputs → **400** (validated server-side; the browser is never trusted).
- GitHub API failure → **502**, generic message; real error only in Worker logs.
- Responses never carry secrets or internal detail.

**Public-repo considerations:**
- **No secret in any committed file.** Worker secrets via `wrangler secret put`
  (encrypted at Cloudflare); GitHub App private key never committed; `.dev.vars`
  gitignored. Committed Worker source is logic only — safe to be public.
- **`workflow_dispatch` is not publicly triggerable** — requires write access; fork
  PRs cannot fire it. No `pull_request` / `pull_request_target` triggers exist, so
  forks never receive secret access.
- **Public logs → masking matters more.** The export step pipes to `/dev/null` and
  masks credentials; the existing log-cleanup workflow remains as defense-in-depth.
- **Worker endpoint is internet-reachable.** Every request must present a Google token
  validly signed for our client ID before anything happens; add rate limiting + CORS.
- **Least privilege:** GitHub App = Actions:write on one repo; keep repo collaborators
  minimal (any collaborator can read Actions secrets).

## Rollout order (the daily cron is untouched throughout)

1. **Revoke the leaked `WORKFLOW_TRIGGER_TOKEN` PAT now** — it only powers the old
   browser trigger (cron uses different secrets), so revoking stops the active exposure
   without breaking anything critical.
2. Create the GitHub App (Actions: write), install on the repo, capture App ID /
   Installation ID / private key.
3. Deploy the Worker; set its secrets via `wrangler secret put`.
4. Update the frontend → calls the Worker; update `deploy-pages.yml` to inject only the
   Google client ID + Worker URL.
5. Convert `web-trigger.yml` → `workflow_dispatch` only + env-var hardening.
6. Delete the `WORKFLOW_TRIGGER_TOKEN` secret and all token-injection code.

## Dependency upgrade (bundled with this work)

- `requirements.txt` → latest: CVE fixes (`requests` ≥ 2.34.2, `python-dotenv` ≥ 1.2.2),
  `pandas` 3.0.0 → 3.0.3, `pydantic`, the three `google-*` libraries; `rich` 14 → 15
  reviewed before applying.
- GitHub Actions: `actions/setup-python@v4 → v5`.
- Add `.github/dependabot.yml` (ecosystems: pip, github-actions, and the Worker's npm).
- Add request **timeouts** in `convert_harvest_json_to_csv.py` (lines 476, 506).
- **nixpkgs stays on 26.05** (reverted); `shell.nix` tracks nixpkgs, so no pin bump.

## Testing

- **Worker:** `wrangler dev` locally. Verify the accept path (valid Google token +
  allowed email) and every reject path (bad audience, `email_verified:false`,
  non-allowed email, malformed date) returns the correct 4xx.
- **Workflow:** `gh workflow run web-trigger.yml -f from_date=... -f to_date=...` to
  confirm `workflow_dispatch` + inputs work and the Sheet updates.
- **End-to-end:** sign in on the live Pages site → trigger → confirm the Actions run
  and the spreadsheet update.

## Out of scope

- The architectural redesign does not change the export logic in
  `convert_harvest_json_to_csv.py` beyond adding request timeouts.
- The daily scheduled export (`daily-harvest-export.yml`) is unchanged.
