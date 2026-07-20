// TUI helpers — status bar progress, notification formatting, JSONL logging.

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import type { DeliberationResult, ProgressCallback } from "./types.js";
import { CANONICAL_PROBE_ORDER } from "./config.js";

/** JSONL logger for consortium actions. */
export class ConsortiumLogger {
  private logPath: string;
  private fd: number | null = null;

  constructor(cwd: string, sessionId: string) {
    const dir = path.join(cwd, ".pi", "consortium");
    fs.mkdirSync(dir, { recursive: true });
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    this.logPath = path.join(dir, `${ts}_${sessionId}.jsonl`);
  }

  private getFd(): number {
    if (this.fd === null) {
      this.fd = fs.openSync(this.logPath, "a");
    }
    return this.fd;
  }

  log(entry: Record<string, unknown>): void {
    const line = JSON.stringify({ ts: new Date().toISOString(), ...entry }) + "\n";
    try {
      fs.writeSync(this.getFd(), line);
    } catch {
      // Non-fatal: log file write failures shouldn't break deliberation
    }
  }

  close(): void {
    if (this.fd !== null) {
      try {
        fs.closeSync(this.fd);
      } catch {
        /* ignore */
      }
      this.fd = null;
    }
  }
}

/** Build progress status text for the status bar. */
export function formatProgressText(phase: string, current: number, total: number, role?: string): string {
  switch (phase) {
    case "probe":
      return role
        ? `consortium: ${current}/${total} ${role}…`
        : `consortium: ${current}/${total} probing…`;
    case "synthesis":
      return "consortium: synthesizing…";
    case "complete":
      return "consortium: ✓ complete";
    default:
      return `consortium: ${phase}`;
  }
}

/** Format a visible TUI notification — probe details + synthesis. */
export function formatVisibleMessage(result: DeliberationResult): string {
  const lines: string[] = [];

  // Header
  const contributions = result.probes.filter((p) => !p.text.trim().startsWith("NO_CONTRIBUTION")).length;
  lines.push(`◇ Consortium deliberation — ${contributions}/${result.probes.length} probes contributed`);

  // Probe outputs in canonical (alphabetical) order
  const probeMap = new Map(result.probes.map((p) => [p.role, p]));
  for (const role of CANONICAL_PROBE_ORDER) {
    const probe = probeMap.get(role);
    if (!probe) continue;
    if (probe.text.trim().startsWith("NO_CONTRIBUTION")) {
      lines.push(`  ${role}: NO_CONTRIBUTION`);
    } else {
      const text = probe.text.trim();
      const tagMatch = /^(INFO|WARN|BLOCK)\s+(.*)/.exec(text);
      if (tagMatch) {
        const [, tag, body] = tagMatch;
        lines.push(`  ${role} (${tag}): ${body}`);
      } else {
        lines.push(`  ${role}: ${text}`);
      }
    }
  }

  // Synthesis
  const synthPreview = result.synthesis.length > 200
    ? result.synthesis.slice(0, 200) + "…"
    : result.synthesis;
  lines.push(`  synthesis: ${synthPreview}`);

  // Errors
  if (result.errors?.length) {
    lines.push(`  errors: ${result.errors.length}`);
  }

  return lines.join("\n");
}

/** Create a progress callback wired to ctx.ui.setStatus. */
export function createProgressCallback(ctx: ExtensionContext): ProgressCallback {
  return (phase, current, total, role) => {
    if (ctx.hasUI) {
      ctx.ui.setStatus("consortium", formatProgressText(phase, current, total, role));
    }
  };
}