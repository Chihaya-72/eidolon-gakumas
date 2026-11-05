import { describe, expect, it } from "vitest";

import { imageModelsFirst } from "./ServiceModelField";

describe("imageModelsFirst", () => {
  it("puts image models first, otherwise keeping the relay's order", () => {
    expect(imageModelsFirst(["gpt-5", "gpt-image-2", "claude", "DALL-E-3"])).toEqual([
      "gpt-image-2",
      "DALL-E-3",
      "gpt-5",
      "claude",
    ]);
  });
});
