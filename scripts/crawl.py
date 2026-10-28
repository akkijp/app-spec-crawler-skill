#!/usr/bin/env python3
"""
app-spec-crawler / crawl.py
---------------------------
ログイン済みブラウザプロファイル（または起動中のChromeへのCDP接続）を使い、
指定URL配下のWebアプリケーションを読み取り専用で巡回し、
全ページ・全「安全なクリック状態」のスクリーンショットと構造情報 (pages.json) を出力する。

絶対原則: アプリケーションのデータを一切変更しない。
  1. ネットワーク層: GET/HEAD/OPTIONS 以外のHTTPリクエストを全て遮断（既定）
  2. 要素層:        保存/削除/送信 等のキーワードを含む要素・submit系要素は絶対にクリックしない
  3. 入力層:        フォームに文字を入力しない、ファイルを選択しない
  4. ダイアログ層:  confirm/prompt/beforeunload は全て dismiss（=キャンセル）
  5. 遷移層:        logout/delete 等を含むURLには遷移しない

使い方（例）:
  python crawl.py --url https://app.example.com/ --profile "/Users/me/Library/Application Support/Google/Chrome" \
      --profile-directory "Profile 1" --out ./out
  python crawl.py --url https://app.example.com/ --cdp http://localhost:9222 --out ./out   # 起動中Chromeに接続
  python crawl.py --url ... --storage-state state.json --out ./out                          # Playwright保存状態
  オプション: --headless で非表示実行（既定は表示）
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import traceback
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:  # pragma: no cover
    print("playwright が見つかりません: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# ----------------------------------------------------------------------------
# 引数
# ----------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="読み取り専用 Webアプリ巡回・スクリーンショット収集")
    p.add_argument("--url", required=True, help="巡回の起点URL")
    p.add_argument("--out", default="./out", help="出力ディレクトリ")

    g = p.add_argument_group("ブラウザ/認証（いずれか1つ）")
    g.add_argument("--profile", help="ブラウザのユーザーデータディレクトリ（Chrome/Edge/Chromium）。※そのプロファイルでブラウザを起動中だと使えないのでコピーを指定するのが確実")
    g.add_argument("--profile-directory", default=None, help="--profile 内のプロファイル名（例: 'Default', 'Profile 1'）")
    g.add_argument("--cdp", help="起動中ブラウザのCDPエンドポイント（例: http://localhost:9222）。chrome --remote-debugging-port=9222 で起動しておく")
    g.add_argument("--storage-state", help="Playwright の storage_state JSON")
    g.add_argument("--channel", default=None, help="chrome / msedge / chromium（既定: profile指定時はchrome、それ以外はchromium）")

    s = p.add_argument_group("巡回範囲")
    s.add_argument("--scope-prefix", action="append", default=[], help="このURLプレフィックス配下のみ巡回（複数可）。未指定なら起点URLと同一オリジン全体")
    s.add_argument("--exclude", action="append", default=[], help="除外URL正規表現（複数可）")
    s.add_argument("--max-pages", type=int, default=300)
    s.add_argument("--max-depth", type=int, default=10)
    s.add_argument("--keep-query", action="store_true", help="クエリ文字列を区別して別ページ扱いにする（既定: 無視）")
    s.add_argument("--id-collapse", action="store_true", help="/users/123 のような数値IDセグメントを同一視し、代表1件のみ巡回する")

    c = p.add_argument_group("クリック探索")
    c.add_argument("--click-mode", choices=["safe", "none"], default="safe", help="safe: 安全判定を通った要素のみクリック / none: クリックしない")
    c.add_argument("--max-clicks-per-page", type=int, default=40)
    c.add_argument("--click-allow-pattern", help="この正規表現にマッチするテキストの要素のみクリック対象にする（さらに絞る）")

    d = p.add_argument_group("表示・待機")
    d.add_argument("--headless", action="store_true", help="ヘッドレス実行（既定は画面表示）")
    d.add_argument("--viewport", default="1440x900")
    d.add_argument("--wait", type=int, default=1200, help="遷移/クリック後の追加待機 ms")
    d.add_argument("--timeout", type=int, default=20000, help="ナビゲーションタイムアウト ms")
    d.add_argument("--full-page", action="store_true", default=True)
    d.add_argument("--no-full-page", dest="full_page", action="store_false")
    d.add_argument("--save-html", action="store_true", help="各ページのDOM(HTML)も保存する")

    x = p.add_argument_group("危険オプション（通常は使わない）")
    x.add_argument("--allow-mutations", action="store_true", help="GET以外のリクエストを遮断しない。顧客環境では絶対に使わないこと")
    x.add_argument("--allow-post-pattern", action="append", default=[], help="この正規表現にマッチするURLへのPOSTのみ許可（GraphQLの読み取り等）。mutationが混ざる恐れがあるため慎重に")

    p.add_argument("--rules", default=str(HERE / "safety_rules.json"), help="安全判定ルールJSON")
    return p.parse_args()


# ----------------------------------------------------------------------------
# ユーティリティ
# ----------------------------------------------------------------------------
def load_rules(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def norm_url(url: str, keep_query: bool, id_collapse: bool) -> str:
    u = urlparse(url)
    path = u.path or "/"
    if id_collapse:
        path = re.sub(r"/\d+(?=/|$)", "/{id}", path)
        path = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?=/|$)", "/{uuid}", path, flags=re.I)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunparse((u.scheme, u.netloc.lower(), path, "", u.query if keep_query else "", ""))


def page_id(index: int) -> str:
    return f"p{index:03d}"


def text_key(*parts: str) -> str:
    return " ".join((x or "") for x in parts).lower()


def contains_any(hay: str, needles: list[str]) -> str | None:
    for n in needles:
        if n and n.lower() in hay:
            return n
    return None


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


# ----------------------------------------------------------------------------
# ページ内情報抽出（ブラウザ側で実行するJS）
# ----------------------------------------------------------------------------
EXTRACT_JS = r"""
(clickableSelector) => {
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
  };
  const txt = (el) => (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 120);
  const attr = (el, a) => el.getAttribute(a) || '';
  const cssPath = (el) => {
    // 安定しやすいセレクタ: id > data-testid > 階層パス
    if (el.id) return '#' + CSS.escape(el.id);
    const tid = attr(el, 'data-testid'); if (tid) return `[data-testid="${tid}"]`;
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 8) {
      let sel = cur.tagName.toLowerCase();
      if (cur.id) { parts.unshift('#' + CSS.escape(cur.id)); break; }
      const sib = Array.from(cur.parentNode ? cur.parentNode.children : []).filter(c => c.tagName === cur.tagName);
      if (sib.length > 1) sel += `:nth-of-type(${sib.indexOf(cur) + 1})`;
      parts.unshift(sel);
      cur = cur.parentNode;
    }
    return parts.join(' > ');
  };

  const headings = Array.from(document.querySelectorAll('h1,h2,h3')).filter(vis).map(h => ({level: h.tagName, text: txt(h)})).slice(0, 60);

  const links = Array.from(document.querySelectorAll('a[href]')).filter(vis).map(a => ({
    text: txt(a), href: a.href, target: attr(a, 'target')
  })).slice(0, 500);

  const forms = Array.from(document.querySelectorAll('form, [role="form"]')).map((f, i) => ({
    index: i, action: attr(f, 'action'), method: (attr(f, 'method') || 'get').toUpperCase(), name: attr(f, 'name') || attr(f, 'id'),
    fields: Array.from(f.querySelectorAll('input,select,textarea')).map(el => ({
      tag: el.tagName.toLowerCase(), type: attr(el, 'type') || (el.tagName.toLowerCase()==='select'?'select':'text'),
      name: attr(el, 'name'), id: el.id, placeholder: attr(el, 'placeholder'), required: el.required || attr(el,'aria-required')==='true',
      label: (el.labels && el.labels[0]) ? txt(el.labels[0]) : (attr(el,'aria-label') || ''),
      options: el.tagName.toLowerCase()==='select' ? Array.from(el.options).map(o => txt(o)).slice(0, 30) : undefined,
      disabled: el.disabled, readonly: el.readOnly
    }))
  }));
  // フォーム外の入力要素
  const looseFields = Array.from(document.querySelectorAll('input,select,textarea')).filter(el => !el.closest('form') && vis(el)).map(el => ({
    tag: el.tagName.toLowerCase(), type: attr(el, 'type') || 'text', name: attr(el, 'name'), id: el.id, placeholder: attr(el, 'placeholder'),
    label: (el.labels && el.labels[0]) ? txt(el.labels[0]) : (attr(el,'aria-label') || '')
  }));

  const tables = Array.from(document.querySelectorAll('table')).filter(vis).map(t => ({
    caption: t.caption ? txt(t.caption) : '',
    headers: Array.from(t.querySelectorAll('thead th, tr:first-child th')).map(txt).slice(0, 40),
    rows: t.querySelectorAll('tbody tr').length
  })).slice(0, 30);

  const clickables = Array.from(document.querySelectorAll(clickableSelector)).filter(vis).map((el, i) => ({
    index: i, tag: el.tagName.toLowerCase(), text: txt(el), ariaLabel: attr(el, 'aria-label'), title: attr(el, 'title'),
    name: attr(el, 'name'), id: el.id, className: (typeof el.className === 'string' ? el.className : ''), type: attr(el, 'type'),
    role: attr(el, 'role'), href: attr(el, 'href'), value: attr(el, 'value'), disabled: !!el.disabled || attr(el,'aria-disabled')==='true',
    inForm: !!el.closest('form'), selector: cssPath(el)
  })).slice(0, 400);

  const nav = Array.from(document.querySelectorAll('nav, [role="navigation"], aside')).filter(vis).map(n => txt(n).slice(0, 400)).slice(0, 5);
  const bodyText = (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 4000);
  const modals = Array.from(document.querySelectorAll('[role="dialog"], [aria-modal="true"], .modal.show, .MuiDialog-root, dialog[open]')).filter(vis).map(m => ({ title: txt(m).slice(0, 200) }));

  return { title: document.title, headings, links, forms, looseFields, tables, clickables, nav, bodyText, modals,
           lang: document.documentElement.lang || '' };
}
"""


# ----------------------------------------------------------------------------
# 本体
# ----------------------------------------------------------------------------
class Crawler:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.rules = load_rules(args.rules)
        self.out = Path(args.out).resolve()
        self.shots = self.out / "screenshots"
        self.html_dir = self.out / "html"
        self.shots.mkdir(parents=True, exist_ok=True)
        if args.save_html:
            self.html_dir.mkdir(exist_ok=True)

        start = urlparse(args.url)
        self.origin = f"{start.scheme}://{start.netloc.lower()}"
        self.scope = [s.rstrip("/") for s in args.scope_prefix] or [self.origin]
        self.exclude = [re.compile(x, re.I) for x in args.exclude]
        self.allow_post = [re.compile(x, re.I) for x in args.allow_post_pattern]
        self.click_allow = re.compile(args.click_allow_pattern, re.I) if args.click_allow_pattern else None

        self.pages: dict[str, dict] = {}        # norm_url -> page record
        self.order: list[str] = []
        self.queue: deque[tuple[str, int, str | None]] = deque()
        self.blocked_requests: list[dict] = []
        self.skipped_elements: list[dict] = []
        self.skipped_urls: list[dict] = []
        self.errors: list[dict] = []
        self.log_path = self.out / "crawl.log"
        self._log_fh = open(self.log_path, "a", encoding="utf-8")

    # -- ログ ---------------------------------------------------------------
    def log(self, msg: str) -> None:
        line = f"[{now_iso()}] {msg}"
        print(line, flush=True)
        self._log_fh.write(line + "\n")
        self._log_fh.flush()

    # -- 安全判定 -------------------------------------------------------------
    def url_in_scope(self, url: str) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        u = urlparse(url)
        if f"{u.scheme}://{u.netloc.lower()}" != self.origin:
            return False
        if not any(url.startswith(s) for s in self.scope):
            return False
        return not any(x.search(url) for x in self.exclude)

    def url_is_dangerous(self, url: str) -> str | None:
        return contains_any(url.lower(), self.rules.get("deny_url_keywords", []))

    def element_click_verdict(self, el: dict) -> tuple[bool, str]:
        """(クリックしてよいか, 理由)"""
        if el.get("disabled"):
            return False, "disabled"
        if (el.get("type") or "").lower() in {"submit", "reset", "image"}:
            return False, "submit/reset 要素"
        if el.get("tag") in {"input"}:
            return False, "input 要素"
        hay = text_key(el.get("text"), el.get("ariaLabel"), el.get("title"), el.get("name"), el.get("id"),
                       el.get("className"), el.get("value"), el.get("href"))
        hit = contains_any(hay, self.rules.get("deny_click_keywords", []))
        if hit:
            return False, f"禁止キーワード: {hit}"
        if el.get("inForm") and el.get("tag") == "button" and not (el.get("type") or "").lower() == "button":
            # form 内で type 未指定の button は submit 扱いになる
            return False, "form内のtype未指定button(=submit)"
        if self.click_allow and not self.click_allow.search(hay):
            return False, "click-allow-pattern 不一致"
        label = (el.get("text") or el.get("ariaLabel") or el.get("title") or "").strip()
        if not label and not el.get("id") and not el.get("ariaLabel"):
            # ラベルのないアイコンボタンは何をするか判別不能 → 既定では押さない
            return False, "ラベルなし要素（用途不明）"
        return True, "ok"

    # -- ネットワーク遮断 -----------------------------------------------------
    def install_request_guard(self, context) -> None:
        def handler(route, request):
            m = request.method.upper()
            if m in SAFE_METHODS or self.args.allow_mutations:
                return route.continue_()
            if m == "POST" and any(p.search(request.url) for p in self.allow_post):
                return route.continue_()
            self.blocked_requests.append({"time": now_iso(), "method": m, "url": request.url, "page": self.current_url})
            self.log(f"BLOCKED {m} {request.url}")
            return route.abort("blockedbyclient")
        context.route("**/*", handler)

    def install_dialog_guard(self, page) -> None:
        def on_dialog(dialog):
            self.log(f"DIALOG dismissed ({dialog.type}): {dialog.message[:120]}")
            try:
                dialog.dismiss()
            except Exception:
                pass
        page.on("dialog", on_dialog)

    # -- ブラウザ起動 ---------------------------------------------------------
    def launch(self, pw):
        a = self.args
        w, h = (int(x) for x in a.viewport.lower().split("x"))
        if a.cdp:
            browser = pw.chromium.connect_over_cdp(a.cdp)
            context = browser.contexts[0] if browser.contexts else browser.new_context(viewport={"width": w, "height": h})
            self.log(f"CDP接続: {a.cdp} (contexts={len(browser.contexts)})")
            return browser, context, True
        if a.profile:
            launch_args = ["--disable-blink-features=AutomationControlled"]
            if a.profile_directory:
                launch_args.append(f"--profile-directory={a.profile_directory}")
            context = pw.chromium.launch_persistent_context(
                a.profile, channel=a.channel or "chrome", headless=a.headless,
                viewport={"width": w, "height": h}, args=launch_args, accept_downloads=False,
            )
            self.log(f"プロファイル起動: {a.profile} / {a.profile_directory or 'Default'} headless={a.headless}")
            return None, context, False
        browser = pw.chromium.launch(channel=a.channel, headless=a.headless)
        context = browser.new_context(viewport={"width": w, "height": h}, storage_state=a.storage_state, accept_downloads=False)
        self.log(f"新規コンテキスト起動 storage_state={a.storage_state} headless={a.headless}")
        return browser, context, False

    # -- 巡回 -----------------------------------------------------------------
    def run(self) -> None:
        self.current_url = self.args.url
        with sync_playwright() as pw:
            browser, context, attached = self.launch(pw)
            context.set_default_navigation_timeout(self.args.timeout)
            context.set_default_timeout(min(self.args.timeout, 8000))
            self.install_request_guard(context)
            page = context.new_page()
            self.install_dialog_guard(page)
            page.set_viewport_size({"width": int(self.args.viewport.split("x")[0]), "height": int(self.args.viewport.split("x")[1])})

            start_norm = norm_url(self.args.url, self.args.keep_query, self.args.id_collapse)
            self.queue.append((self.args.url, 0, None))
            seen = {start_norm}
            try:
                while self.queue and len(self.pages) < self.args.max_pages:
                    url, depth, parent = self.queue.popleft()
                    try:
                        self.visit(page, url, depth, parent, seen)
                    except Exception as e:  # ページ単位で続行
                        self.errors.append({"url": url, "error": repr(e), "trace": traceback.format_exc()[-1500:]})
                        self.log(f"ERROR {url}: {e!r}")
                    self.write_outputs()  # 途中結果を逐次保存
            finally:
                self.write_outputs(final=True)
                try:
                    if attached:
                        page.close()  # 利用者のブラウザは閉じない
                    else:
                        context.close()
                        if browser:
                            browser.close()
                except Exception:
                    pass

    def goto(self, page, url: str) -> None:
        self.current_url = url
        try:
            page.goto(url, wait_until="domcontentloaded")
        except PWTimeout:
            self.log(f"goto timeout (domcontentloaded) {url}")
        try:
            page.wait_for_load_state("networkidle", timeout=min(self.args.timeout, 10000))
        except PWTimeout:
            pass
        page.wait_for_timeout(self.args.wait)

    def extract(self, page) -> dict:
        return page.evaluate(EXTRACT_JS, self.rules.get("clickable_selector"))

    def visit(self, page, url: str, depth: int, parent: str | None, seen: set[str]) -> None:
        nurl = norm_url(url, self.args.keep_query, self.args.id_collapse)
        pid = page_id(len(self.pages) + 1)
        self.log(f"VISIT {pid} depth={depth} {url}")
        self.goto(page, url)
        final_url = page.url
        final_norm = norm_url(final_url, self.args.keep_query, self.args.id_collapse)
        if final_norm != nurl and final_norm in self.pages:
            self.log(f"  -> redirect to already-visited {final_url}; skip")
            return
        if not self.url_in_scope(final_url):
            self.log(f"  -> redirected out of scope {final_url}; skip")
            return

        info = self.extract(page)
        shot = f"{pid}.png"
        page.screenshot(path=str(self.shots / shot), full_page=self.args.full_page)
        if self.args.save_html:
            (self.html_dir / f"{pid}.html").write_text(page.content(), encoding="utf-8")

        rec = {
            "id": pid, "url": final_url, "norm_url": final_norm, "requested_url": url, "depth": depth, "parent": parent,
            "title": info.get("title"), "lang": info.get("lang"), "visited_at": now_iso(), "screenshot": f"screenshots/{shot}",
            "headings": info.get("headings", []), "forms": info.get("forms", []), "looseFields": info.get("looseFields", []),
            "tables": info.get("tables", []), "nav": info.get("nav", []), "modals_on_load": info.get("modals", []),
            "bodyText": info.get("bodyText", ""), "links": [], "clickables": [], "states": [],
        }
        self.pages[final_norm] = rec
        self.order.append(final_norm)

        # --- リンク収集 → キュー
        self.enqueue_links(info.get("links", []), final_url, depth, pid, seen, rec)

        # --- クリック探索
        if self.args.click_mode == "safe":
            self.explore_clicks(page, rec, info, depth, seen)

    def enqueue_links(self, links: list[dict], base: str, depth: int, pid: str, seen: set[str], rec: dict) -> None:
        known = {(l.get("text"), l.get("href")) for l in rec["links"]}
        for ln in links:
            href = urljoin(base, ln.get("href") or "")
            if (ln.get("text"), href) in known:
                continue
            known.add((ln.get("text"), href))
            entry = {"text": ln.get("text"), "href": href, "internal": self.url_in_scope(href)}
            if entry["internal"]:
                danger = self.url_is_dangerous(href)
                if danger:
                    entry["skipped"] = f"危険URLキーワード: {danger}"
                    if not any(s["page"] == pid and s["href"] == href for s in self.skipped_urls):
                        self.skipped_urls.append({"page": pid, "href": href, "reason": entry["skipped"]})
                else:
                    n = norm_url(href, self.args.keep_query, self.args.id_collapse)
                    entry["norm"] = n
                    if n not in seen and depth < self.args.max_depth:
                        seen.add(n)
                        self.queue.append((href, depth + 1, pid))
            rec["links"].append(entry)

    def explore_clicks(self, page, rec: dict, info: dict, depth: int, seen: set[str]) -> None:
        candidates = []
        for el in info.get("clickables", []):
            ok, reason = self.element_click_verdict(el)
            entry = {k: el.get(k) for k in ("index", "tag", "text", "ariaLabel", "title", "role", "type", "selector", "inForm", "disabled")}
            entry["clickable"] = ok
            entry["reason"] = reason
            rec["clickables"].append(entry)
            if ok:
                candidates.append(el)
            else:
                self.skipped_elements.append({"page": rec["id"], "text": el.get("text"), "selector": el.get("selector"), "reason": reason})
        candidates = candidates[: self.args.max_clicks_per_page]
        self.log(f"  clickables: {len(info.get('clickables', []))} total, {len(candidates)} safe")

        before_sig = dom_signature(info)
        page_url = rec["url"]
        for i, el in enumerate(candidates, start=1):
            sid = f"c{i:02d}"
            label = (el.get("text") or el.get("ariaLabel") or el.get("title") or el.get("id") or "")[:80]
            state = {"id": sid, "label": label, "selector": el.get("selector"), "role": el.get("role") or el.get("tag"), "result": None}
            try:
                # 毎回ページを再読込して初期状態から1クリックだけ行う（状態の混入を防ぎ、結果を決定的にする）
                self.goto(page, page_url)
                loc = page.locator(el["selector"]).first
                if loc.count() == 0 or not loc.is_visible():
                    state["result"] = "要素が見つからない/非表示"
                    rec["states"].append(state)
                    continue
                loc.scroll_into_view_if_needed(timeout=3000)
                loc.click(timeout=4000, no_wait_after=True)
                page.wait_for_timeout(self.args.wait)
                after_url = page.url
                after = self.extract(page)
                shot = f"{rec['id']}_{sid}.png"
                page.screenshot(path=str(self.shots / shot), full_page=self.args.full_page)
                state["screenshot"] = f"screenshots/{shot}"
                state["url_after"] = after_url
                state["modals"] = after.get("modals", [])
                state["headings_after"] = after.get("headings", [])[:10]
                # 変化判定はDOMの内容（本文・見出し・モーダル）で行う。画像比較だとフォーカス枠だけでも差が出るため
                state["changed"] = dom_signature(after) != before_sig
                if norm_url(after_url, self.args.keep_query, self.args.id_collapse) != rec["norm_url"]:
                    state["result"] = "ページ遷移"
                    if self.url_in_scope(after_url) and not self.url_is_dangerous(after_url):
                        n = norm_url(after_url, self.args.keep_query, self.args.id_collapse)
                        if n not in seen:
                            seen.add(n)
                            self.queue.append((after_url, depth + 1, rec["id"]))
                elif state["modals"]:
                    state["result"] = "モーダル/ダイアログ表示"
                    self.enqueue_links(after.get("links", []), after_url, depth, rec["id"], seen, rec)
                elif state["changed"]:
                    state["result"] = "画面内変化（展開/タブ/メニュー等）"
                    self.enqueue_links(after.get("links", []), after_url, depth, rec["id"], seen, rec)
                else:
                    state["result"] = "変化なし"
            except Exception as e:
                state["result"] = f"エラー: {e!r}"[:200]
                self.log(f"  click error {label!r}: {e!r}")
            rec["states"].append(state)
            self.log(f"  {sid} {label!r} -> {state['result']}")

    def close_overlays(self, page) -> None:
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass
        for sel in self.rules.get("close_selectors", []):
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=1500, no_wait_after=True)
                    page.wait_for_timeout(300)
                    return
            except Exception:
                continue

    # -- 出力 -----------------------------------------------------------------
    def write_outputs(self, final: bool = False) -> None:
        data = {
            "meta": {
                "start_url": self.args.url, "origin": self.origin, "scope": self.scope, "generated_at": now_iso(),
                "headless": self.args.headless, "click_mode": self.args.click_mode, "allow_mutations": self.args.allow_mutations,
                "page_count": len(self.pages), "state_count": sum(len(p["states"]) for p in self.pages.values()),
                "blocked_request_count": len(self.blocked_requests), "skipped_element_count": len(self.skipped_elements),
                "skipped_url_count": len(self.skipped_urls), "error_count": len(self.errors), "complete": final,
                "args": vars(self.args),
            },
            "pages": [self.pages[k] for k in self.order],
        }
        (self.out / "pages.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.out / "safety_report.json").write_text(json.dumps({
            "blocked_requests": self.blocked_requests, "skipped_elements": self.skipped_elements,
            "skipped_urls": self.skipped_urls, "errors": self.errors,
        }, ensure_ascii=False, indent=2), encoding="utf-8")


def dom_signature(info: dict) -> str:
    key = json.dumps({"t": info.get("bodyText"), "h": info.get("headings"), "m": info.get("modals"), "c": len(info.get("clickables", []))}, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def file_hash(p: Path) -> str:
    try:
        return hashlib.md5(p.read_bytes()).hexdigest()
    except FileNotFoundError:
        return ""


def main() -> None:
    args = parse_args()
    if not (args.profile or args.cdp or args.storage_state):
        print("警告: --profile / --cdp / --storage-state のいずれも未指定。未ログイン状態で巡回します。", file=sys.stderr)
    if args.allow_mutations:
        print("!!! --allow-mutations が指定されています。データ変更リクエストが遮断されません。顧客環境では絶対に使用しないでください !!!", file=sys.stderr)
        time.sleep(3)
    c = Crawler(args)
    c.log(f"開始 url={args.url} out={c.out}")
    c.run()
    c.log(f"完了 pages={len(c.pages)} blocked={len(c.blocked_requests)} skipped_elements={len(c.skipped_elements)} errors={len(c.errors)}")
    print(f"\n出力: {c.out}/pages.json, {c.out}/screenshots/, {c.out}/safety_report.json")


if __name__ == "__main__":
    main()
