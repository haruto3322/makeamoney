# 解析結果のスキーマ

## `out/parts/cut_NNN.json`

カット 1 つ分の解析結果。**タイムコード・尺・フレームパスは書かない**(`cuts.json` の値を
`build_cutsheet.py` が転記する)。書くのは解析と執筆の結果だけ。

```jsonc
{
  // ---- 被写体レイヤ: 汎用プロンプトでは丸ごと {subject} に置き換わる ----
  "subject": {
    "description": "20代の日本人女性、黒のロングヘア、白いニットセーター",
    "action": "コーヒーカップを両手で持ち上げ、立ちのぼる湯気を見つめて微笑む",
    "position_in_frame": "画面中央やや左、バストアップ"
  },

  // ---- スタイルレイヤ: 両方のプロンプトで共通して使う ----
  "camera": {
    "shot_size": "CU",
    "angle": "eye-level",
    "movement": "slow dolly-in",
    "lens_feel": "85mm相当・浅い被写界深度、背景は大きくボケる"
  },
  "composition": "三分割構図。被写体は左寄り、右に抜けの空間。前景に湯気",
  "lighting": "窓からの柔らかい自然光で軽い逆光。背景に暖色のプラクティカル",
  "color_grade": "暖色寄りのフィルムルック。低コントラスト、ハイライトがふんわり、微粒子",
  "environment": "朝のカフェ。木目のテーブル、窓の外は淡くボケた街並み",
  "mood": "静かで温かい、親密",
  "audio_notes": "カフェの環境音、BGM は Lo-fi(推定)",
  "transition_out": "cut",

  // ---- 生成プロンプト(英語) ----
  "prompt_exact": "Close-up of a Japanese woman in her 20s with long black hair, wearing a white knit sweater, lifting a coffee cup with both hands and smiling softly at the rising steam. Slow dolly push-in at eye level, 85mm look with shallow depth of field, background falling into soft bokeh. Soft backlit window light with warm practical lamps behind her. Rule-of-thirds framing with steam drifting in the foreground. Warm film-look grade, low contrast, gentle highlight rolloff, fine grain. Quiet, intimate morning-cafe mood. Duration about 2.6 seconds.",

  "prompt_generic": "Close-up of {subject}, lifting a coffee cup with both hands and smiling softly at the rising steam. Slow dolly push-in at eye level, 85mm look with shallow depth of field, background falling into soft bokeh. Soft backlit window light with warm practical lamps behind the subject. Rule-of-thirds framing with steam drifting in the foreground. Warm film-look grade, low contrast, gentle highlight rolloff, fine grain. Quiet, intimate morning-cafe mood. Duration about 2.6 seconds."
}
```

上の例で、2 つのプロンプトの差分が `a Japanese woman ... white knit sweater` → `{subject}` と
`behind her` → `behind the subject` の 2 箇所だけになっている点に注意する。これが正しい形。

### フィールド

| フィールド | 必須 | 内容 |
|---|---|---|
| `subject.description` | ○ | 被写体の見た目。人物なら年代・性別・髪型・服装。物なら形状・色・材質 |
| `subject.action` | ○ | カット中に起きる動き。フレーム間の差分から読む |
| `subject.position_in_frame` | | 画面内の位置とサイズ感 |
| `camera.shot_size` | ○ | `EWS` / `WS` / `FS` / `MS` / `MCU` / `CU` / `ECU` / `insert` |
| `camera.angle` | ○ | `eye-level` / `low` / `high` / `overhead` / `dutch` / `POV` / `over-the-shoulder` |
| `camera.movement` | ○ | `static` / `pan` / `tilt` / `dolly-in` / `dolly-out` / `truck` / `handheld` / `gimbal follow` / `zoom` / `crane` / `orbit` |
| `camera.lens_feel` | | 焦点距離感、被写界深度、歪み |
| `composition` | ○ | 構図・被写体配置・前景/背景の層 |
| `lighting` | ○ | 光の方向・質・色温度・光源 |
| `color_grade` | ○ | カラーの傾向、コントラスト、粒子感 |
| `environment` | ○ | 場所・時間帯・美術 |
| `mood` | ○ | 情緒。1 行 |
| `audio_notes` | | 画から推測できる範囲で。断定しない |
| `transition_out` | | `cut` / `dissolve` / `fade` / `whip pan` / `match cut` / `wipe` |
| `prompt_exact` | ○ | 完全再現プロンプト(英語) |
| `prompt_generic` | ○ | 汎用スタイルプロンプト(英語、`{subject}` 必須) |

被写体が人物でないカット(風景・物のインサートなど)でも `subject` は埋める。
被写体が存在しない純粋な風景カットなら `description` に「被写体なし(風景)」と書き、
`prompt_generic` は `{subject}` を使わず**風景そのものをスタイル記述として残す** —
この場合だけ `{subject}` 無しを許容し、`build_cutsheet.py` の警告は無視してよい。

## `out/parts/overall.json`(任意)

```jsonc
{
  "structure": "商品紹介の縦型広告。掴み3カット → 使用シーン → 商品アップ → CTA",
  "style": "手持ち中心、寄りと引きの落差を大きく取る。カット尺は平均2秒台と短い",
  "color_grade": "全体に暖色寄り、シャドウを持ち上げたフィルムルックで統一",
  "editing": "アクション繋ぎとマッチカットを多用。BGM のビートに合わせて切っている"
}
```
