#!/bin/bash
# Machine God autonomous cycle: propose (free pool, vetted templates only) -> run one preregistered trial (copies only) -> check due adoptions.
# Off switch: touch ~/.local/share/machine-god/KILL   (all steps check it). Log: ~/.local/share/machine-god/cycle.log
cd "$(dirname "$0")" || exit 1
mkdir -p ~/.local/share/machine-god
{
    date -Is
    python3 mg_propose.py
    nice -n 15 ionice -c3 python3 mg_loop.py tick
    nice -n 15 ionice -c3 python3 mg_watch.py tick
    # weekly fresh probe set (DESIGN 1, 5.2): once per ISO week, inside this already-scheduled cycle
    [ -e ~/.local/share/machine-god/KILL ] || [ -e ~/.local/share/machine-god/fresh/probes-$(date +%G%V).jsonl ] || \
        { python3 mg_fresh.py build && nice -n 15 ionice -c3 python3 mg_fresh.py measure; }
} >> ~/.local/share/machine-god/cycle.log 2>&1
