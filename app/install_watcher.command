#!/bin/bash
# iPhone 連携の設定。iCloud Drive に受信/完成フォルダを作り、Mac が 1 分ごとに
# 受信フォルダを見張るようにする。Finder でダブルクリックすればよい。
#
# 解除したいときは、ターミナルから:  ./app/install_watcher.command --uninstall
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

LABEL="com.cutsheet.watch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ICLOUD="$HOME/Library/Mobile Documents/com~apple~CloudDocs"
INBOX="$ICLOUD/カット表/受信"
OUTBOX="$ICLOUD/カット表/完成"

finish() {
    echo ""
    read -r -p "Enter キーで閉じる" _ 2>/dev/null || true
    exit "$1"
}

if [ "$(uname)" != "Darwin" ]; then
    echo "❌ macOS 専用。"
    finish 1
fi

if [ "${1:-}" = "--uninstall" ]; then
    launchctl unload -w "$PLIST" 2>/dev/null
    rm -f "$PLIST"
    echo "✅ 見張りを解除した(iCloud のフォルダとファイルはそのまま残る)。"
    finish 0
fi

echo "════════════════════════════════════════"
echo "  iPhone 連携の設定"
echo "════════════════════════════════════════"
echo ""

if [ ! -d "$ICLOUD" ]; then
    echo "❌ iCloud Drive が有効になっていない。"
    echo "   システム設定 → Apple ID → iCloud → iCloud Drive をオンにする。"
    finish 1
fi

mkdir -p "$INBOX" "$OUTBOX"
echo "[1/3] iCloud にフォルダを用意した"
echo "      受信: $INBOX"
echo "      完成: $OUTBOX"
echo ""

echo "[2/3] 必要なものを確認"
if venv_ready; then
    echo "      ✅ ライブラリ"
else
    echo "      ⚠️  ライブラリが未導入。先に「セットアップ」を実行する。"
fi
CLAUDE_BIN="$(find_claude || true)"
if [ -n "$CLAUDE_BIN" ]; then
    echo "      ✅ Claude Code($CLAUDE_BIN)"
else
    echo "      ⚠️  Claude Code が見つからない。無人処理には CLI が必要。"
    echo "         先に「セットアップ」を実行する。"
fi
echo ""

echo "[3/3] 1 分ごとの見張りを登録"
chmod +x "$SCRIPT_DIR/watch.sh"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPT_DIR/watch.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>60</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$REPO_ROOT/.watch.log</string>
    <key>StandardErrorPath</key>
    <string>$REPO_ROOT/.watch.log</string>
</dict>
</plist>
PLIST_EOF

launchctl unload -w "$PLIST" 2>/dev/null
if launchctl load -w "$PLIST" 2>/dev/null; then
    echo "      ✅ 登録した"
else
    echo "      ⚠️  登録に失敗した。ターミナルで次を実行して結果を見せる:"
    echo "         launchctl load -w '$PLIST'"
fi
echo ""

echo "════════════════════════════════════════"
echo "  使い方"
echo ""
echo "  iPhone の「ファイル」アプリ →"
echo "    iCloud Drive → カット表 → 受信"
echo "  に動画を入れる。"
echo ""
echo "  Mac が電源オンでネットに繋がっていれば、"
echo "  数分後に「完成」フォルダに HTML が現れる。"
echo "  iPhone でタップすればカット表が読める。"
echo ""
echo "  ・Mac がスリープ中は処理されない(復帰後に処理する)"
echo "  ・動作ログ: $REPO_ROOT/.watch.log"
echo "  ・解除: ./app/install_watcher.command --uninstall"
echo "════════════════════════════════════════"

finish 0
