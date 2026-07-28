#!/bin/bash
# デスクトップアプリだけを作り直す。通常は repo 直下の「セットアップ.command」を使えばよい。
#
# 別名で作りたい場合:  ./app/build_app.command マイツール
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

APP_NAME="${1:-カット表}"
APP_PATH="$(build_desktop_app "$APP_NAME" || true)"

echo ""
if [ -n "$APP_PATH" ]; then
    echo "✅ 作成した: $APP_PATH"
    echo ""
    echo "使い方: デスクトップの「${APP_NAME}」に参照動画をドラッグ&ドロップする。"
    echo "        (ダブルクリックすると動画の選択ダイアログが出る)"
    echo ""
    echo "参照先リポジトリ: $REPO_ROOT"
    echo "このフォルダを移動したら、もう一度実行してアプリを作り直す。"
else
    echo "❌ アプリを作れなかった。"
fi
echo ""
read -r -p "Enter キーで閉じる" _ 2>/dev/null || true
