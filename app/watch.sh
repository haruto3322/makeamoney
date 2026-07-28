#!/bin/bash
# iCloud Drive の受信フォルダを見張り、新しい動画があればカット表を作って
# 完成フォルダに置く。iPhone の「ファイル」アプリから動画を入れるだけで、
# Mac 側が勝手に処理して結果を返す、という使い方のための常駐処理。
#
#   app/watch.sh          … 1 回スキャンして終了(launchd から定期実行される)
#
# 受信 / 完成フォルダは環境変数で差し替えられる(テスト用)。
#   CUTSHEET_INBOX / CUTSHEET_OUTBOX
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT" || exit 1

ICLOUD="$HOME/Library/Mobile Documents/com~apple~CloudDocs"
INBOX="${CUTSHEET_INBOX:-$ICLOUD/カット表/受信}"
OUTBOX="${CUTSHEET_OUTBOX:-$ICLOUD/カット表/完成}"
STATE_DIR="$REPO_ROOT/.watch-state"
LOCK="$REPO_ROOT/.watch.lock"

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1"
}

mkdir -p "$INBOX" "$OUTBOX" "$STATE_DIR"

# 前回の処理が終わっていなければ何もしない(重複起動の防止)。
if ! mkdir "$LOCK" 2>/dev/null; then
    exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# ファイルの同一性は「名前 + サイズ + 更新時刻」で見る。処理済みなら飛ばす。
state_key() {
    local file="$1" size mtime
    size="$(wc -c < "$file" 2>/dev/null | tr -d ' ')"
    mtime="$(date -r "$file" '+%s' 2>/dev/null || echo 0)"
    printf '%s' "$(basename "$file")_${size}_${mtime}" | tr -c 'A-Za-z0-9._-' '_'
}

# iCloud 上でまだ実体が落ちてきていないファイルは、ダウンロードを促して次回に回す。
request_downloads() {
    local placeholder found=0
    while IFS= read -r placeholder; do
        [ -n "$placeholder" ] || continue
        found=1
        if command -v brctl >/dev/null 2>&1; then
            brctl download "$placeholder" >/dev/null 2>&1
        fi
    done < <(find "$INBOX" -maxdepth 1 -name '.*.icloud' 2>/dev/null)
    # 見つかったときだけ成功(=真)を返す。
    [ "$found" -eq 1 ]
}

if request_downloads; then
    log "iCloud からのダウンロード待ちのファイルがある。次回のスキャンで処理する。"
fi

CLAUDE_BIN="$(find_claude || true)"
PY="$(resolved_python)"

processed=0
while IFS= read -r video; do
    [ -n "$video" ] || continue
    key="$(state_key "$video")"
    marker="$STATE_DIR/$key"
    [ -e "$marker" ] && continue

    name="$(basename "$video")"
    log "処理開始: $name"

    if [ -z "$CLAUDE_BIN" ]; then
        log "  claude が見つからないので中断する。セットアップ.command を実行する。"
        break
    fi
    if [ -z "$PY" ]; then
        log "  python3 が見つからないので中断する。"
        break
    fi

    slug="$(printf '%s' "${name%.*}" | tr ' \t/:\\' '_____')"
    outdir="out/${slug}_$(date +%Y%m%d-%H%M%S)"

    if ! "$PY" "$REPO_ROOT/tools/extract_cuts.py" "$video" -o "$outdir" >> "$REPO_ROOT/.watch.log" 2>&1; then
        log "  キーフレーム抽出に失敗した"
        : > "$marker"
        continue
    fi

    # 対話なしで解析させる。--parts-only を付けて、Claude には解析結果の
    # 書き出しだけをさせる。統合と整形はこのスクリプトが自分で実行するので、
    # 無人実行のためにコマンド実行の権限を広く与える必要がない。
    if ! "$CLAUDE_BIN" -p "/cutsheet $outdir --parts-only" \
            --permission-mode acceptEdits >> "$REPO_ROOT/.watch.log" 2>&1; then
        log "  解析に失敗した(詳細は .watch.log)"
        : > "$marker"
        continue
    fi

    if ! "$PY" "$REPO_ROOT/tools/build_cutsheet.py" "$outdir" >> "$REPO_ROOT/.watch.log" 2>&1; then
        log "  カット表の組み立てに失敗した(詳細は .watch.log)"
        : > "$marker"
        continue
    fi
    "$PY" "$REPO_ROOT/tools/render_cutsheet.py" "$outdir/cutsheet.json" \
        >> "$REPO_ROOT/.watch.log" 2>&1

    result="$REPO_ROOT/$outdir/cutsheet.html"
    if [ -f "$result" ]; then
        cp "$result" "$OUTBOX/${slug}_$(date +%Y%m%d-%H%M%S).html"
        log "  完成: $OUTBOX に置いた"
    else
        log "  cutsheet.html ができていない(詳細は .watch.log)"
    fi

    : > "$marker"
    processed=$((processed + 1))
done < <(find "$INBOX" -maxdepth 1 -type f \
    \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' -o -iname '*.webm' \) 2>/dev/null | sort)

[ "$processed" -gt 0 ] && log "$processed 件処理した"
exit 0
