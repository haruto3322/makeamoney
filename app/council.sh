#!/bin/bash
# 合議を 1 回まわす。launchd から 5 時間ごとに呼ばれる想定。
#
#   app/council.sh                  … council/agenda.md を議題にする
#   app/council.sh "議題をここに"    … 議題をその場で指定する
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT" || exit 1

LOCK="$REPO_ROOT/.council.lock"
LOG="$REPO_ROOT/.council.log"

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1"
}

# 前回の合議が終わっていなければ何もしない(5 時間より長引いた場合の保険)。
if ! mkdir "$LOCK" 2>/dev/null; then
    log "前回の合議がまだ動いているので今回は見送る"
    exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

CLAUDE_BIN="$(find_claude || true)"
if [ -z "$CLAUDE_BIN" ]; then
    log "claude が見つからない。セットアップ.command を実行する"
    exit 1
fi
export CLAUDE_BIN

PY="$(resolved_python)"
if [ -z "$PY" ]; then
    log "python3 が見つからない"
    exit 1
fi

log "合議を開始する"
if [ $# -gt 0 ] && [ -n "$1" ]; then
    "$PY" "$REPO_ROOT/tools/council.py" --topic "$1"
else
    "$PY" "$REPO_ROOT/tools/council.py"
fi
status=$?

if [ $status -ne 0 ]; then
    log "合議に失敗した(終了コード $status)"
    exit $status
fi
log "合議が完了した"

# iPhone から読めるように、結論を iCloud にも置く。
OUTBOX="$HOME/Library/Mobile Documents/com~apple~CloudDocs/カット表/完成"
if [ -d "$OUTBOX" ] && [ -f "$REPO_ROOT/council/latest.md" ]; then
    cp "$REPO_ROOT/council/latest.md" "$OUTBOX/合議_$(date +%Y%m%d-%H%M).md"
    log "結論を iCloud に置いた"
fi
exit 0
