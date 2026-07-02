#!/bin/sh

repo="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

if command -v cygpath >/dev/null 2>&1; then
  repo_win="$(cygpath -w "$repo")"
else
  repo_win="$repo"
fi

log="$repo/.git/skill-sync.log"
ps="powershell.exe"

"$ps" -NoProfile -ExecutionPolicy Bypass -File "$repo_win\\scripts\\sync_skill.ps1" -Quiet -Auto >>"$log" 2>&1
status=$?

if [ "$status" -ne 0 ]; then
  echo "[skill-sync] sync failed; see .git/skill-sync.log" >&2
fi

exit 0
