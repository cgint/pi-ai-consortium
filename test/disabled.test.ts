// Tests for consortium enabled/disabled toggle via slash commands.
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

type ContextHandler = (
  event: { messages: unknown[] },
  ctx: any,
) => Promise<{ messages: unknown[] } | undefined>;

let contextHandler: ContextHandler;
let commands: Map<string, { description: string; handler: Function }> = new Map();

beforeEach(async () => {
  vi.resetModules();
  deliberate.mockReset();
  deliberate.mockResolvedValue({ synthesis: "Keep the answer concise.", probes: [], errors: [] });
  buildUserContextFromMessages.mockClear();
  commands = new Map();

  const handlers = new Map<string, Function>();
  const pi = {
    on: vi.fn((event: string, handler: Function) => handlers.set(event, handler)),
    appendEntry: vi.fn(),
    registerCommand: vi.fn((name: string, def: { description: string; handler: Function }) => {
      commands.set(name, def);
    }),
  };

  const { default: register } = await import("../index.ts");
  register(pi as any);
  contextHandler = handlers.get("context") as ContextHandler;
});

describe("consortium enabled/disabled toggle", () => {
  it("skips deliberation when disabled", async () => {
    const original = [
      { role: "user", content: "What files are here?", timestamp: 1 },
    ];
    const ctx = {
      cwd: process.cwd(),
      sessionManager: { getSessionId: () => "test-session" },
      model: { provider: "test", id: "model" },
      modelRegistry: {},
      signal: new AbortController().signal,
      hasUI: true,
      ui: { setStatus: vi.fn(), notify: vi.fn() },
    };

    // Disable consortium
    const offHandler = commands.get("ai-consortium-off")!.handler;
    await offHandler("", ctx);

    expect(ctx.ui.setStatus).toHaveBeenCalledWith("consortium", "consortium: disabled");

    // Context handler should return undefined (no modification)
    const result = await contextHandler({ messages: original }, ctx);

    expect(result).toBeUndefined();
    // Deliberation must NOT have been called
    expect(deliberate).not.toHaveBeenCalled();
    expect(ctx.ui.setStatus).toHaveBeenCalledWith("consortium", "consortium: disabled");
  });

  it("proceeds with deliberation when enabled", async () => {
    const original = [
      { role: "user", content: "What files are here?", timestamp: 1 },
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

    // Ensure enabled
    const onHandler = commands.get("ai-consortium-on")!.handler;
    await onHandler("", ctx);

    const result = await contextHandler({ messages: original }, ctx);

    expect(result).toBeDefined();
    expect(result?.messages).toHaveLength(2);
    expect(deliberate).toHaveBeenCalled();
  });

  it("provides status command", () => {
    const statusCmd = commands.get("ai-consortium");
    expect(statusCmd).toBeDefined();
    expect(statusCmd!.description).toMatch(/status/i);
  });

  it("provides enable command", () => {
    const onCmd = commands.get("ai-consortium-on");
    expect(onCmd).toBeDefined();
    expect(onCmd!.description).toMatch(/enable/i);
  });

  it("provides disable command", () => {
    const offCmd = commands.get("ai-consortium-off");
    expect(offCmd).toBeDefined();
    expect(offCmd!.description).toMatch(/disable/i);
  });
});
