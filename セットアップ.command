#!/bin/bash
# 初回セットアップ。Finder でこのファイルをダブルクリックするだけでよい。
#
#   1. カット検出に使うライブラリを入れる
#   2. 解析に使う Claude Code を入れる
#   3. デスクトップに「カット表」アプリを作る
#
# 2 回目以降に実行しても問題ない(足りないものだけ入れ直す)。
set -uo pipefail

cd "$(dirname "$0")" || exit 1
# shellcheck source=app/lib.sh
source "app/lib.sh"

APP_NAME="${1:-カット表}"
FAILED=0

finish() {
    echo ""
    read -r -p "Enter キーで閉じる" _ 2>/dev/null || true
    exit "$1"
}

echo "════════════════════════════════════════"
echo "  カット表ツール セットアップ"
echo "════════════════════════════════════════"
echo ""

# ---- 1. Python ライブラリ ----
echo "[1/3] カット検出に使うライブラリ"
if venv_ready; then
    echo "      ✅ 準備済み"
else
    if ensure_venv; then
        echo "      ✅ 完了"
    else
        echo "      ⚠️  入れられなかった。カット検出の精度が落ちた状態でも動作はする。"
        FAILED=1
    fi
fi
echo ""

# ---- 2. Claude Code ----
echo "[2/3] 解析に使う Claude Code"
CLAUDE_BIN="$(find_claude || true)"
if [ -n "$CLAUDE_BIN" ]; then
    echo "      ✅ 準備済み($CLAUDE_BIN)"
elif command -v npm >/dev/null 2>&1; then
    echo "      入っていないので入れる…"
    CLAUDE_BIN="$(install_claude || true)"
    if [ -n "$CLAUDE_BIN" ]; then
        echo "      ✅ 完了($CLAUDE_BIN)"
    else
        echo "      ⚠️  インストールに失敗した。上のエラーを見せてもらえれば対応できる。"
        FAILED=1
    fi
else
    echo "      ⚠️  Node.js が入っていないため自動で入れられない。"
    echo "         Claude Code のデスクトップアプリ / IDE 拡張を使う場合はこのままで問題ない。"
    echo "         ターミナルで完結させたい場合は Node.js を入れてから、もう一度これを実行する:"
    echo "           https://nodejs.org/"
fi
echo ""

# ---- 3. デスクトップアプリ ----
echo "[3/3] デスクトップアプリ"
APP_PATH="$(build_desktop_app "$APP_NAME" || true)"
if [ -n "$APP_PATH" ]; then
    echo "      ✅ 作成した: $APP_PATH"
else
    echo "      ⚠️  作成できなかった。"
    FAILED=1
fi
echo ""

echo "════════════════════════════════════════"
if [ -n "$APP_PATH" ]; then
    echo "  準備完了"
    echo ""
    echo "  デスクトップの「$APP_NAME」に参照動画を"
    echo "  ドラッグ&ドロップすれば、カット表ができる。"
    if [ "$FAILED" -ne 0 ]; then
        echo ""
        echo "  ※ 一部そろっていないものがあるが、動作はする。"
    fi
else
    echo "  セットアップは完了しなかった。"
    echo "  上の ⚠️ の内容を見せてもらえれば対応する。"
fi
echo "════════════════════════════════════════"

finish 0
