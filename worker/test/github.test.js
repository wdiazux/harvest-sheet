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
