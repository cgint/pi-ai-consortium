#!/usr/bin/env bash
# Run one real, production-path Consortium extraction against a minimal prompt.
#
# Usage:
#   CONSORTIUM_MODEL=google/gemini-3.7-flash CONSORTIUM_REASONING=low ./scripts/manual-extraction-smoke.sh
#
# The script intentionally does not participate in `npm test`: it invokes the
# configured external model, incurs provider usage, and records its evidence in
# a fresh temporary directory that is printed on completion.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
model_ref="${CONSORTIUM_MODEL:-google/gemini-3.7-flash}"
reasoning_level="${CONSORTIUM_REASONING:-low}"
run_dir="$(mktemp -d "${TMPDIR:-/tmp}/pi-ai-consortium-extraction-smoke.XXXXXX")"
stdout_log="$run_dir/pi-output.log"

printf 'Manual extraction smoke test\n'
printf '  model: %s\n' "$model_ref"
printf '  reasoning: %s\n' "$reasoning_level"
printf '  prompt: hi\n'
printf '  evidence: %s\n\n' "$run_dir"

set +e
(
  cd "$run_dir"
  CONSORTIUM_MODEL="$model_ref" CONSORTIUM_REASONING="$reasoning_level" pi \
    --mode text \
    --print \
    --no-context-files \
    --no-skills \
    --no-prompt-templates \
    --no-extensions \
    --no-tools \
    --no-session \
    --extension "$repo_root/index.ts" \
    --model "$model_ref" \
    --thinking "$reasoning_level" \
    -- "hi"
) 2>&1 | tee "$stdout_log"
pi_status=${PIPESTATUS[0]}
set -e

if [[ $pi_status -ne 0 ]]; then
  printf '\nFAIL: Pi exited with status %d. Output: %s\n' "$pi_status" "$stdout_log" >&2
  exit "$pi_status"
fi

sidecar="$(find "$run_dir/.pi/consortium" -maxdepth 1 -type f -name '*.md' -print -quit 2>/dev/null || true)"
jsonl="$(find "$run_dir/.pi/consortium" -maxdepth 1 -type f -name '*.jsonl' -print -quit 2>/dev/null || true)"

if [[ -z $sidecar ]]; then
  printf '\nFAIL: Extraction did not produce a parsed-context sidecar.\n' >&2
  if [[ -n $jsonl ]]; then
    printf 'Raw extraction events:\n' >&2
    grep '"modelKey":"extraction"' "$jsonl" >&2 || true
  fi
  printf 'Evidence: %s\n' "$run_dir" >&2
  exit 1
fi

if [[ -z $jsonl ]]; then
  printf '\nFAIL: Extraction telemetry was not written; cannot verify retry count.\n' >&2
  printf 'Evidence: %s\n' "$run_dir" >&2
  exit 1
fi

extraction_attempts="$(grep -c '"type":"probe_start".*"modelKey":"extraction"' "$jsonl" || true)"
if [[ $extraction_attempts -ne 1 ]]; then
  printf '\nFAIL: Expected one structured extraction call, found %s.\n' "$extraction_attempts" >&2
  grep '"modelKey":"extraction"' "$jsonl" >&2 || true
  printf 'Evidence: %s\n' "$run_dir" >&2
  exit 1
fi

printf '\nPASS: AX parsed one real structured extraction response without a repair retry.\n'
printf 'Parsed context: %s\n' "$sidecar"
cat "$sidecar"
printf '\nRaw extraction event:\n'
grep '"modelKey":"extraction"' "$jsonl" || true
