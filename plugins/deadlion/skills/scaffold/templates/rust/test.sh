#!/bin/sh
# test.sh - behaviour tests for __NAME__. Silent on success.
# Usage: BIN=./__NAME__ sh test.sh
set -eu

BIN=${BIN:-./__NAME__}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

fail() {
	echo "FAIL: $*" >&2
	exit 1
}

printf 'a\nb\n' > "$tmp/want"
printf 'a\nb\n' | "$BIN" > "$tmp/out" || fail 'stdin copy exits 0'
cmp -s "$tmp/want" "$tmp/out" || fail 'stdin is copied to stdout exactly'

"$BIN" -v > "$tmp/out" || fail '-v exits 0'
case $(cat "$tmp/out") in
__NAME__-*) ;;
*) fail '-v prints __NAME__-VERSION' ;;
esac

rc=0
"$BIN" -x > /dev/null 2> "$tmp/err" || rc=$?
[ "$rc" -eq 1 ] || fail "-x exits 1, got $rc"
grep -q 'usage: __NAME__' "$tmp/err" || fail '-x prints usage on stderr'

rc=0
"$BIN" /nonexistent > /dev/null 2> "$tmp/err" || rc=$?
[ "$rc" -eq 1 ] || fail "missing file exits 1, got $rc"
case $(sed 1q "$tmp/err") in
'__NAME__: '*) ;;
*) fail 'missing file error starts with __NAME__: ' ;;
esac

printf 'hello\n' > "$tmp/f"
printf 'hello\nhello\n' > "$tmp/want"
"$BIN" "$tmp/f" "$tmp/f" > "$tmp/out" || fail 'file copy exits 0'
cmp -s "$tmp/want" "$tmp/out" || fail 'files are copied in order'
