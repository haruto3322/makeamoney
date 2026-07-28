# ターゲット別プロンプト書式

`build_cutsheet.py --target` に渡す値と対応。ユーザーの指定が無ければ `generic` を使う。

**どのプリセットでも、`prompt_exact` と `prompt_generic` は被写体部分以外が同一文であること**
という原則は変わらない。プリセットで変わるのは文体・長さ・語順だけ。

## 共通の並び順

情報は次の順で書くと、どのモデルでも解釈が安定する。

1. ショットサイズ + 被写体 + アクション
2. カメラワーク(動き、アングル、レンズ感)
3. 照明
4. 構図・前景/背景
5. カラーグレード・質感
6. ムード・場所
7. 尺

## `generic`(既定)

自然な英文で 2〜5 文。上の並び順どおりに書く。どのモデルに投げても概ね通る標準形。

```text
Close-up of {subject}, lifting a coffee cup with both hands and smiling at the rising steam.
Slow dolly push-in at eye level, 85mm look with shallow depth of field. Soft backlit window
light with warm practical lamps behind the subject. Rule-of-thirds framing with steam in the
foreground. Warm film-look grade, low contrast, fine grain. Quiet, intimate morning-cafe mood.
Duration about 2.6 seconds.
```

## `veo` / `sora`

長めの自然文が得意。**カメラワークを文章で丁寧に描写する**。映画的な語彙(cinematic,
shot on 35mm, anamorphic など)がよく効く。時間経過のある描写(「〜しながら、徐々に〜」)も
理解される。

```text
A cinematic close-up of {subject}, lifting a coffee cup with both hands and smiling softly as
steam rises past the frame. The camera slowly pushes in at eye level on an 85mm lens, the
background dissolving into creamy bokeh. Soft backlit morning light spills through a window
behind the subject, with warm practical lamps glowing out of focus. Shot on 35mm film, low
contrast with gentle highlight rolloff and fine grain. Quiet and intimate. About 2.6 seconds.
```

## `runway`

短く、キーワード寄り。カメラ指定を末尾に分けて書く形式が通りやすい。1〜2 文 + 指定句。

```text
Close-up of {subject} lifting a coffee cup, smiling at the steam. Soft backlit window light,
warm film grade, shallow depth of field, cafe interior.
Camera: slow dolly in, eye level, 85mm.
```

## `kling` / `pika`

簡潔な英文 1〜2 文 + スタイルタグをカンマ区切りで。長文は無視されやすいので削る。

```text
{subject} lifting a coffee cup and smiling at the rising steam, slow dolly in, eye level,
shallow depth of field, soft backlit window light, warm film look, low contrast, fine grain,
cozy morning cafe, cinematic
```

## 共通の注意

- **否定形は効きにくい**(`no text`, `not blurry` など)。入れたいものを書く
- **固有名詞・実在人物名は入れない**。生成が拒否されるか、意図しない結果になる
- 縦動画が前提なら、プロンプト末尾に `vertical 9:16 framing` を足す(横なら `16:9`)
- テキストやロゴが画面に映っているカットは、再現しようとせず `environment` に事実として
  記録するだけにする。生成 AI は文字を正しく描けない
