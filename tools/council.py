#!/usr/bin/env python3
"""5 人の助言役による合議を回して、次の一手をまとめた報告書を出す。

  ステップ1: 5 つの役割が、互いの回答を見ずに独立して意見を出す
  ステップ2: 各役が、他の 4 つの意見を匿名で評価する(人ではなく案を評価する)
  ステップ3: 議長が全体をまとめ、具体的な次の行動を決める

役割ごとに別プロセスで Claude を呼ぶ。同じ文脈を共有した 1 回の応答に
5 役を演じさせると意見が互いに引っ張られるため、独立性を保つには分ける必要がある。

    python3 tools/council.py                 # council/agenda.md を議題にして実行
    python3 tools/council.py --topic "..."   # 議題をその場で指定
    python3 tools/council.py --dry-run       # Claude を呼ばずにプロンプトだけ確認
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COUNCIL_DIR = REPO_ROOT / "council"
ROLES_DIR = COUNCIL_DIR / "roles"
LOG_DIR = COUNCIL_DIR / "log"

# (ファイル名の基底, 表示名)
ROLES: list[tuple[str, str]] = [
    ("opponent", "反対役"),
    ("assumption", "前提破壊役"),
    ("expander", "拡張役"),
    ("outsider", "部外者役"),
    ("executor", "実行役"),
]

# プロンプトに載せる 1 資料あたりの上限。文脈は要るが、際限なく膨らませない。
DOC_LIMIT = 6000
ANSWER_LIMIT = 8000


def clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(以下省略)"


def read_role(name: str) -> str:
    path = ROLES_DIR / f"{name}.md"
    if not path.is_file():
        raise SystemExit(f"error: 役割の定義が無い: {path}")
    return path.read_text(encoding="utf-8").strip()


def git_summary() -> str:
    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "-15"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        ).stdout.strip()
    except Exception:
        log = "(取得できなかった)"
    return log


def recent_conclusions(limit: int = 2) -> str:
    """直近の結論を渡して、同じ議論の繰り返しを避ける。"""
    if not LOG_DIR.is_dir():
        return "(まだ無い。今回が初回)"
    reports = sorted(LOG_DIR.glob("*.md"), reverse=True)[:limit]
    if not reports:
        return "(まだ無い。今回が初回)"
    chunks = []
    for report in reversed(reports):
        chunks.append(f"### {report.stem}\n{clip(report.read_text(encoding='utf-8'), 3000)}")
    return "\n\n".join(chunks)


def build_context(topic: str) -> str:
    readme = REPO_ROOT / "README.md"
    design = REPO_ROOT / "docs" / "DESIGN.md"

    def doc(path: Path) -> str:
        return clip(path.read_text(encoding="utf-8"), DOC_LIMIT) if path.is_file() else "(無し)"

    # 差し込む資料自体が複数行なので、字下げ付きのテンプレートは使えない
    # (8 スペース字下げは Markdown ではコードブロックになってしまう)。
    return "\n".join([
        "# 議題",
        "",
        topic.strip(),
        "",
        "# 現在のプロダクト",
        "",
        "参照動画からカット表と動画生成プロンプトを作るツールを開発している。",
        "以下が現時点の資料と開発状況。",
        "",
        "## README(抜粋)",
        "",
        doc(readme),
        "",
        "## 設計メモ(抜粋)",
        "",
        doc(design),
        "",
        "## 直近のコミット",
        "",
        git_summary(),
        "",
        "## 前回までの結論",
        "",
        recent_conclusions(),
    ])


def find_claude() -> str:
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
    raise SystemExit(
        "error: claude が見つからない。セットアップ.command を実行するか、"
        "CLAUDE_BIN に実行ファイルのパスを指定する"
    )


def ask_once(claude_bin: str, prompt: str, timeout: int) -> str:
    """Claude を 1 回呼ぶ。道具は使わせず、文章だけを返させる。"""
    result = subprocess.run(
        [claude_bin, "-p"],
        input=prompt, capture_output=True, text=True, timeout=timeout,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip()[:500] or "不明なエラー")
    answer = result.stdout.strip()
    if not answer:
        raise RuntimeError("応答が空だった")
    return answer


def ask(claude_bin: str, prompt: str, timeout: int, attempts: int = 3) -> str:
    """一過性の失敗で 1 役分の意見が丸ごと欠けるのを防ぐため、間を置いて再試行する。

    無人で回す前提なので、人が気づいて再実行することを当てにできない。
    """
    delay = 5
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return ask_once(claude_bin, prompt, timeout)
        except Exception as error:
            last = error
            if attempt < attempts:
                time.sleep(delay)
                delay *= 3
    raise RuntimeError(f"{attempts} 回試して失敗した: {last}")


def run_round(
    tasks: list[tuple[str, str]], claude_bin: str, timeout: int,
    dry_run: bool, concurrency: int = 3,
) -> dict[str, str]:
    """(ラベル, プロンプト) の集合を並行で処理する。"""
    results: dict[str, str] = {}

    def one(item: tuple[str, str]) -> tuple[str, str]:
        label, prompt = item
        if dry_run:
            return label, f"(dry-run: {len(prompt)} 文字のプロンプトを組み立てた)"
        try:
            return label, ask(claude_bin, prompt, timeout)
        except Exception as error:  # 1 役が落ちても合議は続ける
            return label, f"⚠️ この役は回答できなかった: {error}"

    workers = max(1, min(concurrency, len(tasks)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for label, answer in pool.map(one, tasks):
            results[label] = answer
            mark = "✗" if answer.startswith("⚠️") else "✓"
            print(f"  {mark} {label}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="5 人の助言役による合議を回す")
    parser.add_argument("--topic", help="議題。省略時は council/agenda.md を読む")
    parser.add_argument("--timeout", type=int, default=900, help="1 回の応答の上限秒数")
    parser.add_argument(
        "--concurrency", type=int, default=3,
        help="同時に走らせる役の数。増やすと速いが取りこぼしやすい(既定: 3)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Claude を呼ばずに動作だけ確認する")
    parser.add_argument("--seed", type=int, help="匿名ラベルの並びを固定する(検証用)")
    parser.add_argument("--dump-prompts", type=Path, help="組み立てたプロンプトを書き出す(検証用)")
    args = parser.parse_args()

    def dump(stage: str, label: str, prompt: str) -> None:
        if not args.dump_prompts:
            return
        args.dump_prompts.mkdir(parents=True, exist_ok=True)
        safe = label.replace("/", "_")
        (args.dump_prompts / f"{stage}_{safe}.txt").write_text(prompt, encoding="utf-8")

    agenda_path = COUNCIL_DIR / "agenda.md"
    if args.topic:
        topic = args.topic
    elif agenda_path.is_file():
        topic = agenda_path.read_text(encoding="utf-8").strip()
    else:
        raise SystemExit(f"error: 議題が無い。--topic で渡すか {agenda_path} を用意する")

    claude_bin = "(dry-run)" if args.dry_run else find_claude()
    rng = random.Random(args.seed)
    context = build_context(topic)
    started = datetime.now()

    # ---- ステップ1: 独立した意見 ----
    print("ステップ1: 各役が独立に意見を出す")
    round1_tasks = []
    for key, display in ROLES:
        prompt = f"{read_role(key)}\n\n---\n\n{context}"
        dump("round1", display, prompt)
        round1_tasks.append((display, prompt))
    round1 = run_round(round1_tasks, claude_bin, args.timeout, args.dry_run, args.concurrency)

    # ---- ステップ2: 匿名の相互評価 ----
    print("ステップ2: 互いの案を匿名で評価する")
    evaluator = read_role("evaluator")
    round2_tasks = []
    label_maps: dict[str, dict[str, str]] = {}
    for _, display in ROLES:
        others = [d for _, d in ROLES if d != display]
        rng.shuffle(others)
        # 誰の案かは伏せる。評価対象を案そのものに限定するため。
        label_map = {chr(ord("A") + i): other for i, other in enumerate(others)}
        label_maps[display] = label_map
        body = "\n\n".join(
            f"## 案{letter}\n\n{clip(round1[name], ANSWER_LIMIT)}"
            for letter, name in label_map.items()
        )
        prompt = (
            f"{evaluator}\n\n---\n\n# 議題\n\n{topic}\n\n"
            f"# あなた自身の意見\n\n{clip(round1[display], ANSWER_LIMIT)}\n\n"
            f"# 評価対象(誰の案かは伏せてある)\n\n{body}"
        )
        dump("round2", display, prompt)
        round2_tasks.append((display, prompt))
    round2 = run_round(round2_tasks, claude_bin, args.timeout, args.dry_run, args.concurrency)

    # ---- ステップ3: 議長のまとめ ----
    print("ステップ3: 議長がまとめる")
    opinions = "\n\n".join(
        f"## {display} の意見\n\n{clip(round1[display], ANSWER_LIMIT)}" for _, display in ROLES
    )
    reviews = "\n\n".join(
        f"## 評価者{index + 1}\n\n{clip(round2[display], ANSWER_LIMIT)}"
        for index, (_, display) in enumerate(ROLES)
    )
    chair_prompt = (
        f"{read_role('chair')}\n\n---\n\n{context}\n\n"
        f"# ステップ1: 各役の意見\n\n{opinions}\n\n"
        f"# ステップ2: 匿名での相互評価\n\n{reviews}"
    )
    dump("round3", "議長", chair_prompt)
    chair = run_round([("議長", chair_prompt)], claude_bin, args.timeout, args.dry_run)["議長"]

    # ---- 報告書 ----
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d-%H%M")
    elapsed = (datetime.now() - started).total_seconds()

    lines = [
        f"# 合議レポート {started.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"所要 {elapsed / 60:.1f} 分 / 呼び出し {len(ROLES) * 2 + 1} 回",
        "",
        "## 議題",
        "",
        topic.strip(),
        "",
        "---",
        "",
        "## 結論(議長)",
        "",
        chair,
        "",
        "---",
        "",
        "## ステップ1: 各役の意見",
        "",
    ]
    for _, display in ROLES:
        lines += [f"### {display}", "", round1[display], ""]
    lines += ["---", "", "## ステップ2: 匿名での相互評価", ""]
    for index, (_, display) in enumerate(ROLES):
        lines += [f"### 評価者{index + 1}", "", round2[display], ""]

    report_path = LOG_DIR / f"{stamp}.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    (COUNCIL_DIR / "latest.md").write_text("\n".join(lines), encoding="utf-8")

    print()
    print(f"書き出し: {report_path}")
    print(f"最新版:   {COUNCIL_DIR / 'latest.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
