#!/bin/bash
# ドロップされた動画からカット表を作る。デスクトップアプリの実体。
#
#   app/cutsheet.sh <動画ファイル> [extract_cuts.py への追加オプション]
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
shift
[ -f "$VIDEO" ] || abort "動画が見つからない: $VIDEO"

echo "🎬 カット表を作る"
echo "   入力: $VIDEO"
echo ""

# ---- Python の用意 ----
PYTHON_BIN="$(command -v python3 || true)"
[ -n "$PYTHON_BIN" ] || abort "python3 が見つからない。Xcode Command Line Tools か Homebrew の Python を入れる:
   xcode-select --install"

VENV="$REPO_ROOT/.venv"
STAMP="$VENV/.deps-ok"

hash_requirements() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$REPO_ROOT/requirements.txt" | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$REPO_ROOT/requirements.txt" | awk '{print $1}'
    else
        # ハッシュが取れない環境では内容の変化を検知できないので固定値にする。
        echo "no-hash"
    fi
}

REQ_HASH="$(hash_requirements)"

# インストールが最後まで成功したときだけスタンプを書く。venv があるだけでは
# 完了とみなさない(途中で失敗したまま次回スキップされるのを防ぐ)。
if [ ! -x "$VENV/bin/python" ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$REQ_HASH" ]; then
    echo "初回セットアップ中… 必要なライブラリを入れる(数分かかることがある)"
    if [ ! -x "$VENV/bin/python" ]; then
        "$PYTHON_BIN" -m venv "$VENV" || abort "仮想環境の作成に失敗した"
    fi
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    if "$VENV/bin/python" -m pip install -r "$REPO_ROOT/requirements.txt"; then
        printf '%s' "$REQ_HASH" > "$STAMP"
        echo "セットアップ完了"
    else
        echo ""
        echo "⚠️  ライブラリのインストールに失敗した。簡易的なカット検出で続行する。"
        echo "    精度が必要なら、ネットワークを確認してもう一度実行する。"
    fi
    echo ""
fi
PY="$VENV/bin/python"

if ! "$PY" -c "import scenedetect" >/dev/null 2>&1; then
    echo "⚠️  高精度なカット検出(PySceneDetect)が使えない状態。簡易検出で進む。"
    echo "    入れ直すには次を実行する:"
    echo "      rm -rf '$VENV' && '$SCRIPT_DIR/cutsheet.sh' <動画>"
    echo ""
fi

# ---- カット分割とキーフレーム抽出 ----
BASENAME="$(basename "$VIDEO")"
# 出力先パスに空白などが混ざると、後段に渡す引数が曖昧になるので潰しておく。
SLUG="$(printf '%s' "${BASENAME%.*}" | tr ' \t/:\\' '_____')"
OUTDIR="out/${SLUG}_$(date +%Y%m%d-%H%M%S)"

"$PY" "$REPO_ROOT/tools/extract_cuts.py" "$VIDEO" -o "$OUTDIR" "$@" || abort "カット分割に失敗した"

echo ""

# ---- Claude Code を探す ----
# インストール方法によって場所が大きく違ううえ、ログインシェル(zsh)にだけ
# PATH が通っていることも多いので、順に広く探す。
find_claude() {
    local found
    found="$(command -v claude 2>/dev/null || true)"
    if [ -n "$found" ]; then
        echo "$found"
        return 0
    fi

    local candidate
    for candidate in \
        "$HOME/.local/bin/claude" \
        "$HOME/.claude/local/claude" \
        "$HOME/.bun/bin/claude" \
        "$HOME/.volta/bin/claude" \
        "/opt/homebrew/bin/claude" \
        "/usr/local/bin/claude"; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done

    for candidate in "$HOME"/.nvm/versions/node/*/bin/claude; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done

    if command -v npm >/dev/null 2>&1; then
        local prefix
        prefix="$(npm config get prefix 2>/dev/null)"
        if [ -n "$prefix" ] && [ -x "$prefix/bin/claude" ]; then
            echo "$prefix/bin/claude"
            return 0
        fi
    fi

    # bash から起動された場合、zsh 側にだけ通っている PATH を拾う。
    if command -v zsh >/dev/null 2>&1; then
        found="$(zsh -lic 'command -v claude' 2>/dev/null | tail -n 1)"
        if [ -n "$found" ] && [ -x "$found" ]; then
            echo "$found"
            return 0
        fi
    fi

    return 1
}

CLAUDE_BIN="$(find_claude || true)"

if [ -z "$CLAUDE_BIN" ]; then
    echo "⚠️  claude コマンドが見つからないので、ここから先は手動で実行する。"
    echo ""
    echo "   cd $REPO_ROOT"
    echo "   claude \"/cutsheet $OUTDIR\""
    echo ""
    echo "Claude Code をまだ入れていない場合は先にインストールする:"
    echo "   npm install -g @anthropic-ai/claude-code"
    echo "   (手順の詳細: https://code.claude.com/docs)"
    echo ""
    exit 0
fi

echo "🤖 Claude Code に解析を引き継ぐ…"
echo ""
exec "$CLAUDE_BIN" "/cutsheet $OUTDIR"
