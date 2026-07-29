#!/bin/bash
# 生成した動画を、参照カットと突き合わせて再現度を測る。
#
#   bash app/verify.sh out/xxx
#
# 事前に out/xxx/verify/generated/cut_NNN.mp4 を置いておく
# (ワークシートは tools/make_worksheet.py が作る)。
#
# 生成物を参照と同じパイプラインに通して解析し、構造として比べる。
# 目で見比べるのではなく、ショットサイズやカメラワークが項目として一致するかを見る。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT" || exit 1

abort() {
    echo ""
    echo "❌ $1"
    exit 1
}

[ $# -ge 1 ] || abort "使い方: bash app/verify.sh <カット表の出力ディレクトリ>"
OUTDIR="$1"
[ -f "$OUTDIR/cutsheet.json" ] || abort "$OUTDIR/cutsheet.json が無い"

GENERATED="$OUTDIR/verify/generated"
[ -d "$GENERATED" ] || abort "$GENERATED が無い。先に make_worksheet.py を実行する"

PY="$(resolved_python)"
[ -n "$PY" ] || abort "python3 が見つからない"
CLAUDE_BIN="$(find_claude || true)"
[ -n "$CLAUDE_BIN" ] || abort "claude が見つからない。セットアップ.command を実行する"

shopt -s nullglob
videos=("$GENERATED"/cut_*.mp4 "$GENERATED"/cut_*.mov "$GENERATED"/cut_*.webm)
shopt -u nullglob
[ ${#videos[@]} -gt 0 ] || abort "$GENERATED に cut_NNN.mp4 が無い"

echo "🔍 再現度を検証する(${#videos[@]} 本)"
echo ""

for video in "${videos[@]}"; do
    name="$(basename "$video")"
    stem="${name%.*}"
    analysis="$OUTDIR/verify/analysis/$stem"

    if [ -f "$analysis/cutsheet.json" ]; then
        echo "  = $name(解析済みなので飛ばす)"
        continue
    fi

    echo "  → $name を解析する"
    # 生成物は 1 カットのはずなので分割はしない。割れたらそれ自体が所見になる。
    if ! "$PY" "$REPO_ROOT/tools/extract_cuts.py" "$video" -o "$analysis" >/dev/null 2>&1; then
        echo "    ⚠️ キーフレーム抽出に失敗した"
        continue
    fi

    if ! "$CLAUDE_BIN" -p "/cutsheet $analysis --parts-only" --permission-mode acceptEdits >/dev/null 2>&1; then
        echo "    ⚠️ 解析に失敗した"
        continue
    fi

    if ! "$PY" "$REPO_ROOT/tools/build_cutsheet.py" "$analysis" --allow-missing >/dev/null 2>&1; then
        echo "    ⚠️ カット表の組み立てに失敗した"
        continue
    fi
    echo "    ✓ 完了"
done

echo ""
"$PY" "$REPO_ROOT/tools/compare_cutsheets.py" "$OUTDIR" || abort "比較に失敗した"

echo ""
echo "レポート: $OUTDIR/verify/report.html"
echo "(iPhone に送れば、参照と生成を並べて確認できる)"
