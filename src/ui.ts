// TUI helpers — status bar progress, notification formatting, JSONL logging.

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import type { DeliberationResult, ExtractedContext, ProgressCallback } from "./types.js";
import { CANONICAL_PROBE_ORDER } from "./config.js";

/** Helper to format a string array for Markdown/TUI logs. */
function formatArrayText(items: string[] | undefined): string {
  if (!items || items.length === 0) return "[none]";
  return items.join("; ");
}

/** JSONL & sidecar Markdown logger for consortium actions. */
export class ConsortiumLogger {
  private logPath: string;
  private mdPath: string;
  private fd: number | null = null;
  private mdFd: number | null = null;
  private turnCount = 0;

  constructor(cwd: string, sessionId: string) {
    const dir = path.join(cwd, ".pi", "consortium");
    fs.mkdirSync(dir, { recursive: true });
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    const baseName = `${ts}_${sessionId}`;
    this.logPath = path.join(dir, `${baseName}.jsonl`);
    this.mdPath = path.join(dir, `${baseName}.md`);
  }

  private getFd(): number {
    if (this.fd === null) {
      this.fd = fs.openSync(this.logPath, "a");
    }
    return this.fd;
  }

  private getMdFd(): number {
    if (this.mdFd === null) {
      this.mdFd = fs.openSync(this.mdPath, "a");
      if (fs.statSync(this.mdPath).size === 0) {
        fs.writeSync(this.mdFd, "# Consortium Extracted Context Log\n\n");
      }
    }
    return this.mdFd;
  }

  log(entry: Record<string, unknown>): void {
    const line = JSON.stringify({ ts: new Date().toISOString(), ...entry }) + "\n";
    try {
      fs.writeSync(this.getFd(), line);
    } catch {
      // Non-fatal: log file write failures shouldn't break deliberation
    }
  }

  /** Write a clean human-readable Markdown section to the sidecar .md log file. */
  logExtraction(context: ExtractedContext): void {
    this.turnCount++;
    const ts = new Date().toISOString();
    const section = [
      `## Turn ${this.turnCount} (${ts})`,
      `* **User Requirements:** ${formatArrayText(context.userRequirements)}`,
      `* **Deliverables:** ${formatArrayText(context.deliverables)}`,
      `* **Revised / Superseded:** ${formatArrayText(context.revisedOrSupersededDirection)}`,
      `* **User Decisions:** ${formatArrayText(context.userDecisions)}`,
      `* **Questions & Info Gaps:** ${formatArrayText(context.questionsAndInformationGaps)}`,
      `* **Control Boundaries:** ${formatArrayText(context.controlBoundaries)}`,
      `* **Observed Work:** ${formatArrayText(context.observedWork)}`,
      `* **Observed Critical Facts:** ${formatArrayText(context.observedCriticalFacts)}`,
      `* **Relevant Learnings:** ${formatArrayText(context.relevantLearnings)}`,
      ``,
      `---`,
      ``,
    ].join("\n");

    try {
      fs.writeSync(this.getMdFd(), section);
    } catch {
      // Non-fatal
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
    if (this.mdFd !== null) {
      try {
        fs.closeSync(this.mdFd);
      } catch {
        /* ignore */
      }
      this.mdFd = null;
    }
  }
}

/** Build progress status text for the status bar. */
export function formatProgressText(phase: string, current: number, total: number, role?: string): string {
  switch (phase) {
    case "extraction":
      return "consortium: extracting goals, intent…";
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

/** Format a visible TUI notification — extracted 9 strategic vectors, skip info, probe details + synthesis. */
export function formatVisibleMessage(result: DeliberationResult): string {
  const lines: string[] = [];

  // Header
  if (result.skippedByGovernor) {
    lines.push(`◇ Consortium deliberation — skipped (${result.governorReason || "governor gate"})`);
  } else if (result.synthesis.trim().startsWith("NO_CONTRIBUTION")) {
    lines.push(`◇ Consortium deliberation — 0/${result.probes.length} probes contributed (nothing to add)`);
  } else {
    const contributions = result.probes.filter((p) => !p.text.trim().startsWith("NO_CONTRIBUTION")).length;
    lines.push(`◇ Consortium deliberation — ${contributions}/${result.probes.length} probes contributed`);
  }

  // Extracted 9 Strategic Context Vectors (Compact & High-Signal for TUI)
  if (result.extractedContext) {
    const ec = result.extractedContext;
    lines.push(`  Extracted Strategic Context:`);
    lines.push(`   • Requirements: ${formatArrayText(ec.userRequirements)}`);
    lines.push(`   • Deliverables: ${formatArrayText(ec.deliverables)}`);
    lines.push(`   • Revised/Superseded: ${formatArrayText(ec.revisedOrSupersededDirection)}`);
    lines.push(`   • Decisions: ${formatArrayText(ec.userDecisions)}`);
    lines.push(`   • Questions & Gaps: ${formatArrayText(ec.questionsAndInformationGaps)}`);
    lines.push(`   • Control Boundaries: ${formatArrayText(ec.controlBoundaries)}`);
    lines.push(`   • Observed Work: ${formatArrayText(ec.observedWork)}`);
    lines.push(`   • Critical Facts: ${formatArrayText(ec.observedCriticalFacts)}`);
    lines.push(`   • Relevant Learnings: ${formatArrayText(ec.relevantLearnings)}`);
  }

  // Probe outputs (only if probes ran)
  if (result.probes.length > 0) {
    lines.push(`  Probes:`);
    const probeMap = new Map(result.probes.map((p) => [p.role, p]));
    for (const role of CANONICAL_PROBE_ORDER) {
      const probe = probeMap.get(role);
      if (!probe) continue;
      if (probe.text.trim().startsWith("NO_CONTRIBUTION")) {
        lines.push(`   ${role}: NO_CONTRIBUTION`);
      } else {
        const text = probe.text.trim();
        const tagMatch = /^(INFO|WARN|BLOCK)\s+(.*)/.exec(text);
        if (tagMatch) {
          const [, tag, body] = tagMatch;
          lines.push(`   ${role} (${tag}): ${body}`);
        } else {
          lines.push(`   ${role}: ${text}`);
        }
      }
    }

    // Synthesis
    const synthPreview = result.synthesis.length > 200
      ? result.synthesis.slice(0, 200) + "…"
      : result.synthesis;
    lines.push(`  synthesis: ${synthPreview}`);
  }

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
