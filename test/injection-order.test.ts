import { beforeEach, describe, expect, it, vi } from "vitest";

const deliberate = vi.fn();
const buildUserContextFromMessages = vi.fn(() => "current agent context");

vi.mock("../src/core.js", () => ({
  ConsortiumCore: class {
    deliberate = deliberate;
  },
}));
vi.mock("../src/config.js", () => ({
  DEFAULT_CONFIG: { probes: [], synthesis: {} },
}));
vi.mock("../src/context.js", () => ({
  buildUserContext: vi.fn(),
  buildUserContextFromMessages,
}));
vi.mock("../src/model.js", () => ({ callModelWithAuth: vi.fn() }));
vi.mock("../src/ui.js", () => ({
  ConsortiumLogger: class { log = vi.fn(); },
  createProgressCallback: vi.fn(),
  formatVisibleMessage: vi.fn(() => "deliberation"),
}));

type ContextHandler = (event: { messages: unknown[] }, ctx: any) => Promise<{ messages: unknown[] } | undefined>;

let contextHandler: ContextHandler;

beforeEach(async () => {
  vi.resetModules();
  deliberate.mockReset();
  deliberate.mockResolvedValue({ synthesis: "Keep the answer concise.", probes: [], errors: [] });
  buildUserContextFromMessages.mockClear();

  const handlers = new Map<string, Function>();
  const pi = {
    on: vi.fn((event: string, handler: Function) => handlers.set(event, handler)),
    appendEntry: vi.fn(),
    registerCommand: vi.fn(),
  };

  const { default: register } = await import("../index.ts");
  register(pi as any);
  contextHandler = handlers.get("context") as ContextHandler;
});

describe("consortium context injection", () => {
  it("appends the synthetic deliberation after existing messages to preserve their prefix", async () => {
    const original = [
      { role: "user", content: "Investigate cache behavior.", timestamp: 1 },
      { role: "assistant", content: "I will inspect the code.", timestamp: 2 },
    ];
    const ctx = {
      cwd: process.cwd(),
      sessionManager: { getSessionId: () => "test-session" },
      model: { provider: "test", id: "model" },
      modelRegistry: {},
      signal: new AbortController().signal,
      hasUI: false,
      ui: { setStatus: vi.fn(), notify: vi.fn() },
    };

    const result = await contextHandler({ messages: original }, ctx);

    expect(result?.messages).toHaveLength(3);
    expect(result?.messages?.slice(0, 2)).toEqual(original);
    expect(result?.messages?.[2]).toMatchObject({
      role: "user",
      content: "[CONSORTIUM DELIBERATION]\n\nKeep the answer concise.",
    });
  });
});
