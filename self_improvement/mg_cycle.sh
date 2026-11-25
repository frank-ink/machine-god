#!/bin/bash
# Machine God autonomous cycle: propose (free pool, vetted templates only) -> run one preregistered trial (copies only) -> ledger.
# Off switch: touch ~/.local/share/machine-god/KILL   (both steps check it). Log: ~/.local/share/machine-god/cycle.log
cd "$(dirname "$0")" || exit 1
mkdir -p ~/.local/share/machine-god
{ date -Is; python3 mg_propose.py; nice -n 15 ionice -c3 python3 mg_loop.py tick; } >> ~/.local/share/machine-god/cycle.log 2>&1
