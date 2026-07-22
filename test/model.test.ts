// Tests for model invocation (callModelWithAuth) — the auth-forwarding layer.
// Red phase: test contract before implementation exists.

import { describe, expect, it, vi } from "vitest";

// Mock streamSimple at module level
const mockStreamSimple = vi.fn();
vi.mock("@earendil-works/pi-ai/compat", () => ({
  streamSimple: mockStreamSimple,
}));

// The function under test — import will fail until src/model.ts exists
describe("callModelWithAuth", () => {
  it("retrieves auth from modelRegistry via getApiKeyAndHeaders", async () => {
    const { callModelWithAuth } = await import("../src/model.js");

    const modelRegistry = {
      find: vi.fn().mockReturnValue({ provider: "test", id: "model" }),
      getApiKeyAndHeaders: vi.fn().mockResolvedValue({
        ok: true,
        apiKey: "test-key",
        headers: { "X-Custom": "h1" },
      }),
    };
    mockStreamSimple.mockReturnValue({
      result: vi.fn().mockResolvedValue({
        role: "assistant",
        content: [{ type: "text", text: "WARN probe ok" }],
      }),
    } as any);

    const result = await callModelWithAuth(
      "test", "model",
      "system prompt", "user prompt",
      modelRegistry as any,
    );

    expect(modelRegistry.find).toHaveBeenCalledWith("test", "model");
    expect(modelRegistry.getApiKeyAndHeaders).toHaveBeenCalledWith(
      { provider: "test", id: "model" },
    );
    expect(result).toBe("WARN probe ok");
  });

  it("re-throws when model not found in registry", async () => {
    const { callModelWithAuth } = await import("../src/model.js");

    const modelRegistry = {
      find: vi.fn().mockReturnValue(null),
      getApiKeyAndHeaders: vi.fn(),
    };

    await expect(callModelWithAuth("bad", "missing", "", "", modelRegistry as any))
      .rejects.toThrow("Model not found: bad/missing");
  });

  it("re-throws when getApiKeyAndHeaders returns auth error", async () => {
    const { callModelWithAuth } = await import("../src/model.js");

    const modelRegistry = {
      find: vi.fn().mockReturnValue({ provider: "test", id: "model" }),
      getApiKeyAndHeaders: vi.fn().mockResolvedValue({
        ok: false,
        error: "No API key configured",
      }),
    };

    await expect(callModelWithAuth("test", "model", "", "", modelRegistry as any))
      .rejects.toThrow("No API key configured");
  });
});
