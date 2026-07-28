#!/usr/bin/env python3
"""cutsheet.json を人が読む形式(Markdown / CSV)に整形する。

解析と文章生成は Claude が担当し、表の組み立てはこのスクリプトが決定的に行う。
そうすることで出力形式を変えてもプロンプト本文がぶれない。

    python3 tools/render_cutsheet.py out/cutsheet.json
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import mimetypes
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


HTML_STYLE = """
:root { color-scheme: light dark; --bg:#fbfaf8; --card:#fff; --fg:#1c1b19; --muted:#6b6862;
        --line:#e6e2db; --accent:#9a5b3d; --code:#f4f1ec; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14130f; --card:#1e1c18; --fg:#ece8e1; --muted:#a09a90;
          --line:#302d27; --accent:#d99a72; --code:#252320; }
}
* { box-sizing: border-box; }
body { margin:0; padding:0 0 3rem; background:var(--bg); color:var(--fg);
       font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif;
       line-height:1.65; -webkit-text-size-adjust:100%; }
header { padding:1.5rem 1rem 1rem; border-bottom:1px solid var(--line); }
h1 { margin:0 0 .35rem; font-size:1.25rem; line-height:1.35; word-break:break-word; }
.meta { color:var(--muted); font-size:.82rem; }
main { padding:1rem; max-width:820px; margin:0 auto; }
.overall { background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:.9rem 1rem; margin-bottom:1.25rem; font-size:.9rem; }
.overall h2 { margin:0 0 .5rem; font-size:.95rem; }
.overall p { margin:.3rem 0; }
.overall b { color:var(--muted); font-weight:600; }
.cut { background:var(--card); border:1px solid var(--line); border-radius:14px;
       overflow:hidden; margin-bottom:1.1rem; }
.cut img { display:block; width:100%; height:auto; background:#000; }
.cut-body { padding:.85rem 1rem 1rem; }
.cut-no { display:flex; flex-wrap:wrap; gap:.5rem; align-items:baseline;
          font-weight:700; font-size:1rem; margin-bottom:.6rem; }
.cut-no small { font-weight:500; color:var(--muted); font-size:.8rem; }
dl { display:grid; grid-template-columns:5.5rem 1fr; gap:.3rem .7rem;
     margin:0 0 .9rem; font-size:.86rem; }
dt { color:var(--muted); }
dd { margin:0; word-break:break-word; }
.prompt { margin-top:.75rem; }
.prompt-head { display:flex; align-items:center; justify-content:space-between;
               gap:.5rem; margin-bottom:.3rem; }
.prompt-head span { font-size:.8rem; font-weight:600; color:var(--accent); }
button { font:inherit; font-size:.78rem; padding:.32rem .7rem; border-radius:999px;
         border:1px solid var(--line); background:var(--bg); color:var(--fg);
         cursor:pointer; -webkit-tap-highlight-color:transparent; }
button:active { opacity:.6; }
button.done { border-color:var(--accent); color:var(--accent); }
pre { margin:0; padding:.7rem .8rem; background:var(--code); border-radius:10px;
      font-size:.8rem; line-height:1.55; white-space:pre-wrap; word-break:break-word;
      font-family:ui-monospace,SFMono-Regular,Menlo,monospace; -webkit-user-select:text;
      user-select:text; }
footer { text-align:center; color:var(--muted); font-size:.75rem; padding:1.5rem 1rem 0; }
"""

HTML_SCRIPT = """
document.querySelectorAll('button[data-target]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var pre = document.getElementById(btn.dataset.target);
    if (!pre) return;
    var text = pre.textContent;
    var done = function () {
      btn.textContent = 'コピーした';
      btn.classList.add('done');
      setTimeout(function () {
        btn.textContent = 'コピー';
        btn.classList.remove('done');
      }, 1500);
    };
    // file:// で開くと clipboard API が使えないことがあるので必ず退避策を持つ。
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(pre, done); });
    } else {
      fallback(pre, done);
    }
  });
});
function fallback(pre, done) {
  var range = document.createRange();
  range.selectNodeContents(pre);
  var sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  try {
    if (document.execCommand('copy')) { done(); return; }
  } catch (e) { /* 選択状態のままにして長押しコピーに委ねる */ }
}
"""


def data_uri(path: Path) -> str | None:
    """画像を data URI にして HTML に埋め込む。1 ファイルで完結させるため。"""
    if not path.is_file():
        return None
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def render_html(data: dict, json_path: Path, embed: bool = True) -> str:
    cuts = data.get("cuts", [])
    base_dir = json_path.parent
    esc = html.escape

    source = data.get("source") or "(unknown)"
    title = f"カット表 — {Path(str(source)).name}"

    meta_bits = [f"{len(cuts)} カット"]
    if data.get("duration_sec"):
        meta_bits.append(f"尺 {data['duration_sec']}s")
    if data.get("target_model"):
        meta_bits.append(f"書式 {data['target_model']}")
    if data.get("generated_at"):
        meta_bits.append(str(data["generated_at"])[:16].replace("T", " "))

    out: list[str] = []
    out.append("<!doctype html>")
    out.append('<html lang="ja"><head><meta charset="utf-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    out.append(f"<title>{esc(title)}</title>")
    out.append(f"<style>{HTML_STYLE}</style></head><body>")
    out.append(f"<header><h1>{esc(title)}</h1>")
    out.append(f'<div class="meta">{esc(" / ".join(meta_bits))}</div></header><main>')

    overall = data.get("overall") or {}
    if overall:
        out.append('<section class="overall"><h2>全体所感</h2>')
        for label, key in [
            ("構成", "structure"), ("撮影", "style"),
            ("カラー", "color_grade"), ("編集", "editing"),
        ]:
            if overall.get(key):
                out.append(f"<p><b>{label}</b> {esc(str(overall[key]))}</p>")
        out.append("</section>")

    for index, cut in enumerate(cuts):
        row = flatten(cut)
        out.append('<article class="cut">')

        thumbnail = cut.get("thumbnail")
        if thumbnail:
            src = data_uri(base_dir / thumbnail) if embed else esc(str(thumbnail))
            if src:
                out.append(f'<img loading="lazy" alt="Cut {row["cut_no"]}" src="{src}">')

        out.append('<div class="cut-body">')
        out.append(
            f'<div class="cut-no">Cut {esc(str(row["cut_no"]))}'
            f'<small>{esc(row["start_tc"])} → {esc(row["end_tc"])} / {esc(str(row["duration_sec"]))}s</small></div>'
        )

        out.append("<dl>")
        for label, key in [
            ("被写体", "subject"), ("アクション", "action"),
            ("ショット", "shot_size"), ("アングル", "angle"), ("カメラ", "movement"),
            ("レンズ", "lens_feel"), ("構図", "composition"), ("照明", "lighting"),
            ("カラー", "color_grade"), ("場所", "environment"), ("ムード", "mood"),
            ("繋ぎ", "transition_out"),
        ]:
            if row[key]:
                out.append(f"<dt>{label}</dt><dd>{esc(str(row[key]))}</dd>")
        out.append("</dl>")

        for suffix, label, key in [
            ("e", "完全再現プロンプト", "prompt_exact"),
            ("g", "汎用スタイルプロンプト", "prompt_generic"),
        ]:
            if not row[key]:
                continue
            pre_id = f"p{index}{suffix}"
            out.append('<div class="prompt"><div class="prompt-head">')
            out.append(f"<span>{label}</span>")
            out.append(f'<button type="button" data-target="{pre_id}">コピー</button>')
            out.append("</div>")
            out.append(f'<pre id="{pre_id}">{esc(str(row[key]))}</pre></div>')

        out.append("</div></article>")

    out.append("</main>")
    out.append(f"<footer>{esc(str(source))}</footer>")
    out.append(f"<script>{HTML_SCRIPT}</script></body></html>")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="cutsheet.json を Markdown / CSV / HTML に整形する")
    parser.add_argument("cutsheet", type=Path, help="cutsheet.json のパス")
    parser.add_argument(
        "--format", default="md,csv,html",
        help="出力形式をカンマ区切りで指定(md / csv / html、既定: md,csv,html)",
    )
    parser.add_argument(
        "--no-embed", action="store_true",
        help="HTML にサムネイルを埋め込まず、画像ファイルを参照する(単体では持ち出せなくなる)",
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

    if "html" in formats:
        html_path = outdir / f"{stem}.html"
        html_path.write_text(
            render_html(data, args.cutsheet, embed=not args.no_embed), encoding="utf-8"
        )
        size_mb = html_path.stat().st_size / 1_000_000
        note = " ※ サイズが大きい。--no-embed も検討する" if size_mb > 8 else ""
        print(f"書き出し: {html_path}({size_mb:.1f} MB){note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
