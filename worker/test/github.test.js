import { describe, it, expect, vi, afterEach, beforeAll } from "vitest";
import { generateKeyPair, exportPKCS8 } from "jose";
import { dispatchWorkflow, mintInstallationToken } from "../src/github.js";

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

describe("mintInstallationToken", () => {
  let pkcs8;
  const INSTALLATION_ID = "98765";
  const appEnv = () => ({
    GH_APP_ID: "12345",
    GH_APP_INSTALLATION_ID: INSTALLATION_ID,
    GH_APP_PRIVATE_KEY: pkcs8,
  });

  beforeAll(async () => {
    const kp = await generateKeyPair("RS256");
    pkcs8 = await exportPKCS8(kp.privateKey);
  });

  it("returns the installation token on success", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ token: "ghs_abc" }), { status: 201 })
    );
    const token = await mintInstallationToken(appEnv());
    expect(token).toBe("ghs_abc");
    const [url, opts] = spy.mock.calls[0];
    expect(url).toContain(`/app/installations/${INSTALLATION_ID}/access_tokens`);
    expect(opts.headers.Authorization).toMatch(/^Bearer /);
  });

  it("returns null on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("unauthorized", { status: 401 }));
    const token = await mintInstallationToken(appEnv());
    expect(token).toBeNull();
  });
});
