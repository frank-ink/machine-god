#!/usr/bin/env bash
cd ~/entityos-kern/omega
nohup lowprio -m 1G -c 50 -- python3 daten_gen.py 250 >> daten/gen.log 2>&1 &
nohup lowprio -m 1G -c 30 -- python3 daten_gen_tools.py 120 > daten/gen_tools.log 2>&1 &
sleep 5; nohup ./pod_nach_daten.sh >/dev/null 2>&1 &
