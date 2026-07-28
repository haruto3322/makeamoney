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

# ---- Python と依存ライブラリの用意 ----
PYTHON_BIN="$(command -v python3 || true)"
[ -n "$PYTHON_BIN" ] || abort "python3 が見つからない。Xcode Command Line Tools か Homebrew の Python を入れる:
   xcode-select --install"

VENV="$REPO_ROOT/.venv"

# 「入っているか」の判定は実際に import できるかどうかだけで行う。
# インストール済みフラグのような間接的な目印は、途中で失敗した状態を
# 見逃してしまうので使わない。
venv_ready() {
    [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import scenedetect" >/dev/null 2>&1
}

install_deps() {
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install -r "$REPO_ROOT/requirements.txt"
}

if ! venv_ready; then
    echo "セットアップ中… 必要なライブラリを入れる(数分かかることがある)"
    if [ ! -x "$VENV/bin/python" ]; then
        "$PYTHON_BIN" -m venv "$VENV"
    fi
    install_deps
    if ! venv_ready; then
        # 仮想環境が壊れている可能性があるので、作り直して一度だけやり直す。
        echo ""
        echo "仮想環境を作り直して再試行する…"
        rm -rf "$VENV"
        "$PYTHON_BIN" -m venv "$VENV" && install_deps
    fi
    echo ""
    if venv_ready; then
        echo "✅ セットアップ完了"
    else
        echo "⚠️  ライブラリを入れられなかった。精度の落ちる簡易検出で続行する。"
        echo "    上のエラーを見せてもらえれば原因を特定できる。"
    fi
    echo ""
fi

if [ -x "$VENV/bin/python" ]; then
    PY="$VENV/bin/python"
else
    PY="$PYTHON_BIN"
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
    echo "──────────────────────────────────────────"
    echo "キーフレームの書き出しまで終わった。解析は Claude Code で行う。"
    echo ""
    echo "【A】Claude Code のアプリ / IDE 拡張を使う場合"
    echo "    次のフォルダを開いて、下の1行を貼り付ける:"
    echo "      $REPO_ROOT"
    echo ""
    echo "      /cutsheet $OUTDIR"
    echo ""
    echo "【B】ターミナルで使う場合(claude コマンドが必要)"
    echo "    まだ入れていなければ:"
    echo "      npm install -g @anthropic-ai/claude-code"
    echo "    入れたあと:"
    echo "      cd $REPO_ROOT && claude \"/cutsheet $OUTDIR\""
    echo ""
    echo "手順の詳細: https://code.claude.com/docs"
    echo "──────────────────────────────────────────"
    exit 0
fi

echo "🤖 Claude Code に解析を引き継ぐ…"
echo ""
exec "$CLAUDE_BIN" "/cutsheet $OUTDIR"
