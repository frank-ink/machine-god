#!/usr/bin/env bash
# Waits for daten_gen.py, rebuilds lm_data_mg, then ONE RunPod run (Gabriel "ja" 2026-11-24, cap 2 USD via podspec + vault).
L=~/entityos-kern/omega/pod.log; P=~/needle-mouth/mund_v05_work/project; N=~/needle-mouth/needle-compiler
log(){ echo "[$(date +%F' '%H:%M)] $*" >> $L; }
while pgrep -f "[d]aten_gen" >/dev/null; do sleep 120; done
log "daten fertig: $(wc -l < ~/entityos-kern/omega/daten/ok.jsonl) dialoge"
cat ~/entityos-kern/omega/daten/ok_tools.jsonl >> ~/entityos-kern/omega/daten/ok.jsonl 2>/dev/null; python3 $P/pod/build_mg_data.py >> $L 2>&1 || { log "build_mg_data FAILED"; exit 1; }
[ -f ~/entityos-kern/omega/POD_DONE ] && { log "schon gelaufen, kein zweiter Pod"; exit 0; }
touch ~/entityos-kern/omega/POD_DONE
cd $N && python3 orch.py keygen >> $L 2>&1
NC_CLOUD=SECURE python3 needle_s/podctl.py run needle_s/mg_podspec.json >> $L 2>&1; log "podctl exit $?"
ls -la $P/../pod_results_mg 2>/dev/null >> $L
