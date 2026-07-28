#!/usr/bin/env python3
"""参照動画をカット(ショット)単位に分割し、解析用のキーフレームを書き出す。

ここまでの処理はすべてローカルで完結するので API 費用は発生しない。
出力した cuts.json と frames/ を Claude Code の cutsheet スキルに渡すと
カット表と再現プロンプトが生成される。

    python3 tools/extract_cuts.py 参照動画.mp4 -o out/

カット検出は PySceneDetect があればそれを使い、無ければ ffmpeg の scene
フィルタで代替する。どちらも入っていない場合はエラーになる。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# 1 カットから切り出すフレーム数の上限。多いほど動きの推定精度は上がるが
# 解析時に読む画像が増える。
DEFAULT_MAX_FRAMES = 5
# キーフレームの長辺ピクセル数。解析精度とトークン消費のバランス点。
DEFAULT_WIDTH = 1024

# 閾値を明示されなかった場合に、粗すぎる結果なら順に下げて試す。
# 検出器ごとに閾値の意味が違うので別のはしごを持つ。
SCENEDETECT_LADDER = [27.0, 20.0, 14.0]
FFMPEG_LADDER = [0.30, 0.18, 0.10]
# 1 カットの平均がこれより長ければ「カットを取りこぼしている」とみなす。
COARSE_AVG_SEC = 12.0


def die(message: str) -> "NoReturn":  # type: ignore[valid-type]
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def find_ffmpeg() -> str:
    """PATH の ffmpeg を優先し、無ければ imageio-ffmpeg の同梱バイナリを使う。"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
    except ImportError:
        die("ffmpeg が見つからない。ffmpeg を入れるか `pip install imageio-ffmpeg` を実行する")
    return imageio_ffmpeg.get_ffmpeg_exe()


def format_tc(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:05.2f}"


def probe(video: Path, ffmpeg: str) -> dict:
    """尺・fps・解像度を取得する。ffprobe が無い環境でも動くようにしてある。"""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "format=duration",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "json", str(video),
            ],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            stream = (data.get("streams") or [{}])[0]
            num, _, den = (stream.get("r_frame_rate") or "0/1").partition("/")
            fps = float(num) / float(den) if den and float(den) else 0.0
            return {
                "duration_sec": round(float(data["format"]["duration"]), 3),
                "fps": round(fps, 3),
                "width": stream.get("width"),
                "height": stream.get("height"),
            }

    # ffprobe が無い場合は ffmpeg のヘッダ出力から拾う。
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(video)], capture_output=True, text=True
    )
    text = result.stderr
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", text)
    if not duration_match:
        die(f"動画の情報を読み取れなかった: {video}")
    hours, minutes, secs = duration_match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(secs)

    fps_match = re.search(r"([\d.]+)\s*fps", text)
    size_match = re.search(r"Stream #\d+:\d+.*?Video:.*?\b(\d{2,5})x(\d{2,5})\b", text, re.S)
    return {
        "duration_sec": round(duration, 3),
        "fps": round(float(fps_match.group(1)), 3) if fps_match else 0.0,
        "width": int(size_match.group(1)) if size_match else None,
        "height": int(size_match.group(2)) if size_match else None,
    }


def detect_with_scenedetect(video: Path, threshold: float) -> list[tuple[float, float]] | None:
    """PySceneDetect によるカット検出。未インストールなら None を返す。"""
    try:
        from scenedetect import ContentDetector, detect
    except ImportError:
        return None

    def to_seconds(timecode) -> float:
        # 0.7 系は seconds プロパティ、0.6 系は get_seconds()。
        value = getattr(timecode, "seconds", None)
        return float(value) if value is not None else float(timecode.get_seconds())

    scenes = detect(str(video), ContentDetector(threshold=threshold))
    return [(to_seconds(scene[0]), to_seconds(scene[1])) for scene in scenes]


def detect_with_ffmpeg(
    video: Path, ffmpeg: str, threshold: float, duration: float
) -> list[tuple[float, float]]:
    """ffmpeg の scene フィルタで代替検出する。

    select='gt(scene,N)' を通過したフレーム = 新しいショットの先頭フレーム
    なので、その pts_time がカットの開始点になる。
    """
    result = subprocess.run(
        [
            ffmpeg, "-nostdin", "-hide_banner",
            "-i", str(video),
            "-filter:v", f"select='gt(scene,{threshold})',showinfo",
            "-an", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    starts = [float(t) for t in re.findall(r"pts_time:([\d.]+)", result.stderr)]
    boundaries = [0.0] + sorted(t for t in starts if 0.0 < t < duration) + [duration]
    return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]


def merge_short_cuts(cuts: list[tuple[float, float]], min_len: float) -> list[tuple[float, float]]:
    """min_len 未満のカットは直前のカットに吸収する(誤検出・フラッシュ対策)。"""
    merged: list[list[float]] = []
    for start, end in cuts:
        if merged and (end - start) < min_len:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    # 先頭が極端に短い場合だけは後ろに吸収する。
    if len(merged) > 1 and (merged[0][1] - merged[0][0]) < min_len:
        merged[1][0] = merged[0][0]
        merged.pop(0)
    return [(start, end) for start, end in merged]


def looks_too_coarse(cuts: list[tuple[float, float]], duration: float) -> bool:
    """カットを取りこぼしていそうかどうかの判定。

    40 秒の広告が 2 カット、のような明らかに粗い結果を検出して、
    閾値を下げた再検出につなげる。長回しの映像なら下げても結果は変わらない。
    """
    if not cuts:
        return True
    if duration <= 0:
        return False
    return (duration / len(cuts)) > COARSE_AVG_SEC


def frame_times(start: float, end: float, max_frames: int) -> list[float]:
    """カット内でキーフレームを取る時刻を決める。

    先頭と末尾はトランジションが乗りやすいので少し内側にずらす。長いカットほど
    枚数を増やし、カメラの動きの軌跡を追えるようにする。
    """
    duration = end - start
    inset = min(0.12, duration * 0.15)
    first, last = start + inset, end - inset
    if last <= first:
        return [(start + end) / 2]

    if duration <= 1.0:
        count = 2
    elif duration <= 3.0:
        count = 3
    else:
        count = 3 + int((duration - 3.0) // 2.0)
    count = max(2, min(count, max_frames))

    step = (last - first) / (count - 1)
    return [first + step * i for i in range(count)]


def extract_frame(ffmpeg: str, video: Path, at: float, out_path: Path, width: int) -> bool:
    result = subprocess.run(
        [
            ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
            "-ss", f"{at:.3f}", "-i", str(video),
            "-frames:v", "1",
            # 元より大きくはしない(min)。高さは偶数に丸める(-2)。
            "-vf", f"scale=w='min({width},iw)':h=-2:flags=lanczos",
            "-q:v", "3", "-y", str(out_path),
        ],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and out_path.exists()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="参照動画をカット分割してキーフレームを書き出す(ローカル処理・API 費用なし)",
    )
    parser.add_argument("video", type=Path, help="参照動画のパス")
    parser.add_argument("-o", "--outdir", type=Path, default=Path("out"), help="出力先ディレクトリ")
    parser.add_argument(
        "--detector", choices=["auto", "scenedetect", "ffmpeg"], default="auto",
        help="カット検出方式(既定: auto = PySceneDetect があれば使う)",
    )
    parser.add_argument(
        "--threshold", type=float,
        help=f"PySceneDetect の閾値。小さいほど細かく割れる(既定: {SCENEDETECT_LADDER[0]} から自動調整)",
    )
    parser.add_argument(
        "--ffmpeg-threshold", type=float,
        help=f"ffmpeg 検出時の閾値 0-1。小さいほど細かく割れる(既定: {FFMPEG_LADDER[0]} から自動調整)",
    )
    parser.add_argument(
        "--min-len", type=float, default=0.4,
        help="この秒数未満のカットは前のカットに統合する(既定: 0.4)",
    )
    parser.add_argument(
        "--max-frames", type=int, default=DEFAULT_MAX_FRAMES,
        help=f"1 カットあたりのキーフレーム上限(既定: {DEFAULT_MAX_FRAMES})",
    )
    parser.add_argument(
        "--width", type=int, default=DEFAULT_WIDTH,
        help=f"キーフレームの長辺ピクセル数(既定: {DEFAULT_WIDTH})",
    )
    args = parser.parse_args()

    if not args.video.is_file():
        die(f"動画が見つからない: {args.video}")

    ffmpeg = find_ffmpeg()
    info = probe(args.video, ffmpeg)
    duration = info["duration_sec"]
    print(f"入力: {args.video}  {duration:.2f}s  {info['width']}x{info['height']}  {info['fps']}fps")

    # 閾値が明示されていなければ、粗すぎる結果が出たぶんだけ段階的に下げて試す。
    cuts: list[tuple[float, float]] = []
    detector_used: str | None = None
    threshold_used: float | None = None

    if args.detector in ("auto", "scenedetect"):
        ladder = [args.threshold] if args.threshold is not None else SCENEDETECT_LADDER
        for value in ladder:
            candidate = detect_with_scenedetect(args.video, value)
            if candidate is None:
                break  # PySceneDetect 未インストール
            cuts = merge_short_cuts(candidate, args.min_len)
            detector_used, threshold_used = "scenedetect", value
            if args.threshold is not None or not looks_too_coarse(cuts, duration):
                break
            print(f"  カットが粗いので閾値を下げて再検出する(threshold={value} で {len(cuts)} カット)")

        if detector_used is None:
            if args.detector == "scenedetect":
                die("PySceneDetect が入っていない。`pip install -r requirements.txt` を実行する")
            print("⚠️  PySceneDetect が使えないので簡易検出(ffmpeg)に切り替える。")
            print("    カット数が実際と大きく違う場合は `pip install -r requirements.txt` で入れ直す。")

    if detector_used is None:
        ladder = [args.ffmpeg_threshold] if args.ffmpeg_threshold is not None else FFMPEG_LADDER
        for value in ladder:
            cuts = merge_short_cuts(
                detect_with_ffmpeg(args.video, ffmpeg, value, duration), args.min_len
            )
            detector_used, threshold_used = "ffmpeg", value
            if args.ffmpeg_threshold is not None or not looks_too_coarse(cuts, duration):
                break
            print(f"  カットが粗いので閾値を下げて再検出する(threshold={value} で {len(cuts)} カット)")

    if not cuts:
        cuts = [(0.0, duration)]

    average = duration / len(cuts) if cuts else 0.0
    print(
        f"カット検出: {len(cuts)} カット"
        f"(検出器: {detector_used}, 閾値: {threshold_used}, 平均 {average:.1f}秒/カット)"
    )
    if looks_too_coarse(cuts, duration):
        flag = "--threshold" if detector_used == "scenedetect" else "--ffmpeg-threshold"
        print(f"  ⚠️  カット数が想定より少ない場合は {flag} をさらに下げて実行し直す。")

    frames_dir = args.outdir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    records = []
    total_frames = 0
    for index, (start, end) in enumerate(cuts, start=1):
        paths = []
        for frame_index, at in enumerate(frame_times(start, end, args.max_frames), start=1):
            out_path = frames_dir / f"cut_{index:03d}_f{frame_index}.jpg"
            if extract_frame(ffmpeg, args.video, at, out_path, args.width):
                paths.append(os.path.relpath(out_path, args.outdir))
            else:
                print(f"  warn: cut {index} の {at:.2f}s のフレーム抽出に失敗", file=sys.stderr)
        total_frames += len(paths)
        records.append({
            "cut_no": index,
            "start_sec": round(start, 3),
            "end_sec": round(end, 3),
            "duration_sec": round(end - start, 3),
            "start_tc": format_tc(start),
            "end_tc": format_tc(end),
            "frames": paths,
        })

    payload = {
        "source": str(args.video),
        "duration_sec": duration,
        "fps": info["fps"],
        "width": info["width"],
        "height": info["height"],
        "detector": detector_used,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cuts": records,
    }
    cuts_json = args.outdir / "cuts.json"
    cuts_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"キーフレーム: {total_frames} 枚 -> {frames_dir}")
    print(f"カット情報: {cuts_json}")
    print()
    print("次のステップ: Claude Code で以下を実行する")
    print(f"  /cutsheet {args.outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
