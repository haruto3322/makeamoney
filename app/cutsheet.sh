#!/bin/bash
# ドロップされた動画からカット表を作る。デスクトップアプリの実体。
#
#   app/cutsheet.sh <動画ファイル> [extract_cuts.py への追加オプション]
#
# 依存は初回だけリポジトリ内の .venv に入れる。システムの Python を汚さないので、
# Homebrew Python の externally-managed-environment エラーや権限エラーに
# 引っかからない。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT" || exit 1

abort() {
    echo ""
    echo "❌ $1"
    echo ""
    echo "このウィンドウは閉じて構わない。"
    exit 1
}

if [ $# -lt 1 ]; then
    abort "動画ファイルが指定されていない。アプリのアイコンに動画をドラッグ&ドロップする。"
fi

VIDEO="$1"
shift
[ -f "$VIDEO" ] || abort "動画が見つからない: $VIDEO"

echo "🎬 カット表を作る"
echo "   入力: $VIDEO"
echo ""

# ---- 依存の用意 ----
if ! ensure_venv; then
    echo ""
    echo "⚠️  ライブラリを入れられなかった。精度の落ちる簡易検出で続行する。"
    echo "    上のエラーを見せてもらえれば原因を特定できる。"
    echo ""
fi
PY="$(resolved_python)"
[ -n "$PY" ] || abort "python3 が見つからない。Xcode Command Line Tools を入れる: xcode-select --install"

# ---- カット分割とキーフレーム抽出 ----
BASENAME="$(basename "$VIDEO")"
# 出力先パスに空白などが混ざると、後段に渡す引数が曖昧になるので潰しておく。
SLUG="$(printf '%s' "${BASENAME%.*}" | tr ' \t/:\\' '_____')"
OUTDIR="out/${SLUG}_$(date +%Y%m%d-%H%M%S)"

"$PY" "$REPO_ROOT/tools/extract_cuts.py" "$VIDEO" -o "$OUTDIR" "$@" || abort "カット分割に失敗した"

echo ""

# ---- Claude Code に引き継ぐ ----
PROMPT="/cutsheet $OUTDIR"
CLAUDE_BIN="$(find_claude || true)"

# 見つからなければ、その場で入れてしまう(初回だけ)。
if [ -z "$CLAUDE_BIN" ] && command -v npm >/dev/null 2>&1 && [ -r /dev/tty ]; then
    echo "解析に使う Claude Code がまだ入っていない。"
    read -r -p "いま入れる? [Y/n]: " answer < /dev/tty
    case "${answer:-Y}" in
        [nN]*) ;;
        *)
            echo ""
            CLAUDE_BIN="$(install_claude || true)"
            echo ""
            ;;
    esac
fi

if [ -n "$CLAUDE_BIN" ]; then
    echo "🤖 Claude Code に解析を引き継ぐ…"
    echo ""
    exec "$CLAUDE_BIN" "$PROMPT"
fi

# 自動で引き継げなかった場合は、貼り付けるだけで済む形にして渡す。
if command -v pbcopy >/dev/null 2>&1; then
    printf '%s' "$PROMPT" | pbcopy
    COPIED="(コマンドはコピー済み。⌘V で貼り付けられる)"
else
    COPIED=""
fi

echo "──────────────────────────────────────────"
echo "キーフレームの書き出しまで終わった。解析は Claude Code で行う。"
echo ""
echo "Claude Code でこのフォルダを開いて、下の1行を実行する $COPIED"
echo "   フォルダ: $REPO_ROOT"
echo ""
echo "   $PROMPT"
echo ""
echo "ターミナルで完結させたい場合は、先に Claude Code を入れる:"
echo "   npm install -g @anthropic-ai/claude-code"
echo "   (Node.js が必要。詳細は https://code.claude.com/docs)"
echo "──────────────────────────────────────────"

command -v open >/dev/null 2>&1 && open "$REPO_ROOT" >/dev/null 2>&1
exit 0
