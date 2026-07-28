#!/usr/bin/env python3
"""cutsheet.json を人が読む形式(Markdown / CSV)に整形する。

解析と文章生成は Claude が担当し、表の組み立てはこのスクリプトが決定的に行う。
そうすることで出力形式を変えてもプロンプト本文がぶれない。

    python3 tools/render_cutsheet.py out/cutsheet.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

CSV_COLUMNS = [
    "cut_no", "start_tc", "end_tc", "duration_sec",
    "shot_size", "angle", "movement", "lens_feel",
    "subject", "action", "position_in_frame",
    "composition", "lighting", "color_grade", "environment", "mood",
    "audio_notes", "transition_out",
    "prompt_exact", "prompt_generic",
]


def flatten(cut: dict) -> dict:
    camera = cut.get("camera") or {}
    subject = cut.get("subject") or {}
    return {
        "cut_no": cut.get("cut_no", ""),
        "start_tc": cut.get("start_tc", ""),
        "end_tc": cut.get("end_tc", ""),
        "duration_sec": cut.get("duration_sec", ""),
        "shot_size": camera.get("shot_size", ""),
        "angle": camera.get("angle", ""),
        "movement": camera.get("movement", ""),
        "lens_feel": camera.get("lens_feel", ""),
        "subject": subject.get("description", ""),
        "action": subject.get("action", ""),
        "position_in_frame": subject.get("position_in_frame", ""),
        "composition": cut.get("composition", ""),
        "lighting": cut.get("lighting", ""),
        "color_grade": cut.get("color_grade", ""),
        "environment": cut.get("environment", ""),
        "mood": cut.get("mood", ""),
        "audio_notes": cut.get("audio_notes", ""),
        "transition_out": cut.get("transition_out", ""),
        "prompt_exact": cut.get("prompt_exact", ""),
        "prompt_generic": cut.get("prompt_generic", ""),
    }


def escape_cell(value: object) -> str:
    """Markdown の表セル用に改行とパイプを潰す。"""
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_markdown(data: dict, json_path: Path) -> str:
    cuts = data.get("cuts", [])
    lines: list[str] = []

    lines.append(f"# カット表 — {data.get('source', '(unknown)')}")
    lines.append("")
    meta = [
        f"尺 {data.get('duration_sec', '?')}s",
        f"カット数 {len(cuts)}",
    ]
    if data.get("target_model"):
        meta.append(f"プロンプト書式 {data['target_model']}")
    if data.get("generated_at"):
        meta.append(f"生成 {data['generated_at']}")
    lines.append(" / ".join(meta))
    lines.append("")

    if data.get("overall"):
        overall = data["overall"]
        lines.append("## 全体所感")
        lines.append("")
        for label, key in [
            ("ジャンル・構成", "structure"),
            ("撮影スタイル", "style"),
            ("カラー", "color_grade"),
            ("編集リズム", "editing"),
        ]:
            if overall.get(key):
                lines.append(f"- **{label}**: {overall[key]}")
        lines.append("")

    lines.append("## 一覧")
    lines.append("")
    lines.append("| # | IN | 尺 | ショット | カメラ | 内容 |")
    lines.append("|---|---|---|---|---|---|")
    for cut in cuts:
        row = flatten(cut)
        summary = row["action"] or row["subject"] or row["environment"]
        lines.append(
            f"| {row['cut_no']} | {row['start_tc']} | {row['duration_sec']}s "
            f"| {escape_cell(row['shot_size'])} | {escape_cell(row['movement'])} "
            f"| {escape_cell(summary)} |"
        )
    lines.append("")

    lines.append("## カット詳細")
    lines.append("")
    for cut in cuts:
        row = flatten(cut)
        lines.append(
            f"### Cut {row['cut_no']} — {row['start_tc']} → {row['end_tc']} "
            f"({row['duration_sec']}s)"
        )
        lines.append("")
        thumbnail = cut.get("thumbnail")
        if thumbnail:
            lines.append(f"![cut {row['cut_no']}]({thumbnail})")
            lines.append("")
        lines.append("| 項目 | 内容 |")
        lines.append("|---|---|")
        for label, key in [
            ("被写体", "subject"),
            ("アクション", "action"),
            ("画面内の位置", "position_in_frame"),
            ("ショットサイズ", "shot_size"),
            ("アングル", "angle"),
            ("カメラワーク", "movement"),
            ("レンズ感", "lens_feel"),
            ("構図", "composition"),
            ("照明", "lighting"),
            ("カラー", "color_grade"),
            ("場所・美術", "environment"),
            ("ムード", "mood"),
            ("音", "audio_notes"),
            ("次への繋ぎ", "transition_out"),
        ]:
            if row[key]:
                lines.append(f"| {label} | {escape_cell(row[key])} |")
        lines.append("")

        if row["prompt_exact"]:
            lines.append("**完全再現プロンプト**")
            lines.append("")
            lines.append("```text")
            lines.append(row["prompt_exact"])
            lines.append("```")
            lines.append("")
        if row["prompt_generic"]:
            lines.append("**汎用スタイルプロンプト**(`{subject}` を差し替えて使う)")
            lines.append("")
            lines.append("```text")
            lines.append(row["prompt_generic"])
            lines.append("```")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"元データ: `{json_path.name}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="cutsheet.json を Markdown / CSV に整形する")
    parser.add_argument("cutsheet", type=Path, help="cutsheet.json のパス")
    parser.add_argument(
        "--format", default="md,csv",
        help="出力形式をカンマ区切りで指定(md / csv、既定: md,csv)",
    )
    args = parser.parse_args()

    if not args.cutsheet.is_file():
        print(f"error: {args.cutsheet} が見つからない", file=sys.stderr)
        return 1

    data = json.loads(args.cutsheet.read_text(encoding="utf-8"))
    cuts = data.get("cuts", [])
    if not cuts:
        print(f"error: {args.cutsheet} に cuts が入っていない", file=sys.stderr)
        return 1

    formats = {f.strip() for f in args.format.split(",") if f.strip()}
    outdir = args.cutsheet.parent
    stem = args.cutsheet.stem

    if "md" in formats:
        md_path = outdir / f"{stem}.md"
        md_path.write_text(render_markdown(data, args.cutsheet), encoding="utf-8")
        print(f"書き出し: {md_path}")

    if "csv" in formats:
        csv_path = outdir / f"{stem}.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for cut in cuts:
                writer.writerow(flatten(cut))
        print(f"書き出し: {csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
