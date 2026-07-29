#!/bin/bash
# クラウド上の定期実行(Routine)から呼ばれる。合議を 1 回まわして、
# 結果をリポジトリに残すところまでを無人で行う。
#
# PC は関与しない。Anthropic 側の環境で動き、結果は GitHub に push されるので
# iPhone のブラウザから読める。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 1

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1"
}

BRANCH="${COUNCIL_BRANCH:-main}"

log "最新の状態に更新する"
git fetch -q origin "$BRANCH" || log "fetch に失敗した(オフライン?)。手元の状態で続行する"
git checkout -q "$BRANCH" 2>/dev/null || log "$BRANCH に切り替えられなかった。現在のブランチで続行する"
git pull -q --rebase origin "$BRANCH" 2>/dev/null || log "pull に失敗した。手元の状態で続行する"

log "合議を開始する"
if ! python3 "$REPO_ROOT/tools/council.py" "$@"; then
    log "合議に失敗した"
    exit 1
fi

if [ ! -f "$REPO_ROOT/council/latest.md" ]; then
    log "結論ファイルができていない"
    exit 1
fi

log "結果をリポジトリに残す"
git add council/log council/latest.md
if git diff --cached --quiet; then
    log "変更が無いので commit しない"
    exit 0
fi

git commit -q -m "Council: $(date '+%Y-%m-%d %H:%M') の合議結果

自動実行された合議の議事録と結論。議題は council/agenda.md。"

if git push -q origin "HEAD:$BRANCH"; then
    log "push した"
else
    log "push に失敗した。次回の実行でまとめて push される"
    exit 1
fi

log "完了"
