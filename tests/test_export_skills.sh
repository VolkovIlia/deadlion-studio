#!/bin/sh
# Tests for scripts/export-skills. Run from anywhere: sh tests/test_export_skills.sh
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
exp=$root/scripts/export-skills
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM

fail() { echo "FAIL: $*" >&2; exit 1; }

# Real tree: every skill exported, paths made relative.
"$exp" "$tmp/out" || fail "export of real plugins/ exited $?"
s=$tmp/out/suckless-code
[ -f "$s/SKILL.md" ] || fail "suckless-code/SKILL.md missing"
! grep -r CLAUDE_SKILL_DIR "$tmp/out" >/dev/null || fail "CLAUDE_SKILL_DIR left in export"
[ -x "$s/scripts/dl-size" ] || fail "suckless-code/scripts/dl-size not executable"

# Re-export replaces existing skill dirs instead of nesting into them.
"$exp" "$tmp/out" || fail "re-export exited $?"
[ ! -e "$s/suckless-code" ] || fail "re-export nested suckless-code/suckless-code"

# Duplicate skill names across plugins: exit 1, nothing copied.
mkdir -p "$tmp/dup/a/skills/x" "$tmp/dup/b/skills/x"
echo 'see ${CLAUDE_SKILL_DIR}/r.md' > "$tmp/dup/a/skills/x/SKILL.md"
cp "$tmp/dup/a/skills/x/SKILL.md" "$tmp/dup/b/skills/x/SKILL.md"
rc=0
PLUGINS_DIR=$tmp/dup "$exp" "$tmp/d" 2>"$tmp/err" || rc=$?
[ "$rc" -eq 1 ] || fail "duplicate: want exit 1, got $rc"
grep -q 'export-skills: duplicate skill x' "$tmp/err" || fail "duplicate: bad message"
[ ! -e "$tmp/d/x" ] || fail "duplicate: skill copied anyway"

# Selecting one plugin avoids the duplicate and rewrites the path.
PLUGINS_DIR=$tmp/dup "$exp" "$tmp/d" a || fail "single plugin export failed"
[ "$(cat "$tmp/d/x/SKILL.md")" = 'see r.md' ] || fail "CLAUDE_SKILL_DIR not stripped"

# Usage and path errors: exit 2.
rc=0; "$exp" 2>/dev/null || rc=$?
[ "$rc" -eq 2 ] || fail "no args: want exit 2, got $rc"
rc=0; "$exp" "$tmp/no/such/dest" 2>/dev/null || rc=$?
[ "$rc" -eq 2 ] || fail "missing DEST parent: want exit 2, got $rc"
rc=0; "$exp" "$tmp/out" no-such-plugin 2>/dev/null || rc=$?
[ "$rc" -eq 2 ] || fail "unknown plugin: want exit 2, got $rc"

echo "ok test_export_skills"
