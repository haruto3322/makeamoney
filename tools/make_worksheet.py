#!/usr/bin/env python3
"""カット表から「生成用ワークシート」を作る。

Google AI Pro(Gemini アプリ / Flow)は画面で操作する前提なので、生成そのものは
自動化できない。そのかわり前後を固めて、人の作業をプロンプトの貼り付けと
できあがった動画の保存だけに減らす。

    python3 tools/make_worksheet.py out/xxx/cutsheet.json

out/xxx/verify/worksheet.html ができる。iPhone でも開けるので、
Flow を触りながらそのまま参照できる。
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_cutsheet import HTML_SCRIPT, HTML_STYLE, data_uri, flatten  # noqa: E402

EXTRA_STYLE = """
.step { background:var(--card); border:1px solid var(--line); border-radius:12px;
        padding:.9rem 1rem; margin-bottom:1.25rem; font-size:.88rem; }
.step ol { margin:.4rem 0 0; padding-left:1.2rem; }
.step li { margin:.3rem 0; }
.save-as { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.78rem;
           background:var(--code); padding:.15rem .4rem; border-radius:5px; }
.target { display:flex; gap:.5rem; flex-wrap:wrap; margin:.5rem 0 .2rem; font-size:.78rem;
          color:var(--muted); }
.target span { background:var(--code); padding:.15rem .5rem; border-radius:999px; }
"""


def pick_cuts(cuts: list[dict], count: int, explicit: str | None) -> list[dict]:
    """検証対象のカットを選ぶ。

    指定が無ければ、ショットサイズとカメラワークの組み合わせがなるべく
    ばらけるように選ぶ。同じような絵ばかり検証しても分かることが少ない。
    """
    if explicit:
        wanted = {int(n) for n in explicit.replace(" ", "").split(",") if n}
        return [c for c in cuts if c.get("cut_no") in wanted]

    if len(cuts) <= count:
        return list(cuts)

    picked: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for cut in cuts:
        camera = cut.get("camera") or {}
        key = (str(camera.get("shot_size", "")), str(camera.get("movement", "")))
        if key not in seen:
            seen.add(key)
            picked.append(cut)
        if len(picked) == count:
            return picked

    # 種類が足りなければ、残りは間隔を空けて補う。
    for cut in cuts:
        if cut not in picked:
            picked.append(cut)
        if len(picked) == count:
            break
    return picked


def render(cuts: list[dict], data: dict, base_dir: Path, generated_dir: Path) -> str:
    esc = html.escape
    source = Path(str(data.get("source") or "")).name or "(unknown)"

    out = [
        "<!doctype html>",
        '<html lang="ja"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>生成ワークシート — {esc(source)}</title>",
        f"<style>{HTML_STYLE}{EXTRA_STYLE}</style></head><body>",
        f"<header><h1>生成ワークシート</h1>",
        f'<div class="meta">{esc(source)} / {len(cuts)} カットを検証</div></header><main>',
        '<div class="step"><b>手順</b><ol>',
        "<li>各カットの「コピー」を押してプロンプトを取る</li>",
        "<li>Gemini アプリ または Flow(labs.google/flow)に貼って生成する</li>",
        "<li>できた動画を、指定のファイル名で保存する</li>",
        f"<li>すべて保存したら <span class='save-as'>bash app/verify.sh {esc(str(base_dir))}</span> "
        "を実行する(自動で参照と比較される)</li>",
        "</ol></div>",
    ]

    for cut in cuts:
        row = flatten(cut)
        number = row["cut_no"]
        out.append('<article class="cut">')
        thumbnail = cut.get("thumbnail")
        if thumbnail:
            src = data_uri(base_dir / thumbnail)
            if src:
                out.append(f'<img loading="lazy" alt="Cut {number}" src="{src}">')
        out.append('<div class="cut-body">')
        out.append(
            f'<div class="cut-no">Cut {esc(str(number))}'
            f'<small>{esc(str(row["duration_sec"]))}s / {esc(row["shot_size"])} / '
            f'{esc(row["movement"])}</small></div>'
        )
        out.append('<div class="target">')
        out.append(f"<span>目標尺 {esc(str(row['duration_sec']))}s</span>")
        if row["shot_size"]:
            out.append(f"<span>{esc(row['shot_size'])}</span>")
        if row["movement"]:
            out.append(f"<span>{esc(row['movement'])}</span>")
        out.append("</div>")

        pre_id = f"p{number}"
        out.append('<div class="prompt"><div class="prompt-head">')
        out.append("<span>このプロンプトで生成する</span>")
        out.append(f'<button type="button" data-target="{pre_id}">コピー</button>')
        out.append("</div>")
        out.append(f'<pre id="{pre_id}">{esc(str(row["prompt_exact"]))}</pre></div>')

        target = generated_dir / f"cut_{int(number):03d}.mp4"
        out.append(
            f'<p style="margin:.7rem 0 0;font-size:.82rem;">保存先: '
            f'<span class="save-as">{esc(str(target))}</span></p>'
        )
        out.append("</div></article>")

    out.append("</main>")
    out.append(f"<script>{HTML_SCRIPT}</script></body></html>")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="カット表から生成用ワークシートを作る")
    parser.add_argument("cutsheet", type=Path, help="cutsheet.json のパス")
    parser.add_argument("--count", type=int, default=3, help="検証するカット数(既定: 3)")
    parser.add_argument("--cuts", help="検証するカット番号をカンマ区切りで指定(例: 1,5,9)")
    args = parser.parse_args()

    if not args.cutsheet.is_file():
        print(f"error: {args.cutsheet} が見つからない", file=sys.stderr)
        return 1

    data = json.loads(args.cutsheet.read_text(encoding="utf-8"))
    cuts = data.get("cuts", [])
    if not cuts:
        print("error: cuts が入っていない", file=sys.stderr)
        return 1

    selected = pick_cuts(cuts, args.count, args.cuts)
    if not selected:
        print("error: 該当するカットが無い", file=sys.stderr)
        return 1

    base_dir = args.cutsheet.parent
    verify_dir = base_dir / "verify"
    generated_dir = verify_dir / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    # 比較のときにどのカットを対象にしたかが分かるよう控えておく。
    (verify_dir / "targets.json").write_text(
        json.dumps({"cut_no": [c["cut_no"] for c in selected]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    worksheet = verify_dir / "worksheet.html"
    worksheet.write_text(render(selected, data, base_dir, generated_dir), encoding="utf-8")

    print(f"書き出し: {worksheet}")
    print(f"検証対象: Cut {', '.join(str(c['cut_no']) for c in selected)}")
    print()
    print("次の手順:")
    print(f"  1. {worksheet} を開いてプロンプトをコピーする")
    print("  2. Gemini アプリ / Flow で生成する")
    print(f"  3. 動画を {generated_dir}/cut_NNN.mp4 として保存する")
    print(f"  4. bash app/verify.sh {base_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
