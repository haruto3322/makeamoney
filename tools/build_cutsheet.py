#!/usr/bin/env python3
"""カットごとの解析結果(parts/)と cuts.json を突き合わせて cutsheet.json を組み立てる。

タイムコードや尺は cuts.json 側の値をそのまま使うので、Claude が数値を書き写す
必要がない(書き写しミスが原理的に起きない)。あわせて、汎用プロンプトに被写体の
identity が残っていないかを機械的にチェックする。

    python3 tools/build_cutsheet.py out/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ANALYSIS_KEYS = [
    "subject", "camera", "composition", "lighting", "color_grade",
    "environment", "mood", "audio_notes", "transition_out",
    "prompt_exact", "prompt_generic",
]

# 汎用プロンプトに残っていてはいけない、被写体を特定する語。
# {subject} に含めるべき情報がスタイル側に漏れていないかの機械チェック用。
IDENTITY_PATTERNS = [
    r"\bwoman\b", r"\bwomen\b", r"\bman\b", r"\bmen\b", r"\bgirl\b", r"\bboy\b",
    r"\blady\b", r"\bguy\b", r"\bmale\b", r"\bfemale\b", r"\bperson\b", r"\bpeople\b",
    r"\bshe\b", r"\bher\b", r"\bhers\b", r"\bhe\b", r"\bhis\b", r"\bhim\b",
    r"\bjapanese\b", r"\bkorean\b", r"\bchinese\b", r"\basian\b", r"\bcaucasian\b",
    r"\bblack\b\s+\b(?:hair|man|woman)\b", r"\bblonde\b", r"\bbrunette\b",
    r"\bteen\b", r"\belderly\b", r"\bmodel\b",
    r"\b\d{1,2}s?[- ]year[- ]old\b", r"\bin (?:her|his) \d0s\b",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pick_thumbnail(frames: list[str]) -> str | None:
    if not frames:
        return None
    return frames[len(frames) // 2]


def check_identity_leak(prompt: str) -> list[str]:
    lowered = prompt.lower()
    # {subject} プレースホルダ自体は当然マッチさせない。
    masked = lowered.replace("{subject}", " ").replace("{action}", " ")
    hits = []
    for pattern in IDENTITY_PATTERNS:
        match = re.search(pattern, masked)
        if match:
            hits.append(match.group(0).strip())
    return sorted(set(hits))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="parts/ の解析結果と cuts.json から cutsheet.json を組み立てる",
    )
    parser.add_argument("outdir", type=Path, help="extract_cuts.py の出力ディレクトリ")
    parser.add_argument("--target", help="プロンプトの想定生成モデル(veo / runway / kling / generic)")
    parser.add_argument(
        "--analyzed-by",
        help="解析したエージェント名(claude / antigravity など)。"
             "参照と生成物を別のモデルで解析すると比較が成立しないため記録する",
    )
    parser.add_argument(
        "--allow-missing", action="store_true",
        help="解析済みでないカットがあっても中断しない(途中経過の確認用)",
    )
    args = parser.parse_args()

    cuts_path = args.outdir / "cuts.json"
    parts_dir = args.outdir / "parts"
    if not cuts_path.is_file():
        print(f"error: {cuts_path} が無い。先に extract_cuts.py を実行する", file=sys.stderr)
        return 1
    if not parts_dir.is_dir():
        print(f"error: {parts_dir} が無い。カットごとの解析結果を置く", file=sys.stderr)
        return 1

    base = load_json(cuts_path)
    merged_cuts = []
    missing = []
    warnings: list[str] = []

    for cut in base.get("cuts", []):
        cut_no = cut["cut_no"]
        part_path = parts_dir / f"cut_{cut_no:03d}.json"
        if not part_path.is_file():
            missing.append(cut_no)
            continue

        analysis = load_json(part_path)
        record = {
            "cut_no": cut_no,
            "start_tc": cut["start_tc"],
            "end_tc": cut["end_tc"],
            "duration_sec": cut["duration_sec"],
            "thumbnail": pick_thumbnail(cut.get("frames", [])),
            "frames": cut.get("frames", []),
        }
        for key in ANALYSIS_KEYS:
            if key in analysis:
                record[key] = analysis[key]
        merged_cuts.append(record)

        generic = record.get("prompt_generic") or ""
        if generic:
            if "{subject}" not in generic:
                warnings.append(f"cut {cut_no}: prompt_generic に {{subject}} が無い")
            leaks = check_identity_leak(generic)
            if leaks:
                warnings.append(
                    f"cut {cut_no}: prompt_generic に被写体を特定する語が残っている -> {', '.join(leaks)}"
                )
        else:
            warnings.append(f"cut {cut_no}: prompt_generic が空")
        if not record.get("prompt_exact"):
            warnings.append(f"cut {cut_no}: prompt_exact が空")

    if missing:
        message = f"未解析のカット: {missing}"
        if args.allow_missing:
            print(f"warn: {message}", file=sys.stderr)
        else:
            print(f"error: {message}(--allow-missing で無視できる)", file=sys.stderr)
            return 1

    if not merged_cuts:
        print("error: 解析済みのカットが 1 つも無い", file=sys.stderr)
        return 1

    payload = {
        "source": base.get("source"),
        "duration_sec": base.get("duration_sec"),
        "fps": base.get("fps"),
        "width": base.get("width"),
        "height": base.get("height"),
        "detector": base.get("detector"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cuts": merged_cuts,
    }
    if args.target:
        payload["target_model"] = args.target
    if args.analyzed_by:
        payload["analyzed_by"] = args.analyzed_by

    overall_path = parts_dir / "overall.json"
    if overall_path.is_file():
        payload["overall"] = load_json(overall_path)

    out_path = args.outdir / "cutsheet.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"書き出し: {out_path}({len(merged_cuts)} カット)")

    for warning in warnings:
        print(f"warn: {warning}", file=sys.stderr)
    if warnings:
        print(
            f"\n{len(warnings)} 件の警告。汎用プロンプトを直したら再実行する。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
