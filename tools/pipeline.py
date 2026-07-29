#!/usr/bin/env python3
"""リポジトリの状態を見て、進められる工程だけを進める。

人が「次はこれをやって」と指示しなくても、置かれているものを見て
「解析がまだ」「依頼票がまだ」「比較がまだ」を判断して片付ける。
クラウド側から定期的に呼ばれることを想定している。

各工程は何度実行しても同じ結果になる(すでに済んでいれば飛ばす)ので、
途中で落ちても次の実行が続きから進める。

    python3 tools/pipeline.py            # 進められるところまで進める
    python3 tools/pipeline.py --dry-run  # 何をするつもりかだけ出す
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "out"


def log(message: str) -> None:
    print(message, flush=True)


def find_claude() -> str | None:
    explicit = os.environ.get("CLAUDE_BIN")
    if explicit and Path(explicit).is_file():
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    for candidate in [
        Path.home() / ".local/bin/claude",
        Path.home() / ".claude/local/claude",
        Path.home() / ".npm-global/bin/claude",
        Path("/opt/homebrew/bin/claude"),
        Path("/usr/local/bin/claude"),
    ]:
        if candidate.is_file():
            return str(candidate)
    return None


def run(command: list[str], dry_run: bool, timeout: int = 1800) -> bool:
    if dry_run:
        log(f"    (dry-run) {' '.join(str(c) for c in command)}")
        return True
    try:
        result = subprocess.run(
            command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        log(f"    ✗ 時間切れ: {' '.join(str(c) for c in command)}")
        return False
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        log(f"    ✗ 失敗: {detail[-1] if detail else '不明'}")
        return False
    return True


def cut_count(cuts_json: Path) -> int:
    try:
        return len(json.loads(cuts_json.read_text(encoding="utf-8")).get("cuts", []))
    except Exception:
        return 0


def parts_complete(work_dir: Path) -> bool:
    """全カット分の解析結果がそろっているか。"""
    cuts_json = work_dir / "cuts.json"
    if not cuts_json.is_file():
        return False
    total = cut_count(cuts_json)
    if total == 0:
        return False
    parts = work_dir / "parts"
    if not parts.is_dir():
        return False
    return sum(1 for _ in parts.glob("cut_*.json")) >= total


def analyze(work_dir: Path, claude_bin: str, python_bin: str, dry_run: bool) -> bool:
    """キーフレームを解析して cutsheet.json まで作る。"""
    relative = work_dir.relative_to(REPO_ROOT)
    if not parts_complete(work_dir):
        log(f"  → {relative} を解析する")
        if not run(
            [claude_bin, "-p", f"/cutsheet {relative} --parts-only",
             "--permission-mode", "acceptEdits"],
            dry_run,
        ):
            return False
    if not run(
        [python_bin, "tools/build_cutsheet.py", str(relative),
         "--analyzed-by", "claude", "--allow-missing"],
        dry_run,
    ):
        return False
    run([python_bin, "tools/render_cutsheet.py", str(relative / "cutsheet.json")], dry_run)
    log(f"    ✓ {relative}/cutsheet.json")
    return True


def targets_of(work_dir: Path) -> list[int]:
    targets = work_dir / "verify" / "targets.json"
    if not targets.is_file():
        return []
    try:
        return list(json.loads(targets.read_text(encoding="utf-8")).get("cut_no", []))
    except Exception:
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description="進められる工程だけを自動で進める")
    parser.add_argument("--dry-run", action="store_true", help="実行せず、やることだけ出す")
    args = parser.parse_args()

    if not OUT_DIR.is_dir():
        log("out/ が無い。処理対象なし。")
        return 0

    python_bin = sys.executable or "python3"
    claude_bin = find_claude()
    did_something = False

    work_dirs = sorted(d for d in OUT_DIR.iterdir() if d.is_dir() and (d / "cuts.json").is_file())
    if not work_dirs:
        log("処理対象なし。")
        return 0

    # ---- 1. 参照動画の解析 ----
    log("[1/3] 参照カットの解析")
    for work_dir in work_dirs:
        if (work_dir / "cutsheet.json").is_file():
            continue
        if not claude_bin:
            log(f"  ! {work_dir.relative_to(REPO_ROOT)} は未解析だが claude が無いので飛ばす")
            continue
        if analyze(work_dir, claude_bin, python_bin, args.dry_run):
            did_something = True
    if not did_something:
        log("  すべて解析済み")

    # ---- 2. 生成依頼の作成 ----
    log("[2/3] 生成依頼の作成")
    queued = False
    for work_dir in work_dirs:
        cutsheet = work_dir / "cutsheet.json"
        if not cutsheet.is_file():
            continue
        if (work_dir / "verify" / "worksheet.html").is_file():
            continue
        log(f"  → {work_dir.relative_to(REPO_ROOT)} の依頼票を作る")
        if run([python_bin, "tools/make_worksheet.py", str(cutsheet.relative_to(REPO_ROOT))],
               args.dry_run):
            queued = did_something = True
    if not queued:
        log("  作成すべき依頼なし")

    # ---- 3. 生成物の解析と比較 ----
    log("[3/3] 生成物の解析と比較")
    compared = False
    for work_dir in work_dirs:
        verify_dir = work_dir / "verify"
        analysis_dir = verify_dir / "analysis"
        if not analysis_dir.is_dir():
            continue

        pending = [d for d in sorted(analysis_dir.iterdir())
                   if d.is_dir() and (d / "cuts.json").is_file() and not (d / "cutsheet.json").is_file()]
        for generated in pending:
            if not claude_bin:
                log(f"  ! {generated.relative_to(REPO_ROOT)} は未解析だが claude が無い")
                continue
            if analyze(generated, claude_bin, python_bin, args.dry_run):
                compared = did_something = True

        ready = [d for d in analysis_dir.iterdir() if d.is_dir() and (d / "cutsheet.json").is_file()]
        if not ready:
            continue
        # 対象がすべてそろってから比べる。途中で比べると判定が偏る。
        expected = targets_of(work_dir)
        if expected and len(ready) < len(expected):
            log(f"  … {work_dir.relative_to(REPO_ROOT)} は {len(ready)}/{len(expected)} 本。そろうまで待つ")
            continue
        log(f"  → {work_dir.relative_to(REPO_ROOT)} を比較する")
        if run([python_bin, "tools/compare_cutsheets.py", str(work_dir.relative_to(REPO_ROOT))],
               args.dry_run):
            compared = did_something = True
    if not compared:
        log("  比較すべき生成物なし")

    log("")
    log("進めた工程あり" if did_something else "進められる工程は無かった")
    return 0


if __name__ == "__main__":
    sys.exit(main())
