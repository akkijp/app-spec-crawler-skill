# browser-use の注意と、手で回すときの手順 — Browser Use / Computer Use / Claude in Chrome

ふだんは `app-spec-crawler crawl`（browser-use。`scripts/bu_crawl.py`）で回す。下の「browser-use CLI の注意」はそのしくみの説明。
browser-use が使えないとき、または利用者が「computer-use で」と指定したときは、Claude が画面を見て手で回す（下の「手順」）。
判断はAIが行うためプログラムよりぶれやすい。そのぶん**記録を厳密に**取り、出力形式は `bu_crawl.py` と同じ（`pages.json` スキーマ）にして `build_book.py` に渡す。
安全ルールは `safety-policy.md` の「手動巡回時の追加ルール」に従う。

## 道具の選択
| 道具 | 使うとき | 備考 |
|---|---|---|
| Claude in Chrome（`mcp__claude-in-chrome__*`） | 利用者の Chrome にログイン済みセッションがある | `chrome-browser` スキルを先に読む。新規タブで作業し、利用者の既存タブは触らない |
| 内蔵ブラウザ（`mcp__Claude_Browser__*` / `mcp__remote-devices__Claude_Browser__*`） | 内蔵ブラウザ側にログインできる | `built-in-browser` スキルを先に読む |
| Browser Use（`browser-use` CLI / Codex 等の browser ツール） | 利用者の起動中の Chrome にログイン済みセッションがある | 下の「browser-use CLI の注意」を読む。「表示／ヘッドレス」はツール側のオプションに従う。既定は表示 |
| Computer Use（`mcp__remote-devices__computer_*` 等） | ブラウザ拡張が無く、画面操作しかできない | `computer-use` スキルを先に読む。スクショは画面単位なので、長いページはスクロールして複数枚撮り、`pXXX_s1.png, s2...` と連番にする |

ヘッドレス指定があり、かつ道具がヘッドレスをサポートしない場合は、その旨を利用者に伝えて表示モードで続行する。

## browser-use CLI の注意
- **つなぐ先を名指しする。** 既定のままだと `localhost:9222` など別の Chrome（他の作業の画面なし Chrome 等）につながることがある。利用者に Chrome の `chrome://inspect/#remote-debugging` で遠隔デバッグを許可してもらい、`~/Library/Application Support/Google/Chrome/DevToolsActivePort`（1 行目がポート、2 行目がパス）から `BU_CDP_WS=ws://127.0.0.1:<port><path>` を作って毎回付ける。最初の接続で Chrome に許可の確認が出たら `browser-use mac-approve`。
- つないだら `cdp("Browser.getVersion")["userAgent"]` に `HeadlessChrome` が入っていないこと、対象アプリのタブ（ログイン済み）があることを確かめてから始める。
- Chrome のプロファイルは選べない（起動中の Chrome 全体につながる）。利用者がプロファイル名を言ったら、`Local State` の `profile.info_cache` で名前とアカウントを照らし、どれのつもりかを伝える。
- 作業用のタブは `new_tab()` で 1 つだけ作り、利用者のタブには触らない。終わったら `close_tab()` で閉じる。
- `app-spec-crawler crawl` はこれらを自動で行う（専用の接続 `BU_NAME=app-spec-crawler`・`BU_CDP_WS` の組み立て・作業用タブ・区切った実行・ログイン切れの検知）。以下は自分でスクリプトを書くときの注意。
- 巡回は Python のスクリプトにして `browser-use < script.py` で流す（helpers は読み込み済み）。状態（キュー・訪問済み・pages）を JSON に毎ページ書き、30 画面ずつのように区切って何度も流せる形にする（1 回の実行の時間切れに備える）。
- スクリーンショットは `Emulation.setDeviceMetricsOverride` で幅 1400px・高さをページの高さ（上限 6000px）にしてから `capture_screenshot()`。撮ったら 1400×900 に戻す。背景のタブのままで撮れる（Chrome を前に出さない）。

## 作業ディレクトリ
```
spec_out/
├── pages.json          ← 下記スキーマで自分で書く（逐次更新）
├── screenshots/        ← pXXX.png / pXXX_cNN.png
├── safety_report.json  ← 押さなかった要素・遷移しなかったURL・エラー
└── crawl.log           ← 時刻付きの操作ログ（何を押したか全て）
```

## 手順
1. 起点URLを開き、ログイン済みであることを確認する。ログイン画面なら利用者に再ログインを依頼して止まる。
2. **ページ台帳**を作る: 現在のページに `p001` を振り、URL・タイトルを `pages.json` に記録し、全画面スクリーンショットを `screenshots/p001.png` に保存する。
3. ページの構造を読み取る（ブラウザツールの「ページをテキストで読む」/ DOM取得を使う）:
   - 見出し、ナビゲーション、内部リンク（href と表示テキスト）、フォームの入力項目（name/type/label/required/placeholder、**値は入力しない**）、テーブルのヘッダ、ボタン類。
   - 内部リンクのうち危険キーワード（`safety_rules.json` の `deny_url_keywords`）を含むものは `skipped_urls` に記録し、キューに入れない。
   - 残りの未訪問リンクをキュー（幅優先）に積む。`/users/123` のようなID付きURLは代表1件だけにする。
4. **クリック探索**: ボタン・タブ・メニュー・アコーディオン・`role=button` を列挙し、1つずつ次を行う。
   - 安全判定（`deny_click_keywords` に該当しない、submit でない、ラベルがある、無効化されていない）。不可なら `clickables[].reason` に理由を書いて飛ばす。
   - **ページを再読込して初期状態に戻してから**要素を1回クリックする。
   - 待ってスクリーンショット `pXXX_cNN.png` を撮り、`states[]` に `label / result（ページ遷移・モーダル・画面内変化・変化なし）/ url_after / modals` を記録する。
   - モーダル内に新しい内部リンクがあればキューに追加する。
   - 遷移した場合は遷移先URLを（危険でなければ）キューに追加し、元のページに戻る。
   - 1ページあたりの上限（既定40）に達したら残りは `reason: "上限超過"` で記録する。
5. キューの次のURLへ進み、2〜4 を繰り返す。上限ページ数（既定300）に達したら利用者に報告する。
6. 各ページ終了ごとに `pages.json` と `crawl.log` を書き出す（途中で止まっても成果が残るように）。
7. 完了後、`build_book.py --crawl spec_out --init-descriptions` → 説明記入 → `build_book.py --crawl spec_out` で `SKILL.md` ②③④へ合流する。階層ツリーは `norm_url` のパスから自動生成されるので、ID付きURLは `/users/{id}` のように `{id}` へ正規化して記録する。

## pages.json スキーマ（crawl.py と同一。手動時は使わない項目は省略可）
```json
{
  "meta": { "start_url": "", "origin": "", "scope": [""], "generated_at": "", "headless": false,
            "click_mode": "safe", "allow_mutations": false, "page_count": 0, "state_count": 0,
            "blocked_request_count": 0, "skipped_element_count": 0, "skipped_url_count": 0, "error_count": 0, "complete": true,
            "method": "manual:claude-in-chrome" },
  "pages": [
    {
      "id": "p001", "url": "https://app.example.com/", "norm_url": "https://app.example.com/", "requested_url": "", "depth": 0, "parent": null,
      "title": "Dashboard", "visited_at": "2026-10-27T10:00:00", "screenshot": "screenshots/p001.png",
      "headings": [{"level": "H1", "text": "ダッシュボード"}],
      "forms": [{"index": 0, "action": "", "method": "GET", "name": "search",
                 "fields": [{"tag": "input", "type": "text", "name": "q", "id": "", "placeholder": "検索", "required": false, "label": "キーワード"}]}],
      "looseFields": [], "tables": [{"caption": "", "headers": ["ID", "名前"], "rows": 20}], "nav": ["ホーム 顧客 設定"],
      "modals_on_load": [], "bodyText": "（本文テキスト先頭 4000 文字）",
      "links": [{"text": "顧客", "href": "https://app.example.com/customers", "internal": true, "norm": "https://app.example.com/customers"},
                {"text": "ログアウト", "href": "https://app.example.com/logout", "internal": true, "skipped": "危険URLキーワード: logout"}],
      "clickables": [{"index": 0, "tag": "button", "text": "絞り込み", "ariaLabel": "", "title": "", "role": "", "type": "button",
                      "selector": "#filterBtn", "inForm": false, "disabled": false, "clickable": true, "reason": "ok"},
                     {"index": 1, "tag": "button", "text": "保存", "clickable": false, "reason": "禁止キーワード: 保存"}],
      "states": [{"id": "c01", "label": "絞り込み", "selector": "#filterBtn", "role": "button",
                  "result": "モーダル/ダイアログ表示", "screenshot": "screenshots/p001_c01.png",
                  "url_after": "https://app.example.com/", "modals": [{"title": "絞り込み条件"}], "changed": true}]
    }
  ]
}
```
`safety_report.json`:
```json
{ "blocked_requests": [], "skipped_elements": [{"page": "p001", "text": "保存", "selector": "", "reason": "禁止キーワード: 保存"}],
  "skipped_urls": [{"page": "p001", "href": "https://app.example.com/logout", "reason": "危険URLキーワード: logout"}], "errors": [] }
```

## Computer Use 特有の注意
- 画面全体ではなくブラウザウィンドウのみを撮る。利用者の他のウィンドウ・通知が写り込まないよう最大化する。
- 長いページはスクロールしながら撮影し、`pXXX_s01.png … s0N.png` と命名。`screenshot` には先頭の1枚を入れ、残りは `extra_screenshots: []` に列挙する（`build_book.py` は未対応なので、必要なら `states` として登録して掲載する）。
- クリック座標の誤差で隣の「保存」を押す事故が起こり得る。変更系ボタンの**隣接要素**はクリック前にズーム表示で位置を確認するか、押さない。
- キーボードで文字を打たない（アドレスバーへのURL入力のみ可）。
