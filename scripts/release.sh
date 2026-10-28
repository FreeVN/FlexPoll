#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
#
# Release voorbereiden: VERSION bijwerken, CHANGELOG-kop zetten, committen, taggen.
# Push daarna met `git push --follow-tags`.
set -euo pipefail

V="${1:-}"
if [[ ! "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "gebruik: scripts/release.sh 1.1.0" >&2
  exit 1
fi

cd "$(dirname "$0")/.."

if [[ -n "$(git status --porcelain)" ]]; then
  echo "werkboom is niet proper — commit of stash eerst" >&2
  git status --short >&2
  exit 1
fi

CUR="$(cat VERSION)"
if [[ "$CUR" == "$V" ]]; then
  echo "VERSION staat al op $V" >&2
  exit 1
fi

if ! grep -q '^## \[Unreleased\]' CHANGELOG.md; then
  echo "CHANGELOG.md heeft geen [Unreleased]-kop" >&2
  exit 1
fi

python3 - "$V" <<'PY'
import datetime, pathlib, sys

v = sys.argv[1]
p = pathlib.Path("CHANGELOG.md")
s = p.read_text(encoding="utf-8")
stamp = datetime.date.today().isoformat()
s = s.replace("## [Unreleased]",
              f"## [Unreleased]\n\n## [{v}] — {stamp}", 1)
p.write_text(s, encoding="utf-8")
PY

printf '%s\n' "$V" > VERSION

git add VERSION CHANGELOG.md
git commit -q -m "chore(release): v$V"
git tag -a "v$V" -m "FlexPoll $V"

echo "v$V klaar. Nu: git push --follow-tags"
