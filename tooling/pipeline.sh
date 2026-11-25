#!/usr/bin/env bash
# pipeline.sh -- runs all remaining phases: team1 + team2 (zerlegen retry, entwurf, review, final), then vereinigung -> GRIDv1.
# NVIDIA free only (team.py). Log: ~/entityos-kern/pipeline.log
K=~/entityos-kern
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a $K/pipeline.log; }
for p in $(pgrep -f "^python3 -I .*team.py zerlegen"); do while kill -0 "$p" 2>/dev/null; do sleep 15; done; done

team(){  # $1 = team dir
  local d=$K/$1
  for try in 1 2; do
    n=$(ls $d/out/zerlegen/*.md 2>/dev/null | wc -l)
    [ "$n" -ge 10 ] && break
    log "$1 zerlegen $n/10 -> retry $try"; TEAM_DIR=$d python3 -I $K/team/team.py zerlegen >> $d/pipeline.log 2>&1
  done
  log "$1 zerlegen final: $(ls $d/out/zerlegen/*.md | wc -l)/10"
  for ph in entwurf review final; do
    for try in 1 2; do
      TEAM_DIR=$d python3 -I $K/team/team.py $ph >> $d/pipeline.log 2>&1
      [ "$ph" = review ] && { n=$(ls $d/out/review/*.md 2>/dev/null | wc -l); [ "$n" -ge 10 ] && break; log "$1 review $n/10"; continue; }
      [ -s $d/out/$ph/$ph.md ] && break
    done
    log "$1 $ph: $(ls $d/out/$ph/ 2>/dev/null | wc -l) files"
  done
}
team team & team team2 & wait
[ -s $K/team/out/final/final.md ] && [ -s $K/team2/out/final/final.md ] || { log "ABBRUCH: ein Team-Final fehlt"; exit 1; }
for ph in v_entwurf v_review v_final; do
  for try in 1 2; do python3 -I $K/vereinigung/vereinigung.py $ph >> $K/vereinigung/pipeline.log 2>&1; done
  log "vereinigung $ph: $(ls $K/vereinigung/out/$ph/ 2>/dev/null | wc -l) files"
done
log "FERTIG: $(ls -la $K/vereinigung/out/v_final/ 2>/dev/null | tail -n +2)"
