# カット表・再現プロンプト生成ツール

参照動画を 1 本入れると、**カット表**と、カットごとの**動画生成プロンプト 2 種類**を出力する。

1. **完全再現プロンプト** — 被写体ごとその映像を再現するためのプロンプト
2. **汎用スタイルプロンプト** — 被写体情報を `{subject}` に抜いたプロンプト。別の被写体を差し込んでも同じ雰囲気・同じ撮り方の映像が作れる

解析は Claude Code 上で動くので、**API の従量課金は発生しない**(定額プランの範囲で動く)。

設計の詳細は [`docs/DESIGN.md`](docs/DESIGN.md)。

## Mac アプリとして使う(推奨)

デスクトップにアプリを置いて、**参照動画をドラッグ&ドロップするだけ**で使えるようにできる。

### 1. 一度だけ: リポジトリを取得してアプリを作る

```bash
cd ~/Desktop
git clone https://github.com/haruto3322/makeamoney.git
cd makeamoney
git checkout claude/video-cut-sheet-generator-a0bpct
```

続けて Finder で `makeamoney/app/build_app.command` を**ダブルクリック**する
(ターミナルから `./app/build_app.command` でも同じ)。デスクトップに
**「カット表.app」**ができる。

### 2. 以降: 動画をドロップするだけ

デスクトップの「カット表」アイコンに参照動画をドラッグ&ドロップすると、

1. ターミナルが開いてカット分割とキーフレーム抽出が走る
2. 続けて Claude Code が起動し、解析とプロンプト生成が始まる
3. `out/<動画名>_<日時>/` にカット表が出力される

アイコンをダブルクリックすれば、動画の選択ダイアログから選ぶこともできる。

初回だけリポジトリ内に `.venv` を作って必要なライブラリを入れる(数分かかる)。
システムの Python は触らないので、権限エラーや externally-managed-environment に
引っかからない。

### 補足

- 初回起動時に「"カット表"がTerminalを制御することを許可しますか?」と聞かれるので許可する
- `makeamoney` フォルダを移動したら、`build_app.command` を実行してアプリを作り直す
  (アプリはビルド時にリポジトリの場所を覚えるため)
- アプリ名を変えたい場合は `./app/build_app.command 好きな名前`
- アイコンを変えたい場合は、Finder でアプリを選んで `⌘I` → 左上のアイコンに画像を貼る

## ターミナルから使う

Mac アプリを使わず、手動で回すこともできる。必要なのは Python 3.10+ と ffmpeg。

```bash
pip install -r requirements.txt
```

`scenedetect` が入っていなければ ffmpeg の scene フィルタで自動的に代替するので、
最低限 ffmpeg さえあれば動く。

### 1. カット分割とキーフレーム抽出(ローカル処理)

```bash
python3 tools/extract_cuts.py 参照動画.mp4 -o out/
```

`out/cuts.json`(カット一覧とタイムコード)と `out/frames/`(解析用キーフレーム)ができる。

カットの割れ方が粗い / 細かすぎるときは閾値を調整する。

```bash
python3 tools/extract_cuts.py 参照動画.mp4 -o out/ --threshold 22    # 細かく割る
```

### 2. カット表とプロンプトを生成

Claude Code で実行する。

```
/cutsheet out/
```

動画パスを直接渡せば手順 1 も込みで走る。

```
/cutsheet 参照動画.mp4
```

キーフレームを読んで解析し、`out/cutsheet.json` / `cutsheet.md` / `cutsheet.csv` を出力する。
生成モデルを指定したい場合は伝える(例: 「Veo 向けの書式で」)。

### 3. 別の被写体に差し替える

```bash
python3 tools/apply_subject.py out/cutsheet.json \
    --subject "a man in his 30s in a black suit" --name suit-man
```

全カットの汎用プロンプトに被写体を差し込んだ `out/prompts_suit-man.md` / `.csv` が出る。

## 出力物

| ファイル | 内容 |
|---|---|
| `out/cuts.json` | カット一覧(タイムコード・尺・キーフレームのパス) |
| `out/frames/` | 解析用キーフレーム |
| `out/parts/cut_NNN.json` | カットごとの解析結果(Claude が書く中間ファイル) |
| `out/cutsheet.json` | 統合済みカット表データ |
| `out/cutsheet.md` | 人が読むカット表(サムネイル・プロンプト付き) |
| `out/cutsheet.csv` | 表計算ソフト用 |
| `out/prompts_*.md` / `.csv` | 被写体差し替え後のプロンプト一式 |

## 構成

```
app/
  build_app.command   デスクトップに「カット表.app」を作る(ダブルクリック)
  droplet.applescript アプリの中身。動画を受け取って cutsheet.sh に渡す
  cutsheet.sh         アプリの実処理。依存の自動セットアップ → 抽出 → Claude 起動
tools/
  extract_cuts.py     カット検出 + キーフレーム抽出(ローカル・無料)
  build_cutsheet.py   解析結果と cuts.json を統合し、被写体情報の漏れを検証
  render_cutsheet.py  cutsheet.json を Markdown / CSV に整形
  apply_subject.py    {subject} を差し替えてプロンプト一式を出力
.claude/skills/cutsheet/
  SKILL.md            解析手順(Claude Code が読む)
  references/         スキーマ・解析観点・モデル別プロンプト書式
```

タイムコードや表の組み立てはスクリプトが決定的に行い、Claude は映像の解析と
プロンプトの執筆だけを担当する。数値の書き写しミスが起きない分業にしてある。

## スクリプト単体のヘルプ

```bash
python3 tools/extract_cuts.py --help
python3 tools/build_cutsheet.py --help
python3 tools/render_cutsheet.py --help
python3 tools/apply_subject.py --help
```
