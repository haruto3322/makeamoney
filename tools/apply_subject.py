#!/usr/bin/env python3
"""汎用スタイルプロンプトの {subject} を差し替えて、別被写体用の一式を書き出す。

    python3 tools/apply_subject.py out/cutsheet.json \
        --subject "a man in his 30s in a black suit" --name suit-man

--action を渡すとアクションまで差し替えられる(元動画のアクションが被写体固有で
流用できない場合に使う)。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w-]+", "-", text, flags=re.UNICODE).strip("-").lower()
    return slug[:40] or "custom"


def fill(template: str, subject: str, action: str | None) -> str:
    filled = template.replace("{subject}", subject)
    if action is not None:
        filled = filled.replace("{action}", action)
    return filled


def main() -> int:
    parser = argparse.ArgumentParser(
        description="汎用プロンプトの {subject} を差し替えて別被写体用のプロンプト一式を作る",
    )
    parser.add_argument("cutsheet", type=Path, help="cutsheet.json のパス")
    parser.add_argument("--subject", required=True, help="差し込む被写体(英語推奨)")
    parser.add_argument("--action", help="アクションも差し替える場合に指定")
    parser.add_argument("--name", help="出力ファイル名に使う識別子(既定: subject から生成)")
    args = parser.parse_args()

    if not args.cutsheet.is_file():
        print(f"error: {args.cutsheet} が見つからない", file=sys.stderr)
        return 1

    data = json.loads(args.cutsheet.read_text(encoding="utf-8"))
    cuts = data.get("cuts", [])
    if not cuts:
        print(f"error: {args.cutsheet} に cuts が入っていない", file=sys.stderr)
        return 1

    name = slugify(args.name or args.subject)
    outdir = args.cutsheet.parent
    rows = []
    missing_placeholder = []

    for cut in cuts:
        template = cut.get("prompt_generic") or ""
        if not template:
            continue
        if "{subject}" not in template:
            missing_placeholder.append(cut.get("cut_no"))
        rows.append({
            "cut_no": cut.get("cut_no", ""),
            "start_tc": cut.get("start_tc", ""),
            "duration_sec": cut.get("duration_sec", ""),
            "prompt": fill(template, args.subject, args.action),
        })

    if not rows:
        print("error: prompt_generic が入っているカットが無い", file=sys.stderr)
        return 1

    md_lines = [
        f"# 差し替えプロンプト — {args.subject}",
        "",
        f"元カット表: `{args.cutsheet.name}` / {len(rows)} カット",
        "",
    ]
    for row in rows:
        md_lines.append(f"## Cut {row['cut_no']} — {row['start_tc']} ({row['duration_sec']}s)")
        md_lines.append("")
        md_lines.append("```text")
        md_lines.append(row["prompt"])
        md_lines.append("```")
        md_lines.append("")

    md_path = outdir / f"prompts_{name}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"書き出し: {md_path}")

    csv_path = outdir / f"prompts_{name}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["cut_no", "start_tc", "duration_sec", "prompt"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"書き出し: {csv_path}")

    if missing_placeholder:
        print(
            f"warn: {missing_placeholder} のプロンプトに {{subject}} が入っていない。"
            "被写体が抽象化されていない可能性がある",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
