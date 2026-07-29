#!/bin/bash
# 合議を自動で回し続ける設定。Finder でダブルクリックすればよい。
#
# 既定は 5 時間ごと。Claude の利用枠が 5 時間単位で切り替わるので、
# 枠ごとに 1 回まわして寝かせない、という考え方。
#
#   ./app/install_council.command           … 5 時間ごと
#   ./app/install_council.command 3         … 3 時間ごと
#   ./app/install_council.command --uninstall
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

LABEL="com.cutsheet.council"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

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
    echo "✅ 自動実行を解除した(これまでの議事録は council/log に残る)。"
    finish 0
fi

HOURS="${1:-5}"
if ! printf '%s' "$HOURS" | grep -qE '^[0-9]+$' || [ "$HOURS" -lt 1 ]; then
    echo "❌ 間隔は 1 以上の整数(時間)で指定する。"
    finish 1
fi
INTERVAL=$((HOURS * 3600))

echo "════════════════════════════════════════"
echo "  合議の自動実行を設定"
echo "════════════════════════════════════════"
echo ""

echo "[1/2] 必要なものを確認"
CLAUDE_BIN="$(find_claude || true)"
if [ -n "$CLAUDE_BIN" ]; then
    echo "      ✅ Claude Code($CLAUDE_BIN)"
else
    echo "      ❌ Claude Code が見つからない。先に「セットアップ」を実行する。"
    finish 1
fi
if [ -f "$REPO_ROOT/council/agenda.md" ]; then
    echo "      ✅ 議題(council/agenda.md)"
else
    echo "      ⚠️  council/agenda.md が無い。実行前に用意する。"
fi
echo ""

echo "[2/2] ${HOURS} 時間ごとの自動実行を登録"
chmod +x "$SCRIPT_DIR/council.sh"
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
        <string>$SCRIPT_DIR/council.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>$INTERVAL</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$REPO_ROOT/.council.log</string>
    <key>StandardErrorPath</key>
    <string>$REPO_ROOT/.council.log</string>
</dict>
</plist>
PLIST_EOF

launchctl unload -w "$PLIST" 2>/dev/null
if launchctl load -w "$PLIST" 2>/dev/null; then
    echo "      ✅ 登録した(登録直後に 1 回目が走る)"
else
    echo "      ⚠️  登録に失敗した。ターミナルで次を実行して結果を見せる:"
    echo "         launchctl load -w '$PLIST'"
fi
echo ""

echo "════════════════════════════════════════"
echo "  これから"
echo ""
echo "  ${HOURS} 時間ごとに 5 人の助言役が議論し、議長が結論を出す。"
echo ""
echo "  ・議題を変える:  council/agenda.md を書き換える"
echo "  ・役割を変える:  council/roles/*.md を書き換える"
echo "  ・最新の結論:    council/latest.md"
echo "  ・過去の議事録:  council/log/"
echo "  ・動作ログ:      $REPO_ROOT/.council.log"
echo "  ・すぐ 1 回試す: ./app/council.sh"
echo "  ・解除:          ./app/install_council.command --uninstall"
echo "════════════════════════════════════════"

finish 0
