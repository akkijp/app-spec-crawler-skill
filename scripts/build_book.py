#!/usr/bin/env python3
"""
app-spec-crawler / build_book.py
--------------------------------
Combines the crawler output (pages.json + screenshots/) with the AI-written descriptions.json and builds a
"screen spec" book made of four kinds of documents. Standard library only, and deterministic (same input -> same output).

  book/
  ├── index.html                 Hub: app-wide summary, section tree, screen list, capture list
  ├── overview.html              App-wide spec: app-level spec items, shared specs, auth / permissions, navigation
  ├── sections/<path>.html       Section (directory) spec: the screens in that section and what they share (nested for deep paths)
  ├── pages/pXXX.html            Screen spec: numbered spec items (SPEC-pXXX-NN) plus descriptions
  ├── captures/pXXX.html         Screen captures: the initial view and each interaction state (evidence for the spec items)
  ├── screenshots/               Images
  └── assets/book.css

  python build_book.py --crawl ./out --init-descriptions   # write the descriptions.json template (lists sections and screens)
  python build_book.py --crawl ./out --out ./out/book      # build the book
  python build_book.py --crawl ./out --lang es             # language of the book: en / ja / zh / es / ko

UI strings are English in this file and go through i18n.t(); translations live in scripts/locales/<lang>.json.
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

import sys
sys.path.insert(0, str(HERE))
import i18n  # noqa: E402
from i18n import t  # noqa: E402

LANG = i18n.DEFAULT  # set in main()


def tr(text: str, **kw) -> str:
    """UI string in the language of the book. `text` is the English source."""
    return t(LANG, text, **kw)


def ld(s):
    """Fixed crawler phrase (state label / result, reason, method) in the language of the book."""
    return i18n.localize_data(LANG, s)


def is_navigation(st: dict) -> bool:
    """True when a state's result is a page navigation (canonical English or legacy Japanese value)."""
    return i18n.localize_data("en", st.get("result")) == "Page navigation"


def screens(n: int) -> str:
    return tr("1 screen") if n == 1 else tr("{n} screens", n=n)


def emit(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# descriptions.json template
# ---------------------------------------------------------------------------
SPEC_ITEM = OrderedDict([
    ("id", ""),            # auto-numbered when empty: SPEC-pXXX-NN / SPEC-SEC-NN / SPEC-APP-NN
    ("type", ""),          # display / action / input / navigation / permission / business rule / visibility / non-functional ...
    ("statement", ""),     # the spec statement ("... is shown", "... does ...")
    ("condition", ""),     # when it holds (when, for whom)
    ("evidence", ""),      # "init" for the initial view, a state id such as "c02" for an interaction state; empty if not verified
    ("confidence", ""),    # verified / inferred / to_confirm (the localized labels are accepted too)
    ("notes", ""),
])

PAGE_TEMPLATE = OrderedDict([
    ("name", ""), ("category", ""), ("summary", ""), ("purpose", ""),
    ("display_conditions", ""), ("users_and_usage", ""),
    ("specs", []),                 # spec items of this screen (list of SPEC_ITEM): the core of the screen spec
    ("features", []), ("ui_elements", []), ("inputs", []), ("flows", []), ("transitions", []),
    ("states_and_variants", ""), ("business_rules", ""), ("open_questions", []),
    ("states", {}),                # description per interaction state {"c01": {"description","when_shown","notes"}}
])

SECTION_TEMPLATE = OrderedDict([
    ("name", ""),                  # section name (e.g. Customers)
    ("summary", ""),               # what this group of screens is
    ("purpose", ""),               # its role in the business
    ("contains", ""),              # the screens it contains and how they divide the work (list -> detail -> sub-screens ...)
    ("common_specs", []),          # spec items shared by every screen in this section (SPEC_ITEM)
    ("navigation", ""),            # navigation patterns within the section
    ("access", ""),                # permissions and visibility
    ("open_questions", []),
])

APP_TEMPLATE = OrderedDict([
    ("name", ""), ("overview", ""), ("target_users", ""), ("auth_and_roles", ""),
    ("global_navigation", ""), ("common_ui", ""),
    ("specs", []),                 # app-wide spec items (SPEC_ITEM)
    ("business_domain", ""),       # business domain (the data handled, main entities)
    ("non_functional", ""),        # non-functional aspects that could be observed (responsive layout, languages, browsers ...)
    ("open_questions", []), ("notes", ""),
])


def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def clone(o):
    return json.loads(json.dumps(o))


# ---------------------------------------------------------------------------
# Section tree
# ---------------------------------------------------------------------------
def path_of(pg: dict) -> str:
    p = urlparse(pg["norm_url"]).path or "/"
    return p if p == "/" else p.rstrip("/")


def section_key(path: str) -> str:
    """File-name key of a section. '/' -> 'root', '/a/b' -> 'a__b'"""
    if path == "/":
        return "root"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.strip("/").replace("/", "__"))


def build_tree(pages: list[dict]) -> dict[str, dict]:
    """Build section nodes from the paths of all pages. A node is a directory that has pages under it.
    Returns: {path: {"path","parent","children":[path...],"pages":[pg...],"index_page":pg|None,"depth"}}"""
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
    # a directory = a path that is a prefix of some other page
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
# Template generation
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
# HTML parts
# ---------------------------------------------------------------------------
def sidebar_html(ctx: dict, rel: str, current: tuple[str, str] | None) -> str:
    """The left-hand contents shared by every page: screens grouped by section, with the current page highlighted"""
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
    head = (f'<div class="grp"><ul><li><a href="{rel}index.html"{mark("index", "")}>{tr("Screen spec home")}</a></li>'
            f'<li><a href="{rel}overview.html"{mark("overview", "")}>{tr("App-wide spec")}</a></li></ul></div>')
    body = head + "".join(groups)
    return f'<aside class="side">{body}<details class="mob"><summary>{tr("Contents ({n} screens)", n=len(ctx["pages"]))}</summary>{body}</details></aside>'


# English source strings; translated in topbar()
BOOK_MENU = [("index", "Home", "index.html"), ("overview", "App-wide spec", "overview.html"), ("section", "Section spec", "sections/root.html"),
             ("page", "Screen list", "index.html#pages"), ("safety", "Safety", "index.html#safety")]


def topbar(rel: str, brand: str, mode: str, has_guide: bool, cur_kind: str = "") -> str:
    """The top bar. Row 1 switches between the two documents (system guide / screen spec); row 2 is the menu
    inside the book (book only). guide.html (made by `write`) uses this too"""
    cur = ' aria-current="page"'
    mode_nav = ""
    if has_guide:
        tabs = [("guide", tr("System guide"), tr("Start here (one page)"), "guide.html"),
                ("book", tr("Screen spec"), tr("Every screen, with specs and screenshots"), "index.html")]
        mode_nav = f'<nav class="mode" aria-label="{tr("Switch document")}">' + "".join(
            f'<a href="{rel}{h}"{cur if m == mode else ""}><b>{title}</b><small>{note}</small></a>' for m, title, note, h in tabs) + "</nav>"
    sub = ""
    if mode == "book":
        sub = f'<nav class="sub" aria-label="{tr("Inside the screen spec")}"><span class="where">{tr("Screen spec")}</span>' + "".join(
            f'<a href="{rel}{h}"{cur if k == cur_kind else ""}>{tr(label)}</a>' for k, label, h in BOOK_MENU) + "</nav>"
    home = "guide.html" if mode == "guide" else "index.html"
    return f'<header class="top"><div class="bar"><a class="brand" href="{rel}{home}">{esc(brand)}</a>{mode_nav}</div>{sub}</header>'


def guide_html(body: str, model: str, ctx: dict) -> str:
    """The system guide (the body is DIR/guide_body.html, written by `write`). Unlike the book it is a one-column read"""
    brand = ctx["desc"].get("app", {}).get("name") or ctx["meta"]["origin"]
    return f"""<!DOCTYPE html>
<html lang="{i18n.html_lang(LANG)}" class="guide-doc"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light">
<title>{esc(tr("{name} — System guide", name=brand))}</title><link rel="stylesheet" href="assets/book.css"></head>
<body>{topbar("", brand, "guide", True)}
<main class="guide-main">{body}</main>
<footer>{tr("{model} wrote this guide from per-screen specs that were built from a read-only browser crawl and screenshots. Items marked “Inferred” or “To confirm” need checking against the original design documents or the developers. The evidence is in the screen spec: each screen's spec items and screenshots.", model=esc(model))}</footer>
</body></html>"""


def layout(title: str, body: str, rel: str, ctx: dict, crumbs: list[tuple[str, str]] | None = None,
           current: tuple[str, str] | None = None) -> str:
    crumb_html = ""
    if crumbs:
        crumb_html = '<nav class="crumbs">' + " / ".join(f'<a href="{esc(h)}">{esc(t)}</a>' if h else f"<span>{esc(t)}</span>" for t, h in crumbs) + "</nav>"
    brand = ctx["desc"].get("app", {}).get("name") or ctx["meta"]["origin"]
    return f"""<!DOCTYPE html>
<html lang="{i18n.html_lang(LANG)}" class="book"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light">
<title>{esc(title)}</title><link rel="stylesheet" href="{rel}assets/book.css"></head>
<body>{topbar(rel, brand, "book", ctx.get("has_guide", False), (current or ("", ""))[0])}
<div class="shell">{sidebar_html(ctx, rel, current)}
<div><main>{crumb_html}{body}</main>
<footer>{tr("Generated {ts}", ts=esc(ctx["generated"]))} · app-spec-crawler · {tr("This spec was inferred from a read-only browser crawl and screenshots. Items marked “Inferred” or “To confirm” need checking against the original design documents or the developers.")}</footer></div></div>
<script>(function(){{var a=document.querySelector('aside.side>.grp [aria-current="page"]');if(a)a.scrollIntoView({{block:"center"}});}})();</script>
</body></html>"""


def about_grid(items: list[tuple[str, str]]) -> str:
    """Put short one- or two-line descriptions side by side on one card"""
    cells = "".join(f'<div class="about-item"><h3>{esc(t)}</h3>{c}</div>' for t, c in items if (c or "").strip())
    return f'<div class="about">{cells}</div>' if cells else ""


def section(title: str, content: str, cls: str = "", anchor: str = "", count: str = "") -> str:
    if not (content or "").strip():
        return ""
    a = f' id="{esc(anchor)}"' if anchor else ""
    c = f' <span class="count">{esc(count)}</span>' if count else ""
    return f'<section class="{cls}"{a}><h2>{esc(title)}{c}</h2>{content}</section>'


def sections_with_toc(parts: list[tuple[str, str, str, str]]) -> str:
    """From a list of (anchor, heading, content, class), build the non-empty sections and an in-page table of contents for them"""
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


def todo(label: str = "(to fill in)") -> str:
    """A "to fill in" placeholder. `label` is an English source string. Always class="todo" (other tools count it)."""
    return f'<p class="todo">{esc(tr(label))}</p>'


def todo_inline(label: str = "(to fill in)") -> str:
    return f'<span class="todo">{esc(tr(label))}</span>'


CONF_CLASS = {"verified": "ok", "inferred": "guess", "to_confirm": "ask"}


def conf_tag(c: str) -> str:
    key = i18n.normalize_confidence(c)
    return f'<span class="conf {CONF_CLASS.get(key, "")}">{esc(i18n.confidence_label(LANG, key) if key else (c or "-"))}</span>'


def conf_chips(items: list[dict]) -> str:
    n = {k: 0 for k in i18n.CONFIDENCE}
    for it in items or []:
        key = i18n.normalize_confidence(it.get("confidence"))
        if key:
            n[key] += 1
    return "".join(f'<span class="chip {CONF_CLASS[k]}">{esc(i18n.confidence_label(LANG, k))} <b>{v}</b></span>' for k, v in n.items() if v)


def spec_table(items: list[dict], prefix: str, cap_href: str | None) -> str:
    """Spec item table. Empty ids are auto-numbered. evidence becomes a link to the capture page"""
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
    head = "".join(f"<th>{h}</th>" for h in ["ID", tr("Type"), tr("Spec"), tr("Condition"), tr("Evidence"), tr("Confidence"), tr("Notes")])
    return f'<div class="tbl"><table class="grid spec"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def parent_chain(pg: dict, by_id: dict) -> str:
    chain, cur, guard = [], pg, 0
    while cur and guard < 20:
        chain.append(cur.get("_name") or cur["id"])
        cur = by_id.get(cur.get("parent")) if cur.get("parent") else None
        guard += 1
    return " ← ".join(chain) if len(chain) > 1 else tr("Start page")


def url_meta(url: str) -> str:
    """Shorten a long URL (e.g. one carrying a token) to one line; clicking it shows the full text"""
    return f'<details class="url-full"><summary><code class="url" title="{esc(url)}">{esc(url)}</code></summary><code class="url">{esc(url)}</code></details>'


def prev_next(pg: dict, alt_href: str, alt_label: str, prefix: str = "") -> str:
    nav = '<nav class="pn">'
    if pg.get("_prev"):
        nav += f'<a class="prev" href="{prefix}{pg["_prev"]["id"]}.html"><small>{tr("← Previous")}</small>{esc(pg["_prev"]["_name"])}</a>'
    nav += f'<a class="alt" href="{esc(alt_href)}">{esc(alt_label)}</a>'
    if pg.get("_next"):
        nav += f'<a class="next" href="{prefix}{pg["_next"]["id"]}.html"><small>{tr("Next →")}</small>{esc(pg["_next"]["_name"])}</a>'
    return nav + "</nav>"


def n_shots(pg: dict) -> int:
    return len([s for s in pg.get("states", []) if s.get("screenshot")]) + 1


# ---------------------------------------------------------------------------
# Screen spec pages/pXXX.html
# ---------------------------------------------------------------------------
def page_spec_html(pg: dict, d: dict, ctx: dict) -> str:
    name, pid = pg["_name"], pg["id"]
    sec_path = pg["_section"]
    rel = "../"
    crumbs = [(tr("Home"), f"{rel}index.html")] + [(ctx["sec_name"](p), f"{rel}sections/{section_key(p)}.html") for p in ctx["ancestors"](sec_path)] + [(name, "")]
    specs = d.get("specs") or []

    lead = f'<p class="lead">{esc(d.get("summary"))}</p>' if d.get("summary") else todo("(fill in summary)")
    chips = (f'<div class="chips"><span class="chip">{esc(pg["_cat"])}</span><span class="chip">{tr("Specs")} <b>{len(specs)}</b></span>'
             f'{conf_chips(specs)}<span class="chip">{tr("Captures")} <b>{n_shots(pg)}</b></span></div>')
    meta = (f'<dl class="meta"><dt>{tr("Path")}</dt><dd><code>{esc(path_of(pg))}</code></dd>'
            f'<dt>{tr("Section")}</dt><dd><a href="{rel}sections/{section_key(sec_path)}.html">{esc(ctx["sec_name"](sec_path))}</a></dd>'
            f'<dt>{tr("Reached via")}</dt><dd>{esc(parent_chain(pg, ctx["by_id"]))}</dd><dt>URL</dt><dd>{url_meta(pg["url"])}</dd></dl>')
    b = [f'<div class="hero"><div><p class="kind">{tr("Screen spec · {pid}", pid=esc(pid))}</p><h1>{esc(name)}</h1>{lead}{chips}{meta}</div>'
         f'<a class="shotlink" href="{rel}captures/{pid}.html"><img src="{rel}{esc(pg["screenshot"])}" alt="{esc(name)}"><span>{tr("View 1 capture →") if n_shots(pg) == 1 else tr("View {n} captures →", n=n_shots(pg))}</span></a></div>']

    sdesc = d.get("states") or {}
    srows = []
    for st in pg.get("states", []):
        if not st.get("screenshot"):
            continue
        sd = sdesc.get(st["id"], {})
        srows.append([f'<a href="{rel}captures/{pid}.html#{esc(st["id"])}">{esc(st["id"])}</a>', esc(ld(st.get("label"))), esc(ld(st.get("result"))),
                      esc(sd.get("description")) if sd.get("description") else todo_inline(), esc(sd.get("when_shown"))])

    b.append(sections_with_toc([
        ("specs", tr("Spec items"), spec_table(specs, f"SPEC-{pid}", f"{rel}captures/{pid}.html") or todo("(fill in this screen's spec items under specs)"), "specs"),
        ("about", tr("About this screen"), about_grid([(tr("Purpose"), para(d.get("purpose")) or todo()), (tr("Shown when"), para(d.get("display_conditions")) or todo()),
                                                       (tr("Who uses it and how"), para(d.get("users_and_usage")) or todo())]), ""),
        ("features", tr("Main features"), ul(d.get("features")), ""),
        ("ui", tr("UI elements and behavior"), table([tr("Element"), tr("Behavior"), tr("Notes")], d.get("ui_elements") or [], ["element", "behavior", "notes"]) or auto_ui_table(pg), ""),
        ("inputs", tr("Input fields"), table([tr("Field"), tr("Type"), tr("Required"), tr("Assumed validation"), tr("Notes")], d.get("inputs") or [], ["field", "type", "required", "validation_assumption", "notes"]) or auto_inputs_table(pg), ""),
        ("flows", tr("Usage flow"), ol(d.get("flows")), ""),
        ("transitions", tr("Navigation"), table([tr("Trigger"), tr("Goes to"), tr("Notes")], d.get("transitions") or [], ["trigger", "to", "notes"]) or auto_transitions(pg, ctx["by_norm"]), ""),
        ("rules", tr("Variants and business rules"), about_grid([(tr("States and variants"), para(d.get("states_and_variants"))), (tr("Business rules and constraints"), para(d.get("business_rules")))]), ""),
        ("states", tr("States reached by interaction"), table([tr("State"), tr("Action"), tr("Result"), tr("Description"), tr("Shown when")], srows, raw_cols={0, 1, 2, 3, 4}), ""),
        ("questions", tr("Open questions"), ul(d.get("open_questions")), "questions"),
    ]))
    b.append(f'<details class="raw"><summary>{tr("Auto-extracted data (headings, links, buttons, tables, click decisions)")}</summary>{auto_raw(pg)}</details>')
    b.append(prev_next(pg, f"{rel}captures/{pid}.html", tr("Captures of this screen")))
    return layout(tr("{name} | Screen spec", name=name), "".join(b), rel, ctx, crumbs, ("page", pid))


# ---------------------------------------------------------------------------
# Screen captures captures/pXXX.html
# ---------------------------------------------------------------------------
def page_capture_html(pg: dict, d: dict, ctx: dict) -> str:
    name, pid, rel = pg["_name"], pg["id"], "../"
    crumbs = [(tr("Home"), f"{rel}index.html"), (name, f"{rel}pages/{pid}.html"), (tr("Captures"), "")]
    sdesc = d.get("states") or {}
    states = [st for st in pg.get("states", []) if st.get("screenshot")]
    b = [f'<div class="hero" style="grid-template-columns:1fr"><div><p class="kind">{tr("Screen captures · {pid}", pid=esc(pid))}</p><h1>{esc(name)}</h1>'
         + (f'<p class="lead">{esc(d.get("summary"))}</p>' if d.get("summary") else "")
         + f'<dl class="meta"><dt>{tr("Captured at")}</dt><dd>{esc(pg.get("visited_at"))}</dd><dt>{tr("Spec page")}</dt><dd><a href="{rel}pages/{pid}.html">{tr("{name} — screen spec", name=esc(name))}</a></dd><dt>URL</dt><dd>{url_meta(pg["url"])}</dd></dl></div></div>']
    if states:
        b.append(f'<nav class="states"><a href="#init"><b>init</b>{tr("Initial view")}</a>'
                 + "".join(f'<a href="#{esc(st["id"])}"><b>{esc(st["id"])}</b>{esc(ld(st.get("label")))}</a>' for st in states) + "</nav>")
    b.append(f'<article class="state" id="init"><h3>init {tr("Initial view")}</h3><figure class="shot"><a href="{rel}{esc(pg["screenshot"])}" target="_blank"><img src="{rel}{esc(pg["screenshot"])}" alt="{esc(name)} {tr("Initial view")}"></a></figure></article>')
    for st in states:
        sd = sdesc.get(st["id"], {})
        b.append(f'<article class="state" id="{esc(st["id"])}"><h3>{esc(st["id"])} {tr("“{label}”", label=esc(ld(st.get("label"))))} <span class="tag">{esc(ld(st.get("result")))}</span></h3>'
                 + (para(sd.get("description")) or todo("(describe this state)"))
                 + (f'<p class="small"><b>{tr("Shown when:")}</b> {esc(sd.get("when_shown"))}</p>' if sd.get("when_shown") else "")
                 + para(sd.get("notes"))
                 + (f'<p class="small">{tr("Goes to:")} <code>{esc(st.get("url_after"))}</code></p>' if is_navigation(st) else "")
                 + f'<figure class="shot"><a href="{rel}{esc(st["screenshot"])}" target="_blank"><img src="{rel}{esc(st["screenshot"])}" alt="" loading="lazy"></a></figure>'
                 + "</article>")
    skipped = [c for c in pg.get("clickables", []) if not c.get("clickable")]
    if skipped:
        b.append(f'<details class="raw"><summary>{tr("Elements not captured: {n} (not clicked under the safety rules)", n=len(skipped))}</summary>'
                 + table([tr("Element"), tr("Type"), tr("Reason")], [[c.get("text") or c.get("ariaLabel") or c.get("title") or tr("(no label)"), c.get("role") or c.get("tag"), ld(c.get("reason"))] for c in skipped]) + "</details>")
    b.append(prev_next(pg, f"{rel}pages/{pid}.html", tr("Spec of this screen")))
    return layout(tr("{name} | Captures", name=name), "".join(b), rel, ctx, crumbs, ("page", pid))


# ---------------------------------------------------------------------------
# Section spec sections/<key>.html
# ---------------------------------------------------------------------------
def page_card(pg: dict, d: dict, rel: str) -> str:
    return (f'<a class="pcard" href="{rel}pages/{pg["id"]}.html"><img src="{rel}{esc(pg["screenshot"])}" alt="" loading="lazy">'
            f'<div><b>{esc(pg["_name"])}<small>{esc(pg["id"])}</small></b><span>{esc(d.get("summary") or "")}</span>'
            f'<em>{tr("Specs")} {len(d.get("specs") or [])} · {tr("Captures")} {n_shots(pg)}</em></div></a>')


def section_html(path: str, node: dict, s: dict, ctx: dict) -> str:
    rel = "../"
    name = ctx["sec_name"](path)
    crumbs = [(tr("Home"), f"{rel}index.html")] + [(ctx["sec_name"](p), f"{rel}sections/{section_key(p)}.html") for p in ctx["ancestors"](path)[:-1]] + [(name, "")]
    desc_pages = descendant_pages(ctx["nodes"], path)
    direct = ([node["index_page"]] if node["index_page"] else []) + node["pages"]
    common = s.get("common_specs") or []
    b = [f'<div class="hero" style="grid-template-columns:1fr"><div><p class="kind">{tr("Section spec · depth {n}", n=node["depth"])}</p><h1>{esc(name)} <small><code>{esc(path)}</code></small></h1>'
         + (f'<p class="lead">{esc(s.get("summary"))}</p>' if s.get("summary") else todo("(fill in summary)"))
         + f'<div class="chips"><span class="chip">{tr("Screens here")} <b>{len(direct)}</b></span><span class="chip">{tr("Subsections")} <b>{len(node["children"])}</b></span>'
         + f'<span class="chip">{tr("Screens below")} <b>{len(desc_pages)}</b></span><span class="chip">{tr("Shared specs")} <b>{len(common)}</b></span></div></div></div>']
    crow = []
    for c in node["children"]:
        cs = ctx["desc"]["sections"].get(c, {})
        crow.append(f'<a class="card" href="{rel}sections/{section_key(c)}.html"><b>{esc(ctx["sec_name"](c))}</b><span>{esc(cs.get("summary") or "")}</span><em>{screens(len(descendant_pages(ctx["nodes"], c)))} · <code>{esc(c)}</code></em></a>')
    b.append(sections_with_toc([
        ("about", tr("About this section"), about_grid([(tr("Role in the business"), para(s.get("purpose"))), (tr("Screens included and how they divide the work"), para(s.get("contains")) or todo()),
                                                        (tr("Navigation within the section"), para(s.get("navigation"))), (tr("Permissions and visibility"), para(s.get("access")))]), ""),
        ("common", tr("Spec items shared across this section"), spec_table(common, f"SPEC-SEC-{section_key(path).upper()}", None), "specs"),
        ("pages", tr("Screens directly in this section"), f'<div class="pgrid">{"".join(page_card(pg, ctx["desc"]["pages"].get(pg["id"], {}), rel) for pg in direct)}</div>' if direct else "", ""),
        ("children", tr("Subsections"), f'<div class="cards">{"".join(crow)}</div>' if crow else "", ""),
        ("questions", tr("Open questions"), ul(s.get("open_questions")), "questions"),
    ]))
    return layout(tr("{name} | Section spec", name=name), "".join(b), rel, ctx, crumbs, ("section", path))


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
# App-wide spec overview.html
# ---------------------------------------------------------------------------
def overview_html(ctx: dict) -> str:
    app = ctx["desc"].get("app", {})
    rel = ""
    specs = app.get("specs") or []
    b = [f'<div class="hero" style="grid-template-columns:1fr"><div><p class="kind">{tr("App-wide spec")}</p><h1>{esc(app.get("name") or ctx["meta"]["origin"])}</h1>'
         f'<div class="chips"><span class="chip">{tr("App-wide specs")} <b>{len(specs)}</b></span>{conf_chips(specs)}</div></div></div>']
    b.append(sections_with_toc([
        ("overview", tr("Application overview"), para(app.get("overview")) or todo(), ""),
        ("specs", tr("App-wide spec items"), spec_table(specs, "SPEC-APP", None) or todo("(fill in app-wide spec items under app.specs)"), "specs"),
        ("domain", tr("Business domain and main entities"), para(app.get("business_domain")), ""),
        ("users", tr("Intended users"), para(app.get("target_users")) or todo(), ""),
        ("auth", tr("Authentication and permissions"), para(app.get("auth_and_roles")) or todo(), ""),
        ("nav", tr("Global navigation"), para(app.get("global_navigation")) or todo(), ""),
        ("common", tr("Shared UI and shared specs"), para(app.get("common_ui")) or todo(), ""),
        ("nonfunc", tr("Non-functional (as observed)"), para(app.get("non_functional")), ""),
        ("tree", tr("Screen hierarchy"), tree_html("/", ctx, rel, root=True), ""),
        ("questions", tr("Open questions"), ul(app.get("open_questions")) + para(app.get("notes")), "questions"),
    ]))
    return layout(tr("{name} — App-wide spec", name=app.get("name") or ctx["meta"]["origin"]), "".join(b), rel, ctx, [(tr("Home"), "index.html"), (tr("App-wide spec"), "")], ("overview", ""))


# ---------------------------------------------------------------------------
# index.html
# ---------------------------------------------------------------------------
def index_html(ctx: dict, safety: dict) -> str:
    app, meta, pages, desc = ctx["desc"].get("app", {}), ctx["meta"], ctx["pages"], ctx["desc"]
    all_specs = list(app.get("specs") or []) + [x for s in desc.get("sections", {}).values() for x in (s.get("common_specs") or [])] \
        + [x for pg in pages for x in (desc["pages"].get(pg["id"], {}).get("specs") or [])]
    first = first_sentence(app.get("overview"))
    b = [f'<p class="kind">{tr("Screen spec")}</p><h1>{esc(app.get("name") or meta["origin"])}</h1>'
         + (f'<p class="lead">{esc(first)}</p>' if first else "")
         + f'<div class="chips">{conf_chips(all_specs)}<span class="chip">{tr("Crawled {ts}", ts=esc(meta.get("generated_at")))}</span></div>'
         + (f'<a class="guide-cta" href="guide.html"><b>{tr("Open the system guide")}</b><span>{tr("One page for newcomers: what it does, a map of the screens, the main workflows, and the rules")}</span></a>' if ctx.get("has_guide") else "")]
    b.append('<div class="stats">' + "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for k, v in [
        (tr("Screens"), len(pages)), (tr("Sections"), len(ctx["nodes"])), (tr("Spec items"), len(all_specs)), (tr("Captures"), sum(n_shots(pg) for pg in pages)),
        (tr("Elements not clicked"), len(safety.get("skipped_elements", []))), (tr("Blocked write requests"), len(safety.get("blocked_requests", [])))]) + "</div>")

    seccards = [f'<a class="card" href="overview.html"><b>{tr("App-wide spec")}</b><span>{tr("Spec items shared by every screen, authentication and permissions, shared UI, navigation")}</span><em>{tr("Specs")} {len(app.get("specs") or [])}</em></a>']
    for path in ctx["section_order"]:
        n = len(descendant_pages(ctx["nodes"], path))
        if path == "/" or not n:
            continue
        s = desc["sections"].get(path, {})
        seccards.append(f'<a class="card" href="sections/{section_key(path)}.html"><b>{esc(ctx["sec_name"](path))}</b><span>{esc(s.get("summary") or "")}</span><em>{screens(n)} · <code>{esc(path)}</code></em></a>')
    b.append(section(tr("Sections"), f'<div class="cards">{"".join(seccards)}</div>', anchor="tree"))

    cats: dict[str, list[dict]] = OrderedDict()
    for pg in pages:
        cats.setdefault(pg["_cat"], []).append(pg)
    toc = ""
    for cat, items in cats.items():
        toc += f'<h3 class="cat">{esc(cat)}<small>{screens(len(items))}</small></h3><div class="pgrid">'
        toc += "".join(page_card(pg, desc["pages"].get(pg["id"], {}), "") for pg in items) + "</div>"
    b.append(section(tr("Screens by category"), toc, anchor="pages", count=screens(len(pages))))

    caps = '<div class="gallery">' + "".join(
        f'<a class="gi" href="captures/{pg["id"]}.html"><img src="{esc(pg["screenshot"])}" alt="" loading="lazy"><span>{esc(pg["_name"])} <small>{esc(pg["id"])}</small></span></a>'
        for pg in pages) + "</div>"
    b.append(f'<details class="raw" id="captures"><summary>{tr("All screen captures ({n} screens)", n=len(pages))}</summary>{caps}</details>')

    rep = (f'<ul><li>{tr("Blocked write requests: {n} (everything except GET is blocked; no application data was changed)", n=len(safety.get("blocked_requests", [])))}</li>'
           f'<li>{tr("Elements not clicked under the safety rules: {n} (save / delete / submit and the like, or purpose unclear)", n=len(safety.get("skipped_elements", [])))}</li>'
           f'<li>{tr("Risky URLs not opened: {n}", n=len(safety.get("skipped_urls", [])))}</li><li>{tr("Errors: {n}", n=len(safety.get("errors", [])))}</li>'
           f'<li>{tr("Crawl method: {method}", method=esc(ld(meta.get("method")) or "crawl.py"))}</li></ul>')
    if safety.get("skipped_urls"):
        uniq = OrderedDict()
        for s_ in safety["skipped_urls"]:
            key = (s_["href"].split("#")[0], s_["reason"])
            uniq.setdefault(key, []).append(s_["page"])
        rep += f'<h4>{tr("URLs not opened")}</h4>' + table(["URL", tr("Reason"), tr("Seen on")], [[k[0], ld(k[1]), screens(len(v))] for k, v in uniq.items()])
    if safety.get("errors"):
        rep += f'<h4>{tr("Errors")}</h4>' + table(["URL", tr("Detail")], [[e["url"], e["error"]] for e in safety["errors"]])
    b.append(section(tr("Crawl scope and safety report"), rep, anchor="safety"))
    return layout(tr("{name} — Screen spec", name=app.get("name") or meta["origin"]), "".join(b), "", ctx, None, ("index", ""))

# ---------------------------------------------------------------------------
# Helpers for auto-extracted data
# ---------------------------------------------------------------------------
def auto_ui_table(pg: dict) -> str:
    rows = [[c.get("text") or c.get("ariaLabel") or c.get("title") or tr("(no label)"), c.get("role") or c.get("tag"),
             tr("Click verified") if c.get("clickable") else tr("Not verified ({reason})", reason=ld(c.get("reason")))] for c in pg.get("clickables", [])]
    return table([tr("Element (auto-extracted)"), tr("Type"), tr("Check")], rows)


def auto_inputs_table(pg: dict) -> str:
    rows = []
    for f in pg.get("forms", []):
        for fl in f.get("fields", []):
            rows.append([fl.get("label") or fl.get("name") or fl.get("id") or fl.get("placeholder") or "-", fl.get("type"), tr("Required") if fl.get("required") else "", "",
                         f'form:{f.get("name") or f.get("index")} method={f.get("method")}' + (" / " + tr("options: {list}", list=", ".join(fl["options"])) if fl.get("options") else "")])
    for fl in pg.get("looseFields", []):
        rows.append([fl.get("label") or fl.get("name") or fl.get("id") or fl.get("placeholder") or "-", fl.get("type"), "", "", tr("Outside a form")])
    return table([tr("Field (auto-extracted)"), tr("Type"), tr("Required"), tr("Assumed validation"), tr("Notes")], rows)


def auto_transitions(pg: dict, by_norm: dict) -> str:
    rows, seen = [], set()
    for ln in pg.get("links", []):
        if not ln.get("internal") or not ln.get("norm") or ln["norm"] in seen:
            continue
        seen.add(ln["norm"])
        target = by_norm.get(ln["norm"])
        rows.append([ln.get("text") or tr("(link)"), (f'{target["_name"]} ({target["id"]})' if target else urlparse(ln["href"]).path), tr("Link (auto-extracted)")])
    for st in pg.get("states", []):
        if is_navigation(st):
            rows.append([tr("Click “{label}”", label=ld(st.get("label"))), urlparse(st.get("url_after", "")).path, tr("Click verified")])
    return table([tr("Trigger"), tr("Goes to"), tr("Notes")], rows)


def auto_raw(pg: dict) -> str:
    out = f'<h4>{tr("Headings")}</h4>' + (ul([f'{h["level"]}: {h["text"]}' for h in pg.get("headings", [])]) or "<p>-</p>")
    out += f'<h4>{tr("Tables")}</h4>' + (table([tr("Caption"), tr("Headers"), tr("Rows")], [[tb.get("caption"), " | ".join(tb.get("headers", [])), tb.get("rows")] for tb in pg.get("tables", [])]) or "<p>-</p>")
    out += f'<h4>{tr("Internal links")}</h4>' + (table([tr("Text"), "URL", tr("Notes")], [[l.get("text"), l.get("href"), ld(l.get("skipped", ""))] for l in pg.get("links", []) if l.get("internal")]) or "<p>-</p>")
    ext = [l for l in pg.get("links", []) if not l.get("internal")]
    if ext:
        out += f'<h4>{tr("External links")}</h4>' + table([tr("Text"), "URL"], [[l.get("text"), l.get("href")] for l in ext])
    out += f'<h4>{tr("Safety decision for clickable elements")}</h4>' + (table([tr("Element"), tr("Type"), tr("Decision"), tr("Reason"), tr("Selector")], [[c.get("text") or c.get("ariaLabel") or c.get("title"), c.get("role") or c.get("tag"), tr("Click") if c.get("clickable") else tr("Skip"), ld(c.get("reason")), c.get("selector")] for c in pg.get("clickables", [])]) or "<p>-</p>")
    out += f'<h4>{tr("Body text (start)")}</h4><pre>' + esc((pg.get("bodyText") or "")[:1500]) + "</pre>"
    return out


def first_sentence(text) -> str:
    """The first sentence of a description, with its end mark. Works for CJK text (ends with 。) and for
    text whose sentences end with ". " (English, Spanish, Korean ...)."""
    text = text or ""
    if "。" in text:
        head = text.split("。")[0]
        return head + "。" if head else ""
    m = re.match(r"\s*(.+?[.!?])(\s|$)", text, re.S)
    if m:
        return m.group(1)
    text = text.strip()
    return text + tr(".") if text else ""


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crawl", required=True, help="crawl output directory (holds pages.json)")
    ap.add_argument("--descriptions", default=None, help="descriptions.json (default: <crawl>/descriptions.json)")
    ap.add_argument("--out", default=None, help="where to write the book (default: <crawl>/book)")
    ap.add_argument("--init-descriptions", action="store_true", help="write the template to fill in (adds what is missing if the file exists)")
    ap.add_argument("--lang", choices=list(i18n.LANGS), default=None,
                    help="language of the book (default: _lang in descriptions.json; ja for a descriptions.json without _lang; otherwise en)")
    a = ap.parse_args()
    global LANG

    crawl_dir = Path(a.crawl).resolve()
    crawl = read_json(crawl_dir / "pages.json")
    desc_path = Path(a.descriptions) if a.descriptions else crawl_dir / "descriptions.json"
    existing = read_json(desc_path) if desc_path.exists() else None
    # A descriptions.json without _lang comes from before languages were supported: those projects are Japanese.
    LANG = a.lang or (existing or {}).get("_lang") or ("ja" if existing is not None else i18n.DEFAULT)
    if LANG not in i18n.LANGS:
        LANG = i18n.DEFAULT
    if a.init_descriptions:
        existing = existing or {}
        existing["_lang"] = LANG  # the language the descriptions are written in; build and write read it
        init_descriptions(crawl, desc_path, existing)
        print(f"Wrote the template: {desc_path}  ({len(crawl['pages'])} screens / {len(build_tree(crawl['pages']))} sections / language: {i18n.language_name(LANG)})")
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
        pg["_cat"] = d.get("category") or tr("Uncategorized")
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
            return tr("Root")
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
        emit(out / "pages" / f"{pg['id']}.html", page_spec_html(pg, d, ctx))
        emit(out / "captures" / f"{pg['id']}.html", page_capture_html(pg, d, ctx))
    for path, node in nodes.items():
        emit(out / "sections" / f"{section_key(path)}.html", section_html(path, node, desc["sections"].get(path, {}), ctx))
    emit(out / "overview.html", overview_html(ctx))
    emit(out / "index.html", index_html(ctx, safety))
    if ctx["has_guide"]:
        raw = (crawl_dir / "guide_body.html").read_text(encoding="utf-8")
        m = re.match(r"<!-- model: (\S+) -->", raw)
        emit(out / "guide.html", guide_html(raw, m.group(1) if m else "Claude", ctx))

    pf = sum(1 for pg in pages if desc["pages"].get(pg["id"], {}).get("specs"))
    sf = sum(1 for p in nodes if desc["sections"].get(p, {}).get("summary"))
    print(f"Built the screen spec: {out}/index.html")
    print(f"  {len(pages)} screens ({pf} with spec items) / {len(nodes)} sections ({sf} filled in) / {len(desc['app'].get('specs') or [])} app-wide spec items / language: {i18n.language_name(LANG)}")
    nc = sum(1 for p in nodes if p != "/" and len(descendant_pages(nodes, p)) > 1 and not desc["sections"].get(p, {}).get("common_specs"))
    if nc:
        print(f"  {nc} sections with two or more screens have no shared specs (common_specs). Move specs the screens have in common up to the section.")
    if pf < len(pages) or sf < len(nodes):
        print("Note: some entries are not filled in. Fill in descriptions.json and run again.")


if __name__ == "__main__":
    main()
