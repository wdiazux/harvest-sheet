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
