# Plan: Surface Undefined Model Behaviours & Add Retry

**Status:** Implemented — all tests green (470/470)
**Date:** 2026-08-25
**Session:** doc-rocker-elixir, model `google/gemini-3.7-flash`
**Implementation complete:** 2026-08-25

---

## Problem

When a consortium model call fails at the provider level (e.g.
`gemini-3.7-flash` returns an empty response with `stopReason: "error"`),
the failure is **silently swallowed** and surfaces as:

```
◇ Consortium deliberation — 0/5 probes contributed (nothing to add)
Probes:
    architect: NO_CONTRIBUTION
    ...
```

And the extracted context block shows generic garbage:

```
Extracted Strategic Context:
 • Requirements: General task execution
 • Observed Work: Session initialized
 • ...
```

Both are indistinguishable from healthy "nothing to contribute" /
"nothing to extract" results. The root cause chain:

1. `pi-ai`'s `eventStream.result()` **resolves** (does not reject) on
   error events. The returned `AssistantMessage` carries
   `stopReason: "error"` and `errorMessage`, but `callModelWithAuth`
   never inspects these fields.
2. `textFromMessage` extracts `""` from the empty content array.
3. `validateProbeOutput("")` falls through to `return "NO_CONTRIBUTION"`.
4. Extraction: `JSON.parse("")` → caught → `getDefaultExtractedContext()`.
5. Panel shows "0/5 probes contributed (nothing to add)" + generic
   context. No `probe_error` logged. No `⚠` status.

**Evidence:** Log file `2026-08-24T07-47-33-603Z_01a032bd-…jsonl`
shows all 45 model calls (5 extraction + 25 probes + 5 synthesis)
returned `output_length: 0`, `usage_reported: false`,
duration 280–550 ms. Zero `probe_error` events.

---

## Design Principle

**No silent fallbacks.** Undefined model behaviour must be loud.

The one allowed "default" path: extraction failed → skip probes
(don't run them with garbage input). Everything else surfaces as an
error in the panel, JSONL, and `DeliberationResult.errors`.

---

## Defined vs Undefined Behaviour

**Defined** (accepted response types — `validateProbeOutput` in
`src/core.ts`):

- `NO_CONTRIBUTION` (possibly with trailing text)
- `INFO <content>`, `WARN <content>`, `BLOCK <content>`
- `TAG <severity> <content>` (leading `TAG ` is stripped)

**Undefined** (everything else — currently silently coerced to
`NO_CONTRIBUTION` or default context):

- Empty string (`""`)
- Thinking-only content (no `type: "text"` parts)
- Provider error (`stopReason: "error"`, `errorMessage` set)
- Aborted call (`stopReason: "aborted"`)
- Any non-matching free text

**Goal:** Undefined behaviour must produce a visible error in the
panel, the JSONL log, and `DeliberationResult.errors` — not a fake
`NO_CONTRIBUTION` or a generic default context.

---

## Changes

### 1. `src/model.ts` — `callModelWithAuth`: throw on undefined behaviour + one retry

```ts
export async function callModelWithAuth(
  provider: string,
  modelId: string,
  systemPrompt: string,
  userPrompt: string,
  modelRegistry: ModelRegistry,
  signal?: AbortSignal,
  retries = 1,                          // ← new param, default 1
): Promise<CallModelResult> {
  // ...existing find/auth/setup...
  const context: Context = { /* ...unchanged... */ };

  let lastError: Error | undefined;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const eventStream = streamSimple(model as any, context, {
        apiKey,
        headers: auth.headers,
        signal,
      } as any);
      const result = await eventStream.result();

      // Loud boundary 1: provider said the call errored or was aborted.
      // pi-ai's result() RESOLVES (does not reject) on error events,
      // so this is the only place we can catch it.
      if (result.stopReason === "error" || result.stopReason === "aborted") {
        throw new Error(
          result.errorMessage ?? `Model call stopped: ${result.stopReason}`
        );
      }

      const text = textFromMessage(result);

      // Loud boundary 2: no text content at all — provider anomaly
      // (e.g. thinking-only response, safety-filtered with no content).
      if (text.length === 0) {
        throw new Error(
          `Empty response from ${provider}/${modelId} ` +
          `(stopReason=${result.stopReason}, totalTokens=${result.usage?.totalTokens ?? 0})`
        );
      }

      return {
        text,
        usage: result.usage?.totalTokens > 0 ? result.usage : null,
      };
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt >= retries || signal?.aborted) throw lastError;
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  throw lastError; // unreachable — loop always returns or throws
}
```

Key points:
- `streamSimple(...)` is **re-invoked per attempt** (not re-reading
  the same settled stream).
- `stopReason` check catches provider rejections (the actual
  gemini-3.7 case).
- Empty-text check catches thinking-only or future provider
  behaviours where `stopReason: "stop"` but no text parts.
- One retry with 500ms backoff for transient failures. In a
  user-session context, this is cheap and bounded.

### 2. `src/core.ts` — extraction failure: skip probes, don't run with garbage

Current code (lines ~113–121):

```ts
} catch (err) {
  const msg = err instanceof Error ? err.message : String(err);
  errors.push(`Extraction: ${msg}`);
  extractedContext = getDefaultExtractedContext(input);
}
userContext = buildProbeInputXml(input, extractedContext);
```

Revised:

```ts
} catch (err) {
  const msg = err instanceof Error ? err.message : String(err);
  errors.push(`Extraction: ${msg}`);
  // Extraction failed — probes would get no meaningful input.
  // Skip them; the panel will show the extraction error.
  onProgress?.("complete", 0, 0);
  return {
    probes: [],
    synthesis: "NO_CONTRIBUTION",
    extractedContext: undefined,
    governorReason: governorDecision.reason,
    errors,
  };
}
```

This is the **only** allowed "default" path: extraction-failed →
skip probes. No `getDefaultExtractedContext()` as an error fallback.

### 3. `src/extraction.ts` — `getDefaultExtractedContext` retained only for empty-history

The function stays, but is now only called when `messages.length === 0`
(the legitimate "no history yet" case at line 85). It is **removed**
from the `catch` block at line 121–122, which now throws up to
`core.ts`'s catch instead:

```ts
// Before (line 121-122):
} catch {
  return getDefaultExtractedContext(messages);
}

// After: remove the catch entirely — let JSON.parse throw,
// which propagates to core.ts's catch.
// The messages.length === 0 early return (line 85) is unchanged.
```

Actually, the `JSON.parse` is inside the try block. The catch at
line 121 catches both `callModel` errors AND `JSON.parse` errors.
With the `model.ts` fix, `callModel` now throws on empty/error
responses, so the catch would catch that. But we want `core.ts` to
handle it, not `extraction.ts`. So:

```ts
// Remove the outer catch entirely.
// JSON.parse errors will propagate to core.ts's catch.
// callModel errors will also propagate to core.ts's catch.
// The messages.length === 0 early return stays.
```

The `extractContextFromMessages` function will no longer have a
`try/catch` wrapping the entire body. The `callModel` call and
`JSON.parse` can both throw; the caller (`core.ts`) handles it.

### 4. `src/ui.ts` — `formatVisibleMessage`: distinguish errors from declines

Add extraction-failure awareness and probe-error display:

```ts
export function formatVisibleMessage(result: DeliberationResult): string {
  const lines: string[] = [];

  if (result.skippedByGovernor) {
    return `Consortium deliberation skipped (${result.governorReason ?? "governor"})`;
  }

  const extractionError = result.errors?.find((e) => e.startsWith("Extraction:"));
  const probeFailed = result.probes.filter((p) => p.text.startsWith("[error:")).length;
  const contributed = result.probes.filter(
    (p) => !p.text.startsWith("NO_CONTRIBUTION") && !p.text.startsWith("[error:"),
  ).length;

  if (extractionError && result.probes.length === 0) {
    // Extraction failed, probes skipped
    lines.push(`⚠ Consortium deliberation — extraction failed, probes skipped`);
    lines.push(`  ${extractionError.replace("Extraction: ", "").slice(0, 120)}`);
    return lines.join("\n");
  }

  if (probeFailed > 0 && contributed === 0) {
    lines.push(`⚠ Consortium deliberation — ${probeFailed}/${result.probes.length} probes FAILED`);
    for (const probe of result.probes) {
      if (probe.text.startsWith("[error:"))
        lines.push(`   ${probe.role}: ERROR — ${probe.text.slice(8, 88)}`);
      else
        lines.push(`   ${probe.role}: NO_CONTRIBUTION`);
    }
    return lines.join("\n");
  }

  if (result.synthesis.trim().startsWith("NO_CONTRIBUTION")) {
    const suffix = probeFailed > 0 ? ` (${probeFailed} failed)` : "";
    lines.push(`◇ Consortium deliberation — 0/${result.probes.length} probes contributed (nothing to add${suffix})`);
    // ...existing probe listing, with [error:] shown as ERROR
    return lines.join("\n");
  }

  // ...existing "contributed > 0" path, with probeFailed count appended
}
```

### 5. No changes to

- **`validateProbeOutput`** — still coerces malformed non-empty text to
  `NO_CONTRIBUTION`. Correct: the model *did* respond with text, it just
  didn't follow the format. That's a defined-but-invalid format, not an
  undefined response.
- **`ProbeResult` type** — the existing `text: string` field already
  carries `[error: msg]` when a probe throws. No new field needed.
- **`index.ts` callModel closure** — already catches, logs `probe_error`,
  and re-throws. No changes.
- **`ConsortiumCore.runProbes*`** — already converts throws to
  `[error: msg]` in `ProbeResult.text` and pushes to `errors[]`. No changes.

---

## Tests (write first, TDD)

In `test/model.test.ts`:

1. **`callModelWithAuth` throws on `stopReason: "error"`**
   - Mock `streamSimple` → `result()` resolves with
     `{ stopReason: "error", errorMessage: "provider rejected", content: [] }`
   - Assert: throws with message containing "provider rejected"

2. **`callModelWithAuth` throws on empty content + `stopReason: "stop"`**
   - Mock: `{ stopReason: "stop", content: [], usage: all-zeros }`
   - Assert: throws with "Empty response"

3. **`callModelWithAuth` succeeds on valid response**
   - Mock: `{ stopReason: "stop", content: [{type:"text", text:"NO_CONTRIBUTION"}], usage: {totalTokens: 42} }`
   - Assert: returns `{ text: "NO_CONTRIBUTION", usage: {…} }`

4. **`callModelWithAuth` retries on transient failure**
   - Mock: first call → `{ stopReason: "error" }`, second call → valid
   - Assert: returns valid result, no exception. Assert `streamSimple`
     called exactly twice.

5. **`callModelWithAuth` exhausts retries and throws**
   - Mock: both calls → `{ stopReason: "error" }`
   - Assert: throws. Assert `streamSimple` called exactly twice.

6. **`callModelWithAuth` respects abort signal during retry**
   - Mock: first call → error, signal aborted before retry
   - Assert: throws immediately, `streamSimple` called once.

In `test/core.test.ts`:

7. **Extraction failure → probes skipped**
   - Mock `callModel` to throw on "extraction" modelKey
   - Assert: result has `probes: []`, `errors` contains extraction error,
     `synthesis: "NO_CONTRIBUTION"`

8. **Extraction success + all probes fail → probes show errors**
   - Mock: extraction succeeds, all 5 probes throw
   - Assert: result has `probes` with `[error:` in text, `errors` populated

In `test/ui.test.ts` (or existing ui test file):

9. **`formatVisibleMessage` with extraction failure + no probes**
   - Input: `errors: ["Extraction: provider rejected"], probes: []`
   - Assert: contains "extraction failed, probes skipped"

10. **`formatVisibleMessage` with all probes failed**
    - Input: `probes: [{role:"architect", text:"[error: provider rejected]"}, …]`
    - Assert: contains "5/5 probes FAILED", not "0/5 contributed"

11. **`formatVisibleMessage` with mixed probes**
    - Input: 2 `[error:]`, 3 `NO_CONTRIBUTION`
    - Assert: shows both counts, errors listed with truncated message

---

## Out of scope (for now)

- **Corrective re-prompt retry** (re-send with "your output violated
  the required format" appended). The one-retry above is for transient
  provider failures. A corrective retry is a different feature that
  requires prompt-level changes.
- **`validateProbeOutput` hardening** for non-empty malformed text.
  Separate concern; current behaviour (coerce to `NO_CONTRIBUTION`) is
  acceptable for "model responded but got format wrong".
- **Extraction failure in JSONL telemetry.** The `probe_error` event
  covers probes. Extraction errors could get a `extraction_error` event
  type — small follow-up.

---

## Verification

- `npm run typecheck`
- `npm run test` (new + existing tests green)
- `./precommit.sh` (typecheck + test + audit)


---

## Implementation Findings (2026-08-25)

### Bugs found during implementation

1. **`[error: msg]` trailing bracket**: `probe.text.slice(8, 88)` on `"[error: msg]"` produces
   `"msg]"` — the closing bracket was included. Fixed with
   `.replace(/\]$/, "")` in `ui.ts`.

2. **Test mock accumulation**: `mockStreamSimple` is a module-level `vi.fn()` that accumulates
   calls across tests. Added `beforeEach(() => mockStreamSimple.mockReset())` to
   `test/model.test.ts`.

3. **`core.ts` syntax error**: The rewrite dropped the `)` in
   `for (const [i, probe] of this.config.probes.entries())`. Caught by typecheck.

### Design decisions confirmed

- **No `ProbeResult.error` field**: The existing `[error: msg]` in `ProbeResult.text`
  plus `DeliberationResult.errors[]` is sufficient. The UI checks `text.startsWith("[error:")`.
- **`validateProbeOutput` unchanged**: Still coerces malformed non-empty text to
  `NO_CONTRIBUTION`. This is correct — the model *responded*, just not in the expected
  format. The loud boundary in `model.ts` ensures it only ever sees real model text.
- **`getDefaultExtractedContext` retained only for empty-history** (`messages.length === 0`).
  Removed from the error path in both `extraction.ts` (catch block deleted) and `core.ts`
  (extraction catch now returns early with `extractedContext: undefined`).
- **Retry is 1 attempt with 500ms backoff**: Bounded, cheap, sufficient for transient
  provider failures. No corrective re-prompt (out of scope).

### Files changed

| File | Change |
|---|---|
| `src/model.ts` | Added `stopReason` check, empty-text check, retry loop with backoff |
| `src/core.ts` | Extraction catch now returns early (skip probes), removed `getDefaultExtractedContext` import |
| `src/extraction.ts` | Removed silent `try/catch` that returned `getDefaultExtractedContext` on error |
| `src/ui.ts` | `formatVisibleMessage` now shows extraction-failure header, `ERROR —` for failed probes, `(N failed)` suffix |
| `test/model.test.ts` | Added 6 new tests (stopReason error/aborted, empty content, thinking-only, retry success/exhaustion/abort) |
| `test/core.test.ts` | Added extraction-failure-skips-probes test |
| `test/extraction.test.ts` | Replaced silent-fallback test with throw-expectation tests |
| `test/ui.test.ts` | New file: 6 tests for `formatVisibleMessage` error states |

### Verification

- `npx tsc --noEmit` — clean
- `npx vitest run` — 470/470 pass
- `./precommit.sh` — typecheck + test + audit all green
