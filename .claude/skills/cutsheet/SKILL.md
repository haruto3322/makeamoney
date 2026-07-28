---
name: cutsheet
description: 参照動画からカット表(絵コンテ表)と映像再現プロンプトを生成する。動画をカット単位に分解し、各カットのカメラワーク・構図・照明・カラー・被写体を解析して、完全再現用プロンプトと、被写体情報を抜いた汎用スタイルプロンプトの2種類を出力する。Use when the user wants a cut sheet, shot list, or shot-by-shot breakdown of a reference video, or wants video-generation prompts (Veo, Sora, Runway, Kling) that reproduce or restyle a reference clip.
---

# カット表・再現プロンプト生成

参照動画を、カット表 + 各カットの動画生成プロンプト(完全再現版 / 被写体を抜いた汎用版)に変換する。

## 分業の原則

**判断が要る部分だけを自分でやり、機械的な部分はスクリプトに任せる。**

| 工程 | 担当 |
|---|---|
| カット検出・キーフレーム抽出 | `tools/extract_cuts.py` |
| 映像の解析とプロンプト執筆 | 自分(このスキル) |
| タイムコードの転記・表の組み立て・検証 | `tools/build_cutsheet.py` + `tools/render_cutsheet.py` |

タイムコードや尺は**絶対に自分で書き写さない**。`cuts.json` の値をスクリプトが転記する。

## 手順

### 1. キーフレームを用意する

引数が動画ファイルなら、先にローカル処理を回す(API 費用は発生しない)。

```bash
python3 tools/extract_cuts.py <動画パス> -o out/
```

引数が既に `out/` のようなディレクトリで `cuts.json` があるなら、この手順は飛ばす。

カット数が明らかに多すぎる / 少なすぎる場合は閾値を調整して取り直す(`--threshold` を下げると細かく割れる。ffmpeg 検出時は `--ffmpeg-threshold`)。カット数を報告して、ユーザーに違和感がないか一度確認するとよい。

### 2. `out/cuts.json` を読む

各カットの `cut_no` / `frames`(キーフレームのパス、`out/` からの相対)が入っている。

### 3. カットを 3〜4 個ずつ解析する

**1 バッチ = 3〜4 カット**。それ以上まとめて画像を読むとコンテキストを圧迫する。

各バッチで:

1. そのカットの `frames` を Read ツールで**全部**読む(1 カットにつき 2〜5 枚)
2. `references/analysis.md` の観点で解析する。**同一カットの時系列フレーム**なので、フレーム間の差分からカメラの動きと被写体のアクションを推定する — これは静止画 1 枚では判別できないので、必ず複数枚を見比べる
3. `references/schema.md` のスキーマに従って、カットごとに `out/parts/cut_001.json` を書く(ファイル名の連番は `cut_no` に合わせてゼロ埋め 3 桁)

バッチごとにファイルを書き切る。途中で中断しても、書けたところまでは残り、再開できる。

初回バッチの前に `references/schema.md` と `references/analysis.md` を読むこと。プロンプトの書式は `references/presets.md` を参照する(ユーザーが生成モデルを指定していればそのプリセット、無ければ `generic`)。

### 4. 全体所感を書く(任意)

全カットを見終えたら、`out/parts/overall.json` に構成・撮影スタイル・カラー・編集リズムの所感を書く。

### 5. 組み立てと出力

```bash
python3 tools/build_cutsheet.py out/ --target generic
python3 tools/render_cutsheet.py out/cutsheet.json
```

`build_cutsheet.py` は汎用プロンプトに被写体を特定する語が残っていないか機械チェックする。**警告が出たら該当カットの `parts/cut_NNN.json` を直して再実行する** — 警告を残したまま完了と報告しない。

出力は `out/cutsheet.json` / `cutsheet.md` / `cutsheet.csv`。

### 6. 報告

カット数、尺、全体の傾向を数行でまとめ、出力先のパスを伝える。カット表の中身を丸ごと本文に貼り直さない(ファイルを見ればよい)。

## プロンプト生成の絶対ルール

出力する 2 種類のプロンプトは、**同じ解析結果から機械的に導ける関係**でなければならない。

- **`prompt_exact`** — 被写体レイヤ + スタイルレイヤの全部。その映像がそのまま再現されることを狙う
- **`prompt_generic`** — 被写体の identity(人種・性別・年齢・髪型・服装・固有名詞)を `{subject}` に置き換え、それ以外(カメラ、構図、照明、カラー、場所、ムード、尺)は `prompt_exact` と**同一**にする

`prompt_generic` は `prompt_exact` の言い換えではなく、**被写体部分だけを差し替えた同一文**にする。両者でカメラワークやカラーの記述が食い違っていたら間違い。

`prompt_generic` に残してはいけない語の例: `woman`, `man`, `she`, `his`, `Japanese`, `blonde`, `in her 20s`, 人名・商品名。代名詞が要る場合は `the subject` を使う。

アクションが被写体固有で他に流用できない場合(例: 「口紅を塗る」)は、アクションも `{action}` プレースホルダにする。汎用的なアクション(例: 「カップを持ち上げて微笑む」)はそのまま残してよい。

## 言語

- カット表の説明フィールド(`subject.description`, `composition`, `lighting` など)は**日本語**。人が読む用。
- `prompt_exact` / `prompt_generic` は**英語**。動画生成モデルは英語プロンプトで最も性能が出る。

## 被写体の差し替え

ユーザーが別の被写体で使いたいと言ったら:

```bash
python3 tools/apply_subject.py out/cutsheet.json --subject "a man in his 30s in a black suit" --name suit-man
```

`out/prompts_suit-man.md` と `.csv` が出る。
