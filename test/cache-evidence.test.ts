import { describe, expect, it } from "vitest";
import { fingerprintCacheRequest } from "../src/cache-evidence.js";

const history = "<historical_observed_past>\n[USER] secret-direction\n</historical_observed_past>";

describe("fingerprintCacheRequest", () => {
  it("matches cacheable prefixes when only the tail differs", () => {
    const c1 = fingerprintCacheRequest("shared system", `${history}\n\nC1 tail`, { tools: [] });
    const c3 = fingerprintCacheRequest("shared system", `${history}\n\nC3 role lens`, { tools: [] });

    expect(c1.historyComplete).toBe(true);
    expect(c3.historyComplete).toBe(true);
    expect(c1.prefixSha256).toBe(c3.prefixSha256);
    expect(c1.prefixBytes).toBe(c3.prefixBytes);
    expect(c1.requestSha256).not.toBe(c3.requestSha256);
  });

  it("treats system and tool declarations as part of the cacheable prefix", () => {
    const baseline = fingerprintCacheRequest("shared system", `${history}\n\nC1 tail`, { tools: [] });
    const differentSystem = fingerprintCacheRequest("different system", `${history}\n\nC3 tail`, { tools: [] });
    const differentTools = fingerprintCacheRequest("shared system", `${history}\n\nC3 tail`, {
      tools: [{ name: "__axOutput", description: "structured", parameters: { type: "object" } }],
    });

    expect(baseline.prefixSha256).not.toBe(differentSystem.prefixSha256);
    expect(baseline.prefixSha256).not.toBe(differentTools.prefixSha256);
  });

  it("does not claim a shared-history prefix when the required history boundary is absent", () => {
    const fingerprint = fingerprintCacheRequest("system", "unframed user input");

    expect(fingerprint).toMatchObject({ historyComplete: false });
    expect(fingerprint.prefixSha256).toBeUndefined();
    expect(fingerprint.prefixBytes).toBeUndefined();
  });

  it("does not retain prompt content in the emitted evidence", () => {
    const fingerprint = fingerprintCacheRequest("system-secret", `${history}\n\ntail-secret`);
    const serialized = JSON.stringify(fingerprint);

    expect(serialized).not.toContain("secret");
    expect(serialized).toMatch(/[a-f0-9]{64}/);
  });
});
