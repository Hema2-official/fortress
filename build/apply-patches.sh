#!/usr/bin/env bash
# Apply the public patch series atomically per patch, preserving every diagnostic.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:?usage: apply-patches.sh /path/to/chromium/src}"
cd "$SRC"
count=0
while IFS= read -r rel; do
  [[ -z "$rel" ]] && continue
  patch="$REPO/$rel"
  if ! git apply --check --recount "$patch"; then
    echo "Patch needs rebase: $rel; source tree was not modified by this patch" >&2
    exit 2
  fi
  git apply --recount --whitespace=nowarn "$patch"
  count=$((count + 1))
  printf '[ok] %s\n' "$rel"
done < "$REPO/patches/series"
printf 'Applied %s public patches.\n' "$count"
