// Tests for ConsortiumLogger sidecar Markdown file generation.

import { describe, expect, it, beforeEach, afterEach } from "vitest";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { ConsortiumLogger } from "../src/ui.js";
import type { ExtractedContext } from "../src/types.js";

describe("ConsortiumLogger sidecar Markdown logging", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "consortium-test-"));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it("creates sidecar .md log file alongside .jsonl and appends readable 9-slot strategic context", () => {
    const logger = new ConsortiumLogger(tmpDir, "session-123");

    const sampleContext: ExtractedContext = {
      userRequirements: ["Integrate JaneCarl UI components into newdesign pages."],
      deliverables: ["Updated routes.py"],
      revisedOrSupersededDirection: ["Filter low-level edit errors"],
      userDecisions: ["Maintain Bootstrap 5 JS modal compatibility."],
      questionsAndInformationGaps: ["Clarify target route mapping"],
      controlBoundaries: ["Allowed paths: dev-external/pi-ai-consortium"],
      observedWork: ["Directory listing verified; tasks 1.1-1.3 complete."],
      observedCriticalFacts: ["Read janecarl-page.js offset 1850."],
      relevantLearnings: ["Operational mechanics pollute context"],
    };

    logger.logExtraction(sampleContext);
    logger.close();

    const logDir = path.join(tmpDir, ".pi", "consortium");
    const files = fs.readdirSync(logDir);

    const mdFile = files.find((f) => f.endsWith("_session-123.md"));
    expect(mdFile).toBeDefined();

    const mdContent = fs.readFileSync(path.join(logDir, mdFile!), "utf-8");
    expect(mdContent).toContain("# Consortium Extracted Context Log");
    expect(mdContent).toContain("## Turn 1");
    expect(mdContent).toContain("* **User Requirements:** Integrate JaneCarl UI components into newdesign pages.");
    expect(mdContent).toContain("* **Deliverables:** Updated routes.py");
    expect(mdContent).toContain("* **Revised / Superseded:** Filter low-level edit errors");
    expect(mdContent).toContain("* **User Decisions:** Maintain Bootstrap 5 JS modal compatibility.");
    expect(mdContent).toContain("* **Questions & Info Gaps:** Clarify target route mapping");
    expect(mdContent).toContain("* **Control Boundaries:** Allowed paths: dev-external/pi-ai-consortium");
    expect(mdContent).toContain("* **Observed Work:** Directory listing verified; tasks 1.1-1.3 complete.");
    expect(mdContent).toContain("* **Observed Critical Facts:** Read janecarl-page.js offset 1850.");
    expect(mdContent).toContain("* **Relevant Learnings:** Operational mechanics pollute context");
  });
});
