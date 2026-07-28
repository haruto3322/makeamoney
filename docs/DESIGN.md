# 参照動画 → カット表 & 再現プロンプト生成ツール 設計書

## 1. コンセプト

参照動画を1本入力するだけで、以下を自動生成するツール。

1. **カット表(Cut Sheet)** — 動画をカット(ショット)単位に分割し、各カットのタイムコード・尺・カメラワーク・構図・照明・被写体・アクションなどの情報を一覧化したもの
2. **完全再現プロンプト** — 各カットの映像を、被写体を含めてそのまま再現するための動画生成AI向けプロンプト
3. **汎用スタイルプロンプト** — 特定の被写体情報を抜き、`{subject}` プレースホルダに置き換えたプロンプト。別の被写体を差し込んでも「同じ雰囲気・同じ撮り方」の映像が生成できる

ユースケース:
- バズった動画の「構成・撮り方」を分解して、自分の商品/人物で同じフォーマットの動画を作る
- 広告・MV・Vlog などのリファレンス動画を、絵コンテ+生成プロンプトのセットに変換する
- 動画生成AI(Veo / Sora / Runway / Kling など)への入力プロンプトを量産する

---

## 2. 全体パイプライン

```mermaid
flowchart TD
    A[参照動画を入力\nmp4 / mov / URL] --> B[① カット検出\nPySceneDetect / TransNetV2]
    B --> C[② カットごとの\nキーフレーム抽出\nffmpeg: 先頭/中間/末尾]
    C --> D[③ 映像解析\nClaude Vision API\n構造化JSONで抽出]
    D --> E[④ カット表データ\nstructured JSON]
    E --> F1[⑤a 完全再現プロンプト生成]
    E --> F2[⑤b 被写体抽象化\n→ 汎用スタイルプロンプト生成]
    F1 --> G[⑥ 出力\nカット表 UI / CSV / Markdown / JSON]
    F2 --> G
```

### ① カット検出(ショット境界検出)
- **PySceneDetect**(ContentDetector)をデフォルトに採用。ヒストグラム差分でカット点を検出。軽量・依存少。
- ディゾルブやフェードが多い映像には **TransNetV2**(学習済みショット境界検出モデル)をオプションで用意。
- 出力: `[{cut_no, start_tc, end_tc, duration_sec}, ...]`

### ② キーフレーム抽出
- 各カットから **先頭・中間・末尾の3フレーム**(長いカットは1秒ごとに追加)を ffmpeg で抽出。
- 複数フレームを渡すことで、静止画1枚では判別できない**カメラの動き(パン/ズーム/ドリー)と被写体のアクション**を解析可能にする。
- サムネイル用に中間フレームを縮小保存。

### ③ 映像解析(ここが核)
- カットごとに複数キーフレームを **Claude API(vision)** に渡し、**構造化出力(JSON Schema)** で解析結果を受け取る。
- モデル: `claude-opus-5`(vision + structured outputs 対応)。コスト重視の量産時は `claude-sonnet-5` に切替可能。
- 1カット=1リクエスト。**Batches API を使えば全カット並列処理で50%オフ**。
- プロンプトのポイント: 「フレーム列は同一カットの時系列。フレーム間の差分からカメラの動きと被写体のアクションを推定せよ」と明示する。

### ④ カット表データ(スキーマ)

**被写体情報とスタイル情報をスキーマレベルで分離する**のが最大の設計ポイント。⑤bの「被写体抜き」を LLM の気分に任せず、フィールド単位で決定的に行えるようにする。

```jsonc
{
  "cut_no": 3,
  "start_tc": "00:00:07.20",
  "end_tc": "00:00:09.85",
  "duration_sec": 2.65,
  "thumbnail": "cuts/003_mid.jpg",

  // ---- 被写体レイヤ(汎用プロンプトでは丸ごと {subject} に置換される) ----
  "subject": {
    "description": "20代の日本人女性、黒のロングヘア、白いニットセーター",
    "action": "コーヒーカップを両手で持ち上げ、湯気を見つめて微笑む",
    "position_in_frame": "画面中央やや左、上半身"
  },

  // ---- スタイルレイヤ(両プロンプトに共通で使われる) ----
  "camera": {
    "shot_size": "close-up",            // ECU/CU/MCU/MS/FS/WS/EWS
    "angle": "eye-level",               // low/eye-level/high/overhead/dutch
    "movement": "slow push-in (dolly)", // static/pan/tilt/dolly/handheld/gimbal/zoom
    "lens_feel": "85mm相当・浅い被写界深度、背景は大きくボケる"
  },
  "composition": "三分割構図。右側に抜けの空間。前景に湯気",
  "lighting": "窓からの柔らかい自然光(逆光気味)、暖色のプラクティカル照明が背景に",
  "color_grade": "暖色系フィルムルック、ハイライトふんわり、コントラスト低め、粒子感あり",
  "environment": "朝のカフェ。木目のテーブル、窓の外は淡くボケた街並み",
  "mood": "静かで温かい、intimate",
  "audio_notes": "環境音(カフェのざわめき小)、BGはLo-fi",   // 参考情報
  "transition_out": "cut",              // cut/dissolve/wipe/match-cut...

  // ---- 生成プロンプト(⑤で生成して書き戻す) ----
  "prompt_exact": "...",
  "prompt_generic": "..."
}
```

### ⑤ プロンプト生成(2系統)

同じ構造化データから、テンプレート+LLM整形で2種類を出力する。

**a. 完全再現プロンプト(prompt_exact)** — 被写体レイヤ+スタイルレイヤをすべて使用:

> A close-up of a Japanese woman in her 20s with long black hair, wearing a white knit sweater, lifting a coffee cup with both hands and smiling softly at the rising steam. Slow dolly push-in at eye level, 85mm look with shallow depth of field. Soft backlit window light with warm practical lights in the background. Rule-of-thirds framing with steam in the foreground. Warm film-look color grade, low contrast, subtle grain. Quiet, intimate morning-café mood. Duration ~2.6s.

**b. 汎用スタイルプロンプト(prompt_generic)** — 被写体レイヤを `{subject}` / `{action}` に置換し、被写体を特定する語(人種・性別・服装・固有名詞など)がスタイル側に漏れていないか LLM で最終チェック:

> A close-up of {subject} {action}. Slow dolly push-in at eye level, 85mm look with shallow depth of field. Soft backlit window light with warm practical lights in the background. Rule-of-thirds framing. Warm film-look color grade, low contrast, subtle grain. Quiet, intimate mood. Duration ~2.6s.

**ターゲット生成AIごとのプリセット**を用意(語彙・長さ・カメラ指定の書式が異なるため):

| プリセット | 特徴 |
|---|---|
| Veo / Sora | 自然文の長め記述。カメラワークを文章で明示 |
| Runway Gen-4 | 短めのキーワード寄り。`camera: dolly-in` 等の指定に対応 |
| Kling / Pika | 簡潔な英文+スタイルタグ |
| 汎用 | 上記の中間。どのモデルにも通じる標準形 |

### ⑥ 出力
- **カット表ビュー**: サムネイル付きテーブル(カットNo / TC / 尺 / ショットサイズ / カメラ / 内容 / プロンプト2種のコピーボタン)
- **エクスポート**: CSV / Markdown / JSON(全スキーマ)/ XLSX
- `{subject}` 一括差し込み機能: 新しい被写体を1回入力すると、全カットの汎用プロンプトに展開した「差し替え版プロンプト一式」を出力

---

## 3. UIイメージ(Webアプリ)

```
┌────────────────────────────────────────────────────────────┐
│  🎬 Cut Sheet Generator          [動画をドロップ / URL入力]  │
├────────────────────────────────────────────────────────────┤
│  解析中… カット検出 ✓ → フレーム抽出 ✓ → AI解析 12/18 ▓▓▓░  │
├────┬──────┬───────┬─────────┬──────────────┬──────────────┤
│ No │ サムネ│ TC/尺 │ ショット │ 内容          │ プロンプト     │
├────┼──────┼───────┼─────────┼──────────────┼──────────────┤
│ 01 │ [img]│ 0:00  │ WS/固定  │ カフェ外観、朝 │ [完全📋][汎用📋]│
│    │      │ 3.2s  │         │              │  ▼ 開いて編集   │
│ 02 │ [img]│ 0:03  │ MS/手持ち│ 女性が入店    │ [完全📋][汎用📋]│
│ 03 │ [img]│ 0:07  │ CU/ドリー│ カップを持つ  │ [完全📋][汎用📋]│
├────┴──────┴───────┴─────────┴──────────────┴──────────────┤
│ 被写体差し替え: [ 30代男性、黒スーツ… ] → [全カットに適用]     │
│ 出力: [CSV] [Markdown] [JSON] [XLSX]   プリセット: [Veo ▼]   │
└────────────────────────────────────────────────────────────┘
```

- 行をクリックすると詳細パネル(全解析フィールド+プロンプト編集+該当区間の動画プレビュー)
- 解析結果は人間が修正可能。修正するとプロンプトが再生成される

---

## 4. 技術スタック(想定)

| レイヤ | 技術 |
|---|---|
| カット検出 | Python + PySceneDetect(オプションで TransNetV2) |
| フレーム抽出 | ffmpeg |
| 映像解析・プロンプト生成 | Claude API(`claude-opus-5`、structured outputs、Batches) |
| バックエンド | Python / FastAPI(ジョブキュー: 動画1本=1ジョブ) |
| フロントエンド | Next.js(まずは CLI → 後から Web UI) |
| ストレージ | ローカル or S3(動画・サムネイル・JSON) |

### 実装ステップ(MVP → 拡張)

1. **MVP(CLI)**: `cutsheet analyze video.mp4 -o out/`
   → カット検出+フレーム抽出+Claude解析+`cutsheet.json` / `cutsheet.md` 出力
2. **プロンプト2系統+ターゲットプリセット**
3. **Web UI**(アップロード、テーブル表示、編集、コピー、エクスポート)
4. **被写体一括差し替え/複数参照動画のスタイル合成**などの応用機能

### コスト感(参考)
- 1カットあたりキーフレーム3枚+解析出力 ≒ 数千トークン
- 60秒・カット数20の動画 1本 ≒ Opus 5 で数十円〜百数十円程度。Batches 利用で半額

---

## 5. 設計上の要点(まとめ)

- **カメラの動きは複数フレームの差分から推定**させる(静止画1枚では原理的に判別不能)
- **被写体とスタイルをスキーマで分離**することで、「被写体を抜いた汎用プロンプト」を決定的・安全に生成できる(LLM 任せの削除だと漏れる)
- 解析→プロンプトを **構造化データ経由の2段構え**にすることで、人間の修正・多形式出力・ターゲットモデル切替がすべて同じデータから派生できる
