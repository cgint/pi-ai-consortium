#!/usr/bin/env python3
"""Extract probe evidence from .pi/consortium/ logs for plan evaluation."""
import json, os, glob
from collections import defaultdict

log_dir = ".pi/consortium/"
roles = ["architect", "clarifier", "contrarian", "navigator", "responder"]

tag_outputs_by_role = defaultdict(list)
responder_blocks = []
responder_warns = []
all_five_fire = []
current_delib = {"probes": [], "file": "?"}

for logfile in sorted(glob.glob(os.path.join(log_dir, "*.jsonl"))):
    with open(logfile) as f:
        for line in f:
            try:
                d = json.loads(line.strip())
            except:
                continue
            t = d.get("type")
            if t == "deliberation_start":
                current_delib = {"probes": [], "file": os.path.basename(logfile)}
            elif t == "probe_complete":
                mk = d.get("modelKey", "")
                output = d.get("output", "").strip()
                if not mk.startswith("probe:"):
                    continue
                idx = int(mk.split(":")[-1])
                role = roles[idx] if idx < len(roles) else f"probe:{idx}"
                current_delib["probes"].append({"role": role, "output": output})
                if output.startswith("TAG ") and not any(
                    output.startswith(p) for p in ["TAG INFO ", "TAG WARN ", "TAG BLOCK "]
                ):
                    tag_outputs_by_role[role].append(output[:200])
                if role == "responder":
                    if output.startswith("BLOCK "):
                        responder_blocks.append(output[:300])
                    elif output.startswith("WARN "):
                        responder_warns.append(output[:300])
            elif t in ("injection_complete", "injection_skipped", "synthesis_complete", "deliberation_failed"):
                if current_delib.get("probes"):
                    n_contrib = sum(1 for p in current_delib["probes"] if not p["output"].startswith("NO_CONTRIBUTION"))
                    if n_contrib == 5:
                        all_five_fire.append({
                            "file": current_delib.get("file", "?"),
                            "outputs": [(p["role"], p["output"][:150]) for p in current_delib["probes"]]
                        })
                current_delib = {"probes": [], "file": "?"}

out = "agent/probe_evidence.txt"
with open(out, "w") as f:
    f.write("=" * 80 + "\n")
    f.write("1. TAG PREFIX OUTPUTS BY ROLE (silently discarded)\n")
    f.write("=" * 80 + "\n")
    for role in roles:
        items = tag_outputs_by_role[role]
        f.write(f"\n{role.upper()}: {len(items)} outputs\n")
        for i, s in enumerate(items[:5]):
            f.write(f"  {i+1}. {s}\n")
        if len(items) > 5:
            f.write(f"  ... and {len(items)-5} more\n")
    f.write("\n" + "=" * 80 + "\n")
    f.write(f"2. RESPONDER BLOCK OUTPUTS ({len(responder_blocks)} total)\n")
    f.write("=" * 80 + "\n")
    for i, s in enumerate(responder_blocks):
        f.write(f"  {i+1}. {s}\n")
    f.write("\n" + "=" * 80 + "\n")
    f.write(f"3. RESPONDER WARN OUTPUTS ({len(responder_warns)} total)\n")
    f.write("=" * 80 + "\n")
    for i, s in enumerate(responder_warns[:10]):
        f.write(f"  {i+1}. {s}\n")
    if len(responder_warns) > 10:
        f.write(f"  ... and {len(responder_warns)-10} more\n")
    f.write("\n" + "=" * 80 + "\n")
    f.write(f"4. ALL-5-FIRE DELIBERATIONS ({len(all_five_fire)} total)\n")
    f.write("=" * 80 + "\n")
    for i, d in enumerate(all_five_fire[:5]):
        f.write(f"\n  Deliberation {i+1} ({d['file']}):\n")
        for role, txt in d["outputs"]:
            f.write(f"    {role}: {txt}\n")
    if len(all_five_fire) > 5:
        f.write(f"\n  ... and {len(all_five_fire)-5} more\n")

print(f"Written to {out}")