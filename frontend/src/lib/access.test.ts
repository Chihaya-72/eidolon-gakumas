import { describe, expect, it } from "vitest";
import { accessReturnTo } from "@/lib/access";

describe("password gate return address", () => {
  it("preserves local deep links and invitation queries", () => {
    expect(accessReturnTo("/login?invite=abc")).toBe("/login?invite=abc");
    expect(accessReturnTo("/conversation/temari")).toBe("/conversation/temari");
  });
  it("refuses external URLs, slash normalization and entry loops", () => {
    for (const value of [null, "https://evil.example", "//evil.example", "/\\evil.example", "/\t/evil.example", "/access?returnTo=/access"]) {
      expect(accessReturnTo(value)).toBe("/");
    }
  });
});
