#!/bin/bash
# クラウドの定期実行から呼ばれる。手元(Antigravity)が置いていったものを見て、
# 進められる工程を進め、結果をリポジトリに返す。
#
# 手元とクラウドは直接やり取りせず、git だけを共有面にしている。
# 片方が止まっていても、もう片方は自分の担当分を進められる。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT" || exit 1

BRANCH="${PIPELINE_BRANCH:-main}"
LOCK="$REPO_ROOT/.pipeline.lock"

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1"
}

if ! mkdir "$LOCK" 2>/dev/null; then
    log "前回の処理がまだ動いているので見送る"
    exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

log "最新の状態に更新する"
git fetch -q origin "$BRANCH" 2>/dev/null || log "fetch に失敗した。手元の状態で続行する"
git checkout -q "$BRANCH" 2>/dev/null || true
git pull -q --rebase origin "$BRANCH" 2>/dev/null || log "pull に失敗した。手元の状態で続行する"

CLAUDE_BIN="$(find_claude || true)"
[ -n "$CLAUDE_BIN" ] && export CLAUDE_BIN

PY="$(resolved_python)"
if [ -z "$PY" ]; then
    log "python3 が見つからない"
    exit 1
fi

"$PY" "$REPO_ROOT/tools/pipeline.py"
status=$?

if [ $status -ne 0 ]; then
    log "処理に失敗した(終了コード $status)"
    exit $status
fi

# 生成物・解析結果・依頼票の変化だけを返す。動画は .gitignore で除外済み。
# 止まっているところが無いか調べ、STATUS.md に残す。
# 無人で回す以上、止まったことに誰も気づかないのが最悪なので毎回書く。
"$PY" "$REPO_ROOT/tools/healthcheck.py" || true

git add out work council STATUS.md 2>/dev/null
if git diff --cached --quiet; then
    log "返すものは無い"
    exit 0
fi

git commit -q -m "Pipeline: $(date '+%Y-%m-%d %H:%M') の自動処理

進められる工程を進めた。詳細は変更されたファイルを参照。"

if git push -q origin "HEAD:$BRANCH"; then
    log "push した"
else
    log "push に失敗した。次回まとめて push される"
    exit 1
fi

log "完了"
