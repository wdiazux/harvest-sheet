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

  it("429 when the rate limiter denies the request", async () => {
    const limitedEnv = { ...env, RATE_LIMITER: { limit: async () => ({ success: false }) } };
    const res = await worker.fetch(post({ google_id_token: "t", from_date: "2026-01-01", to_date: "2026-01-31" }), limitedEnv);
    expect(res.status).toBe(429);
  });

  it("passes through when under the rate limit", async () => {
    vi.spyOn(google, "verifyGoogleToken").mockResolvedValue({ ok: true, email: "alice@example.com" });
    vi.spyOn(github, "mintInstallationToken").mockResolvedValue("inst");
    vi.spyOn(github, "dispatchWorkflow").mockResolvedValue(true);
    const okEnv = { ...env, RATE_LIMITER: { limit: async () => ({ success: true }) } };
    const res = await worker.fetch(post({ google_id_token: "t", from_date: "2026-01-01", to_date: "2026-01-31" }), okEnv);
    expect(res.status).toBe(202);
  });

  it("handles CORS preflight", async () => {
    const res = await worker.fetch(new Request("https://w/trigger", {
      method: "OPTIONS", headers: { Origin: env.ALLOWED_ORIGIN },
    }), env);
    expect(res.status).toBe(204);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe(env.ALLOWED_ORIGIN);
  });
});
