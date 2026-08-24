import { describe, it, expect } from "vitest";

// Tests the unambiguous-prefix resolver for /ai-consortium-cadence.
// index.ts is the extension entry point; its default export registers commands
// against a provided ExtensionAPI, so importing it here is safe — we only use
// the exported pure helpers (CADENCE_MODES, resolveCadenceMode).

describe("resolveCadenceMode (unambiguous prefix resolution)", () => {
  it("resolves exact mode names", async () => {
    const { resolveCadenceMode } = await import("../index.js");
    expect(resolveCadenceMode("smart_extractor")).toEqual({ ok: true, mode: "smart_extractor" });
    expect(resolveCadenceMode("always")).toEqual({ ok: true, mode: "always" });
    expect(resolveCadenceMode("periodic")).toEqual({ ok: true, mode: "periodic" });
    expect(resolveCadenceMode("manual")).toEqual({ ok: true, mode: "manual" });
  });

  it("resolves single-character unambiguous prefixes (user request: p -> periodic)", async () => {
    const { resolveCadenceMode } = await import("../index.js");
    expect(resolveCadenceMode("p")).toEqual({ ok: true, mode: "periodic" });
    expect(resolveCadenceMode("a")).toEqual({ ok: true, mode: "always" });
    expect(resolveCadenceMode("s")).toEqual({ ok: true, mode: "smart_extractor" });
    expect(resolveCadenceMode("m")).toEqual({ ok: true, mode: "manual" });
  });

  it("resolves partial prefixes longer than one character", async () => {
    const { resolveCadenceMode } = await import("../index.js");
    expect(resolveCadenceMode("per")).toEqual({ ok: true, mode: "periodic" });
    expect(resolveCadenceMode("sm")).toEqual({ ok: true, mode: "smart_extractor" });
  });

  it("rejects input that matches no mode", async () => {
    const { resolveCadenceMode } = await import("../index.js");
    const r = resolveCadenceMode("x");
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.candidates).toEqual([]);
  });

  it("rejects empty input", async () => {
    const { resolveCadenceMode } = await import("../index.js");
    const r = resolveCadenceMode("");
    expect(r.ok).toBe(false);
  });

  it("rejects ambiguous prefixes when two modes share a start", async () => {
    const { resolveCadenceMode } = await import("../index.js");
    // Inject a deliberately colliding mode list to prove the ambiguous branch
    // works without adding a real mode to CADENCE_MODES.
    const r = resolveCadenceMode("a", ["always", "amazing"] as any);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.candidates).toEqual(["always", "amazing"]);
  });
});

describe("cadence mode naming invariant (future-proof guardrail)", () => {
  // INTENT: The unambiguous-prefix resolver only stays correct while every
  // cadence mode is uniquely addressable. If a future mode collides with an
  // existing one (same first character, or one name is a prefix of the other),
  // the prefix shortcut silently breaks and this test MUST fail, forcing the
  // resolver, handler, and usage string to be revisited before the collision
  // degrades the user experience.
  it("every cadence mode is uniquely addressable by first character, and no mode is a prefix of another", async () => {
    const { CADENCE_MODES, resolveCadenceMode } = await import("../index.js");

    const firsts = CADENCE_MODES.map((m: string) => m[0]);
    const uniqueFirsts = new Set(firsts);
    expect(uniqueFirsts.size, `first-letter collision among ${CADENCE_MODES.join(", ")}`).toBe(CADENCE_MODES.length);

    for (const a of CADENCE_MODES) {
      for (const b of CADENCE_MODES) {
        if (a === b) continue;
        expect(b.startsWith(a), `"${a}" must not be a prefix of "${b}"`).toBe(false);
      }
    }

    // The resolver itself must be unambiguous on every full mode name.
    for (const m of CADENCE_MODES) {
      expect(resolveCadenceMode(m)).toEqual({ ok: true, mode: m });
    }
  });
});
