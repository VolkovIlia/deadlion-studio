#!/bin/sh
# test.sh - behaviour tests for __NAME__. Silent on success.
# Usage: BIN=./__NAME__ sh test.sh
# The interactive checks drive __NAME__ in a private headless tmux server.
set -eu

BIN=${BIN:-./__NAME__}
tmp=$(mktemp -d)
items="printf 'alpha\nbeta\ngamma\n'"

t() {
	tmux -L "__NAME__-test-$$" -f /dev/null "$@"
}

trap 't kill-server 2> /dev/null || :; rm -rf "$tmp"' EXIT

fail() {
	echo "FAIL: $*" >&2
	exit 1
}

# start CMD: run CMD by /bin/sh in a fresh 40x12 session s
start() {
	rm -f "$tmp/out" "$tmp/rc"
	t new-session -d -s s -x 40 -y 12 -c "$PWD" /bin/sh -c "$1"
	t set-option -g status off
}

# wait_for PATTERN: poll the screen until PATTERN shows (5 s max)
wait_for() {
	i=0
	until t capture-pane -p -t s | grep -q -- "$1"; do
		i=$((i + 1))
		[ "$i" -lt 100 ] || fail "screen never showed '$1'"
		sleep 0.05
	done
}

# wait_rc: poll until the session wrote its exit status (5 s max)
wait_rc() {
	i=0
	until [ -s "$tmp/rc" ]; do
		i=$((i + 1))
		[ "$i" -lt 100 ] || fail 'program did not exit'
		sleep 0.05
	done
}

command -v tmux > /dev/null || fail 'tmux not installed'

"$BIN" -v > "$tmp/out" || fail '-v exits 0'
case $(cat "$tmp/out") in
__NAME__-*) ;;
*) fail '-v prints __NAME__-VERSION' ;;
esac

rc=0
"$BIN" -x < /dev/null > /dev/null 2> "$tmp/err" || rc=$?
[ "$rc" -eq 1 ] || fail "-x exits 1, got $rc"
grep -q 'usage: __NAME__' "$tmp/err" || fail '-x prints usage on stderr'

rc=0
printf '' | "$BIN" > /dev/null 2> "$tmp/err" || rc=$?
[ "$rc" -eq 1 ] || fail "empty input exits 1, got $rc"
[ "$(cat "$tmp/err")" = '__NAME__: no input' ] || fail 'empty input reports no input'

rc=0
printf 'a\n' | TERM=dumb "$BIN" > /dev/null 2> "$tmp/err" || rc=$?
[ "$rc" -eq 1 ] || fail "TERM=dumb exits 1, got $rc"
case $(sed 1q "$tmp/err") in
'__NAME__: TERM=dumb'*) ;;
*) fail 'TERM=dumb error starts with __NAME__: TERM=dumb' ;;
esac

# pick: filter, Enter prints the line, the terminal mode is restored
start "$items | $BIN > $tmp/out; echo \$? > $tmp/rc; stty -a > $tmp/stty"
wait_for alpha
t send-keys -t s -l ga
wait_for 'filter: ga'
t send-keys -t s Enter
wait_rc
[ "$(cat "$tmp/rc")" = 0 ] || fail "pick exits 0, got $(cat "$tmp/rc")"
[ "$(cat "$tmp/out")" = gamma ] || fail 'pick prints the filtered line'
grep -q ' icanon' "$tmp/stty" || fail 'terminal mode is restored'

# cancel: Esc exits 1 and prints nothing, also without colour
start "$items | NO_COLOR=1 $BIN > $tmp/out; echo \$? > $tmp/rc"
wait_for alpha
t send-keys -t s Escape
wait_rc
[ "$(cat "$tmp/rc")" = 1 ] || fail "cancel exits 1, got $(cat "$tmp/rc")"
[ ! -s "$tmp/out" ] || fail 'cancel prints nothing'

# resize: the status line is redrawn at the new width
start "$items | $BIN > $tmp/out; echo \$? > $tmp/rc"
wait_for alpha
t resize-window -t s -x 20 -y 5
wait_for '1/3  Up/Down move  E$'
t send-keys -t s Escape
wait_rc
[ "$(cat "$tmp/rc")" = 1 ] || fail "cancel after resize exits 1, got $(cat "$tmp/rc")"
