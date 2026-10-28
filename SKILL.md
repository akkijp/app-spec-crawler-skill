---
name: app-spec-crawler
description: 利用者の起動中の Chrome（ログイン済み）に browser-use でつなぎ（使えなければ computer-use）、指定URL配下のWebアプリケーションを「読み取り専用」で全ページ巡回し、全ページ・全モーダル/タブ/メニューのスクリーンショットを撮って、アプリ共通の仕様・階層（ディレクトリ）仕様・画面仕様・画面キャプチャの4層からなるHTML画面仕様書（index.html付き）を作成するスキル。「このアプリの仕様書を作って」「画面を全部調査して」「スクショを撮ってまとめて」「既存システムのリバースエンジニアリング」「画面一覧・機能一覧を洗い出して」「URLを渡すので中身を調べて」といった依頼では、"仕様書"という言葉がなくても必ずこのスキルを使う。保存・更新・削除・送信などデータを変更する操作は絶対に行わない。最後に claude -p（Fable 5.1）で、初めての人向けのシステム概要書 guide.html も書く。画面はライト固定。「/app-spec-crawler」「app-spec-crawler help」で使い方、「app-spec-crawler doctor」でこのスキルが今使えるかを表示する。
---

# app-spec-crawler — Webアプリ読み取り専用巡回・画面仕様書生成

対象アプリに**一切の変更を加えずに**、全ページと全「安全な操作状態」（モーダル・タブ・メニュー・展開など）を
スクリーンショット付きで調査し、次の4層からなる HTML 画面仕様書を作る。

| 層 | ファイル | 内容 |
|---|---|---|
| アプリ共通の仕様 | `overview.html` | アプリ全体の仕様項目（SPEC-APP-NN）、認証/権限、共通UI、ナビゲーション、業務ドメイン |
| 階層仕様 | `sections/<path>.html` | URLディレクトリごとに「この階層にはこういう画面群があり、共通してこういう仕様がある」。深い階層はネストし、子階層・配下画面へリンク |
| 画面仕様 | `pages/pXXX.html` | 1画面1ファイル。「この画面にはこういう仕様がある」を番号付き仕様項目（SPEC-pXXX-NN）で列挙し、根拠としてキャプチャを参照 |
| 画面キャプチャ | `captures/pXXX.html` | 1画面1ファイル。初期表示＋操作状態のスクリーンショット集。仕様書とは分離し、相互リンク |

`index.html` はこれらのハブ（階層ツリー・分類別画面一覧・キャプチャ一覧・安全性レポート）。
最後に、4 層の中身を材料に **`claude -p` で Fable 5.1 が書く読み物 `guide.html`**（できること・画面の地図・業務の流れ・決まりごと・用語・確認が必要なこと）を足し、表紙と上部バーからリンクする。
画面は**ライト固定**（OS がダークでも明るいまま。`prefers-color-scheme` を書かない）。

成果物は決定的（同じ入力→同じ出力）であるべき部分をプログラム化してあり、
AI（あなた）の仕事は「各画面の意味を読み解いて説明を書く」部分に限定している。

```
app-spec-crawler/
├── SKILL.md                    ← この手順書
├── bin/app-spec-crawler        ← コマンドの入口（~/.local/bin にリンク。help / doctor / crawl / describe / build / write / verify）
├── scripts/
│   ├── app_spec_crawler.py     ← コマンド本体（標準ライブラリのみ。エラーの原因と直し方を出す）
│   ├── bu_crawl.py             ← ① browser-use の中で動く巡回（URL で開く・スクショ・構造抽出・ページ内タブ）
│   ├── bu_verify.py            ← ④ browser-use の中で動く見た目の確認（幅 1440/390。OS をダークにしても明るいままか）
│   ├── build_book.py           ← ③ 4層HTMLブック生成（標準ライブラリのみ, 決定的）
│   ├── safety_rules.json       ← 禁止キーワード等（調整可）
│   ├── crawl.py                ← （任意・既定では使わない）Playwright 方式の巡回
│   └── requirements.txt        ← crawl.py 用（Playwright）。browser-use 方式では不要
├── references/
│   ├── safety-policy.md        ← 禁止事項の詳細と防護（必ず一読）
│   ├── description-guide.md    ← ② descriptions.json の書き方・品質基準
│   ├── guide-prompt.md         ← ④ write で Fable に渡す指示（システム概要書の構成と書き方）
│   └── manual-crawl.md         ← browser-use の注意・computer-use での手動巡回の手順
└── assets/book.css
```

## コマンドとして呼ばれたとき（最初に見る）

`/app-spec-crawler` の引数、または利用者の言葉で次のように振り分ける。どれも結果は**そのまま利用者に見せる**（要約しすぎない）。

| 呼ばれ方 | すること |
|---|---|
| 引数なし（`/app-spec-crawler`）・`help` | `app-spec-crawler help` を実行して、出た使い方を見せる。巡回は始めない |
| `doctor`（「使える？」「準備できてる？」） | `app-spec-crawler doctor [--url 対象URL]` を実行して表を見せる。NG・注意があれば「直し方」を示し、**直してよいか人に聞いてから**直す |
| URL や「仕様書を作って」 | 下の「2. 手順」。最初に `doctor` を流し、NG が無いことを確かめてから巡回する |

### 足りないもの・エラーのとき
- コマンドが失敗したら、出力の「✖ エラー / 原因 / 直し方」を**そのまま**見せ、なぜそうなったかを一言で補う。終了コード: 2 使い方 / 3 ログイン切れ / 4 Chrome につながらない / 5 必要なものが無い / 6 見た目の確認で問題 / 7 生成失敗 / 8 Fable での書き出しに失敗。
- **直す操作は人の承認をもらってから行う。** パッケージのインストール（`uv tool install browser-use` 等）、`browser-use mac-approve`・`--reload`、スキルのファイルの修正、`--exclude` を足しての再実行も含む。人の操作が要るもの（Chrome の遠隔デバッグの許可、ログインし直し）は、手順を示して待つ。
- 足りないパッケージがあれば、何に要るのかと入れるコマンドを示し、「入れてよいか」を聞く。承認されたら入れて、`doctor` をもう一度流して OK を確かめる。

### Playwright は要るか
**要らない。** 巡回も見た目の確認も browser-use で行う。Playwright は `scripts/crawl.py`（任意の別方式）を利用者が明示して使うときだけ要る。

## 0. 絶対禁止事項（最優先）

対象は顧客の本番環境であることが多い。**アプリケーションのデータ変更・更新・削除・送信・設定変更は、理由を問わず絶対に行わない。**
「編集」「保存」「登録」「更新」「送信」「決定」「確定」「削除」「承認」「公開」「ログアウト」等のボタン／リンクは**見るだけ**で押さない。
フォームに文字を入力しない。ファイルを選択しない。確認ダイアログは必ずキャンセルする。

browser-use 方式（`app-spec-crawler crawl`）は、画面を **URL で開くだけ**で回る（GET のみ）。入力・送信をする処理はコードに無い。
クリックするのは「今のページの `#名前` へのページ内タブ」だけ（`--no-tabs` で止められる）。logout / delete / approve / export 等を含む URL は開かない。
computer-use で手で回す場合も同じ基準で、迷ったら押さない。詳細は `references/safety-policy.md`。
（任意の `crawl.py` を使うときは `--allow-mutations` を顧客環境では**絶対に**使わない。）

## 1. 実行方式の選択

| 状況 | 方式 |
|---|---|
| `doctor` が「使える」（browser-use で利用者の Chrome につながる）**← 第一選択** | `app-spec-crawler crawl`（browser-use。判定がぶれず、網羅性ログが残る。Chrome を前に出さずに回る） |
| browser-use が使えない・入れられない、または利用者が「computer-use で」と言った | computer-use で手で回す（`references/manual-crawl.md` の Computer Use 手順） |
| 利用者が Playwright 方式を明示した | `scripts/crawl.py`（任意。`pip install -r scripts/requirements.txt && playwright install chromium` が要る。入れる前に承認をもらう） |

どの方式でも**出力形式（`pages.json` + `screenshots/`）は共通**なので、③のブック生成はそのまま使える。

### 利用者に確認すること（最初の1回だけ、まとめて聞く）
1. 起点URL と、巡回範囲（同一オリジン全体でよいか、`/admin/` 配下だけか等）
2. 対象アプリに、いつもの Chrome でログインしてあるか（browser-use は起動中の Chrome 全体につながるので、プロファイルは選べない）。
   Chrome の遠隔デバッグが無効なら、`chrome://inspect/#remote-debugging` で許可してもらう（`doctor` が教える）。
3. ページ上限（既定 300）と、画面を `?page=` のようなクエリで切り替えるアプリかどうか（それなら `--route-param`）
4. 出力先（社員の氏名などが写るので、git に入らない場所を勧める）

既に指示が揃っていれば聞かずに始める。

## 2. 手順

### ① 巡回（browser-use）
```bash
app-spec-crawler doctor --url https://app.example.com/          # NG が無いことを確かめる
app-spec-crawler crawl --url https://app.example.com/ --out ./spec_out

# 画面をクエリ（?page=...）で切り替えるアプリ
app-spec-crawler crawl --url "https://app.example.com/admin/<トークン>?page=/top" --out ./spec_out \
    --route-param page --variant-param tab --allow-route /export/select
```
- 利用者の Chrome に専用の接続（`BU_NAME=app-spec-crawler`）でつなぎ、作業用のタブを 1 つ作って回す。利用者のタブには触らない。初回は Chrome に許可の確認が出る（人が押すか、承認を得て `BU_NAME=app-spec-crawler browser-use mac-approve`）。
- 30 画面ずつ区切って回し、毎画面 `state.json` に書く。止まっても `--resume` で続きから回る。ログインが切れたら終了コード 3 で止まるので、人にログインし直してもらい、新しい URL で `--resume`。
- サイト内ヘルプやチャット窓などの外部の案内ツールが画面に重なるときは、`--hide <CSS セレクタ>`（複数可）で撮る直前に隠す。セレクタは対象アプリで開発者ツールを開いて調べる。
- ボタンの `onclick="location.href=..."` の移動先も拾う。今のページの `#名前` へのページ内タブはクリックして `states` として撮る。

出力: `spec_out/pages.json`（全ページの構造・リンク・フォーム・ボタン・操作状態）、`spec_out/screenshots/pXXX.png`（初期表示）と `pXXX_cNN.png`（タブ）、`spec_out/safety_report.json`、`spec_out/crawl.log`、`spec_out/state.json`（続きのための台帳）。

巡回後に確認すること:
- `safety_report.json` の `skipped_urls`（危険な言葉で開かなかった画面）を見て、ただの一覧なのに外れたものは利用者に確かめたうえで `--allow-route` で足す。
- `errors` があればその URL を `--exclude` するか、`--resume` で回し直す。
- 画面数が `--max-pages` に達していたら上限を上げて `--resume`。

### ② 画面説明の記入（AI）
```bash
app-spec-crawler describe ./spec_out     # descriptions.json の雛形を生成
```
`spec_out/descriptions.json` を埋める。これがこのスキルの中核であり、あなたの仕事。雛形には URL から自動生成した
**階層（`sections`）** と **画面（`pages`）** が列挙されている。書く順序は **全体 → 階層 → 画面** ではなく、
**画面 → 階層 → 全体** の順（個々の画面を見てから共通項を階層・全体に持ち上げる方が正確）。
各ページについて、`pages.json` の該当レコードと **スクリーンショットを必ず自分の目で見て**（Read で画像を開く）書く。
書き方・品質基準・良い例は `references/description-guide.md` を参照。

**仕様項目（specs）が本体。** `app.specs` / `sections[path].common_specs` / `pages[pXXX].specs` の3階層に、
`{type, statement, condition, evidence, confidence}` 形式で仕様を書く。`evidence` に `init` または状態ID `c02` を入れると、
ブック上でキャプチャの該当画像へリンクされる。画面固有でない仕様は階層か全体へ持ち上げ、同じ文を各画面に繰り返さない。

画面ごとの補助項目:
- `name`（画面名）/ `category`（機能分類）/ `summary`（1〜2文）
- `purpose`: 業務上の目的
- `display_conditions`: いつ・誰に・どの状態で表示されるか／されないか（権限、データ有無、前提操作）
- `users_and_usage`: 想定利用者と使われ方
- `features`: 主要機能の箇条書き
- `ui_elements`: 各ボタン・リンク・入力欄の挙動（押していないものは「推定」と明記）
- `inputs`: 入力項目と必須・バリデーション想定
- `flows`: 想定利用フロー（手順）
- `transitions`: 画面遷移
- `states_and_variants`: 空状態・エラー・権限差などのバリエーション
- `business_rules`: 推定される業務ルール
- `open_questions`: 不明点（推測で埋めず、ここに書く）
- `states.cNN`: 操作状態（モーダル等）ごとの説明と表示条件

ページが多い場合はカテゴリ単位でサブエージェントに分担させてよいが、各エージェントにもスクリーンショットを見させること。
事実（見えたもの）と推定（こうだろう）を文中で区別する。

### ③ ブック生成（プログラム）
```bash
app-spec-crawler build ./spec_out        # → ./spec_out/book/index.html
```
`book/index.html`、`overview.html`、`sections/*.html`、`pages/*.html`、`captures/*.html` が生成される。
未記入の箇所は「（要記入）」と表示され、実行時に画面・階層の記入済件数が出るので、未記入が無くなるまで②③を繰り返す。
画面が 2 つ以上ある階層で `common_specs` が空なら実行時に知らせるので、階層内で繰り返し出る仕様（共通のタブ、表示条件の形、ボタンの色分け等）を持ち上げる。

ブックの見た目（`assets/book.css` と `build_book.py` のテンプレート）:
- **上の帯は 2 段に分ける。** 1 段目はアプリ名と、2 つの読み物の**切り替え**（「システム概要書 ─ はじめに読む（1 ページ）」／「画面仕様書 ─ 画面ごとの仕様とスクリーンショット」。今いる方を塗る）。押すとページの作り（1 カラムの読み物 ⇔ 左に目次のあるブック）が変わるので、ふつうのメニューと同じ列に並べない。2 段目はブックのときだけ出す「画面仕様書」の中のメニュー（トップ/アプリ共通の仕様/階層仕様/画面一覧/安全性。今いる所に下線）。スマホではアプリ名を隠し、切り替えを幅いっぱいにする。
- 全ページの左に階層ごとの画面目次を常設し、今いる画面を強調して中央までスクロールする。
- 画面仕様の頭は 1 枚のカード（画面名・`summary` を大きめの一文・件数の札〔仕様 n・確認済/推定/要確認・キャプチャ n〕・パス・所属階層・到達経路・URL）。トークン入りの長い URL は 1 行に縮め、押すと全文。
- 本文は節ごとの白いカード。節が 3 つ以上あるとページ内目次（横 1 列・スクロール）を付ける。目的/表示条件/利用者、バリエーション/業務ルール（階層では役割/画面/遷移/権限）は短いので 1 枚のカードに並べる。
- 仕様の表は ID・種別・根拠・確度を折り返さない。スマホ幅では ID 列を隠す。
- トップは数字の札、階層カード、分類別のサムネイル付き画面カード。キャプチャ一覧はたたんで置く。
- **ライト固定。** OS がダークでも明るいまま（`color-scheme: light` と `<meta name="color-scheme" content="light">`。ダーク用のメディアクエリは書かない）。

### ④ システム概要書を Fable に書かせる（最後に必ず）
```bash
app-spec-crawler write ./spec_out        # → ./spec_out/book/guide.html（数分。上限 --budget 8 ドル）
```
- 中で `claude -p --model claude-fable-5-1 --tools "" --permission-mode dontAsk --effort high` を呼ぶ。標準入力は `references/guide-prompt.md` の指示 ＋ 材料（`descriptions.json` の読み物に要る項目と、リンクしてよいファイルの一覧）。
- Fable は `<article class="guide">` だけを書く。コマンドが script/style/on〜 属性と、無いファイルへのリンク・画像を除き、本文を `DIR/guide_body.html` に保存し、`build` が上の帯（切り替え）付きの枠に入れて `book/guide.html` を作る。枠や帯を直したときは `build` だけで反映され、Fable に書き直させる必要はない。
- 書き終わったら **Claude が guide.html を読み、材料と照らす。** 数字・画面名・ボタン名が材料と違う、材料に無い事実が足されている、「推定」が断定になっている、個人名が出ている — を見つけたら guide.html を直接直す（直した点を報告する）。
- 書く相手は初めての人（発注者・新メンバー・非エンジニアの担当者）。構成を変えたいときは `guide-prompt.md` を直す。
- `claude` が無い・ログイン切れ・上限に達したときは終了コード 8（または 5）と原因が出る。上限を上げる・入れる・ログインし直すのは人の承認を得てから。

### ⑤ 検証と納品
- `app-spec-crawler verify ./spec_out` を流す。トップ・システム概要書・アプリ共通の仕様・階層・画面仕様・キャプチャを、幅 1440px と 390px で、**OS をダークにした状態**で browser-use で開いて `spec_out/verify/` に撮り、はみ出し・読めない画像・暗い背景（ライト固定が崩れていないか）・「要記入」を数える（問題があれば終了コード 6）。撮った画像は **Read で開いて自分の目で見る**。
  - 機械で確かめること: 各ページの `document.documentElement.scrollWidth` が画面幅を超えない（横にはみ出さない）、読み込みに失敗した画像（`img.complete && naturalWidth===0`）が 0、`grep -r 要記入 book` が 0。
  - 目で見ること: 表の印や ID が途中で折り返していないか、左の目次で今の画面が強調されているか、スクリーンショットにアプリ以外の重なり（案内ツール等）が写っていないか。階層ツリーが実際のメニュー構造と食い違う場合は `sections[path].name` で階層名を付け直す（ツリー自体はURLから決定的に作られる）。
- ページ数が `pages.json` の件数と一致し、`safety_report.json` に未遮断の変更系リクエストが無いことを確認する。
- `book/` ディレクトリを zip にして渡す（スクリーンショットも同梱されるので単体で開ける）。
- 納品時に、巡回範囲・ページ数・押さなかった要素の件数・遮断したリクエスト数を一言添える。

## 3. よくある問題

- **`doctor` で「Chrome の遠隔デバッグ」が NG**: 利用者に `chrome://inspect/#remote-debugging` で許可してもらう（人の操作）。
- **browser-use が返ってこない（終了コード 4）**: Chrome に許可の確認が出たまま。人に押してもらうか、承認を得て `BU_NAME=app-spec-crawler browser-use mac-approve`。
- **ログイン画面に飛ばされる・「セッションが無効」（終了コード 3）**: 人にログインし直してもらい、新しい URL で `crawl --resume`。ログイン切れの文言が拾えないアプリは `--session-text` で足す。
- **SPAでリンクが `<a href>` でない**: browser-use 方式はボタンを押さないので、`onclick="location.href"` 以外の JS 遷移は拾えない。不足する画面は computer-use で手で開いて `pages.json` に追記するか、利用者に URL を聞いて `--resume` の起点にする。
- **無限にページが増える（カレンダー、ページネーション）**: `--exclude '[?&]page=' --exclude '/calendar/\d{4}'` 等で絞る。ID 付き URL（/users/123）は既定で `{id}` にまとまる。
- （`crawl.py` を使うときだけ）プロファイルのロック・GraphQL の POST・`--click-mode` などは `python scripts/crawl.py -h` を見る。
- **案内ツールのポップアップが全画面に重なる**: アプリ本体ではないので、`--hide <CSS セレクタ>` で撮る直前に `display:none` にして撮る（クリックで閉じない。「ガイドを停止」等は利用者の設定を変える）。仕様には「外部ツールが重なる」とアプリ共通の仕様に 1 行だけ書く。
- **ボタンで画面を移るアプリ**（`<button onclick="location.href='...'">`）: リンクだけ拾うと設定画面などが丸ごと抜ける。onclick の `location.href` も移動先として拾う（GET なので開いてよい。危険URLの判定は同じくかける）。
- **ページ内タブ**（`<a href="#xxx_contents">`）: URL の末尾（#）を変えるだけでは切り替わらないことがある。ページ内リンクのタブはクリックしてよい（サーバーに何も送らない）ので、`states` として撮る。
- **URL にセッションのトークンが入るアプリ**（`/admin/{トークン}?page=...`）: 一定時間操作が無いと切れるので、間を空けずに回す。`norm_url` は route-param の値をパスに見立てて作ると階層ツリーがメニュー構造に合う。
