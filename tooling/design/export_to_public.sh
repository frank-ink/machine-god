#!/bin/bash
# Design-Team-Ergebnis (gridv1/design, nur src/ui) -> lokaler Branch design-ui auf dem Stand des oeffentlichen Repos (mg/main). Kein Push.
set -e
M=~/void-build/machine-god; P=~/void-build/public-banner
B=$(git -C "$M" merge-base gridv1/design gridv1/zero)
git -C "$M" diff "$B" gridv1/design -- src/ui > /tmp/design-ui.patch
git -C "$M" fetch mg -q
git -C "$P" checkout -q banner-d
git -C "$P" branch -D design-ui 2>/dev/null || true
git -C "$P" checkout -q -b design-ui mg/main
git -C "$P" apply --check /tmp/design-ui.patch
git -C "$P" apply /tmp/design-ui.patch
git -C "$P" add -A
git -C "$P" -c user.name=frank-ink -c user.email=frank-ink@users.noreply.github.com commit -q -m "ui: design team improvements (src/ui)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git -C "$P" log --oneline -1; git -C "$P" diff --stat HEAD~1 | tail -1
git -C "$P" checkout -q banner-d
