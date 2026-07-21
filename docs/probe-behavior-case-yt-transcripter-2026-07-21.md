# Case Study: yt-transcripter Sessions and Probe Reliability

**As-of:** 2026-07-21  
**Scope:** Two sessions in `/Users/cgint/dev/yt-transcripter` that processed entries from `inbox_queue.md`.  
**Related analysis:** [Probe Behavior Issues](probe-behavior-issues.md)

## Conclusion

The first session shows that consortium feedback can identify real execution defects, but is unsafe when it retains an obsolete diagnosis or invents context not present in the current session. The second session completes the same kind of task without recorded consortium deliberations, but still demonstrates that probes cannot substitute for the agent following local instructions and using the most direct known path.

This is a concrete instance of the broader failure modes described in the related analysis, with an additional requirement: a synthesized warning must be tied to an observable current condition and must expire when later evidence resolves that condition.

## Evidence

The original records are preserved verbatim in [`probe-behavior-references/`](probe-behavior-references/):

| Session | Role in this case | SHA-256 |
|---|---|---|
| [`2026-07-21T06-12-57-782Z_019f834e-5936-75b1-8949-402c80617aac.jsonl`](probe-behavior-references/2026-07-21T06-12-57-782Z_019f834e-5936-75b1-8949-402c80617aac.jsonl) | Consortium-enabled run; one video processed with several genuine and false/misplaced signals | `b97140cbb09d2de99c48a90d275cd01f904200ff9791828f1ba06035176306c7` |
| [`2026-07-21T06-26-49-793Z_019f835b-0b41-7658-8270-a9a579a643e4.jsonl`](probe-behavior-references/2026-07-21T06-26-49-793Z_019f835b-0b41-7658-8270-a9a579a643e4.jsonl) | Comparison run; same queue workflow, with no `pi-ai-consortium` deliberation records | `39cc1b91b1ec3a6c34a355247fdfa56b291c7951968c190c8f12705be75c47c2` |

The session records are evidence of what the agent and consortium saw; they do not independently prove that generated transcript content was accurate.

## Session 1: useful signals mixed with invalid or stale ones

The agent initially interpreted “new entry in inbox” as an intercom request rather than the local `inbox_queue.md`. After the user clarified the filename, it tried a repository-wide `find` in an unrelated repository and emitted malformed tool arguments. These were agent errors. The consortium's warning to search the current directory, and its later warning that the required `intent` and `rationale` fields were missing, were directionally useful.

The run then processed video `1lgFGaHoGq8` successfully from the correct `yt-transcripter` working directory. The process nonetheless exposed three probe-quality limitations:

1. **Diagnosis did not expire after resolution.** After a corrected `read` call succeeded, the next synthesis still surfaced a BLOCK saying that the missing tool fields were blocking progress. That condition was no longer true.
2. **The probe introduced an unrelated working-directory story.** After the queue edit, synthesis said the agent had to use the `pi-ai-consortium` session/path. The recorded session `cwd` is `/Users/cgint/dev/yt-transcripter`; no evidence supports the claimed path requirement.
3. **A valid workflow warning was not tracked through the following action.** When the pipeline completed, synthesis correctly noted that the queue entry had not been moved to DONE. The subsequent edit only added the title beneath the entry still in `INBOX`; it did not move the entry. The following synthesis switched to the incorrect path complaint rather than preserving or re-checking the unresolved queue-state defect. The agent then claimed “Processed and moved.”

The last point matters: the problem is not simply a false positive. A high-quality signal was emitted, but the system had no durable representation of the condition it named, no verification after the remediation attempt, and no way to distinguish a fixed defect from an unrelated new concern.

## Session 2: comparison, not a clean control

The second session contains no `pi-ai-consortium` custom events, so it cannot measure probe behavior directly. It is useful as a workflow comparison only.

The agent again started with an unnecessary search for `inbox_queue.md`, even though the file was in the project root and had just been used in the preceding session. It also made several unsuccessful direct API calls before reading `run_yt_transcript.py`, which already defined the supported pipeline. These are agent instruction-following and task-efficiency failures, not evidence against the consortium.

Once it read the script, the agent invoked the supported command, verified that transcript, fixed-transcript, summary, and metadata files existed, sampled the summary, and correctly moved video `8G_1-3IO4ZQ` from `INBOX` to `SUCCESSFULLY DONE` with its title. It skipped the queue's stated intermediate `PROCESSING` state, so this is successful final bookkeeping rather than strict workflow parity.

## Relationship to the broader issue document

This case supports the existing concerns about incomplete or misleading probe context, but sharpens them:

- **Timing:** a verdict may be valid at one event and invalid at the next. Evaluating only the latest transcript is insufficient if a synthesis repeats an earlier state without checking whether tool evidence resolved it.
- **Semantics:** a probe must ground claims about paths, mode, and task state in explicit session evidence. It should not infer a required repository merely because that repository is visible elsewhere in its context.
- **Synthesis:** selecting a single highest-severity message loses continuity. The system needs to retain the *condition* behind an alert and re-evaluate it after relevant actions, rather than treating each response as an isolated severity contest.

## Design implications to investigate

1. **Condition-based alerts:** represent a warning as a falsifiable predicate (for example, “video ID remains under `INBOX` after successful processing”), not merely prose. Re-check it after edits or tool results that could resolve it.
2. **Evidence-bound context:** label current `cwd`, latest tool action/result, and durable session flags separately from quoted or historical text. Probes should cite the field that supports a constraint claim.
3. **Synthesis lifecycle:** suppress resolved alerts; do not replace an unresolved, verified condition with an ungrounded higher-severity claim. If evidence is insufficient, emit no enforcement signal rather than a confident BLOCK.
4. **Agent responsibilities remain separate:** require local instructions (such as `AGENTS.md`) to be read before execution, and favor known project commands over improvised API exploration. Probe quality cannot reliably compensate for these omissions.

## Open questions

- Which exact fields and message ordering were supplied to each first-session probe? The saved session captures the visible deliberations, not the internal serialized prompt.
- Did the synthesis component retain previous probe outputs, or did each stale/misplaced signal arise from a fresh prompt? Implementation inspection is required.
- Should the queue's `PROCESSING` section be an enforced intermediate state, or is its omission accepted workflow practice?
