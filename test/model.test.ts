// Tests for model invocation (callModelWithAuth) — the auth-forwarding layer.
// Tests usage retention in returned result.

import { describe, expect, it, vi } from "vitest";

// Mock streamSimple at module level
const mockStreamSimple = vi.fn();
vi.mock("@earendil-works/pi-ai/compat", () => ({
  streamSimple: mockStreamSimple,
}));

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
        usage: {
          input: 10, output: 20, cacheRead: 0, cacheWrite: 0, totalTokens: 30,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
        },
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
    expect(result.text).toBe("WARN probe ok");
    expect(result.usage).not.toBeNull();
    expect(result.usage!.totalTokens).toBe(30);
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

  // ── Usage retention tests ──

  it("returns byte-identical text from textFromMessage", async () => {
    const { callModelWithAuth } = await import("../src/model.js");

    const modelRegistry = {
      find: vi.fn().mockReturnValue({ provider: "test", id: "model" }),
      getApiKeyAndHeaders: vi.fn().mockResolvedValue({ ok: true, apiKey: "key" }),
    };
    mockStreamSimple.mockReturnValue({
      result: vi.fn().mockResolvedValue({
        role: "assistant",
        content: [{ type: "text", text: "  Exact text with spaces  \n\n" }],
        usage: { input: 5, output: 10, cacheRead: 0, cacheWrite: 0, totalTokens: 15, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      }),
    } as any);

    const result = await callModelWithAuth("test", "model", "", "", modelRegistry as any);
    // textFromMessage trims, so "Exact text with spaces"
    expect(result.text).toBe("Exact text with spaces");
  });

  it("retains positive Usage when totalTokens > 0", async () => {
    const { callModelWithAuth } = await import("../src/model.js");

    const modelRegistry = {
      find: vi.fn().mockReturnValue({ provider: "test", id: "model" }),
      getApiKeyAndHeaders: vi.fn().mockResolvedValue({ ok: true, apiKey: "key" }),
    };
    mockStreamSimple.mockReturnValue({
      result: vi.fn().mockResolvedValue({
        role: "assistant",
        content: [{ type: "text", text: "OK" }],
        usage: {
          input: 100, output: 50, cacheRead: 10, cacheWrite: 5, totalTokens: 165,
          reasoning: 30,
          cost: { input: 0.5, output: 0.3, cacheRead: 0.01, cacheWrite: 0.02, total: 0.83 },
        },
      }),
    } as any);

    const result = await callModelWithAuth("test", "model", "", "", modelRegistry as any);
    expect(result.usage).not.toBeNull();
    expect(result.usage!.input).toBe(100);
    expect(result.usage!.output).toBe(50);
    expect(result.usage!.reasoning).toBe(30);
    expect(result.usage!.cost.total).toBe(0.83);
  });

  it("returns null usage when all-zero Usage (totalTokens === 0)", async () => {
    const { callModelWithAuth } = await import("../src/model.js");

    const modelRegistry = {
      find: vi.fn().mockReturnValue({ provider: "test", id: "model" }),
      getApiKeyAndHeaders: vi.fn().mockResolvedValue({ ok: true, apiKey: "key" }),
    };
    mockStreamSimple.mockReturnValue({
      result: vi.fn().mockResolvedValue({
        role: "assistant",
        content: [{ type: "text", text: "OK" }],
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      }),
    } as any);

    const result = await callModelWithAuth("test", "model", "", "", modelRegistry as any);
    expect(result.usage).toBeNull();
    expect(result.text).toBe("OK");
  });

  it("returns null usage when usage is absent", async () => {
    const { callModelWithAuth } = await import("../src/model.js");

    const modelRegistry = {
      find: vi.fn().mockReturnValue({ provider: "test", id: "model" }),
      getApiKeyAndHeaders: vi.fn().mockResolvedValue({ ok: true, apiKey: "key" }),
    };
    mockStreamSimple.mockReturnValue({
      result: vi.fn().mockResolvedValue({
        role: "assistant",
        content: [{ type: "text", text: "OK" }],
      }),
    } as any);

    const result = await callModelWithAuth("test", "model", "", "", modelRegistry as any);
    expect(result.usage).toBeNull();
    expect(result.text).toBe("OK");
  });
});