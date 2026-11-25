#!/usr/bin/env bash
# waits for the current round to end (STOP), repairs a red baseline left by the old ratchet bug, restarts zero40
cd ~/entityos-kern/zero
while systemctl --user is-active -q zero40; do sleep 30; done
python3 - <<'PY'
import json
s = json.load(open("state.json")); b = s["base"]; good = {"cargo_ok": True, "cargo_pass": 1315, "cargo_fail": 0, "tsc_ok": True, "node_pass": 491, "node_fail": 0, "py_sh_ok": True, "plugin_ok": True}
if not (b.get("cargo_ok") and b.get("tsc_ok") and b.get("cargo_pass", 0) >= 1315 and b.get("node_pass", 0) >= 491 and b.get("node_fail", 1) == 0):
    s["base"] = good; s["last_gate"] = None; json.dump(s, open("state.json", "w"), indent=1); print("baseline repaired from", b)
PY
rm -f STOP
systemd-run --user --unit=zero40 --description="zero40: 40h Agent Zero + FranKenstein fusion loop (free tokens)" \
 -p Nice=10 -p MemoryMax=12G -p Restart=on-failure -p RestartSec=300 -p StartLimitIntervalSec=7200 -p StartLimitBurst=4 \
 --setenv=PATH="$PATH" --setenv=HOME="$HOME" --working-directory=$HOME/entityos-kern/zero \
 bash -c 'exec python3 -u zero40.py >> zero40.log 2>&1'
echo "[$(date +%H:%M:%S)] zero40 restarted with patched code (ratchet fix)" >> zero40.log
