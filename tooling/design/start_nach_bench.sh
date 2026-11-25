#!/usr/bin/env bash
# waits for bench.py, then starts design20 as its own user unit (Nice 10, MemoryMax 10G, no endless restart)
D=~/entityos-kern/design
while pgrep -f "[b]ench.py" >/dev/null; do sleep 60; done
[ -s $D/bench.json ] || { echo "$(date +%T) no bench.json" >> $D/start.log; exit 1; }
systemd-run --user --unit=design20 -p Nice=10 -p MemoryMax=10G -p Restart=on-failure -p RestartSec=300 \
  -p StartLimitIntervalSec=7200 -p StartLimitBurst=3 --setenv=PYTHONPYCACHEPREFIX=/tmp/design20-pyc \
  --setenv=PATH=$HOME/.cargo/bin:$HOME/.local/bin:$HOME/bin:$HOME/.bun/bin:$HOME/.nvm/versions/node/v22.23.2/bin:$HOME/.nvm/versions/node/v20.20.0/bin:/usr/local/bin:/usr/bin:/bin \
  --working-directory=$D /usr/bin/python3 $D/design20.py >> $D/start.log 2>&1
echo "$(date +%T) design20 started" >> $D/start.log
