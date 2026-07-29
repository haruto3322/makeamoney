# カット表・再現プロンプト生成ツール

参照動画を 1 本入れると、**カット表**と、カットごとの**動画生成プロンプト 2 種類**を出力する。

1. **完全再現プロンプト** — 被写体ごとその映像を再現するためのプロンプト
2. **汎用スタイルプロンプト** — 被写体情報を `{subject}` に抜いたプロンプト。別の被写体を差し込んでも同じ雰囲気・同じ撮り方の映像が作れる

解析は Claude Code 上で動くので、**API の従量課金は発生しない**(定額プランの範囲で動く)。

設計の詳細は [`docs/DESIGN.md`](docs/DESIGN.md)、
Antigravity との連携は [`docs/ANTIGRAVITY.md`](docs/ANTIGRAVITY.md)。

## Mac アプリとして使う(推奨)

デスクトップにアプリを置いて、**参照動画をドラッグ&ドロップするだけ**で使えるようにできる。

### 1. 一度だけ: セットアップ

リポジトリを取得する(ターミナルを使うのはここだけ)。

```bash
cd ~/Desktop
git clone https://github.com/haruto3322/makeamoney.git
```

あとは Finder で `makeamoney` フォルダを開き、**「セットアップ」をダブルクリック**するだけ。
次の3つが自動でそろう。

1. カット検出に使う Python ライブラリ(リポジトリ内の `.venv` に入れる。システムの Python は触らない)
2. 解析に使う Claude Code(未導入なら自動で入れる)
3. デスクトップの**「カット表」アプリ**

数分かかる。何度実行しても問題ない(足りないものだけ入れ直す)。

### 2. 以降: 動画をドロップするだけ

デスクトップの「カット表」アイコンに参照動画をドラッグ&ドロップすると、

1. ターミナルが開いてカット分割とキーフレーム抽出が走る
2. 続けて Claude Code が起動し、解析とプロンプト生成が始まる
3. `out/<動画名>_<日時>/` にカット表が出力される

アイコンをダブルクリックすれば、動画の選択ダイアログから選ぶこともできる。
以降ターミナルにコマンドを打つ必要はない。

### 補足

- 初回起動時に「"カット表"がTerminalを制御することを許可しますか?」と聞かれるので許可する
- `makeamoney` フォルダを移動したら、「セットアップ」をもう一度実行してアプリを作り直す
  (アプリはビルド時にリポジトリの場所を覚えるため)
- アプリ名を変えたい場合は、ターミナルから `./セットアップ.command 好きな名前`
- アイコンを変えたい場合は、Finder でアプリを選んで `⌘I` → 左上のアイコンに画像を貼る
- Claude Code のデスクトップアプリや IDE 拡張を使っていて CLI を入れたくない場合は、
  セットアップの手順2をスキップしてよい。動画をドロップするとキーフレーム抽出まで進み、
  貼り付けるだけのコマンドがクリップボードに入る

## iPhone から使う

### 結果を iPhone で見る

出力される `cutsheet.html` は**画像もすべて埋め込まれた 1 ファイル**なので、AirDrop で
送るか iCloud Drive に置くだけで iPhone の Safari から読める。サムネイル付きのカット表が
縦画面向けに並び、各プロンプトの「コピー」ボタンを押せばそのまま生成 AI に貼り付けられる。

### iPhone から動画を投げて、自動で処理させる

Mac 側に見張りを仕掛けると、**iPhone からフォルダに動画を入れるだけ**でカット表が返ってくる。

Finder で `app/install_watcher.command` をダブルクリックすると、iCloud Drive に
「カット表 / 受信」「カット表 / 完成」フォルダが作られ、Mac が 1 分ごとに受信フォルダを
見張るようになる。

あとは iPhone の**「ファイル」アプリ → iCloud Drive → カット表 → 受信**に動画を入れるだけ。
数分後に「完成」フォルダへ HTML が現れるので、タップすれば読める。

- Mac の電源が入っていてネットに繋がっている必要がある(スリープ中は復帰後に処理される)
- 無人で解析するため Claude Code の CLI が必要。先に「セットアップ」を済ませておく
- 動作ログは `.watch.log`。解除は `./app/install_watcher.command --uninstall`

## AI 合議で開発方針を決める

5 つの助言役が独立に意見を出し、互いの案を匿名で評価し、議長がまとめて次の行動を決める。
これを 5 時間ごとに自動で回し続けられる(Claude の利用枠が 5 時間単位で切り替わるため、
枠ごとに 1 回議論させて寝かせない、という考え方)。

| 役 | 仕事 |
|---|---|
| 反対役 | 反対意見だけを出す。賛成点は書かない |
| 前提破壊役 | 書かれていない前提を掘り出し、すべて疑う |
| 拡張役 | 見落としている可能性を探す |
| 部外者役 | 業界を何も知らない立場から素朴な質問をする |
| 実行役 | 次に何をするべきかだけを考える |
| 議長 | 全体をまとめ、具体的な次の行動を決める |

役ごとに**別プロセスで Claude を呼ぶ**。1 回の応答で 5 役を演じさせると意見が互いに
引っ張られてしまい、独立した視点にならないため。

### すぐ 1 回試す

```bash
./app/council.sh
```

`council/latest.md` に結論、`council/log/` に議事録が残る。

### 自動で回し続ける — クラウド(PC 不要・推奨)

Claude Code の Routine(定期実行)に `app/council_online.sh` を仕込むと、**PC を一切使わず**
Anthropic 側の環境で 5 時間ごとに合議が走る。結果は自動で GitHub に push されるので、
iPhone のブラウザから `council/latest.md` を開けば読める。手元で何かを起動しておく必要はない。

Mac の電源やスリープに左右されず、こちらが推奨。設定は Claude Code のセッションから
Routine を作るだけで、その後は何もしなくてよい。

### 自動で回し続ける — Mac(ローカル)

PC 側で回したい場合は、Finder で `app/install_council.command` をダブルクリックする
(既定は 5 時間ごと。`./app/install_council.command 3` のように間隔を指定してもよい)。

- 議題を変える: `council/agenda.md` を書き換える
- 役割の性格を変える: `council/roles/*.md` を書き換える
- 解除: `./app/install_council.command --uninstall`

前回までの結論が次回の文脈に入るので、同じ議論を繰り返さず先に進む。
iCloud 連携を設定してあれば、結論は iPhone からも読める。

## 生成AIで再現できているかを検証する

作ったプロンプトが本当に狙った映像を作れるのかを、印象ではなく**項目ごとに**判定する。

> **Google AI Pro について**: AI Pro は Gemini アプリ / Flow を使う権利であって、API
> アクセスは含まれない。そのため**生成そのものは Flow の画面で行う必要がある**。
> このツールは生成の前後を自動化して、人の作業を「プロンプトを貼る」「できた動画を置く」
> の 2 つだけに減らす。

### 1. 生成用ワークシートを作る

```bash
python3 tools/make_worksheet.py out/xxx/cutsheet.json
```

`out/xxx/verify/worksheet.html` ができる。ショットサイズとカメラワークがなるべく
ばらけるように 3 カットが自動で選ばれる(同じような絵ばかり検証しても分かることが少ない)。

iPhone でも開けるので、Flow を触りながらそのまま参照できる。

### 2. Flow で生成して、動画を置く

ワークシートの「コピー」を押してプロンプトを取り、Gemini アプリまたは
Flow(labs.google/flow)で生成する。できた動画を、ワークシートに書かれている
`out/xxx/verify/generated/cut_NNN.mp4` として保存する。

この手順は **Antigravity のブラウザ操作に任せることもできる**。
`make_worksheet.py` は同時に `work/queue/` へ依頼票を置くので、Antigravity に
「work/queue の依頼票を処理して」と頼めばよい。詳細は
[`docs/ANTIGRAVITY.md`](docs/ANTIGRAVITY.md)。

### 3. 検証する

```bash
bash app/verify.sh out/xxx
```

生成物を**参照と同じパイプライン**に通して解析し、構造として比較する。

| 項目 | 判定のしかた |
|---|---|
| ショットサイズ | 完全一致 / 隣接(CU と MCU など)は「近い」/ それ以外は不一致 |
| アングル | 表記ゆれ(eye-level と eye level)を吸収して比較 |
| カメラワーク | 語彙単位で比較(slow dolly-in と dolly in は一致) |
| 尺 | 0.5 秒以内は一致、1 秒以内は「近い」 |
| 構図・照明・カラー・場所・ムード | 機械判定できないので、参照と生成を並べて表示 |

`out/xxx/verify/report.html` に、参照と生成のサムネイルを並べた比較表が出る。

**同じ項目が 2 カット以上でズレていたら「体系的なズレ」として名指しされる。**
1 カットだけのズレは生成のばらつきとして扱い、修正対象にしない。プロンプトの
書き方を直すべきかどうかが、この一行で判断できる。

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
| `out/cutsheet.html` | iPhone / ブラウザ用。画像込みの 1 ファイルで持ち出せる |
| `out/cutsheet.csv` | 表計算ソフト用 |
| `out/prompts_*.md` / `.csv` | 被写体差し替え後のプロンプト一式 |

## 構成

```
セットアップ.command  初回セットアップ(ダブルクリック)。依存 + Claude Code + アプリ作成
app/
  lib.sh              依存の導入・Claude Code の探索/導入・アプリ生成の共通処理
  cutsheet.sh         アプリの実処理。準備 → 抽出 → Claude Code に引き継ぎ
  droplet.applescript アプリの中身。動画を受け取って cutsheet.sh に渡す
  build_app.command   アプリだけ作り直したいとき用
  watch.sh            iCloud の受信フォルダを見張って自動処理する
  install_watcher.command  iPhone 連携(iCloud フォルダ + 定期実行)の設定
  verify.sh           生成物を解析して参照と比較する
  council.sh          合議を 1 回まわす(ローカル)
  council_online.sh   合議 → コミット → push まで無人で行う(クラウド定期実行用)
  pipeline_online.sh  進められる工程を自動で進める(クラウド定期実行用)
  install_council.command  合議の自動実行(既定 5 時間ごと)の設定
tools/
  extract_cuts.py     カット検出 + キーフレーム抽出(ローカル・無料)
  build_cutsheet.py   解析結果と cuts.json を統合し、被写体情報の漏れを検証
  render_cutsheet.py  cutsheet.json を Markdown / CSV / HTML に整形
  apply_subject.py    {subject} を差し替えてプロンプト一式を出力
  make_worksheet.py   生成用ワークシートと、Antigravity 向けの依頼票を作る
  compare_cutsheets.py 参照と生成を項目ごとに比較して判定する
  pipeline.py         リポジトリの状態を見て、進められる工程だけを進める
  council.py          5 役の合議を回して結論をまとめる
AGENTS.md             エージェント(Antigravity / Claude Code)への指示
work/
  queue/              未処理の生成依頼。Antigravity が拾う
  done/ failed/       処理済み / 失敗した依頼
council/
  agenda.md           議題(書き換えて使う)
  roles/              各役と議長のプロンプト
  log/                過去の議事録
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
