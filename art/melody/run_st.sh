#!/bin/bash
cd "$(dirname "$0")"
for p in "$@"; do
  ~/.venvs/comfy-mcp/bin/comfy --json run --workflow workflows/st_$p.json --host 127.0.0.1 --port 8188 --wait --timeout 1200 > gen/_st_$p.json 2>&1
  echo "$p: $(grep -o '"ok": [a-z]*' gen/_st_$p.json | head -1) $(grep -o '"elapsed_seconds": [0-9.]*' gen/_st_$p.json)"
done
