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
