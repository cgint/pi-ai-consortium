import { beforeEach, describe, expect, it, vi } from "vitest";
import * as fs from "node:fs";
import * as path from "node:path";

const deliberate = vi.fn();
const loggerLog = vi.fn();
const buildUserContextFromMessages = vi.fn(() => "current agent context");

vi.mock("../src/core.js", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/core.js")>();
  return {
    ...actual,
    ConsortiumCore: class {
      deliberate = deliberate;
    },
  };
});
vi.mock("../src/config.js", () => ({
  DEFAULT_CONFIG: { probes: [], synthesis: {} },
  parseModelRef: () => undefined,
}));
vi.mock("../src/context.js", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/context.js")>();
  return {
    ...actual,
    buildUserContext: vi.fn(),
    buildUserContextFromMessages,
  };
});
vi.mock("../src/model.js", () => ({ callModelWithAuth: vi.fn() }));
vi.mock("../src/ui.js", () => ({
  ConsortiumLogger: class { log = loggerLog; },
  createProgressCallback: vi.fn(),
  formatVisibleMessage: vi.fn(() => "deliberation"),
}));

type ContextHandler = (event: { messages: unknown[] }, ctx: any) => Promise<{ messages: unknown[] } | undefined>;
type SessionStartHandler = (event: unknown, ctx: any) => Promise<void>;

let contextHandler: ContextHandler;
let sessionStartHandler: SessionStartHandler;

beforeEach(async () => {
  vi.resetModules();
  deliberate.mockReset();
  deliberate.mockResolvedValue({ synthesis: "Keep the answer concise.", probes: [], errors: [] });
  buildUserContextFromMessages.mockClear();
  loggerLog.mockClear();

  const handlers = new Map<string, Function>();
  const pi = {
    on: vi.fn((event: string, handler: Function) => handlers.set(event, handler)),
    appendEntry: vi.fn(),
    registerCommand: vi.fn(),
  };

  const { default: register } = await import("../index.ts");
  register(pi as any);
  contextHandler = handlers.get("context") as ContextHandler;
  sessionStartHandler = handlers.get("session_start") as SessionStartHandler;
});

describe("consortium context injection", () => {
  it("logs effective workspace guard governor input for structured text content", async () => {
    const workspaceBase = path.join(process.cwd(), ".parcour-runs");
    fs.mkdirSync(workspaceBase, { recursive: true });
    const tmpDir = fs.mkdtempSync(path.join(workspaceBase, "consortium-governor-"));
    try {
      fs.mkdirSync(path.join(tmpDir, ".pi"));
      fs.writeFileSync(
        path.join(tmpDir, ".pi", "settings.json"),
        JSON.stringify({ consortium: { stateSupersessionGuard: true } }),
      );
      const ctx = {
        cwd: tmpDir,
        sessionManager: { getSessionId: () => "test-session" },
        model: { provider: "test", id: "model" },
        modelRegistry: {},
        signal: new AbortController().signal,
        hasUI: false,
        ui: { setStatus: vi.fn(), notify: vi.fn() },
      };

      await sessionStartHandler({}, ctx);
      await contextHandler({
        messages: [{ role: "user", content: [{ type: "text", text: "structured input" }], timestamp: 1 }],
      }, ctx);

      const telemetry = loggerLog.mock.calls
        .map(([entry]) => entry)
        .find((entry) => entry.type === "governor_input");
      expect(telemetry).toMatchObject({
        state_supersession_guard: true,
        state_supersession_guard_source: "workspace_settings",
      });
      expect(telemetry.current_human_turn_length).toBeGreaterThan(0);
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

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
