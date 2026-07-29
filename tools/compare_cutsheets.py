#!/usr/bin/env python3
"""参照カットと、そのプロンプトで生成した動画を突き合わせる。

プロンプトが狙った映像を再現できているかを、印象ではなく項目ごとに判定する。
機械的に判定できる項目(ショットサイズ・カメラワーク・尺)は Python が比べ、
文章で書かれた項目(照明・カラー・構図)は並べて人が見られるようにする。

    python3 tools/compare_cutsheets.py out/xxx

out/xxx/verify/report.html ができる。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_cutsheet import HTML_SCRIPT, HTML_STYLE, data_uri, flatten  # noqa: E402

# 同種のズレがこの数以上のカットで出たら「体系的」とみなし、修正対象とする。
SYSTEMATIC_THRESHOLD = 2

# 尺のずれをどこまで許すか(秒)。生成 AI 側の尺は指定どおりにならないことが多い。
DURATION_TOLERANCE = 1.0

# 寄りから引きへ並べた尺度。隣り合うものは「近い」と判定する。
SHOT_SIZES = ["ECU", "CU", "MCU", "MS", "FS", "WS", "EWS"]
# 照合は長いものから試す。短いものを先に試すと MCU が CU に食われる。
SHOT_SIZE_MATCH_ORDER = sorted(SHOT_SIZES + ["INSERT"], key=len, reverse=True)

MOVEMENT_KEYS = [
    "static", "pan", "tilt", "dolly", "truck", "zoom", "handheld",
    "gimbal", "steadicam", "orbit", "arc", "crane", "push", "pull",
]

# 表記ゆれ(eye-level / eye level)は norm() が空白に寄せるので、空白側だけ持つ。
ANGLE_KEYS = ["eye level", "low", "high", "overhead", "dutch", "pov", "over the shoulder"]

EXTRA_STYLE = """
.pair { display:grid; grid-template-columns:1fr 1fr; gap:.4rem; margin-bottom:.6rem; }
.pair figure { margin:0; }
.pair img { width:100%; height:auto; display:block; border-radius:8px; background:#000; }
.pair figcaption { font-size:.72rem; color:var(--muted); text-align:center; padding:.2rem 0; }
table.cmp { width:100%; border-collapse:collapse; font-size:.82rem; margin-bottom:.8rem; }
table.cmp th, table.cmp td { text-align:left; padding:.35rem .4rem; border-bottom:1px solid var(--line);
                             vertical-align:top; }
table.cmp th { color:var(--muted); font-weight:500; white-space:nowrap; width:5.5rem; }
.v-ok { color:#3a7d44; font-weight:600; }
.v-near { color:#a8791f; font-weight:600; }
.v-ng { color:#b4442e; font-weight:600; }
@media (prefers-color-scheme: dark) {
  .v-ok { color:#7ec98c; } .v-near { color:#e3bd6b; } .v-ng { color:#ef8e78; }
}
.summary { background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:.9rem 1rem; margin-bottom:1.25rem; font-size:.88rem; }
.summary h2 { margin:0 0 .5rem; font-size:.95rem; }
.summary li { margin:.25rem 0; }
.prose { font-size:.8rem; }
.prose b { color:var(--muted); font-weight:500; }
"""


def norm(text: object) -> str:
    """ハイフン・アンダースコアを空白に寄せ、表記ゆれを潰す。"""
    lowered = re.sub(r"[-_/]+", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", lowered).strip()


def tokens(text: object, keys: list[str]) -> set[str]:
    """語彙表に載っている語だけを拾って集合にする。

    語頭で境界を見るので "panning" や "dollying" も拾えるが、"slow" の中の
    "low" のように語の途中には反応しない。
    """
    normalized = norm(text)
    return {key for key in keys if re.search(r"\b" + re.escape(key), normalized)}


def shot_size_of(text: object) -> str:
    upper = re.sub(r"[-_/]+", " ", str(text or "")).upper()
    for size in SHOT_SIZE_MATCH_ORDER:
        if re.search(r"\b" + size + r"\b", upper):
            return size
    return upper.strip()


def compare_field(name: str, reference: object, generated: object) -> tuple[str, str]:
    """(判定, 補足) を返す。判定は ok / near / ng / unknown。"""
    if not str(reference or "").strip() or not str(generated or "").strip():
        return "unknown", "どちらかが空"

    if name == "shot_size":
        a, b = shot_size_of(reference), shot_size_of(generated)
        if a == b:
            return "ok", ""
        # 隣り合うサイズなら「近い」とみなす(CU と MCU など)。
        if a in SHOT_SIZES and b in SHOT_SIZES:
            if abs(SHOT_SIZES.index(a) - SHOT_SIZES.index(b)) == 1:
                return "near", f"{a} → {b}(隣接)"
        return "ng", f"{a} → {b}"

    if name == "movement":
        a, b = tokens(reference, MOVEMENT_KEYS), tokens(generated, MOVEMENT_KEYS)
        if a and a == b:
            return "ok", ""
        if a & b:
            return "near", f"共通: {', '.join(sorted(a & b))} / 差: {', '.join(sorted(a ^ b))}"
        return "ng", f"{', '.join(sorted(a)) or '?'} → {', '.join(sorted(b)) or '?'}"

    if name == "angle":
        a, b = tokens(reference, ANGLE_KEYS), tokens(generated, ANGLE_KEYS)
        if a and a == b:
            return "ok", ""
        if a & b:
            return "near", ""
        return "ng", f"{', '.join(sorted(a)) or '?'} → {', '.join(sorted(b)) or '?'}"

    return "unknown", ""


def compare_duration(reference: float, generated: float) -> tuple[str, str]:
    diff = abs(float(reference) - float(generated))
    note = f"{reference}s → {generated}s(差 {diff:.1f}s)"
    if diff <= DURATION_TOLERANCE / 2:
        return "ok", note
    if diff <= DURATION_TOLERANCE:
        return "near", note
    return "ng", note


VERDICT_LABEL = {"ok": "一致", "near": "近い", "ng": "不一致", "unknown": "判定不可"}

DETERMINISTIC = [
    ("shot_size", "ショットサイズ"),
    ("angle", "アングル"),
    ("movement", "カメラワーク"),
]

PROSE = [
    ("composition", "構図"),
    ("lighting", "照明"),
    ("color_grade", "カラー"),
    ("environment", "場所"),
    ("mood", "ムード"),
]


def build_comparisons(reference_cuts: list[dict], verify_dir: Path) -> list[dict]:
    results = []
    for cut in reference_cuts:
        number = int(cut["cut_no"])
        generated_sheet = verify_dir / "analysis" / f"cut_{number:03d}" / "cutsheet.json"
        if not generated_sheet.is_file():
            continue
        generated_data = json.loads(generated_sheet.read_text(encoding="utf-8"))
        generated_cuts = generated_data.get("cuts", [])
        if not generated_cuts:
            continue

        # 生成物は 1 カットであるはず。割れていたら、それ自体が所見。
        generated = generated_cuts[0]
        ref_row, gen_row = flatten(cut), flatten(generated)

        fields = []
        for key, label in DETERMINISTIC:
            verdict, note = compare_field(key, ref_row[key], gen_row[key])
            fields.append({
                "key": key, "label": label, "verdict": verdict, "note": note,
                "reference": ref_row[key], "generated": gen_row[key],
            })
        verdict, note = compare_duration(cut.get("duration_sec", 0), generated_data.get("duration_sec", 0))
        fields.append({
            "key": "duration", "label": "尺", "verdict": verdict, "note": note,
            "reference": cut.get("duration_sec"), "generated": generated_data.get("duration_sec"),
        })

        results.append({
            "cut_no": number,
            "reference": cut,
            "generated": generated,
            "generated_dir": generated_sheet.parent,
            "generated_cut_count": len(generated_cuts),
            "fields": fields,
            "prose": [
                {"label": label, "reference": ref_row[key], "generated": gen_row[key]}
                for key, label in PROSE
            ],
        })
    return results


def summarize(comparisons: list[dict]) -> list[str]:
    """体系的なズレだけを拾う。1 カットだけのズレは生成のばらつきとして扱う。"""
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for comparison in comparisons:
        for field in comparison["fields"]:
            labels[field["key"]] = field["label"]
            if field["verdict"] == "ng":
                counts[field["key"]] = counts.get(field["key"], 0) + 1

    notes = []
    for key, count in sorted(counts.items(), key=lambda item: -item[1]):
        if count >= SYSTEMATIC_THRESHOLD:
            notes.append(
                f"**{labels[key]}** が {count}/{len(comparisons)} カットで不一致 → "
                "体系的なズレ。プロンプトの書き方を見直す対象"
            )
    split = [c for c in comparisons if c["generated_cut_count"] > 1]
    if split:
        numbers = ", ".join(str(c["cut_no"]) for c in split)
        notes.append(f"生成物が 1 カットに収まっていない(Cut {numbers})→ プロンプトが複数場面を示唆している可能性")
    if not notes:
        notes.append("体系的なズレは見つからなかった。個別のばらつきのみ。修正は不要")
    return notes


def render(comparisons: list[dict], reference_dir: Path, source: str) -> str:
    esc = html.escape
    out = [
        "<!doctype html>",
        '<html lang="ja"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>再現度の検証 — {esc(source)}</title>",
        f"<style>{HTML_STYLE}{EXTRA_STYLE}</style></head><body>",
        "<header><h1>再現度の検証</h1>",
        f'<div class="meta">{esc(source)} / {len(comparisons)} カットを比較</div></header><main>',
    ]

    out.append('<section class="summary"><h2>判定</h2><ul>')
    for note in summarize(comparisons):
        # ** で囲まれた部分だけ強調する。
        parts = esc(note).split("**")
        rendered = "".join(p if i % 2 == 0 else f"<b>{p}</b>" for i, p in enumerate(parts))
        out.append(f"<li>{rendered}</li>")
    out.append("</ul></section>")

    for comparison in comparisons:
        number = comparison["cut_no"]
        out.append('<article class="cut"><div class="cut-body">')
        out.append(f'<div class="cut-no">Cut {number}</div>')

        ref_thumb = comparison["reference"].get("thumbnail")
        gen_thumb = comparison["generated"].get("thumbnail")
        ref_src = data_uri(reference_dir / ref_thumb) if ref_thumb else None
        gen_src = data_uri(comparison["generated_dir"] / gen_thumb) if gen_thumb else None
        if ref_src or gen_src:
            out.append('<div class="pair">')
            out.append(
                f'<figure><img src="{ref_src}" alt="参照"><figcaption>参照</figcaption></figure>'
                if ref_src else "<figure><figcaption>参照(画像なし)</figcaption></figure>"
            )
            out.append(
                f'<figure><img src="{gen_src}" alt="生成"><figcaption>生成</figcaption></figure>'
                if gen_src else "<figure><figcaption>生成(画像なし)</figcaption></figure>"
            )
            out.append("</div>")

        out.append('<table class="cmp">')
        for field in comparison["fields"]:
            css = {"ok": "v-ok", "near": "v-near", "ng": "v-ng"}.get(field["verdict"], "")
            detail = field["note"] or f"{field['reference']} → {field['generated']}"
            out.append(
                f'<tr><th>{esc(field["label"])}</th>'
                f'<td><span class="{css}">{VERDICT_LABEL[field["verdict"]]}</span> '
                f'<span style="color:var(--muted)">{esc(str(detail))}</span></td></tr>'
            )
        out.append("</table>")

        out.append('<div class="prose">')
        for item in comparison["prose"]:
            if not item["reference"] and not item["generated"]:
                continue
            out.append(
                f'<p><b>{esc(item["label"])}</b><br>参照: {esc(str(item["reference"]))}'
                f'<br>生成: {esc(str(item["generated"]))}</p>'
            )
        out.append("</div>")
        out.append("</div></article>")

    out.append("</main>")
    out.append(f"<script>{HTML_SCRIPT}</script></body></html>")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="参照カットと生成動画の再現度を比較する")
    parser.add_argument("outdir", type=Path, help="カット表の出力ディレクトリ(cutsheet.json がある場所)")
    args = parser.parse_args()

    reference_sheet = args.outdir / "cutsheet.json"
    if not reference_sheet.is_file():
        print(f"error: {reference_sheet} が無い", file=sys.stderr)
        return 1

    verify_dir = args.outdir / "verify"
    data = json.loads(reference_sheet.read_text(encoding="utf-8"))

    targets_file = verify_dir / "targets.json"
    target_numbers = None
    if targets_file.is_file():
        target_numbers = set(json.loads(targets_file.read_text(encoding="utf-8")).get("cut_no", []))

    cuts = [
        c for c in data.get("cuts", [])
        if target_numbers is None or c.get("cut_no") in target_numbers
    ]
    comparisons = build_comparisons(cuts, verify_dir)
    if not comparisons:
        print(
            "error: 比較できる生成物が無い。"
            f"{verify_dir / 'generated'} に動画を置いて app/verify.sh を実行する",
            file=sys.stderr,
        )
        return 1

    verify_dir.mkdir(parents=True, exist_ok=True)
    source = Path(str(data.get("source") or "")).name or "(unknown)"
    report = verify_dir / "report.html"
    report.write_text(render(comparisons, args.outdir, source), encoding="utf-8")

    print(f"書き出し: {report}({len(comparisons)} カットを比較)")
    print()
    for note in summarize(comparisons):
        print("  - " + note.replace("**", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
