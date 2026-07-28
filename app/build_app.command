#!/bin/bash
# デスクトップに「カット表.app」を作る。Finder でこのファイルをダブルクリックすればよい。
#
# 別名で作りたい場合はターミナルから:  ./app/build_app.command マイツール
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="${1:-カット表}"
DEST="$HOME/Desktop/${APP_NAME}.app"

abort() {
    echo ""
    echo "❌ $1"
    echo ""
    read -r -p "Enter キーで閉じる" _
    exit 1
}

if [ "$(uname)" != "Darwin" ]; then
    abort "このスクリプトは macOS 専用。"
fi
command -v osacompile >/dev/null 2>&1 || abort "osacompile が見つからない。Xcode Command Line Tools を入れる:
   xcode-select --install"

chmod +x "$SCRIPT_DIR/cutsheet.sh"

TMPDIR_BUILD="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_BUILD"' EXIT

# リポジトリの場所をアプリに焼き込む(アプリはデスクトップに置かれ、リポジトリから離れるため)。
sed "s|__REPO_ROOT__|${REPO_ROOT}|g" "$SCRIPT_DIR/droplet.applescript" > "$TMPDIR_BUILD/droplet.applescript"

rm -rf "$DEST"
osacompile -o "$DEST" "$TMPDIR_BUILD/droplet.applescript" || abort "アプリのビルドに失敗した"

echo "✅ 作成した: $DEST"
echo ""
echo "使い方: デスクトップの「${APP_NAME}」に参照動画をドラッグ&ドロップする。"
echo "        (ダブルクリックすると動画の選択ダイアログが出る)"
echo ""
echo "参照先リポジトリ: $REPO_ROOT"
echo "このフォルダを移動したら、もう一度このスクリプトを実行してアプリを作り直す。"
echo ""
read -r -p "Enter キーで閉じる" _
