あなたは業務システムの仕様書を書く担当です。下の「材料」（Web アプリを読み取り専用で巡回して作った、画面ごとの仕様のメモ）だけを使って、
初めてこのシステムに触れる人（発注者・新しく入ったメンバー・非エンジニアの担当者）が読んで全体をつかめる「仕様書」を書いてください。

## 出すもの

- `<article class="guide">` で始まり `</article>` で終わる HTML だけを出す。前後に説明文やコードフェンスを付けない。
- `<html>` `<head>` `<style>` `<script>`、style 属性、on〜 属性は書かない。見た目はこちらで付ける。

## 構成（この順。材料に無い節は省く）

1. `<header class="g-hero">`: `<h1>` に「システム名 システム概要書」、`<p class="g-lead">` に「何のためのシステムか」を 2〜3 文。
2. `<nav class="g-toc">`: 下の各節（`<section id="...">`）へのリンクの `<a>` だけを並べる（`<ul>` は使わない）。
3. `<section id="whatis">` このシステムでできること: 3〜7 個の大きなまとまりを `<div class="g-cards">` と `<div class="g-card"><h3>…</h3><p>…</p></div>` で。
4. `<section id="users">` 誰がどう使うか: 利用者の種類と、権限による見え方の違い。
5. `<section id="map">` 画面の地図: メニューの階層を `<ul class="g-tree">` の入れ子で。各画面名は画面仕様へリンクする。
6. `<section id="flows">` 主な業務の流れ: 2〜5 本。`<ol class="g-steps">` で、各手順に使う画面へのリンクを入れる。
7. `<section id="features">` 機能ごとの説明: 機能の分類ごとに `<h3>`。各分類の中で、代表の画面を 1〜2 枚の `<figure class="g-shot">`（`<a href="pages/pXXX.html"><img src="screenshots/pXXX.png" alt="画面名" loading="lazy"></a><figcaption>…</figcaption>`）で見せ、その分類でできることを箇条書き。全画面を図にしなくてよい。
8. `<section id="rules">` 決まりごと: 業務ルール・表示条件・制約を `<table class="g-table">`（列: 決まりごと / どの画面 / 確かさ）で。
9. `<section id="terms">` 用語: システム固有の言葉を `<dl class="g-terms">` で。
10. `<section id="open">` 確認が必要なこと: 材料の open_questions と「推定」の項目のうち、利用者や開発者に聞くべきものを箇条書き。

## 書き方

- 正しい日本語の常体（だ・である）。普段の仕事の言葉で書く。一文を短く。専門用語は最初に一度だけ言い換える。
- 材料にある事実だけを書く。数字・画面名・ボタン名・URL を変えない、足さない。材料が「推定」としたことは「〜と推定される」「（推定）」と書き、確かなことのように書かない。押していないボタンの結果を断定しない。
- 「確かさ」の列は `<span class="g-ok">確認済</span>` `<span class="g-guess">推定</span>` `<span class="g-ask">要確認</span>` のどれか。
- リンクと画像は材料の「使えるファイル」にあるパスだけを使う（`pages/pXXX.html` `captures/pXXX.html` `sections/….html` `screenshots/….png` `overview.html`）。外部 URL は書かない。
- 仕様項目の ID（SPEC-…）や、巡回の手順・ツールの話は本文に出さない。
- 個人名・社員番号など、スクリーンショットや材料に出ていた個人の情報は書かない。
- 結論を先に書く。各節の最初の 1 文で、その節で分かることを言う。

## 材料
