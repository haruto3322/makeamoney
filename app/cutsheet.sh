#!/bin/bash
# ドロップされた動画からカット表を作る。デスクトップアプリの実体。
#
#   app/cutsheet.sh <動画ファイル>
#
# 初回だけリポジトリ内に .venv を作って依存を入れる。システムの Python を
# 汚さないので、Homebrew Python の externally-managed-environment エラーや
# 権限エラーに引っかからない。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
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
[ -f "$VIDEO" ] || abort "動画が見つからない: $VIDEO"

echo "🎬 カット表を作る"
echo "   入力: $VIDEO"
echo ""

# ---- Python の用意 ----
PYTHON_BIN="$(command -v python3 || true)"
[ -n "$PYTHON_BIN" ] || abort "python3 が見つからない。Xcode Command Line Tools か Homebrew の Python を入れる:
   xcode-select --install"

VENV="$REPO_ROOT/.venv"
if [ ! -x "$VENV/bin/python" ]; then
    echo "初回セットアップ中… 必要なライブラリを入れる(数分かかることがある)"
    "$PYTHON_BIN" -m venv "$VENV" || abort "仮想環境の作成に失敗した"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    if ! "$VENV/bin/python" -m pip install --quiet -r "$REPO_ROOT/requirements.txt"; then
        abort "ライブラリのインストールに失敗した。ネットワーク接続を確認する"
    fi
    echo "セットアップ完了"
    echo ""
fi
PY="$VENV/bin/python"

# ---- カット分割とキーフレーム抽出 ----
BASENAME="$(basename "$VIDEO")"
# 出力先パスに空白などが混ざると、後段に渡す引数が曖昧になるので潰しておく。
SLUG="$(printf '%s' "${BASENAME%.*}" | tr ' \t/:\\' '_____')"
OUTDIR="out/${SLUG}_$(date +%Y%m%d-%H%M%S)"

"$PY" "$REPO_ROOT/tools/extract_cuts.py" "$VIDEO" -o "$OUTDIR" || abort "カット分割に失敗した"

echo ""

# ---- Claude Code に引き継ぐ ----
CLAUDE_BIN="$(command -v claude || true)"
if [ -z "$CLAUDE_BIN" ]; then
    for candidate in "$HOME/.local/bin/claude" "/opt/homebrew/bin/claude" "/usr/local/bin/claude"; do
        if [ -x "$candidate" ]; then
            CLAUDE_BIN="$candidate"
            break
        fi
    done
fi

if [ -z "$CLAUDE_BIN" ]; then
    echo "⚠️  claude コマンドが見つからないので、ここから先は手動で実行する。"
    echo ""
    echo "   cd $REPO_ROOT"
    echo "   claude \"/cutsheet $OUTDIR\""
    echo ""
    exit 0
fi

echo "🤖 Claude Code に解析を引き継ぐ…"
echo ""
exec "$CLAUDE_BIN" "/cutsheet $OUTDIR"
