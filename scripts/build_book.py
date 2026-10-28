#!/usr/bin/env python3
"""
app-spec-crawler / build_book.py
--------------------------------
crawl.py の出力 (pages.json + screenshots/) と、AIが記入した descriptions.json を合成し、
4種類の文書からなる「画面仕様書」を生成する。標準ライブラリのみ使用・決定的（同じ入力→同じ出力）。

  book/
  ├── index.html                 目次ハブ（アプリ共通の仕様サマリ・階層ツリー・画面一覧・キャプチャ一覧）
  ├── overview.html              アプリ共通の仕様（アプリ全体の仕様項目・共通仕様・認証/権限・ナビゲーション）
  ├── sections/<path>.html       階層（ディレクトリ）仕様: その階層に含まれる画面群と共通仕様（深い階層はネスト）
  ├── pages/pXXX.html            画面仕様: 番号付き仕様項目（SPEC-pXXX-NN）＋説明
  ├── captures/pXXX.html         画面キャプチャ: 初期表示＋操作状態のスクリーンショット集（仕様項目の根拠）
  ├── screenshots/               画像
  └── assets/book.css

  python build_book.py --crawl ./out --init-descriptions   # 記入用テンプレート descriptions.json を生成（階層・画面を自動列挙）
  python build_book.py --crawl ./out --out ./out/book      # ブック生成
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"

# ---------------------------------------------------------------------------
# descriptions.json テンプレート
# ---------------------------------------------------------------------------
SPEC_ITEM = OrderedDict([
    ("id", ""),            # 省略時は自動採番 SPEC-pXXX-NN / SPEC-SEC-NN / SPEC-APP-NN
    ("type", ""),          # 表示 / 操作 / 入力 / 遷移 / 権限 / 業務ルール / 表示条件 / 非機能 など
    ("statement", ""),     # 仕様文（「〜する」「〜が表示される」）
    ("condition", ""),     # 成立条件（いつ・誰に）
    ("evidence", ""),      # 根拠: 初期表示なら "init"、操作状態なら "c02" のように状態ID。未検証なら空
    ("confidence", ""),    # 確認済 / 推定 / 要確認
    ("notes", ""),
])

PAGE_TEMPLATE = OrderedDict([
    ("name", ""), ("category", ""), ("summary", ""), ("purpose", ""),
    ("display_conditions", ""), ("users_and_usage", ""),
    ("specs", []),                 # ← この画面の仕様項目（SPEC_ITEM の配列）。画面仕様書の本体
    ("features", []), ("ui_elements", []), ("inputs", []), ("flows", []), ("transitions", []),
    ("states_and_variants", ""), ("business_rules", ""), ("open_questions", []),
    ("states", {}),                # クリック状態ごとの説明 {"c01": {"description","when_shown","notes"}}
])

SECTION_TEMPLATE = OrderedDict([
    ("name", ""),                  # 階層名（例: 顧客管理）
    ("summary", ""),               # この階層が何の画面群か
    ("purpose", ""),               # 業務上の役割
    ("contains", ""),              # 含まれる画面と役割分担の説明（一覧→詳細→サブ画面 など）
    ("common_specs", []),          # この階層の全画面に共通する仕様項目（SPEC_ITEM）
    ("navigation", ""),            # 階層内の遷移パターン
    ("access", ""),                # 権限・表示条件
    ("open_questions", []),
])

APP_TEMPLATE = OrderedDict([
    ("name", ""), ("overview", ""), ("target_users", ""), ("auth_and_roles", ""),
    ("global_navigation", ""), ("common_ui", ""),
    ("specs", []),                 # アプリ全体に関わる仕様項目（SPEC_ITEM）
    ("business_domain", ""),       # 業務ドメインの説明（扱うデータ・主要エンティティ）
    ("non_functional", ""),        # 非機能（レスポンシブ、言語、ブラウザ等で観察できたもの）
    ("open_questions", []), ("notes", ""),
])


def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def clone(o):
    return json.loads(json.dumps(o))


# ---------------------------------------------------------------------------
# 階層ツリー
# ---------------------------------------------------------------------------
def path_of(pg: dict) -> str:
    p = urlparse(pg["norm_url"]).path or "/"
    return p if p == "/" else p.rstrip("/")


def section_key(path: str) -> str:
    """セクションのファイル名キー。'/' → 'root', '/a/b' → 'a__b'"""
    if path == "/":
        return "root"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.strip("/").replace("/", "__"))


def build_tree(pages: list[dict]) -> dict[str, dict]:
    """全ページのパスから階層ノードを作る。ノード = 配下にページを持つディレクトリ。
    返り値: {path: {"path","parent","children":[path...],"pages":[pg...],"index_page":pg|None,"depth"}}"""
    nodes: dict[str, dict] = {}

    def ensure(path: str) -> dict:
        if path not in nodes:
            parent = None if path == "/" else ("/" + "/".join(path.strip("/").split("/")[:-1])).rstrip("/") or "/"
            nodes[path] = {"path": path, "parent": parent, "children": [], "pages": [], "index_page": None,
                           "depth": 0 if path == "/" else path.count("/")}
            if parent is not None and parent != path:
                ensure(parent)
                if path not in nodes[parent]["children"]:
                    nodes[parent]["children"].append(path)
        return nodes[path]

    ensure("/")
    paths = {path_of(pg) for pg in pages}
    # ディレクトリ = 自分以外のページのプレフィックスになっているパス
    for pg in pages:
        p = path_of(pg)
        is_dir = p == "/" or any(q != p and q.startswith(p + "/") for q in paths)
        if is_dir:
            node = ensure(p)
            node["index_page"] = node["index_page"] or pg
        else:
            parent = ("/" + "/".join(p.strip("/").split("/")[:-1])).rstrip("/") or "/"
            ensure(parent)["pages"].append(pg)
    for n in nodes.values():
        n["children"].sort()
        n["pages"].sort(key=lambda pg: path_of(pg))
    return nodes


def descendant_pages(nodes: dict, path: str) -> list[dict]:
    n = nodes[path]
    out = ([n["index_page"]] if n["index_page"] else []) + list(n["pages"])
    for c in n["children"]:
        out += descendant_pages(nodes, c)
    return out


# ---------------------------------------------------------------------------
# テンプレート生成
# ---------------------------------------------------------------------------
def init_descriptions(crawl: dict, out_path: Path, existing: dict | None) -> None:
    desc = existing or {}
    app = desc.setdefault("app", {})
    for k, v in APP_TEMPLATE.items():
        app.setdefault(k, clone(v))
    desc.setdefault("sections", {})
    desc.setdefault("pages", {})
    nodes = build_tree(crawl["pages"])
    for path, n in sorted(nodes.items()):
        sec = desc["sections"].setdefault(path, clone(SECTION_TEMPLATE))
        sec["_children"] = n["children"]
        sec["_pages"] = [f'{pg["id"]} {path_of(pg)}' for pg in ([n["index_page"]] if n["index_page"] else []) + n["pages"]]
    for pg in crawl["pages"]:
        entry = desc["pages"].setdefault(pg["id"], clone(PAGE_TEMPLATE))
        for k, v in PAGE_TEMPLATE.items():
            entry.setdefault(k, clone(v))
        for st in pg.get("states", []):
            entry["states"].setdefault(st["id"], {"description": "", "when_shown": "", "notes": "", "_label": st.get("label"), "_result": st.get("result")})
        entry["_url"] = pg["url"]
        entry["_title"] = pg.get("title")
        p = path_of(pg)
        entry["_section"] = p if p in nodes and nodes[p]["index_page"] is pg else (("/" + "/".join(p.strip("/").split("/")[:-1])).rstrip("/") or "/")
    desc["_spec_item_template"] = clone(SPEC_ITEM)
    out_path.write_text(json.dumps(desc, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# HTML 部品
# ---------------------------------------------------------------------------
def sidebar_html(ctx: dict, rel: str, current: tuple[str, str] | None) -> str:
    """全ページ共通の左の目次。階層ごとに直下の画面を並べ、今いるページを強調する"""
    cur_kind, cur_key = current or ("", "")

    def mark(kind: str, key: str) -> str:
        return ' aria-current="page"' if (cur_kind, cur_key) == (kind, key) else ""

    groups = []
    for path in ctx["section_order"]:
        node = ctx["nodes"][path]
        direct = ([node["index_page"]] if node["index_page"] else []) + node["pages"]
        if not direct:
            continue
        items = "".join(f'<li><a href="{rel}pages/{pg["id"]}.html"{mark("page", pg["id"])}>{esc(pg["_name"])}<small>{esc(pg["id"])}</small></a></li>' for pg in direct)
        groups.append(f'<div class="grp"><a class="gh" href="{rel}sections/{section_key(path)}.html"{mark("section", path)}>{esc(ctx["sec_name"](path))}</a><ul>{items}</ul></div>')
    head = (f'<div class="grp"><ul><li><a href="{rel}index.html"{mark("index", "")}>画面仕様書トップ</a></li>'
            f'<li><a href="{rel}overview.html"{mark("overview", "")}>アプリ共通の仕様</a></li></ul></div>')
    body = head + "".join(groups)
    return f'<aside class="side">{body}<details class="mob"><summary>目次（{len(ctx["pages"])} 画面）</summary>{body}</details></aside>'


BOOK_MENU = [("index", "トップ", "index.html"), ("overview", "アプリ共通の仕様", "overview.html"), ("section", "階層仕様", "sections/root.html"),
             ("page", "画面一覧", "index.html#pages"), ("safety", "安全性", "index.html#safety")]


def topbar(rel: str, brand: str, mode: str, has_guide: bool, cur_kind: str = "") -> str:
    """上の帯。1 段目は 2 つの読み物（システム概要書 / 画面仕様書）の切り替え、2 段目はブックの中のメニュー（ブックのときだけ）。
    guide.html（write が作る）もこれを使う"""
    cur = ' aria-current="page"'
    mode_nav = ""
    if has_guide:
        tabs = [("guide", "システム概要書", "はじめに読む（1 ページ）", "guide.html"), ("book", "画面仕様書", "画面ごとの仕様とスクリーンショット", "index.html")]
        mode_nav = '<nav class="mode" aria-label="読み物の切り替え">' + "".join(
            f'<a href="{rel}{h}"{cur if m == mode else ""}><b>{t}</b><small>{sub}</small></a>' for m, t, sub, h in tabs) + "</nav>"
    sub = ""
    if mode == "book":
        sub = '<nav class="sub" aria-label="画面仕様書の中"><span class="where">画面仕様書</span>' + "".join(
            f'<a href="{rel}{h}"{cur if k == cur_kind else ""}>{t}</a>' for k, t, h in BOOK_MENU) + "</nav>"
    home = "guide.html" if mode == "guide" else "index.html"
    return f'<header class="top"><div class="bar"><a class="brand" href="{rel}{home}">{esc(brand)}</a>{mode_nav}</div>{sub}</header>'


def guide_html(body: str, model: str, ctx: dict) -> str:
    """システム概要書（本文は write で Fable が書いた DIR/guide_body.html）。ブックと違い 1 カラムの読み物"""
    brand = ctx["desc"].get("app", {}).get("name") or ctx["meta"]["origin"]
    return f"""<!DOCTYPE html>
<html lang="ja" class="guide-doc"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light">
<title>{esc(brand)} システム概要書</title><link rel="stylesheet" href="assets/book.css"></head>
<body>{topbar("", brand, "guide", True)}
<main class="guide-main">{body}</main>
<footer>この仕様書は、ブラウザ巡回とスクリーンショットから作った画面ごとの仕様をもとに {esc(model)} が書いた。「推定」「要確認」と記した項目は、原本の設計書・開発者への確認が要る。根拠は「画面仕様書」の各画面の仕様とスクリーンショットにある。</footer>
</body></html>"""


def layout(title: str, body: str, rel: str, ctx: dict, crumbs: list[tuple[str, str]] | None = None,
           current: tuple[str, str] | None = None) -> str:
    crumb_html = ""
    if crumbs:
        crumb_html = '<nav class="crumbs">' + " / ".join(f'<a href="{esc(h)}">{esc(t)}</a>' if h else f"<span>{esc(t)}</span>" for t, h in crumbs) + "</nav>"
    brand = ctx["desc"].get("app", {}).get("name") or ctx["meta"]["origin"]
    return f"""<!DOCTYPE html>
<html lang="ja" class="book"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light">
<title>{esc(title)}</title><link rel="stylesheet" href="{rel}assets/book.css"></head>
<body>{topbar(rel, brand, "book", ctx.get("has_guide", False), (current or ("", ""))[0])}
<div class="shell">{sidebar_html(ctx, rel, current)}
<div><main>{crumb_html}{body}</main>
<footer>生成日時 {esc(ctx["generated"])} · app-spec-crawler · 本書はブラウザ巡回とスクリーンショットから推定した仕様であり、「推定」「要確認」と記した項目は原本の設計書・開発者への確認が必要です。</footer></div></div>
<script>(function(){{var a=document.querySelector('aside.side>.grp [aria-current="page"]');if(a)a.scrollIntoView({{block:"center"}});}})();</script>
</body></html>"""


def about_grid(items: list[tuple[str, str]]) -> str:
    """1〜2 行で終わる短い説明をまとめて 1 枚のカードに並べる"""
    cells = "".join(f'<div class="about-item"><h3>{esc(t)}</h3>{c}</div>' for t, c in items if (c or "").strip())
    return f'<div class="about">{cells}</div>' if cells else ""


def section(title: str, content: str, cls: str = "", anchor: str = "", count: str = "") -> str:
    if not (content or "").strip():
        return ""
    a = f' id="{esc(anchor)}"' if anchor else ""
    c = f' <span class="count">{esc(count)}</span>' if count else ""
    return f'<section class="{cls}"{a}><h2>{esc(title)}{c}</h2>{content}</section>'


def sections_with_toc(parts: list[tuple[str, str, str, str]]) -> str:
    """(anchor, 見出し, 中身, class) の並びから、空でない節と、その節へのページ内目次を作る"""
    kept = [(a, t, c, cls) for a, t, c, cls in parts if (c or "").strip()]
    toc = '<nav class="toc-inpage">' + "".join(f'<a href="#{esc(a)}">{esc(t)}</a>' for a, t, _, _ in kept) + "</nav>" if len(kept) > 2 else ""
    return toc + "".join(section(t, c, cls, a) for a, t, c, cls in kept)


def para(text) -> str:
    if not text:
        return ""
    return "".join(f"<p>{esc(t)}</p>" for t in str(text).split("\n") if t.strip())


def ul(items) -> str:
    items = [i for i in (items or []) if i]
    return "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>" if items else ""


def ol(items) -> str:
    items = [i for i in (items or []) if i]
    return "<ol>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ol>" if items else ""


def table(headers: list[str], rows: list, keys: list[str] | None = None, raw_cols: set[int] | None = None) -> str:
    if not rows:
        return ""
    h = "".join(f"<th>{esc(x)}</th>" for x in headers)
    body = ""
    for r in rows:
        cells = [r.get(k, "") for k in keys] if keys else r
        body += "<tr>" + "".join(f"<td>{c if raw_cols and i in raw_cols else esc(c)}</td>" for i, c in enumerate(cells)) + "</tr>"
    return f'<div class="tbl"><table class="grid"><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table></div>'


def todo(label: str = "要記入") -> str:
    return f'<p class="todo">（{esc(label)}）</p>'


def conf_tag(c: str) -> str:
    cls = {"確認済": "ok", "推定": "guess", "要確認": "ask"}.get((c or "").strip(), "")
    return f'<span class="conf {cls}">{esc(c or "-")}</span>'


def conf_chips(items: list[dict]) -> str:
    n = {"確認済": 0, "推定": 0, "要確認": 0}
    for it in items or []:
        c = (it.get("confidence") or "").strip()
        if c in n:
            n[c] += 1
    cls = {"確認済": "ok", "推定": "guess", "要確認": "ask"}
    return "".join(f'<span class="chip {cls[k]}">{k} <b>{v}</b></span>' for k, v in n.items() if v)


def spec_table(items: list[dict], prefix: str, cap_href: str | None) -> str:
    """仕様項目テーブル。id 未記入は自動採番。evidence は キャプチャページへのリンクにする"""
    if not items:
        return ""
    body = ""
    for i, it in enumerate(items, start=1):
        sid = it.get("id") or f"{prefix}-{i:02d}"
        ev = (it.get("evidence") or "").strip()
        ev_html = f'<a href="{esc(cap_href)}#{esc(ev)}">{esc(ev)}</a>' if ev and cap_href else esc(ev or "-")
        body += (f'<tr id="{esc(sid)}"><td class="id"><code>{esc(sid)}</code></td><td class="type">{esc(it.get("type"))}</td>'
                 f'<td class="stmt">{esc(it.get("statement"))}</td><td class="cond">{esc(it.get("condition"))}</td>'
                 f'<td class="ev">{ev_html}</td><td class="cf">{conf_tag(it.get("confidence"))}</td><td class="note">{esc(it.get("notes"))}</td></tr>')
    head = "".join(f"<th>{h}</th>" for h in ["ID", "種別", "仕様", "条件", "根拠", "確度", "備考"])
    return f'<div class="tbl"><table class="grid spec"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def parent_chain(pg: dict, by_id: dict) -> str:
    chain, cur, guard = [], pg, 0
    while cur and guard < 20:
        chain.append(cur.get("_name") or cur["id"])
        cur = by_id.get(cur.get("parent")) if cur.get("parent") else None
        guard += 1
    return " ← ".join(chain) if len(chain) > 1 else "起点ページ"


def url_meta(url: str) -> str:
    """トークン入りの長い URL は 1 行に縮め、押すと全文が出るようにする"""
    return f'<details class="url-full"><summary><code class="url" title="{esc(url)}">{esc(url)}</code></summary><code class="url">{esc(url)}</code></details>'


def prev_next(pg: dict, alt_href: str, alt_label: str, prefix: str = "") -> str:
    nav = '<nav class="pn">'
    if pg.get("_prev"):
        nav += f'<a class="prev" href="{prefix}{pg["_prev"]["id"]}.html"><small>← 前の画面</small>{esc(pg["_prev"]["_name"])}</a>'
    nav += f'<a class="alt" href="{esc(alt_href)}">{esc(alt_label)}</a>'
    if pg.get("_next"):
        nav += f'<a class="next" href="{prefix}{pg["_next"]["id"]}.html"><small>次の画面 →</small>{esc(pg["_next"]["_name"])}</a>'
    return nav + "</nav>"


def n_shots(pg: dict) -> int:
    return len([s for s in pg.get("states", []) if s.get("screenshot")]) + 1


# ---------------------------------------------------------------------------
# 画面仕様 pages/pXXX.html
# ---------------------------------------------------------------------------
def page_spec_html(pg: dict, d: dict, ctx: dict) -> str:
    name, pid = pg["_name"], pg["id"]
    sec_path = pg["_section"]
    rel = "../"
    crumbs = [("トップ", f"{rel}index.html")] + [(ctx["sec_name"](p), f"{rel}sections/{section_key(p)}.html") for p in ctx["ancestors"](sec_path)] + [(name, "")]
    specs = d.get("specs") or []

    lead = f'<p class="lead">{esc(d.get("summary"))}</p>' if d.get("summary") else todo("summary を記入")
    chips = (f'<div class="chips"><span class="chip">{esc(pg["_cat"])}</span><span class="chip">仕様 <b>{len(specs)}</b></span>'
             f'{conf_chips(specs)}<span class="chip">キャプチャ <b>{n_shots(pg)}</b></span></div>')
    meta = (f'<dl class="meta"><dt>パス</dt><dd><code>{esc(path_of(pg))}</code></dd>'
            f'<dt>所属階層</dt><dd><a href="{rel}sections/{section_key(sec_path)}.html">{esc(ctx["sec_name"](sec_path))}</a></dd>'
            f'<dt>到達経路</dt><dd>{esc(parent_chain(pg, ctx["by_id"]))}</dd><dt>URL</dt><dd>{url_meta(pg["url"])}</dd></dl>')
    b = [f'<div class="hero"><div><p class="kind">画面仕様 · {esc(pid)}</p><h1>{esc(name)}</h1>{lead}{chips}{meta}</div>'
         f'<a class="shotlink" href="{rel}captures/{pid}.html"><img src="{rel}{esc(pg["screenshot"])}" alt="{esc(name)}"><span>キャプチャ {n_shots(pg)} 枚を見る →</span></a></div>']

    sdesc = d.get("states") or {}
    srows = []
    for st in pg.get("states", []):
        if not st.get("screenshot"):
            continue
        sd = sdesc.get(st["id"], {})
        srows.append([f'<a href="{rel}captures/{pid}.html#{esc(st["id"])}">{esc(st["id"])}</a>', esc(st.get("label")), esc(st.get("result")), esc(sd.get("description") or "（要記入）"), esc(sd.get("when_shown"))])

    b.append(sections_with_toc([
        ("specs", "仕様項目", spec_table(specs, f"SPEC-{pid}", f"{rel}captures/{pid}.html") or todo("この画面の仕様項目を specs に記入"), "specs"),
        ("about", "この画面について", about_grid([("目的・位置づけ", para(d.get("purpose")) or todo()), ("表示条件", para(d.get("display_conditions")) or todo()),
                                                 ("利用者と使われ方", para(d.get("users_and_usage")) or todo())]), ""),
        ("features", "主要機能", ul(d.get("features")), ""),
        ("ui", "UI要素と挙動", table(["要素", "挙動", "備考"], d.get("ui_elements") or [], ["element", "behavior", "notes"]) or auto_ui_table(pg), ""),
        ("inputs", "入力項目", table(["項目", "種別", "必須", "バリデーション想定", "備考"], d.get("inputs") or [], ["field", "type", "required", "validation_assumption", "notes"]) or auto_inputs_table(pg), ""),
        ("flows", "利用フロー", ol(d.get("flows")), ""),
        ("transitions", "画面遷移", table(["トリガー", "遷移先", "備考"], d.get("transitions") or [], ["trigger", "to", "notes"]) or auto_transitions(pg, ctx["by_norm"]), ""),
        ("rules", "バリエーションと業務ルール", about_grid([("状態・バリエーション", para(d.get("states_and_variants"))), ("業務ルール・制約", para(d.get("business_rules")))]), ""),
        ("states", "操作で現れる状態", table(["状態", "操作", "結果", "説明", "表示条件"], srows, raw_cols={0, 1, 2, 3, 4}), ""),
        ("questions", "不明点・要確認", ul(d.get("open_questions")), "questions"),
    ]))
    b.append(f'<details class="raw"><summary>自動抽出データ（見出し・リンク・ボタン・テーブル・クリック判定）</summary>{auto_raw(pg)}</details>')
    b.append(prev_next(pg, f"{rel}captures/{pid}.html", "この画面のキャプチャ"))
    return layout(f"{name} | 画面仕様", "".join(b), rel, ctx, crumbs, ("page", pid))


# ---------------------------------------------------------------------------
# 画面キャプチャ captures/pXXX.html
# ---------------------------------------------------------------------------
def page_capture_html(pg: dict, d: dict, ctx: dict) -> str:
    name, pid, rel = pg["_name"], pg["id"], "../"
    crumbs = [("トップ", f"{rel}index.html"), (name, f"{rel}pages/{pid}.html"), ("キャプチャ", "")]
    sdesc = d.get("states") or {}
    states = [st for st in pg.get("states", []) if st.get("screenshot")]
    b = [f'<div class="hero" style="grid-template-columns:1fr"><div><p class="kind">画面キャプチャ · {esc(pid)}</p><h1>{esc(name)}</h1>'
         + (f'<p class="lead">{esc(d.get("summary"))}</p>' if d.get("summary") else "")
         + f'<dl class="meta"><dt>取得日時</dt><dd>{esc(pg.get("visited_at"))}</dd><dt>仕様書</dt><dd><a href="{rel}pages/{pid}.html">{esc(name)} の画面仕様</a></dd><dt>URL</dt><dd>{url_meta(pg["url"])}</dd></dl></div></div>']
    if states:
        b.append('<nav class="states"><a href="#init"><b>init</b>初期表示</a>'
                 + "".join(f'<a href="#{esc(st["id"])}"><b>{esc(st["id"])}</b>{esc(st.get("label"))}</a>' for st in states) + "</nav>")
    b.append(f'<article class="state" id="init"><h3>init 初期表示</h3><figure class="shot"><a href="{rel}{esc(pg["screenshot"])}" target="_blank"><img src="{rel}{esc(pg["screenshot"])}" alt="{esc(name)} 初期表示"></a></figure></article>')
    for st in states:
        sd = sdesc.get(st["id"], {})
        b.append(f'<article class="state" id="{esc(st["id"])}"><h3>{esc(st["id"])} 「{esc(st.get("label"))}」 <span class="tag">{esc(st.get("result"))}</span></h3>'
                 + (para(sd.get("description")) or todo("この状態の説明を記入"))
                 + (f'<p class="small"><b>表示条件:</b> {esc(sd.get("when_shown"))}</p>' if sd.get("when_shown") else "")
                 + para(sd.get("notes"))
                 + (f'<p class="small">遷移先: <code>{esc(st.get("url_after"))}</code></p>' if st.get("result") == "ページ遷移" else "")
                 + f'<figure class="shot"><a href="{rel}{esc(st["screenshot"])}" target="_blank"><img src="{rel}{esc(st["screenshot"])}" alt="" loading="lazy"></a></figure>'
                 + "</article>")
    skipped = [c for c in pg.get("clickables", []) if not c.get("clickable")]
    if skipped:
        b.append(f'<details class="raw"><summary>キャプチャしていない要素 {len(skipped)} 件（安全判定で押していない）</summary>'
                 + table(["要素", "種別", "理由"], [[c.get("text") or c.get("ariaLabel") or c.get("title") or "(ラベルなし)", c.get("role") or c.get("tag"), c.get("reason")] for c in skipped]) + "</details>")
    b.append(prev_next(pg, f"{rel}pages/{pid}.html", "この画面の仕様書"))
    return layout(f"{name} | キャプチャ", "".join(b), rel, ctx, crumbs, ("page", pid))


# ---------------------------------------------------------------------------
# 階層仕様 sections/<key>.html
# ---------------------------------------------------------------------------
def page_card(pg: dict, d: dict, rel: str) -> str:
    return (f'<a class="pcard" href="{rel}pages/{pg["id"]}.html"><img src="{rel}{esc(pg["screenshot"])}" alt="" loading="lazy">'
            f'<div><b>{esc(pg["_name"])}<small>{esc(pg["id"])}</small></b><span>{esc(d.get("summary") or "")}</span>'
            f'<em>仕様 {len(d.get("specs") or [])} · キャプチャ {n_shots(pg)}</em></div></a>')


def section_html(path: str, node: dict, s: dict, ctx: dict) -> str:
    rel = "../"
    name = ctx["sec_name"](path)
    crumbs = [("トップ", f"{rel}index.html")] + [(ctx["sec_name"](p), f"{rel}sections/{section_key(p)}.html") for p in ctx["ancestors"](path)[:-1]] + [(name, "")]
    desc_pages = descendant_pages(ctx["nodes"], path)
    direct = ([node["index_page"]] if node["index_page"] else []) + node["pages"]
    common = s.get("common_specs") or []
    b = [f'<div class="hero" style="grid-template-columns:1fr"><div><p class="kind">階層仕様 · 深さ {node["depth"]}</p><h1>{esc(name)} <small><code>{esc(path)}</code></small></h1>'
         + (f'<p class="lead">{esc(s.get("summary"))}</p>' if s.get("summary") else todo("summary を記入"))
         + f'<div class="chips"><span class="chip">直下の画面 <b>{len(direct)}</b></span><span class="chip">子階層 <b>{len(node["children"])}</b></span>'
         + f'<span class="chip">配下の画面 <b>{len(desc_pages)}</b></span><span class="chip">共通仕様 <b>{len(common)}</b></span></div></div></div>']
    crow = []
    for c in node["children"]:
        cs = ctx["desc"]["sections"].get(c, {})
        crow.append(f'<a class="card" href="{rel}sections/{section_key(c)}.html"><b>{esc(ctx["sec_name"](c))}</b><span>{esc(cs.get("summary") or "")}</span><em>{len(descendant_pages(ctx["nodes"], c))} 画面 · <code>{esc(c)}</code></em></a>')
    b.append(sections_with_toc([
        ("about", "この階層について", about_grid([("業務上の役割", para(s.get("purpose"))), ("含まれる画面と役割分担", para(s.get("contains")) or todo()),
                                                 ("階層内の遷移パターン", para(s.get("navigation"))), ("権限・表示条件", para(s.get("access")))]), ""),
        ("common", "階層共通の仕様項目", spec_table(common, f"SPEC-SEC-{section_key(path).upper()}", None), "specs"),
        ("pages", "この階層直下の画面", f'<div class="pgrid">{"".join(page_card(pg, ctx["desc"]["pages"].get(pg["id"], {}), rel) for pg in direct)}</div>' if direct else "", ""),
        ("children", "子階層", f'<div class="cards">{"".join(crow)}</div>' if crow else "", ""),
        ("questions", "不明点・要確認", ul(s.get("open_questions")), "questions"),
    ]))
    return layout(f"{name} | 階層仕様", "".join(b), rel, ctx, crumbs, ("section", path))


def tree_html(path: str, ctx: dict, rel: str, root: bool = False) -> str:
    node = ctx["nodes"][path]
    name = ctx["sec_name"](path)
    inner = ""
    for pg in ([node["index_page"]] if node["index_page"] else []) + node["pages"]:
        inner += f'<li class="pg"><a href="{rel}pages/{pg["id"]}.html">{esc(pg["_name"])}</a><small>{esc(pg["id"])}</small></li>'
    for c in node["children"]:
        inner += tree_html(c, ctx, rel)
    label = f'<a class="sec" href="{rel}sections/{section_key(path)}.html">{esc(name)}</a> <code>{esc(path)}</code>'
    if root:
        return f'<ul class="tree">{inner}</ul>' if inner else "<p>-</p>"
    return f'<li class="dir">{label}<ul class="tree">{inner}</ul></li>'


# ---------------------------------------------------------------------------
# アプリ共通の仕様 overview.html
# ---------------------------------------------------------------------------
def overview_html(ctx: dict) -> str:
    app = ctx["desc"].get("app", {})
    rel = ""
    specs = app.get("specs") or []
    b = [f'<div class="hero" style="grid-template-columns:1fr"><div><p class="kind">アプリ共通の仕様</p><h1>{esc(app.get("name") or ctx["meta"]["origin"])}</h1>'
         f'<div class="chips"><span class="chip">全体の仕様 <b>{len(specs)}</b></span>{conf_chips(specs)}</div></div></div>']
    b.append(sections_with_toc([
        ("overview", "アプリケーション概要", para(app.get("overview")) or todo(), ""),
        ("specs", "アプリ共通の仕様項目", spec_table(specs, "SPEC-APP", None) or todo("アプリ全体に関わる仕様を app.specs に記入"), "specs"),
        ("domain", "業務ドメイン・主要エンティティ", para(app.get("business_domain")), ""),
        ("users", "想定利用者", para(app.get("target_users")) or todo(), ""),
        ("auth", "認証・権限", para(app.get("auth_and_roles")) or todo(), ""),
        ("nav", "グローバルナビゲーション", para(app.get("global_navigation")) or todo(), ""),
        ("common", "共通UI・共通仕様", para(app.get("common_ui")) or todo(), ""),
        ("nonfunc", "非機能（観察できた範囲）", para(app.get("non_functional")), ""),
        ("tree", "画面階層の全体像", tree_html("/", ctx, rel, root=True), ""),
        ("questions", "不明点・要確認", ul(app.get("open_questions")) + para(app.get("notes")), "questions"),
    ]))
    return layout(f'{app.get("name") or ctx["meta"]["origin"]} アプリ共通の仕様', "".join(b), rel, ctx, [("トップ", "index.html"), ("アプリ共通の仕様", "")], ("overview", ""))


# ---------------------------------------------------------------------------
# index.html
# ---------------------------------------------------------------------------
def index_html(ctx: dict, safety: dict) -> str:
    app, meta, pages, desc = ctx["desc"].get("app", {}), ctx["meta"], ctx["pages"], ctx["desc"]
    all_specs = list(app.get("specs") or []) + [x for s in desc.get("sections", {}).values() for x in (s.get("common_specs") or [])] \
        + [x for pg in pages for x in (desc["pages"].get(pg["id"], {}).get("specs") or [])]
    first = (app.get("overview") or "").split("。")[0]
    b = [f'<p class="kind">画面仕様書</p><h1>{esc(app.get("name") or meta["origin"])}</h1>'
         + (f'<p class="lead">{esc(first)}。</p>' if first else "")
         + f'<div class="chips">{conf_chips(all_specs)}<span class="chip">巡回 {esc(meta.get("generated_at"))}</span></div>'
         + ('<a class="guide-cta" href="guide.html"><b>システム概要書を開く</b><span>初めての人向けに、できること・画面の地図・業務の流れ・決まりごとを 1 ページにまとめたもの</span></a>' if ctx.get("has_guide") else "")]
    b.append('<div class="stats">' + "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for k, v in [
        ("画面", len(pages)), ("階層", len(ctx["nodes"])), ("仕様項目", len(all_specs)), ("キャプチャ", sum(n_shots(pg) for pg in pages)),
        ("押していない要素", len(safety.get("skipped_elements", []))), ("遮断した変更系通信", len(safety.get("blocked_requests", [])))]) + "</div>")

    seccards = [f'<a class="card" href="overview.html"><b>アプリ共通の仕様</b><span>全画面に共通する仕様項目・認証/権限・共通UI・ナビゲーション</span><em>仕様 {len(app.get("specs") or [])}</em></a>']
    for path in ctx["section_order"]:
        n = len(descendant_pages(ctx["nodes"], path))
        if path == "/" or not n:
            continue
        s = desc["sections"].get(path, {})
        seccards.append(f'<a class="card" href="sections/{section_key(path)}.html"><b>{esc(ctx["sec_name"](path))}</b><span>{esc(s.get("summary") or "")}</span><em>{n} 画面 · <code>{esc(path)}</code></em></a>')
    b.append(section("階層", f'<div class="cards">{"".join(seccards)}</div>', anchor="tree"))

    cats: dict[str, list[dict]] = OrderedDict()
    for pg in pages:
        cats.setdefault(pg["_cat"], []).append(pg)
    toc = ""
    for cat, items in cats.items():
        toc += f'<h3 class="cat">{esc(cat)}<small>{len(items)} 画面</small></h3><div class="pgrid">'
        toc += "".join(page_card(pg, desc["pages"].get(pg["id"], {}), "") for pg in items) + "</div>"
    b.append(section("画面一覧（分類別）", toc, anchor="pages", count=f"{len(pages)} 画面"))

    caps = '<div class="gallery">' + "".join(
        f'<a class="gi" href="captures/{pg["id"]}.html"><img src="{esc(pg["screenshot"])}" alt="" loading="lazy"><span>{esc(pg["_name"])} <small>{esc(pg["id"])}</small></span></a>'
        for pg in pages) + "</div>"
    b.append(f'<details class="raw" id="captures"><summary>画面キャプチャ一覧（{len(pages)} 画面）</summary>{caps}</details>')

    rep = (f'<ul><li>遮断した変更系リクエスト: {len(safety.get("blocked_requests", []))} 件（GET以外は全て遮断。アプリのデータは変更されていない）</li>'
           f'<li>安全判定でクリックしなかった要素: {len(safety.get("skipped_elements", []))} 件（保存/削除/送信等、または用途不明）</li>'
           f'<li>遷移しなかった危険URL: {len(safety.get("skipped_urls", []))} 件</li><li>エラー: {len(safety.get("errors", []))} 件</li>'
           f'<li>巡回の方式: {esc(meta.get("method") or "crawl.py")}</li></ul>')
    if safety.get("skipped_urls"):
        uniq = OrderedDict()
        for s_ in safety["skipped_urls"]:
            key = (s_["href"].split("#")[0], s_["reason"])
            uniq.setdefault(key, []).append(s_["page"])
        rep += "<h4>遷移しなかったURL</h4>" + table(["URL", "理由", "出てきた画面"], [[k[0], k[1], f'{len(v)} 画面'] for k, v in uniq.items()])
    if safety.get("errors"):
        rep += "<h4>エラー</h4>" + table(["URL", "内容"], [[e["url"], e["error"]] for e in safety["errors"]])
    b.append(section("巡回範囲と安全性レポート", rep, anchor="safety"))
    return layout(f'{app.get("name") or meta["origin"]} 画面仕様書', "".join(b), "", ctx, None, ("index", ""))

# ---------------------------------------------------------------------------
# 自動抽出の補助
# ---------------------------------------------------------------------------
def auto_ui_table(pg: dict) -> str:
    rows = [[c.get("text") or c.get("ariaLabel") or c.get("title") or "(ラベルなし)", c.get("role") or c.get("tag"), "クリック検証済" if c.get("clickable") else f"未検証（{c.get('reason')}）"] for c in pg.get("clickables", [])]
    return table(["要素（自動抽出）", "種別", "検証"], rows)


def auto_inputs_table(pg: dict) -> str:
    rows = []
    for f in pg.get("forms", []):
        for fl in f.get("fields", []):
            rows.append([fl.get("label") or fl.get("name") or fl.get("id") or fl.get("placeholder") or "-", fl.get("type"), "必須" if fl.get("required") else "", "", f'form:{f.get("name") or f.get("index")} method={f.get("method")}' + (" / 選択肢: " + ", ".join(fl["options"]) if fl.get("options") else "")])
    for fl in pg.get("looseFields", []):
        rows.append([fl.get("label") or fl.get("name") or fl.get("id") or fl.get("placeholder") or "-", fl.get("type"), "", "", "フォーム外"])
    return table(["項目（自動抽出）", "種別", "必須", "バリデーション想定", "備考"], rows)


def auto_transitions(pg: dict, by_norm: dict) -> str:
    rows, seen = [], set()
    for ln in pg.get("links", []):
        if not ln.get("internal") or not ln.get("norm") or ln["norm"] in seen:
            continue
        seen.add(ln["norm"])
        t = by_norm.get(ln["norm"])
        rows.append([ln.get("text") or "(リンク)", (f'{t["_name"]} ({t["id"]})' if t else urlparse(ln["href"]).path), "リンク（自動抽出）"])
    for st in pg.get("states", []):
        if st.get("result") == "ページ遷移":
            rows.append([f'「{st.get("label")}」をクリック', urlparse(st.get("url_after", "")).path, "クリック検証済"])
    return table(["トリガー", "遷移先", "備考"], rows)


def auto_raw(pg: dict) -> str:
    out = "<h4>見出し</h4>" + (ul([f'{h["level"]}: {h["text"]}' for h in pg.get("headings", [])]) or "<p>-</p>")
    out += "<h4>テーブル</h4>" + (table(["キャプション", "ヘッダ", "行数"], [[t.get("caption"), " | ".join(t.get("headers", [])), t.get("rows")] for t in pg.get("tables", [])]) or "<p>-</p>")
    out += "<h4>内部リンク</h4>" + (table(["テキスト", "URL", "備考"], [[l.get("text"), l.get("href"), l.get("skipped", "")] for l in pg.get("links", []) if l.get("internal")]) or "<p>-</p>")
    ext = [l for l in pg.get("links", []) if not l.get("internal")]
    if ext:
        out += "<h4>外部リンク</h4>" + table(["テキスト", "URL"], [[l.get("text"), l.get("href")] for l in ext])
    out += "<h4>クリック要素の安全判定</h4>" + (table(["要素", "種別", "判定", "理由", "セレクタ"], [[c.get("text") or c.get("ariaLabel") or c.get("title"), c.get("role") or c.get("tag"), "クリック" if c.get("clickable") else "スキップ", c.get("reason"), c.get("selector")] for c in pg.get("clickables", [])]) or "<p>-</p>")
    out += "<h4>本文テキスト（先頭）</h4><pre>" + esc((pg.get("bodyText") or "")[:1500]) + "</pre>"
    return out


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crawl", required=True, help="crawl.py の出力ディレクトリ")
    ap.add_argument("--descriptions", default=None, help="descriptions.json（既定: <crawl>/descriptions.json）")
    ap.add_argument("--out", default=None, help="ブック出力先（既定: <crawl>/book）")
    ap.add_argument("--init-descriptions", action="store_true", help="記入用テンプレートを生成（既存があれば不足分を追記）")
    a = ap.parse_args()

    crawl_dir = Path(a.crawl).resolve()
    crawl = read_json(crawl_dir / "pages.json")
    desc_path = Path(a.descriptions) if a.descriptions else crawl_dir / "descriptions.json"
    existing = read_json(desc_path) if desc_path.exists() else None
    if a.init_descriptions:
        init_descriptions(crawl, desc_path, existing)
        print(f"テンプレートを書き出しました: {desc_path}  (画面 {len(crawl['pages'])} 件 / 階層 {len(build_tree(crawl['pages']))} 件)")
        return

    desc = existing or {"app": {}, "sections": {}, "pages": {}}
    desc.setdefault("app", {}); desc.setdefault("sections", {}); desc.setdefault("pages", {})
    out = Path(a.out).resolve() if a.out else crawl_dir / "book"
    for sub in ("pages", "captures", "sections", "assets", "screenshots"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy(ASSETS / "book.css", out / "assets" / "book.css")
    for png in (crawl_dir / "screenshots").glob("*.png"):
        shutil.copy(png, out / "screenshots" / png.name)
    safety = read_json(crawl_dir / "safety_report.json") if (crawl_dir / "safety_report.json").exists() else {}

    pages = crawl["pages"]
    nodes = build_tree(pages)
    by_id, by_norm = {}, {}
    for i, pg in enumerate(pages):
        d = desc["pages"].get(pg["id"], {})
        pg["_name"] = d.get("name") or pg.get("title") or path_of(pg)
        pg["_cat"] = d.get("category") or "未分類"
        p = path_of(pg)
        pg["_section"] = p if (p in nodes and nodes[p]["index_page"] is pg) else (("/" + "/".join(p.strip("/").split("/")[:-1])).rstrip("/") or "/")
        pg["_prev"] = pages[i - 1] if i > 0 else None
        pg["_next"] = pages[i + 1] if i + 1 < len(pages) else None
        by_id[pg["id"]] = pg
        by_norm[pg["norm_url"]] = pg

    def sec_name(path: str) -> str:
        s = desc["sections"].get(path, {})
        if s.get("name"):
            return s["name"]
        if path == "/":
            return "ルート"
        n = nodes.get(path)
        if n and n["index_page"]:
            return n["index_page"]["_name"]
        return path.strip("/").split("/")[-1]

    def ancestors(path: str) -> list[str]:
        out_, cur = [], path
        while cur is not None:
            out_.append(cur)
            cur = nodes[cur]["parent"] if cur in nodes else None
        return list(reversed(out_))

    def walk(path: str) -> list[str]:
        return [path] + [x for c in nodes[path]["children"] for x in walk(c)]

    ctx = {"desc": desc, "meta": crawl["meta"], "pages": pages, "nodes": nodes, "by_id": by_id, "by_norm": by_norm,
           "sec_name": sec_name, "ancestors": ancestors, "section_order": walk("/"), "has_guide": (crawl_dir / "guide_body.html").exists(),
           "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}

    for pg in pages:
        d = desc["pages"].get(pg["id"], {})
        (out / "pages" / f"{pg['id']}.html").write_text(page_spec_html(pg, d, ctx), encoding="utf-8")
        (out / "captures" / f"{pg['id']}.html").write_text(page_capture_html(pg, d, ctx), encoding="utf-8")
    for path, node in nodes.items():
        (out / "sections" / f"{section_key(path)}.html").write_text(section_html(path, node, desc["sections"].get(path, {}), ctx), encoding="utf-8")
    (out / "overview.html").write_text(overview_html(ctx), encoding="utf-8")
    (out / "index.html").write_text(index_html(ctx, safety), encoding="utf-8")
    if ctx["has_guide"]:
        raw = (crawl_dir / "guide_body.html").read_text(encoding="utf-8")
        m = re.match(r"<!-- model: (\S+) -->", raw)
        (out / "guide.html").write_text(guide_html(raw, m.group(1) if m else "Claude", ctx), encoding="utf-8")

    pf = sum(1 for pg in pages if desc["pages"].get(pg["id"], {}).get("specs"))
    sf = sum(1 for p in nodes if desc["sections"].get(p, {}).get("summary"))
    print(f"画面仕様書を生成しました: {out}/index.html")
    print(f"  画面 {len(pages)} 件（仕様項目記入済 {pf} 件） / 階層 {len(nodes)} 件（記入済 {sf} 件） / アプリ共通の仕様項目 {len(desc['app'].get('specs') or [])} 件")
    nc = sum(1 for p in nodes if p != "/" and len(descendant_pages(nodes, p)) > 1 and not desc["sections"].get(p, {}).get("common_specs"))
    if nc:
        print(f"  画面が 2 つ以上ある階層のうち {nc} 件は共通仕様（common_specs）が空です。共通する仕様があれば持ち上げてください。")
    if pf < len(pages) or sf < len(nodes):
        print("※ 未記入があります。descriptions.json を記入して再実行してください。")


if __name__ == "__main__":
    main()
