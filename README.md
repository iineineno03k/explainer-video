# explainer-video

資料 (文書・画面の写し・図) から、**ずんだもん (何も知らない役) と四国めたん (説明役) の掛け合い**で話す、字幕つきの解説動画 (mp4) を作る仕組み。

台本 (YAML) 1 つから、コマンド 1 回で動画までできる。台本は Claude Code (または Codex) に skill で下書きさせる。

```
台本 (YAML) → 音声 (VOICEVOX) → 画 (HTML + Chrome) → 動画 (ffmpeg → mp4 + 字幕 SRT)
```

いちばん大事にしているのは、**見る人の認知負荷を減らす**こと。

- 何が分かる動画かを、最初に問いの一覧で見せ、最後に答えで閉じる。
- 図は見方を先に言う。画面の写しは話している所を赤枠で囲み、枠の外は自動で暗くする。
- 1 画面・1 台詞・1 場面に言うことは 1 つ。

この道具には案件のことを入れない。台本・画像・読みの辞書は使う側のリポジトリに置き、できた動画はチームが開ける場所に置く。

| 入っているもの | 中身 |
|---|---|
| `explainer/` | 台本から mp4 を作るコマンド `explainer` |
| `skills/explainer-script/` | 資料から台本を下書きし、台詞のつながりをサブエージェントにレビューさせ、mp4 まで作る skill |
| `skills/understanding-video/` | 業務・システムを知らない人向けに、ナレッジのページを正本にして「全体像 → 業務の箱ごと」の理解用ページと動画を作る skill。ページとの突き合わせのレビューと、作ってみて分かったこと (頼み方のひな形・見たときに確かめること) つき |
| `samples/how-it-works/` | この仕組みそのものを説明する見本の台本 |

## 入れる

```bash
# コマンド
uv tool install git+https://github.com/iineineno03k/explainer-video   # 以後 explainer で動く

# skill (Claude Code)
/plugin marketplace add iineineno03k/explainer-video
/plugin install explainer-video@explainer-video
```

skill をプラグインで入れないときは、`skills/` の中のフォルダを `~/.claude/skills/` (Codex なら `~/.codex/skills/`) か、使うリポジトリの `.claude/skills/` にコピーする。

## 必要なもの

| もの | Mac | Windows |
|---|---|---|
| uv (Python の実行) | `brew install uv` | `winget install astral-sh.uv` |
| Chrome か Edge | 入っていればよい | 入っていればよい (Edge は最初から入っている) |
| VOICEVOX エンジン | 下の「VOICEVOX を動かす」 | 同じ |

ffmpeg は Python の依存 (imageio-ffmpeg) が持ってくるので、別に入れなくてよい。Chrome の場所が標準と違うときは、環境変数 `CHROME_PATH` に実行ファイルのパスを入れる。

## VOICEVOX を動かす

どちらかの方法でエンジンを `http://127.0.0.1:50021` に立てる。

**Docker (おすすめ。Mac も Windows も同じ)**: Docker Desktop を入れて、このフォルダで

```bash
docker compose up -d      # 初回はイメージ (約 2.4GB) を取ってくる
docker compose down       # 止める
```

**VOICEVOX のアプリ**: [VOICEVOX](https://voicevox.hiroshiba.jp/) を入れて起動しておくと、アプリが同じ URL でエンジンを立てる。Docker が使えないときはこちら。

つながるかは `explainer check` で確かめる (話し手とスタイルの番号が出る)。

## 動かす

```bash
explainer check                                       # エンジンにつながるか
explainer preview samples/how-it-works/script.yaml    # 音声なしで、台詞ごとの画だけ描く
explainer build   samples/how-it-works/script.yaml    # mp4 と字幕まで作る
explainer lines   samples/how-it-works/script.yaml    # 台詞を場面をまたいで通しで並べる (読み直し・レビュー用)
```

出力は台本の `output` (既定は台本と同じフォルダの `out/<名前>.mp4`)。同じ台詞の音声は `out/cache/` から使い回すので、台本を少し直して作り直すのは速い。`--engine` でエンジンの URL を変えられる。clone して手元で動かすときは `uv run explainer ...`。

## 台本の書き方

```yaml
name: how-it-works                 # 出力のファイル名
title: 資料を、聞いて分かる動画にする   # 最初の画面
subtitle: ずんだもんと四国めたんの掛け合い解説の作り方
readings: readings.yaml            # 読みの辞書 (下)
output: out/how-it-works.mp4       # 省略可

scenes:
  - title: どうやって動画になる？      # 場面で言うことを 1 つ
    image: images/pipeline.png      # 見せる画像 (台本からの相対パス)
    zoom: {x: 0, y: 0, w: 1600, h: 500}   # 切り出す範囲 (画像のピクセル)。省略で全体
    boxes: [{x: 40, y: 120, w: 310, h: 350, label: ① 台本}]   # 赤枠 (場面全体)。枠の外は暗くなる
    point: 画面の下に出す一言          # 省略可
    lines:
      - zundamon: でも、どうやって動画になるのだ？
      - metan: まず台本。場面ごとに、見せる画像と台詞を YAML に書くの。
        boxes: [{x: 40, y: 120, w: 310, h: 350, label: 台本}]   # この台詞のときだけの赤枠
        point: explainer build 台本.yaml                        # この台詞のときだけの一言
      - metan: この図は、左から右へ順に進むの。
        boxes: []                                               # 枠なし (図の見方を言うとき)
        dim: false                                              # 暗くしない
        subtitle: 字幕だけ変えたいとき
        pause: 1.0                                              # 台詞のあとの間 (秒)

  - title: 聞きやすくする決まり
    card:                           # 画像がない場面はカード
      title: 聞きやすくする 4 つの決まり
      sub: 小さい説明 (省略可)
      reveal: true                  # 項目を台詞ごとに 1 つずつ出す
      points: [1 つの場面で言うことは 1 つ, 台詞は短く切る]
    lines:
      - zundamon: 聞きやすくする工夫はあるのだ？
        upto: 0                     # reveal のとき、出す項目の数
      - metan: 1 つの場面で言うことは、1 つにしているわ。
        upto: 1
```

- 話し手は `zundamon` (ずんだもん、ノーマル) と `metan` (四国めたん、ノーマル) が最初から使える。顔はエンジンに入っている公式のアイコンが自動で入る。声の高さ・速さ・スタイル・色・顔は `speakers:` で上書きし、ほかの話し手も足せる (名前を省くとエンジンから取る):
  ```yaml
  speakers:
    zundamon: {style_id: 1, speed: 1.15}          # あまあま
    tsumugi: {style_id: 8, color: "#e8a33d"}      # 春日部つむぎ。台詞は「- tsumugi: …」
    metan: {icon: images/metan.png}               # 顔を差し替え。icon: false で頭文字の丸
  ```
  スタイルの番号は `explainer check` で見る。画面に出る顔は、台本で最初に話す 2 人 (3 人目以降が話すときは、右の顔がその人に替わる)。
- 画像の場面で `boxes` があると、枠の外が暗くなる (見る所を 1 か所に絞る)。場面か台詞に `dim: false` で止める。
- 台詞は 1 本 40 字以内、字幕は 2 行まで。長いときは台詞を分ける。
- 数字・専門用語は、台詞で言うだけでなく `label`・`points`・`point` で画面にも出す。

## 読みの辞書

`readings.yaml` に `表記: 読み` を書く (読みは ひらがな か カタカナ)。字幕は表記のまま、声だけ読みで話す。

```yaml
VOICEVOX: ボイスボックス
台本: だいほん
画像: がぞう      # 「画 (え)」を直すときは、熟語を先に入れておく
画: え
```

長い表記から先に置き換える。読み間違いに気づいたら足す。案件ごとに 1 つ持つ。

## 台本を AI に書かせる

skill を入れて、Claude Code に頼む。

| 頼み方 | skill |
|---|---|
| 「この資料 (パス) を、新しく入った人向けに 5 分の解説動画にして。見終わって〜が分かるように」 | `explainer-script` |
| 「〜の業務の全体像の理解用の動画を作って」「〜の箱の理解用のページと動画を作って」 | `understanding-video` |

どちらも、build の前に、書いた会話を引き継がないサブエージェントにレビューさせる (台詞のつながりは `skills/explainer-script/review.md`、ナレッジのページとの突き合わせは `skills/understanding-video/review-content.md`)。回すのは 3 回まで。

## クレジット (必ず残す)

VOICEVOX の音声は、使うときにクレジット表記が要る。動画の最後に「VOICEVOX:ずんだもん」「VOICEVOX:四国めたん」(使った話し手の名前) の画面を自動で付ける。消さない。動画を置く場所の説明にも同じ表記を書く。キャラクターの利用の決まりは、各キャラクターの利用規約 (ずんだもん・四国めたんは東北ずん子・ずんだもんプロジェクトのガイドライン) に従う。

## サンプルの図を描き直す

`samples/how-it-works/images/pipeline.png` は同じフォルダの `pipeline.html` を Chrome で 1600×600 に描いたもの。

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --window-size=1600,600 --screenshot=pipeline.png "file://$PWD/pipeline.html"
```

## ライセンス

コードと skill は MIT ([LICENSE](LICENSE))。VOICEVOX の音声・キャラクター・アイコンは、それぞれの利用規約に従う (上の「クレジット」)。
