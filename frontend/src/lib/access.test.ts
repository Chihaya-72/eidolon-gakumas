import { describe, expect, it } from "vitest";
import { accessReturnTo, needsAccessCheck } from "@/lib/access";

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

describe("which requests ask the backend about the password gate", () => {
  it("checks every page", () => {
    for (const path of ["/", "/about", "/settings", "/conversation/temari", "/login"]) {
      expect(needsAccessCheck(path)).toBe(true);
    }
  });
  it("skips the entry page and static pictures, sounds and fonts", () => {
    for (const path of ["/access", "/favicon.ico", "/landing/welcome/gakumas-logo.webp", "/sounds/ring.MP3", "/opengraph-image.jpg"]) {
      expect(needsAccessCheck(path)).toBe(false);
    }
  });
});
