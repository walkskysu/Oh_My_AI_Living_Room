#!/bin/bash
# Pose edits used: bored_11 (yawn + stretch), working_33 (writing music in a notebook), done_11 (wave).
# Prompts are in the workflows' node 459 (built with make_edit.py from omalr_melody_white.png).
cd "$(dirname "$0")"
for p in "$@"; do
  ~/.venvs/comfy-mcp/bin/comfy --json run --workflow workflows/edit_$p.json --host 127.0.0.1 --port 8188 --wait --timeout 1200 > gen/_run_$p.json 2>&1
  echo "$p done: $(tail -c 300 gen/_run_$p.json)"
done
