# Secure Web Trigger Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the static-page PAT trigger with a Cloudflare Worker that verifies Google Sign-In, enforces an email allow-list, and triggers the export via a GitHub App + `workflow_dispatch`.

**Architecture:** Static GitHub Pages frontend (no secrets) → POSTs a Google ID token to a Cloudflare Worker → Worker verifies the token, checks the allow-list, mints a 1-hour GitHub App installation token, and calls `workflow_dispatch` on `web-trigger.yml`. All secrets live server-side (Worker secrets + Actions secrets).

**Tech Stack:** Cloudflare Workers (ESM JS), `jose` (JWT verify/sign on Web Crypto), `vitest` for unit tests, `wrangler` for deploy. GitHub App for repo access. Existing Python export script unchanged except request timeouts.

**Reference:** Design at `docs/plans/2026-05-28-secure-web-trigger-design.md`.

**Repo:** `wdiazux/harvest-sheet` (PUBLIC). Worker source is committed (logic only, no secrets).

---

## Conventions

- Worker code lives in `worker/`. Frontend stays in `docs/`.
- **No secret is ever committed.** Worker secrets are set with `wrangler secret put`. `worker/.dev.vars` (local-only) is gitignored.
- Commit after each task. Use conventional-commit messages matching repo style (`feat:`, `chore:`, `docs:`, `fix:`).
- Tests are colocated under `worker/test/`.

---

## Phase A — Cloudflare Worker (the secure backend)

### Task A1: Scaffold the Worker project

**Files:**
- Create: `worker/package.json`
- Create: `worker/wrangler.toml`
- Create: `worker/.gitignore`
- Create: `worker/vitest.config.js`
- Modify: root `.gitignore` (add `worker/node_modules`, `worker/.dev.vars`)

**Step 1: Create `worker/package.json`**

```json
{
  "name": "harvest-web-trigger",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "wrangler dev",
    "deploy": "wrangler deploy",
    "test": "vitest run"
  },
  "dependencies": {
    "jose": "^5.9.6"
  },
  "devDependencies": {
    "vitest": "^2.1.8",
    "wrangler": "^3.95.0"
  }
}
```

**Step 2: Create `worker/wrangler.toml`** (NO secrets here)

```toml
name = "harvest-web-trigger"
main = "src/index.js"
compatibility_date = "2026-05-01"

[vars]
GITHUB_OWNER = "wdiazux"
GITHUB_REPO = "harvest-sheet"
WORKFLOW_FILE = "web-trigger.yml"
WORKFLOW_REF = "main"
ALLOWED_ORIGIN = "https://wdiazux.github.io"
```

**Step 3: Create `worker/.gitignore`**

```
node_modules/
.dev.vars
.wrangler/
```

**Step 4: Create `worker/vitest.config.js`**

```js
import { defineConfig } from "vitest/config";
export default defineConfig({ test: { environment: "node" } });
```

**Step 5: Install deps**

Run: `cd worker && npm install`
Expected: `node_modules/` populated, `package-lock.json` created.

**Step 6: Append to root `.gitignore`**

```
# Cloudflare Worker
worker/node_modules/
worker/.dev.vars
worker/.wrangler/
```

**Step 7: Commit**

```bash
git add worker/package.json worker/wrangler.toml worker/.gitignore worker/vitest.config.js worker/package-lock.json .gitignore
git commit -m "feat: scaffold cloudflare worker for web trigger"
```

---

### Task A2: Input validation (pure function, TDD)

**Files:**
- Create: `worker/src/validate.js`
- Test: `worker/test/validate.test.js`

**Step 1: Write the failing test** — `worker/test/validate.test.js`

```js
import { describe, it, expect } from "vitest";
import { validateInputs } from "../src/validate.js";

describe("validateInputs", () => {
  it("accepts a well-formed payload", () => {
    const { ok, value } = validateInputs({
      from_date: "2026-01-01", to_date: "2026-01-31",
      user_prefix: "WILLIAM_DIAZ", upload_to_sheets: true, include_advanced_fields: false,
    });
    expect(ok).toBe(true);
    expect(value.from_date).toBe("2026-01-01");
    expect(value.upload_to_sheets).toBe("true");   // workflow_dispatch needs strings
    expect(value.include_advanced_fields).toBe("false");
  });

  it("defaults user_prefix to 'all'", () => {
    const { ok, value } = validateInputs({ from_date: "2026-01-01", to_date: "2026-01-31" });
    expect(ok).toBe(true);
    expect(value.user_prefix).toBe("all");
  });

  it("rejects a malformed date", () => {
    const { ok } = validateInputs({ from_date: "01-01-2026", to_date: "2026-01-31" });
    expect(ok).toBe(false);
  });

  it("rejects injection characters in user_prefix", () => {
    const { ok } = validateInputs({
      from_date: "2026-01-01", to_date: "2026-01-31", user_prefix: "a; rm -rf /",
    });
    expect(ok).toBe(false);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd worker && npx vitest run test/validate.test.js`
Expected: FAIL — `validateInputs` not exported.

**Step 3: Write minimal implementation** — `worker/src/validate.js`

```js
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const PREFIX_RE = /^[A-Za-z0-9_]+$/;

export function validateInputs(body) {
  const from_date = String(body?.from_date ?? "");
  const to_date = String(body?.to_date ?? "");
  if (!DATE_RE.test(from_date) || !DATE_RE.test(to_date)) return { ok: false };

  let user_prefix = body?.user_prefix ? String(body.user_prefix) : "all";
  if (user_prefix !== "all" && !PREFIX_RE.test(user_prefix)) return { ok: false };

  return {
    ok: true,
    value: {
      from_date,
      to_date,
      user_prefix,
      upload_to_sheets: body?.upload_to_sheets ? "true" : "false",
      include_advanced_fields: body?.include_advanced_fields ? "true" : "false",
    },
  };
}
```

**Step 4: Run test to verify it passes**

Run: `cd worker && npx vitest run test/validate.test.js`
Expected: PASS (4 tests).

**Step 5: Commit**

```bash
git add worker/src/validate.js worker/test/validate.test.js
git commit -m "feat: add input validation for worker trigger"
```

---

### Task A3: Allow-list check (pure function, TDD)

**Files:**
- Create: `worker/src/allowlist.js`
- Test: `worker/test/allowlist.test.js`

**Step 1: Write the failing test** — `worker/test/allowlist.test.js`

```js
import { describe, it, expect } from "vitest";
import { isAllowed } from "../src/allowlist.js";

describe("isAllowed", () => {
  const list = "alice@example.com, bob@example.com";
  it("allows a listed email (case-insensitive, trimmed)", () => {
    expect(isAllowed("ALICE@example.com", list)).toBe(true);
  });
  it("rejects an unlisted email", () => {
    expect(isAllowed("eve@example.com", list)).toBe(false);
  });
  it("rejects when list is empty/undefined", () => {
    expect(isAllowed("alice@example.com", "")).toBe(false);
    expect(isAllowed("alice@example.com", undefined)).toBe(false);
  });
  it("does substring-safe exact match only", () => {
    expect(isAllowed("lice@example.com", list)).toBe(false);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd worker && npx vitest run test/allowlist.test.js`
Expected: FAIL — `isAllowed` not defined.

**Step 3: Write minimal implementation** — `worker/src/allowlist.js`

```js
export function isAllowed(email, allowedCsv) {
  if (!email || !allowedCsv) return false;
  const target = String(email).trim().toLowerCase();
  return String(allowedCsv)
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean)
    .includes(target);
}
```

**Step 4: Run test to verify it passes**

Run: `cd worker && npx vitest run test/allowlist.test.js`
Expected: PASS (4 tests).

**Step 5: Commit**

```bash
git add worker/src/allowlist.js worker/test/allowlist.test.js
git commit -m "feat: add email allow-list check for worker"
```

---

### Task A4: Google ID token verification (TDD with a local key)

**Files:**
- Create: `worker/src/google.js`
- Test: `worker/test/google.test.js`

**Approach:** `verifyGoogleToken(idToken, clientId, jwks)` takes an injectable JWKS resolver so tests can sign a token with a local key. Production passes a `createRemoteJWKSet` pointed at Google.

**Step 1: Write the failing test** — `worker/test/google.test.js`

```js
import { describe, it, expect, beforeAll } from "vitest";
import { generateKeyPair, exportJWK, SignJWT } from "jose";
import { verifyGoogleToken } from "../src/google.js";

const CLIENT_ID = "test-client-id.apps.googleusercontent.com";
let privateKey, jwks;

beforeAll(async () => {
  const kp = await generateKeyPair("RS256");
  privateKey = kp.privateKey;
  const pub = await exportJWK(kp.publicKey);
  pub.kid = "test-kid"; pub.alg = "RS256";
  jwks = async () => kp.publicKey; // resolver stub
});

async function mint(claims) {
  return await new SignJWT(claims)
    .setProtectedHeader({ alg: "RS256", kid: "test-kid" })
    .setIssuer("https://accounts.google.com")
    .setAudience(CLIENT_ID)
    .setIssuedAt()
    .setExpirationTime("5m")
    .sign(privateKey);
}

describe("verifyGoogleToken", () => {
  it("returns email for a valid, verified token", async () => {
    const token = await mint({ email: "alice@example.com", email_verified: true });
    const { ok, email } = await verifyGoogleToken(token, CLIENT_ID, jwks);
    expect(ok).toBe(true);
    expect(email).toBe("alice@example.com");
  });
  it("rejects wrong audience", async () => {
    const token = await mint({ email: "a@e.com", email_verified: true, aud: "other" });
    const { ok } = await verifyGoogleToken(token, "different-client", jwks);
    expect(ok).toBe(false);
  });
  it("rejects email_verified=false", async () => {
    const token = await mint({ email: "a@e.com", email_verified: false });
    const { ok } = await verifyGoogleToken(token, CLIENT_ID, jwks);
    expect(ok).toBe(false);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd worker && npx vitest run test/google.test.js`
Expected: FAIL — `verifyGoogleToken` not defined.

**Step 3: Write minimal implementation** — `worker/src/google.js`

```js
import { jwtVerify, createRemoteJWKSet } from "jose";

const GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"];

// Production resolver (cached by jose). Tests inject their own resolver.
export function googleJWKS() {
  return createRemoteJWKSet(new URL("https://www.googleapis.com/oauth2/v3/certs"));
}

export async function verifyGoogleToken(idToken, clientId, jwksResolver) {
  try {
    const { payload } = await jwtVerify(idToken, jwksResolver, {
      audience: clientId,
      issuer: GOOGLE_ISSUERS,
    });
    if (payload.email_verified !== true) return { ok: false };
    if (!payload.email) return { ok: false };
    return { ok: true, email: String(payload.email) };
  } catch {
    return { ok: false };
  }
}
```

**Step 4: Run test to verify it passes**

Run: `cd worker && npx vitest run test/google.test.js`
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add worker/src/google.js worker/test/google.test.js
git commit -m "feat: add google id token verification to worker"
```

---

### Task A5: GitHub App token minting + workflow_dispatch (TDD with mocked fetch)

**Files:**
- Create: `worker/src/github.js`
- Test: `worker/test/github.test.js`

**Approach:** `mintInstallationToken(env, signFn)` builds the App JWT and exchanges it; `dispatchWorkflow(env, token, inputs)` calls the REST endpoint. Tests stub `globalThis.fetch` and the signer.

**Step 1: Write the failing test** — `worker/test/github.test.js`

```js
import { describe, it, expect, vi, afterEach } from "vitest";
import { dispatchWorkflow } from "../src/github.js";

afterEach(() => vi.restoreAllMocks());

const env = {
  GITHUB_OWNER: "wdiazux", GITHUB_REPO: "harvest-sheet",
  WORKFLOW_FILE: "web-trigger.yml", WORKFLOW_REF: "main",
};

describe("dispatchWorkflow", () => {
  it("POSTs to the dispatches endpoint and succeeds on 204", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    const ok = await dispatchWorkflow(env, "inst-token", {
      from_date: "2026-01-01", to_date: "2026-01-31", user_prefix: "all",
      upload_to_sheets: "true", include_advanced_fields: "false",
    });
    expect(ok).toBe(true);
    const [url, opts] = spy.mock.calls[0];
    expect(url).toContain("/repos/wdiazux/harvest-sheet/actions/workflows/web-trigger.yml/dispatches");
    expect(opts.method).toBe("POST");
    expect(opts.headers.Authorization).toBe("Bearer inst-token");
    expect(JSON.parse(opts.body).ref).toBe("main");
    expect(JSON.parse(opts.body).inputs.from_date).toBe("2026-01-01");
  });

  it("returns false on non-204", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("nope", { status: 422 }));
    const ok = await dispatchWorkflow(env, "t", { from_date: "x" });
    expect(ok).toBe(false);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd worker && npx vitest run test/github.test.js`
Expected: FAIL — `dispatchWorkflow` not defined.

**Step 3: Write minimal implementation** — `worker/src/github.js`

```js
import { SignJWT, importPKCS8 } from "jose";

const API = "https://api.github.com";
const UA = "harvest-web-trigger";

// env.GH_APP_PRIVATE_KEY must be PKCS8 PEM ("BEGIN PRIVATE KEY").
export async function mintInstallationToken(env) {
  const key = await importPKCS8(env.GH_APP_PRIVATE_KEY, "RS256");
  const now = Math.floor(Date.now() / 1000);
  const appJwt = await new SignJWT({})
    .setProtectedHeader({ alg: "RS256" })
    .setIssuedAt(now - 60)
    .setExpirationTime(now + 600)
    .setIssuer(String(env.GH_APP_ID))
    .sign(key);

  const res = await fetch(`${API}/app/installations/${env.GH_APP_INSTALLATION_ID}/access_tokens`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${appJwt}`,
      Accept: "application/vnd.github+json",
      "User-Agent": UA,
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.token ?? null;
}

export async function dispatchWorkflow(env, installationToken, inputs) {
  const url = `${API}/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${env.WORKFLOW_FILE}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${installationToken}`,
      Accept: "application/vnd.github+json",
      "User-Agent": UA,
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: env.WORKFLOW_REF, inputs }),
  });
  return res.status === 204;
}
```

**Step 4: Run test to verify it passes**

Run: `cd worker && npx vitest run test/github.test.js`
Expected: PASS (2 tests).

**Step 5: Commit**

```bash
git add worker/src/github.js worker/test/github.test.js
git commit -m "feat: add github app token minting and workflow dispatch"
```

---

### Task A6: Request handler + CORS + wiring (TDD)

**Files:**
- Create: `worker/src/index.js`
- Test: `worker/test/index.test.js`

**Step 1: Write the failing test** — `worker/test/index.test.js`

```js
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import worker from "../src/index.js";
import * as google from "../src/google.js";
import * as github from "../src/github.js";

const env = {
  GOOGLE_CLIENT_ID: "cid", ALLOWED_EMAILS: "alice@example.com",
  ALLOWED_ORIGIN: "https://wdiazux.github.io",
  GITHUB_OWNER: "wdiazux", GITHUB_REPO: "harvest-sheet",
  WORKFLOW_FILE: "web-trigger.yml", WORKFLOW_REF: "main",
};

function post(body) {
  return new Request("https://w/trigger", {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: env.ALLOWED_ORIGIN },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  vi.spyOn(google, "googleJWKS").mockReturnValue(async () => ({}));
});
afterEach(() => vi.restoreAllMocks());

describe("worker fetch", () => {
  it("202 on valid token + allowed email", async () => {
    vi.spyOn(google, "verifyGoogleToken").mockResolvedValue({ ok: true, email: "alice@example.com" });
    vi.spyOn(github, "mintInstallationToken").mockResolvedValue("inst");
    vi.spyOn(github, "dispatchWorkflow").mockResolvedValue(true);
    const res = await worker.fetch(post({ google_id_token: "t", from_date: "2026-01-01", to_date: "2026-01-31" }), env);
    expect(res.status).toBe(202);
  });

  it("401 on invalid token", async () => {
    vi.spyOn(google, "verifyGoogleToken").mockResolvedValue({ ok: false });
    const res = await worker.fetch(post({ google_id_token: "bad", from_date: "2026-01-01", to_date: "2026-01-31" }), env);
    expect(res.status).toBe(401);
  });

  it("403 on non-allowed email", async () => {
    vi.spyOn(google, "verifyGoogleToken").mockResolvedValue({ ok: true, email: "eve@example.com" });
    const res = await worker.fetch(post({ google_id_token: "t", from_date: "2026-01-01", to_date: "2026-01-31" }), env);
    expect(res.status).toBe(403);
  });

  it("400 on bad inputs", async () => {
    vi.spyOn(google, "verifyGoogleToken").mockResolvedValue({ ok: true, email: "alice@example.com" });
    const res = await worker.fetch(post({ google_id_token: "t", from_date: "nope", to_date: "2026-01-31" }), env);
    expect(res.status).toBe(400);
  });

  it("handles CORS preflight", async () => {
    const res = await worker.fetch(new Request("https://w/trigger", {
      method: "OPTIONS", headers: { Origin: env.ALLOWED_ORIGIN },
    }), env);
    expect(res.status).toBe(204);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe(env.ALLOWED_ORIGIN);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd worker && npx vitest run test/index.test.js`
Expected: FAIL — no default export.

**Step 3: Write minimal implementation** — `worker/src/index.js`

```js
import { verifyGoogleToken, googleJWKS } from "./google.js";
import { isAllowed } from "./allowlist.js";
import { validateInputs } from "./validate.js";
import { mintInstallationToken, dispatchWorkflow } from "./github.js";

function cors(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}
const json = (env, status, obj) =>
  new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...cors(env) } });

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(env) });
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/trigger") return json(env, 404, { error: "not found" });

    let body;
    try { body = await request.json(); } catch { return json(env, 400, { error: "bad json" }); }

    const auth = await verifyGoogleToken(body.google_id_token, env.GOOGLE_CLIENT_ID, googleJWKS());
    if (!auth.ok) return json(env, 401, { error: "unauthenticated" });
    if (!isAllowed(auth.email, env.ALLOWED_EMAILS)) return json(env, 403, { error: "forbidden" });

    const { ok, value } = validateInputs(body);
    if (!ok) return json(env, 400, { error: "invalid input" });

    const token = await mintInstallationToken(env);
    if (!token) return json(env, 502, { error: "upstream auth failed" });

    const dispatched = await dispatchWorkflow(env, token, value);
    if (!dispatched) return json(env, 502, { error: "dispatch failed" });

    return json(env, 202, { status: "triggered" });
  },
};
```

**Step 4: Run test to verify it passes**

Run: `cd worker && npx vitest run`
Expected: PASS (all suites).

**Step 5: Commit**

```bash
git add worker/src/index.js worker/test/index.test.js
git commit -m "feat: add worker request handler with auth, allow-list, dispatch"
```

---

## Phase B — Frontend (GitHub Pages)

### Task B1: Rewrite `docs/app.js` to call the Worker (no token)

**Files:**
- Modify: `docs/app.js` (remove `GITHUB_TOKEN`, `GITHUB_OWNER/REPO`, direct dispatch; POST to Worker)
- Modify: `docs/index.html` if a `WORKER_URL` placeholder element is needed

**Step 1:** Replace the `CONFIG` block at the top of `docs/app.js`:

```js
const CONFIG = {
    GOOGLE_CLIENT_ID: 'YOUR_GOOGLE_CLIENT_ID',
    WORKER_URL: 'YOUR_WORKER_URL',   // injected at deploy, e.g. https://harvest-web-trigger.<acct>.workers.dev
    AVAILABLE_USERS: []
};
```

**Step 2:** Replace `triggerGitHubAction()` (the function that called `api.github.com/.../dispatches`) with a Worker call:

```js
async function triggerGitHubAction(params) {
    const runButton = document.getElementById('runButton');
    runButton.disabled = true;
    runButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Triggering workflow...';
    try {
        const res = await fetch(`${CONFIG.WORKER_URL}/trigger`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                google_id_token: currentUser.token,           // Google ID token (response.credential)
                from_date: params.from_date,
                to_date: params.to_date,
                user_prefix: params.user_prefix,
                upload_to_sheets: params.upload_to_sheets,
                include_advanced_fields: params.include_advanced_fields,
            }),
        });
        if (res.status === 202) {
            showJobStatus('✅ Workflow triggered. Check the Actions tab for progress.', 'success');
        } else if (res.status === 401) {
            showJobStatus('❌ Sign-in could not be verified. Please sign in again.', 'error');
        } else if (res.status === 403) {
            showJobStatus('❌ Your account is not authorized.', 'error');
        } else {
            showJobStatus('❌ Could not start the job. Please try again later.', 'error');
        }
    } catch (e) {
        showJobStatus('❌ Network error. Please try again.', 'error');
    } finally {
        runButton.disabled = false;
        runButton.innerHTML = '<i class="fas fa-play"></i> Generate Report';
    }
}
```

**Step 3:** Delete now-dead code in `docs/app.js`: `hashToken()`, `generateCSRFToken()`, `showManualTriggerInstructions()`, and any `GITHUB_API_BASE`/`GITHUB_TOKEN` references.

**Step 4: Verify locally**

Run: `cd worker && npx wrangler dev` (in one shell), then open `docs/index.html` with a local server pointing `WORKER_URL` at `http://localhost:8787`. Manually confirm: sign in → submit → 202 path shows success. (Full e2e happens in Phase E.)

**Step 5: Commit**

```bash
git add docs/app.js docs/index.html
git commit -m "refactor: web UI calls worker instead of embedding github token"
```

---

### Task B2: Update `deploy-pages.yml` injection (no token)

**Files:**
- Modify: `.github/workflows/deploy-pages.yml`

**Step 1:** Replace the "Inject secrets" step body so it injects only non-secret config:

```yaml
      - name: Inject configuration
        env:
          GOOGLE_CLIENT_ID: ${{ secrets.OAUTH_CLIENT_ID }}
          WORKER_URL: ${{ vars.WORKER_URL }}
          AVAILABLE_USERS: ${{ vars.AVAILABLE_USERS }}
        run: |
          if [ -z "$GOOGLE_CLIENT_ID" ] || [ -z "$WORKER_URL" ]; then
            echo "Missing GOOGLE_CLIENT_ID or WORKER_URL"; exit 1
          fi
          sed -i "s|YOUR_GOOGLE_CLIENT_ID|${GOOGLE_CLIENT_ID}|g" docs/app.js docs/index.html
          sed -i "s|YOUR_WORKER_URL|${WORKER_URL}|g" docs/app.js
          if [ -n "$AVAILABLE_USERS" ]; then echo "$AVAILABLE_USERS" > docs/config.json; fi
          if grep -q "YOUR_GOOGLE_CLIENT_ID\|YOUR_WORKER_URL" docs/app.js; then
            echo "Injection failed"; exit 1
          fi
```

> Note: the Google client ID is not secret (it ships in the page anyway), so `vars.WORKER_URL` + `secrets.OAUTH_CLIENT_ID` are both fine. No GitHub token is injected anywhere.

**Step 2: Verify**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/deploy-pages.yml'))" && echo OK`
Expected: `OK` (valid YAML).

**Step 3: Commit**

```bash
git add .github/workflows/deploy-pages.yml
git commit -m "refactor: inject worker url + client id, drop token injection"
```

---

## Phase C — Workflow hardening

### Task C1: Convert `web-trigger.yml` to workflow_dispatch + env-var safety

**Files:**
- Modify: `.github/workflows/web-trigger.yml`

**Step 1:** Remove the `repository_dispatch` trigger and the `repository_dispatch` branch of the "Extract and validate parameters" step. Keep `workflow_dispatch` with its inputs.

**Step 2:** Remove the entire "Validate user authorization" step and the token-hash/CSRF handling (the Worker already authenticated; only authorized callers reach `workflow_dispatch`).

**Step 3:** Rewrite the parameter + run steps to pass inputs via `env:` (no `${{ }}` inside `run:` shell). Example for the run step:

```yaml
      - name: Run Harvest script
        id: harvest
        env:
          FROM_DATE: ${{ inputs.from_date }}
          TO_DATE: ${{ inputs.to_date }}
          USER_PREFIX: ${{ inputs.user_prefix }}
          UPLOAD_TO_GOOGLE_SHEET: ${{ inputs.upload_to_sheets }}
          INCLUDE_ADVANCED_FIELDS: ${{ inputs.include_advanced_fields }}
        run: |
          [[ "$FROM_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "bad from_date"; exit 1; }
          [[ "$TO_DATE"   =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "bad to_date"; exit 1; }
          ARGS="--from-date $FROM_DATE --to-date $TO_DATE"
          if [ "$USER_PREFIX" != "all" ]; then
            SAFE_PREFIX="$(printf '%s' "$USER_PREFIX" | tr -cd 'A-Za-z0-9_')"
            ARGS="$ARGS --user $SAFE_PREFIX"
          fi
          export UPLOAD_TO_GOOGLE_SHEET INCLUDE_ADVANCED_FIELDS
          python convert_harvest_json_to_csv.py $ARGS > /dev/null 2>&1
```

(The Google SA + USER_CREDENTIALS loading step stays as-is — it already uses `env:` + `::add-mask::`.)

**Step 4:** Reduce job permissions to `contents: read` (drop `actions: write` — it's no longer needed since the run executes the script, it doesn't dispatch).

**Step 5: Verify**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/web-trigger.yml'))" && echo OK`
Expected: `OK`.

**Step 6: Commit**

```bash
git add .github/workflows/web-trigger.yml
git commit -m "fix: workflow_dispatch only + env-var inputs (no script injection)"
```

---

## Phase D — Dependency upgrade & hardening

### Task D1: Upgrade `requirements.txt`

**Files:**
- Modify: `requirements.txt`

**Step 1:** Set pins to current latest (verify each with `pip index versions <pkg>` or PyPI before applying; `rich` 15 is a major bump — skim its changelog):

```
google-api-python-client==2.196.0
google-auth==2.53.0
google-auth-oauthlib==1.4.0
gspread==6.2.1
pandas==3.0.3
pydantic==2.13.4
python-dateutil==2.9.0.post0
python-dotenv==1.2.2
requests==2.34.2
rich==15.0.0
```

**Step 2: Verify install resolves**

Run: `python -m venv /tmp/hv && /tmp/hv/bin/pip install -r requirements.txt && echo OK`
Expected: clean install, `OK`. (If `rich` 15 breaks console usage during the Phase E smoke test, pin back to `14.3.1`.)

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: upgrade python dependencies (incl. requests/python-dotenv CVE fixes)"
```

---

### Task D2: Add request timeouts to the export script

**Files:**
- Modify: `convert_harvest_json_to_csv.py` (the two `requests.get(...)` calls, ~lines 476 and 506)

**Step 1:** Add `timeout=(5, 30)` to both calls:

```python
response = requests.get(base_url, headers=headers, params=params, timeout=(5, 30))
```

**Step 2:** Confirm `requests.exceptions.Timeout` is covered — the existing `except requests.RequestException` blocks already catch it (Timeout subclasses RequestException). No new handler needed.

**Step 3: Verify**

Run: `python -c "import ast; ast.parse(open('convert_harvest_json_to_csv.py').read()); print('OK')"`
Expected: `OK`.

**Step 4: Commit**

```bash
git add convert_harvest_json_to_csv.py
git commit -m "fix: add connect/read timeouts to harvest api requests"
```

---

### Task D3: Bump `setup-python` and add Dependabot

**Files:**
- Modify: `.github/workflows/daily-harvest-export.yml`, `.github/workflows/web-trigger.yml` (`setup-python@v4 → v5`)
- Create: `.github/dependabot.yml`

**Step 1:** Replace `uses: actions/setup-python@v4` with `@v5` in both workflows.

**Step 2:** Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: "/"
    schedule: { interval: weekly }
  - package-ecosystem: github-actions
    directory: "/"
    schedule: { interval: weekly }
  - package-ecosystem: npm
    directory: "/worker"
    schedule: { interval: weekly }
```

**Step 3: Verify**

Run: `python -c "import yaml; [yaml.safe_load(open(f)) for f in ['.github/dependabot.yml','.github/workflows/daily-harvest-export.yml','.github/workflows/web-trigger.yml']]; print('OK')"`
Expected: `OK`.

**Step 4: Commit**

```bash
git add .github/dependabot.yml .github/workflows/daily-harvest-export.yml .github/workflows/web-trigger.yml
git commit -m "chore: setup-python v5 + dependabot for pip/actions/npm"
```

---

## Phase E — Manual provisioning & cutover (owner actions + verification)

> These steps need your GitHub/Cloudflare accounts. Claude provides exact instructions; you click.

### Task E1: Create the GitHub App
1. GitHub → Settings → Developer settings → GitHub Apps → **New GitHub App**.
2. Name it (e.g. `harvest-web-trigger`); Homepage URL = repo URL.
3. Uncheck **Webhook → Active**.
4. Permissions → Repository → **Actions: Read and write**. No other permissions.
5. "Where can this be installed" → **Only on this account**. Create.
6. **Generate a private key** → downloads a `.pem` (PKCS1). Note the **App ID**.
7. **Install App** → select only `wdiazux/harvest-sheet`. After install, note the **Installation ID** (in the install URL: `.../installations/<id>`).
8. Convert the key to PKCS8 for Web Crypto:
   `openssl pkcs8 -topk8 -inform PEM -outform PEM -nocrypt -in app.private-key.pem -out app.pkcs8.pem`

### Task E2: Deploy the Worker + secrets
1. `cd worker && npx wrangler login`
2. `npx wrangler deploy` → note the `*.workers.dev` URL.
3. Set secrets (paste values when prompted):
   ```
   npx wrangler secret put GOOGLE_CLIENT_ID
   npx wrangler secret put GH_APP_ID
   npx wrangler secret put GH_APP_INSTALLATION_ID
   npx wrangler secret put GH_APP_PRIVATE_KEY      # paste full PKCS8 PEM contents
   npx wrangler secret put ALLOWED_EMAILS          # comma-separated emails
   ```
4. In Google Cloud Console → the OAuth client → **Authorized JavaScript origins**: ensure your Pages origin is listed.

### Task E3: Wire the frontend config (repo vars)
1. Repo → Settings → Secrets and variables → Actions → **Variables**:
   - `WORKER_URL` = the workers.dev URL from E2.
   - (`AVAILABLE_USERS` already exists.)
2. `OAUTH_CLIENT_ID` secret already exists.
3. Re-run **Deploy to GitHub Pages**.

### Task E4: Cutover & cleanup
1. Confirm the new flow works (E5) **first**.
2. Then revoke the old PAT: GitHub → Settings → Developer settings → Personal access tokens → delete the one used for `WORKFLOW_TRIGGER_TOKEN`.
3. Repo → delete the `WORKFLOW_TRIGGER_TOKEN` secret.

### Task E5: End-to-end verification
1. `gh workflow run web-trigger.yml -f from_date=2026-05-01 -f to_date=2026-05-07 -f user_prefix=all` → confirm a run starts and the Sheet updates (validates `workflow_dispatch` + inputs independent of the web UI).
2. Open the live Pages site → sign in with an allow-listed Google account → submit → expect success and a new Actions run + Sheet update.
3. Negative test: sign in with a non-allow-listed account → expect the 403 message and **no** Actions run.

---

## Done criteria
- [ ] `cd worker && npx vitest run` passes (Phases A2–A6).
- [ ] No GitHub token anywhere in `docs/` or in `deploy-pages.yml`.
- [ ] `web-trigger.yml` has only `workflow_dispatch` and no `${{ }}` inside `run:`.
- [ ] `requirements.txt` upgraded; `pip install -r` resolves; CVE'd packages bumped.
- [ ] Old `WORKFLOW_TRIGGER_TOKEN` PAT revoked and secret deleted.
- [ ] E5 web sign-in (allowed) triggers a run; non-allowed gets 403 with no run.
