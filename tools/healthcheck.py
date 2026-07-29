#!/usr/bin/env python3
"""流れが止まっていないかを調べ、STATUS.md に書き出す。

無人で回す仕組みの最悪の failure mode は「止まったまま誰も気づかない」こと。
どこで詰まっているかを名指しし、次に何をすればよいかまで書く。

    python3 tools/healthcheck.py           # STATUS.md を更新する
    python3 tools/healthcheck.py --quiet   # 異常があるときだけ出力する

異常があれば終了コード 1 を返すので、呼び出し側が通知の要否を判断できる。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 依頼票が拾われないまま放置されている、とみなす時間。
QUEUE_STALE_HOURS = 12
# クラウド側の定期処理は 1 時間ごとなので、これを超えたら動いていない。
ANALYSIS_STALE_HOURS = 3


def committed_at(path: Path) -> datetime | None:
    """git に記録された最終更新時刻。

    ファイルの mtime は clone しなおすと現在時刻になってしまい、
    クラウド側では経過時間の判断に使えない。
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(path.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        stamp = result.stdout.strip()
        if stamp:
            return datetime.fromtimestamp(int(stamp), tz=timezone.utc)
    except Exception:
        pass
    return None


def hours_since(moment: datetime | None) -> float | None:
    if moment is None:
        return None
    return (datetime.now(timezone.utc) - moment).total_seconds() / 3600


def check() -> tuple[list[str], list[str]]:
    """(異常, 正常な状態の記録) を返す。"""
    problems: list[str] = []
    notes: list[str] = []

    # ---- 生成の失敗が報告されている ----
    failed_dir = REPO_ROOT / "work" / "failed"
    failures = sorted(failed_dir.glob("*.json")) if failed_dir.is_dir() else []
    for failure in failures:
        reason_file = failure.with_suffix(".md")
        reason = "(理由が書かれていない)"
        if reason_file.is_file():
            reason = reason_file.read_text(encoding="utf-8").strip().splitlines()
            reason = reason[0] if reason else "(空)"
        problems.append(
            f"**生成に失敗している**: `{failure.name}` — {reason}\n"
            f"  → Antigravity 側の手順(AGENTS.md)か Flow の画面が変わっている可能性"
        )

    # ---- 依頼票が拾われていない ----
    queue_dir = REPO_ROOT / "work" / "queue"
    pending = sorted(queue_dir.glob("*.json")) if queue_dir.is_dir() else []
    stale = []
    for task in pending:
        age = hours_since(committed_at(task))
        if age is not None and age > QUEUE_STALE_HOURS:
            stale.append((task.name, age))
    if stale:
        oldest = max(age for _, age in stale)
        problems.append(
            f"**依頼票が {len(stale)} 件、{oldest:.0f} 時間以上放置されている**\n"
            f"  → Antigravity が拾っていない。Mac で Antigravity を開き、"
            f"「work/queue の依頼票を AGENTS.md に従って処理して」と頼む"
        )
    elif pending:
        notes.append(f"未処理の依頼票 {len(pending)} 件(Antigravity の作業待ち)")

    # ---- クラウド側の処理が進んでいない ----
    out_dir = REPO_ROOT / "out"
    unanalyzed = []
    if out_dir.is_dir():
        for work_dir in sorted(out_dir.iterdir()):
            cuts = work_dir / "cuts.json"
            if not work_dir.is_dir() or not cuts.is_file():
                continue
            if (work_dir / "cutsheet.json").is_file():
                continue
            age = hours_since(committed_at(cuts))
            if age is not None and age > ANALYSIS_STALE_HOURS:
                unanalyzed.append((work_dir.name, age))
    if unanalyzed:
        names = ", ".join(name for name, _ in unanalyzed)
        problems.append(
            f"**{len(unanalyzed)} 件が解析されないまま {max(a for _, a in unanalyzed):.0f} 時間**: {names}\n"
            f"  → クラウド側の定期処理(1 時間ごと)が失敗している。"
            f"Routine の実行結果を確認する"
        )

    # ---- 検証が途中で止まっている ----
    if out_dir.is_dir():
        for work_dir in sorted(out_dir.iterdir()):
            verify = work_dir / "verify"
            targets_file = verify / "targets.json"
            if not targets_file.is_file():
                continue
            if (verify / "report.html").is_file():
                continue
            try:
                expected = len(json.loads(targets_file.read_text(encoding="utf-8")).get("cut_no", []))
            except Exception:
                continue
            analysis = verify / "analysis"
            arrived = sum(1 for d in analysis.iterdir() if d.is_dir()) if analysis.is_dir() else 0
            age = hours_since(committed_at(targets_file))
            if arrived < expected and age is not None and age > QUEUE_STALE_HOURS:
                problems.append(
                    f"**検証が {arrived}/{expected} 本で止まっている**: {work_dir.name}\n"
                    f"  → 残りを Flow で生成して、キーフレームを commit する"
                )
            elif arrived < expected:
                notes.append(f"{work_dir.name}: 生成待ち {arrived}/{expected} 本")

    # ---- 何も進んでいない状態そのものは異常ではない ----
    if out_dir.is_dir():
        done = sum(1 for d in out_dir.iterdir() if d.is_dir() and (d / "cutsheet.json").is_file())
        if done:
            notes.append(f"カット表ができている動画: {done} 本")
    if not out_dir.is_dir() or not any(out_dir.iterdir()):
        notes.append("処理対象がまだ無い(参照動画をドロップすると始まる)")

    return problems, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="流れが止まっていないかを調べる")
    parser.add_argument("--quiet", action="store_true", help="異常があるときだけ出力する")
    parser.add_argument("--no-write", action="store_true", help="STATUS.md を書かない")
    args = parser.parse_args()

    problems, notes = check()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = ["# 状態", "", f"最終確認: {now}", ""]
    if problems:
        lines += ["## ⚠️ 止まっているところ", ""]
        for problem in problems:
            lines += [f"- {problem}", ""]
    else:
        lines += ["## ✅ 異常なし", "", "流れは止まっていない。", ""]
    if notes:
        lines += ["## 状況", ""]
        lines += [f"- {note}" for note in notes]
        lines += [""]
    lines += [
        "---",
        "",
        "この内容は `tools/healthcheck.py` が自動で書いている。",
        "止まっているところがあれば、その行をそのまま貼れば診断できる。",
        "",
    ]

    if not args.no_write:
        (REPO_ROOT / "STATUS.md").write_text("\n".join(lines), encoding="utf-8")

    if problems:
        print("⚠️ 止まっているところがある:")
        for problem in problems:
            print("  - " + problem.replace("**", "").replace("\n", "\n  "))
        return 1

    if not args.quiet:
        print("✅ 異常なし")
        for note in notes:
            print("  - " + note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
