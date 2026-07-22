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

  it("creates sidecar .md log file alongside .jsonl and appends readable context vectors", () => {
    const logger = new ConsortiumLogger(tmpDir, "session-123");

    const sampleContext: ExtractedContext = {
      userIntentAndMotive: "Integrate JaneCarl UI components into newdesign pages.",
      activeConstraintsAndGuards: "Maintain Bootstrap 5 JS modal compatibility.",
      verifiedFactsInventory: "Directory listing verified; tasks 1.1-1.3 complete.",
      evidenceFreshnessDelta: "Read janecarl-page.js offset 1850.",
      clarityAndAmbiguityScore: "AMBIGUOUS",
      missingDetails: "User has not specified which route to map.",
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
    expect(mdContent).toContain("* **Intent & Motive:** Integrate JaneCarl UI components into newdesign pages.");
    expect(mdContent).toContain("* **Active Constraints & Guards:** Maintain Bootstrap 5 JS modal compatibility.");
    expect(mdContent).toContain("* **Verified Facts Inventory:** Directory listing verified; tasks 1.1-1.3 complete.");
    expect(mdContent).toContain("* **Evidence Freshness Delta:** Read janecarl-page.js offset 1850.");
    expect(mdContent).toContain("* **Clarity Score:** `AMBIGUOUS`");
    expect(mdContent).toContain("- **Missing Details:** User has not specified which route to map.");
  });
});
