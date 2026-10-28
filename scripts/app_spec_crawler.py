#!/usr/bin/env python3
"""app-spec-crawler のコマンド。help / doctor / crawl / describe / build / write / verify。

標準ライブラリだけで動く。巡回と見た目の確認は browser-use（利用者の起動中の Chrome）で行う。
エラーのときは「何が起きたか・なぜか・どう直すか」を出し、直す操作は自分では行わない（人の承認を待つ）。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
NAME = "app-spec-crawler"
BU_NAME = NAME  # 他の作業の browser-use と混ざらないよう、専用の接続（daemon）を使う
CHROME_DIR = Path.home() / "Library/Application Support/Google/Chrome"

DEFAULT_HIDE: list[str] = []  # 撮る前に隠す重なりは、対象アプリごとに --hide で渡す
DEFAULT_SESSION = ["セッションが無効", "セッションの有効期限", "再度ログインしてください", "ログインしてください", "session (has )?expired",
                   "please (log|sign) ?in again"]

# 終了コード
OK, E_GENERAL, E_USAGE, E_SESSION, E_CONNECT, E_DEPENDENCY, E_VERIFY, E_BUILD, E_WRITE = 0, 1, 2, 3, 4, 5, 6, 7, 8
GUIDE_MODEL = "claude-fable-5-1"  # システム概要書（guide.html）を書くモデル

HELP = f"""\
{NAME} — Web アプリを読み取り専用で巡回し、スクリーンショット付きの HTML 仕様書を作る

使い方
  {NAME} [help]                       この説明を出す
  {NAME} doctor [--url URL]           このスキルが今使えるかを確かめる（足りないもの・直し方を出す）
  {NAME} crawl --url URL --out DIR    ログイン済みの Chrome で巡回する（browser-use）
  {NAME} describe DIR                 説明を書くための雛形 DIR/descriptions.json を作る
  {NAME} build DIR                    DIR/book/index.html（画面仕様書）を作る
  {NAME} write DIR                    claude -p（Fable）でシステム概要書 DIR/book/guide.html を書く
  {NAME} verify DIR                   仕様書を browser-use で開き、見た目を確かめる

流れ
  1. doctor で準備を確かめる（NG があれば直し方が出る。直すのは人の承認を得てから）
  2. 利用者の Chrome で対象アプリにログインしておく
  3. crawl で巡回 → DIR/pages.json と DIR/screenshots/
  4. describe → Claude がスクリーンショットを見て descriptions.json を書く
  5. build → write（Fable がシステム概要書を書く）→ verify → DIR/book/ を zip にして渡す

巡回のしかた（どれを使うか）
  browser-use   … 第一選択。利用者の起動中の Chrome（ログイン済み）を、画面を奪わずに操作する
  computer-use  … browser-use が使えないときの代わり。Claude が画面を見て手で回す（references/manual-crawl.md）
  Playwright    … 不要。使うのは利用者が明示したときだけ（scripts/crawl.py。任意）

crawl のおもなオプション
  --url URL                 起点（ログイン後の画面）
  --out DIR                 出力先（新しい空のフォルダ）
  --resume                  途中で止まった巡回の続き（ログインし直したら --url に新しい URL）
  --scope-prefix URL        この文字列で始まる URL だけ回す（既定: 起点と同じオリジン）
  --route-param NAME        画面を ?NAME=... で切り替えるアプリ（例: page）
  --variant-param NAME      別画面として扱うクエリ（例: tab。複数可）
  --exclude REGEX           開かない URL（複数可）
  --allow-route PATH        危険な言葉を含んでも開いてよい画面（例: /export/select）
  --max-pages N / --max-depth N / --batch N / --wait 秒
  --no-tabs                 ページ内タブ（#xxx）もクリックしない
  --hide SELECTOR           撮る前に隠す重なり（サイト内ヘルプ・チャット窓などの CSS セレクタ。複数可）

安全
  画面は URL で開くだけ。入力・送信・保存・削除はしない。押すのは「#xxx」へのページ内タブだけ。
  logout / delete / approve / export などを含む URL は開かない（scripts/safety_rules.json）。

終了コード
  0 成功 / 1 その他 / 2 使い方の誤り / 3 ログイン切れ / 4 Chrome につながらない
  5 必要なものが入っていない / 6 見た目の確認で問題あり / 7 仕様書の生成に失敗
  8 Fable での仕様書の書き出しに失敗

画面はライト固定（OS がダークでも明るいまま）。
"""


def dwidth(t: str) -> int:
    """端末での表示幅（全角は 2）"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in t)


def pad(t: str, w: int) -> str:
    return t + " " * max(0, w - dwidth(t))


class Fail(Exception):
    def __init__(self, code: int, what: str, why: str, fixes: list[str] | None = None, human: bool = True):
        super().__init__(what)
        self.code, self.what, self.why, self.fixes, self.human = code, what, why, fixes or [], human


def report(f: Fail) -> int:
    print(f"\n✖ エラー: {f.what}", file=sys.stderr)
    print(f"  原因: {f.why}", file=sys.stderr)
    if f.fixes:
        print("  直し方" + ("（実行する前に人の承認をもらうこと）" if f.human else "") + ":", file=sys.stderr)
        for i, x in enumerate(f.fixes, 1):
            print(f"    {i}. {x}", file=sys.stderr)
    return f.code


# ---------------------------------------------------------------------------
# browser-use とのつなぎ
# ---------------------------------------------------------------------------
def devtools_ws() -> tuple[str | None, str]:
    """利用者の Chrome の遠隔デバッグの接続先。無ければ (None, 理由)"""
    f = CHROME_DIR / "DevToolsActivePort"
    if not f.exists():
        return None, "Chrome の遠隔デバッグが有効になっていない（DevToolsActivePort が無い）"
    lines = f.read_text().split()
    if len(lines) < 2:
        return None, "DevToolsActivePort の中身が読めない"
    port, path = lines[0], lines[1]
    try:
        socket.create_connection(("127.0.0.1", int(port)), timeout=2).close()
    except OSError:
        return None, f"Chrome の遠隔デバッグの口（127.0.0.1:{port}）につながらない。Chrome が閉じたか、許可が切れている"
    return f"ws://127.0.0.1:{port}{path}", ""


def need_browser_use() -> str:
    exe = shutil.which("browser-use")
    if not exe:
        raise Fail(E_DEPENDENCY, "browser-use が入っていない", "巡回と見た目の確認は browser-use で行うため",
                   ["uv tool install browser-use（uv が無ければ brew install uv）", f"{NAME} doctor でもう一度確かめる"])
    return exe


def run_bu(script: Path, env_extra: dict, timeout: int, first: bool = False) -> str:
    exe = need_browser_use()
    ws, why = devtools_ws()
    if not ws:
        raise Fail(E_CONNECT, "利用者の Chrome につながらない", why, [
            "Chrome で chrome://inspect/#remote-debugging を開き「Allow remote debugging for this browser instance」を有効にする（人の操作）",
            f"{NAME} doctor でもう一度確かめる"])
    env = dict(os.environ, BU_NAME=BU_NAME, BU_CDP_WS=ws, **env_extra)
    try:
        with open(script) as fh:
            p = subprocess.run([exe], stdin=fh, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        if first:
            raise Fail(E_CONNECT, f"browser-use が {timeout} 秒たっても返ってこない",
                       "Chrome に「リモートデバッグを許可しますか」の確認が出たまま止まっていると思われる（この接続での初回は必ず出る）", [
                           "Chrome に出ている確認で「許可」を押す（人の操作）",
                           f"または BU_NAME={BU_NAME} browser-use mac-approve を実行して許可を押させる",
                           "もう一度同じコマンドを実行する"])
        raise Fail(E_GENERAL, f"browser-use の 1 回の実行が {timeout} 秒で終わらなかった",
                   "重いページで読み込みが終わらない、または Chrome が応答していない", ["--batch を小さくして --resume で続きから回す", "Chrome が固まっていないか見る"], human=False)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0 and "ASC_" not in out:
        tail = "\n      ".join(out.strip().splitlines()[-8:])
        hint = ["browser-use --doctor の結果を見る"]
        if "Allow" in out or "remote debugging" in out.lower():
            hint = ["Chrome の確認で「許可」を押す（人の操作）", f"または BU_NAME={BU_NAME} browser-use mac-approve"]
        raise Fail(E_CONNECT, "browser-use の実行に失敗した", f"browser-use の出力の最後:\n      {tail}", hint)
    return out


def bu_probe() -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write('import json\nv=cdp("Browser.getVersion")\nprint("ASC_PROBE="+json.dumps({"ua":v["userAgent"],"tabs":[t["url"] for t in list_tabs()]}))\n')
    try:
        out = run_bu(Path(fh.name), {}, 40, first=True)
    finally:
        os.unlink(fh.name)
    m = re.search(r"ASC_PROBE=(\{.*\})", out)
    if not m:
        raise Fail(E_CONNECT, "browser-use から Chrome の情報が取れない", "出力に結果が無い: " + out.strip()[-300:], ["browser-use --doctor の結果を見る"])
    return json.loads(m.group(1))


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
def cmd_doctor(a) -> int:
    rows: list[tuple[str, str, str, str]] = []  # (OK/NG/注意/情報, 項目, 中身, 直し方)

    def add(state, item, detail, fix=""):
        rows.append((state, item, detail, fix))

    v = sys.version_info
    add("OK" if v >= (3, 9) else "NG", "Python", f"{v.major}.{v.minor}.{v.micro}（{sys.executable}）", "" if v >= (3, 9) else "Python 3.9 以上を入れる")
    for f in ("scripts/build_book.py", "scripts/bu_crawl.py", "scripts/bu_verify.py", "scripts/safety_rules.json", "references/guide-prompt.md"):
        if not (SKILL / f).exists():
            add("NG", "スキルのファイル", f"{f} が無い", "スキルを入れ直す")
    exe = shutil.which("browser-use")
    if exe:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True)
        add("OK", "browser-use", (r.stdout or r.stderr).strip() or exe)
    else:
        add("NG", "browser-use", "入っていない（巡回・見た目の確認に要る）", "uv tool install browser-use")
    mac = platform.system() == "Darwin"
    if mac:
        add("OK" if Path("/Applications/Google Chrome.app").exists() else "NG", "Google Chrome",
            "/Applications/Google Chrome.app" if Path("/Applications/Google Chrome.app").exists() else "見つからない", "Google Chrome を入れる")
        running = subprocess.run(["pgrep", "-x", "Google Chrome"], capture_output=True).returncode == 0
        add("OK" if running else "NG", "Chrome の起動", "起動している" if running else "起動していない", "Chrome を開いて対象アプリにログインする（人の操作）")
        ws, why = devtools_ws()
        add("OK" if ws else "NG", "Chrome の遠隔デバッグ", ws or why,
            "" if ws else "Chrome で chrome://inspect/#remote-debugging を開き「Allow remote debugging for this browser instance」を有効にする（人の操作）")
        if ws and exe and not a.no_connect:
            try:
                info = bu_probe()
                headless = "Headless" in info["ua"]
                add("NG" if headless else "OK", "browser-use の接続", ("画面なしの Chrome につながっている" if headless else "利用者の Chrome につながった") + f"（タブ {len(info['tabs'])} 枚）",
                    f"BU_NAME={BU_NAME} browser-use --reload で接続を作り直す" if headless else "")
                if a.url:
                    origin = re.match(r"https?://[^/]+", a.url)
                    hit = origin and any(t.startswith(origin.group(0)) for t in info["tabs"])
                    add("OK" if hit else "注意", "対象アプリのタブ", "開いている" if hit else f"{origin.group(0) if origin else a.url} のタブが無い",
                        "" if hit else "Chrome で対象アプリを開いてログインしておく（人の操作）")
            except Fail as f:
                add("NG", "browser-use の接続", f.what + "。" + f.why.split("\n")[0], " / ".join(f.fixes))
    else:
        add("注意", "OS", f"{platform.system()}（Chrome の遠隔デバッグの確認は macOS のみ対応）", "browser-use --doctor で確かめる")
    cl = shutil.which("claude")
    add("OK" if cl else "NG", "claude（write）", (cl + f"（{GUIDE_MODEL} でシステム概要書を書く）") if cl else "入っていない（write で使う）",
        "" if cl else "Claude Code を入れる（npm install -g @anthropic-ai/claude-code）")
    add("情報", "computer-use", "Claude 側の道具なので、このコマンドからは確かめられない。browser-use が使えないときの代わり", "")
    try:
        import importlib.util
        pw = importlib.util.find_spec("playwright") is not None
    except Exception:
        pw = False
    add("情報", "Playwright", ("入っている" if pw else "入っていない") + "（不要。scripts/crawl.py を使うときだけ要る）", "")
    add("OK" if shutil.which("zip") else "注意", "zip", "ある" if shutil.which("zip") else "無い（仕様書を zip で渡すときに要る）", "" if shutil.which("zip") else "zip を入れる")

    w = max(dwidth(r[1]) for r in rows) + 2
    mark = {"OK": "✔", "NG": "✖", "注意": "!", "情報": "·"}
    print(f"{NAME} doctor\n")
    for s, item, detail, _ in rows:
        print(f"  {mark[s]} {pad(s, 5)}{pad(item, w)}{detail}")
    ng = [r for r in rows if r[0] == "NG"]
    warn = [r for r in rows if r[0] == "注意"]
    fixes = [r for r in rows if r[0] in ("NG", "注意") and r[3]]
    if fixes:
        print("\n直し方（実行する前に人の承認をもらうこと）:")
        for i, (_, item, _, fix) in enumerate(fixes, 1):
            print(f"  {i}. [{item}] {fix}")
    print("\n結果: " + ("使える" if not ng and not warn else "使える（注意あり）" if not ng else f"使えない（NG {len(ng)} 件）"))
    if ng:
        return E_CONNECT if any(r[1].startswith(("Chrome", "browser-use の接続")) for r in ng) and not any(r[1] in ("browser-use", "Python") for r in ng) else E_DEPENDENCY
    return OK


# ---------------------------------------------------------------------------
# crawl
# ---------------------------------------------------------------------------
def cmd_crawl(a) -> int:
    out = Path(a.out).expanduser().resolve()
    state = out / "state.json"
    if state.exists() and not a.resume:
        raise Fail(E_USAGE, f"{out} に前回の巡回の続きが残っている", "上書きすると前回の結果が消えるため止めた",
                   ["続きから回すなら --resume を付ける", "最初からやり直すなら別の --out を指定する"], human=False)
    if out.exists() and any(out.iterdir()) and not state.exists():
        raise Fail(E_USAGE, f"{out} は空のフォルダではない", "巡回の結果と他のファイルが混ざらないようにするため", ["新しい空のフォルダを --out に指定する"], human=False)
    if not re.match(r"https?://", a.url or ""):
        raise Fail(E_USAGE, "--url が http(s):// で始まっていない", f"受け取った値: {a.url!r}", ["ログイン後の画面の URL を --url に渡す"], human=False)
    out.mkdir(parents=True, exist_ok=True)
    origin = re.match(r"https?://[^/]+", a.url).group(0)
    cfg = {"url": a.url, "url_display": a.url, "out": str(out), "rules": str(SCRIPTS / "safety_rules.json"),
           "scope_prefix": a.scope_prefix or origin, "scope_display": a.scope_prefix or origin,
           "route_param": a.route_param, "variant_params": a.variant_param, "exclude": a.exclude, "allow_routes": a.allow_route,
           "extra_deny": a.extra_deny, "hide_selectors": DEFAULT_HIDE + a.hide, "session_error_patterns": DEFAULT_SESSION + a.session_text,
           "tabs": not a.no_tabs, "keep_query": a.keep_query, "id_collapse": not a.no_id_collapse,
           "batch": a.batch, "max_pages": a.max_pages, "max_depth": a.max_depth, "wait": a.wait}
    cfg_path = out / "crawl_config.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    print(f"巡回を始めます: {a.url}\n  出力先: {out}\n  1 回 {a.batch} 画面ずつ、上限 {a.max_pages} 画面。ログイン切れを見つけたら止まります。")
    first = True
    for _ in range(1000):
        res = run_bu(SCRIPTS / "bu_crawl.py", {"ASC_CONFIG": str(cfg_path)}, 600, first=first)
        first = False
        for line in res.splitlines():
            if re.match(r"p\d{3} |ERROR ", line):
                print("  " + line)
        m = re.search(r"ASC_STATUS=(\w+) ?(.*)", res)
        if not m:
            tail = "\n      ".join(res.strip().splitlines()[-10:])
            raise Fail(E_GENERAL, "巡回スクリプトが途中で落ちた", f"出力の最後:\n      {tail}", [f"{NAME} crawl ... --resume で続きから回す", "同じ画面で何度も落ちるなら --exclude でその URL を外す"], human=False)
        status, msg = m.group(1), m.group(2)
        if status == "more":
            print(f"  … {msg}")
            continue
        if status == "done":
            s = json.loads(state.read_text())
            print(f"\n✔ 巡回が終わりました（{msg}）\n  画面 {len(s['pages'])} / 開かなかった URL {len(s['skipped_urls'])} / 押さなかった要素 {len(s['skipped_elements'])} / エラー {len(s['errors'])}")
            print(f"  次: {NAME} describe {out}")
            return OK
        if status in ("session", "start_failed"):
            raise Fail(E_SESSION, "ログインが切れている" if status == "session" else "起点の画面がログイン済みで開けない", msg, [
                "Chrome で対象アプリにログインし直す（人の操作）",
                f"ログイン後の URL で {NAME} crawl --url <新しい URL> --out {out} --resume を実行する（URL のトークンが変わっても続きから回る）"])
        raise Fail(E_GENERAL, "巡回が止まった", msg, [f"{NAME} crawl ... --resume で続きから回す"], human=False)
    return OK


# ---------------------------------------------------------------------------
# describe / build / verify
# ---------------------------------------------------------------------------
def crawl_dir(d: str) -> Path:
    p = Path(d).expanduser().resolve()
    if not (p / "pages.json").exists():
        raise Fail(E_USAGE, f"{p} に pages.json が無い", "巡回の結果のフォルダではない、または巡回がまだ終わっていない", [f"{NAME} crawl で巡回する", "巡回の --out に使ったフォルダを渡す"], human=False)
    return p


def run_build(args: list[str]) -> str:
    p = subprocess.run([sys.executable, str(SCRIPTS / "build_book.py")] + args, capture_output=True, text=True)
    if p.returncode != 0:
        err = (p.stderr or p.stdout).strip()
        why = err.splitlines()[-1] if err else "不明"
        fixes = ["エラーの行を見て、該当するファイルを直す"]
        if "JSONDecodeError" in err:
            fixes = ["descriptions.json の書式が壊れている。python3 -m json.tool DIR/descriptions.json で場所を確かめて直す"]
        raise Fail(E_BUILD, "仕様書の生成に失敗した", why, fixes, human=False)
    return p.stdout


def cmd_describe(a) -> int:
    d = crawl_dir(a.dir)
    print(run_build(["--crawl", str(d), "--init-descriptions"]).strip())
    print(f"次: {d}/descriptions.json を書く（references/description-guide.md）→ {NAME} build {d}")
    return OK


def cmd_build(a) -> int:
    d = crawl_dir(a.dir)
    print(run_build(["--crawl", str(d)]).strip())
    print(f"次: {NAME} write {d}（Fable がシステム概要書を書く）→ {NAME} verify {d}")
    return OK


GUIDE_KEEP = ("name", "category", "summary", "purpose", "users_and_usage", "display_conditions", "features", "flows",
              "business_rules", "open_questions", "specs")


def guide_material(d: Path, book: Path) -> str:
    """Fable に渡す材料。説明のうち読み物に要る項目と、リンクしてよいファイルの一覧"""
    desc = json.loads((d / "descriptions.json").read_text(encoding="utf-8"))
    crawl = json.loads((d / "pages.json").read_text(encoding="utf-8"))
    pages = []
    for pg in crawl["pages"]:
        x = {k: v for k, v in desc.get("pages", {}).get(pg["id"], {}).items() if k in GUIDE_KEEP and v}
        for sp in x.get("specs") or []:
            for k in ("evidence", "notes"):
                sp.pop(k, None)
        pages.append({"id": pg["id"], "path": re.sub(r"^https?://[^/]+", "", pg.get("norm_url", "")), **x})
    secs = {p: {k: v for k, v in s.items() if not k.startswith("_") and v} for p, s in desc.get("sections", {}).items()}
    files = sorted(str(f.relative_to(book)) for f in book.rglob("*") if f.suffix in (".html", ".png") and f.name != "guide.html"
                   and not f.relative_to(book).parts[0] == "assets")
    files = [f for f in files if not re.match(r"screenshots/p\d+_", f)]  # 操作状態の画像は省いて材料を軽くする
    return json.dumps({"app": desc.get("app", {}), "sections": secs, "pages": pages, "使えるファイル": files}, ensure_ascii=False, indent=0)


def clean_guide(html: str, book: Path) -> tuple[str, list[str]]:
    """Fable の出力から危ないもの・存在しないリンクを除く。直したことの一覧も返す"""
    notes = []
    m = re.search(r"<article class=\"guide\".*</article>", html, re.S)
    if not m:
        raise Fail(E_WRITE, "Fable の出力に <article class=\"guide\"> が無い", "指示した形で書かれなかった（途中で切れた・説明文だけ返した など）",
                   ["もう一度 write を実行する", "続くなら --budget を上げる"], human=False)
    html = m.group(0)
    for pat, what in ((r"<(script|style|iframe)\b.*?</\1>", "script/style"), (r"\s(on\w+|style)=\"[^\"]*\"", "属性")):
        html, n = re.subn(pat, "", html, flags=re.S | re.I)
        if n:
            notes.append(f"{what} を {n} か所消した")

    def fix(m_):
        attr, val = m_.group(1), m_.group(2)
        target = val.split("#")[0]
        if val.startswith("#") or (target and (book / target).exists()):
            return m_.group(0)
        notes.append(f"無いファイルへの{'画像' if attr == 'src' else 'リンク'}を外した: {val}")
        return f'{attr}="#"' if attr == "href" else 'src="" hidden'
    html = re.sub(r'\b(href|src)="([^"]*)"', fix, html)
    return html, notes


def cmd_write(a) -> int:
    d = crawl_dir(a.dir)
    book = d / "book"
    if not (book / "index.html").exists():
        raise Fail(E_USAGE, "画面仕様書がまだ無い", f"{book}/index.html が無い。システム概要書は画面仕様書の画像とページにリンクするため、先に build が要る", [f"{NAME} build {d}"], human=False)
    if not (d / "descriptions.json").exists():
        raise Fail(E_USAGE, "descriptions.json が無い", "Fable は Claude が書いた画面の説明を材料にする", [f"{NAME} describe {d} のあと descriptions.json を書く"], human=False)
    todo = (d / "descriptions.json").read_text(encoding="utf-8").count('"specs": []')
    if todo:
        print(f"! 仕様項目が空の画面が {todo} 件ある。その画面は薄い説明になる")
    exe = shutil.which("claude")
    if not exe:
        raise Fail(E_DEPENDENCY, "claude（Claude Code）が入っていない", "システム概要書は claude -p で Fable に書かせるため",
                   ["npm install -g @anthropic-ai/claude-code", "claude にログインしておく（人の操作）", f"{NAME} doctor でもう一度確かめる"])
    prompt = (SKILL / "references" / "guide-prompt.md").read_text(encoding="utf-8") + "\n" + guide_material(d, book)
    cmd = [exe, "-p", "--model", a.model, "--tools", "", "--permission-mode", "dontAsk", "--max-budget-usd", str(a.budget), "--effort", "high"]
    print(f"{a.model} に仕様書を書かせています（材料 {len(prompt) // 1000}k 文字。数分かかる。上限 ${a.budget}）…")
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=a.timeout, cwd=tempfile.gettempdir())
    except subprocess.TimeoutExpired:
        raise Fail(E_WRITE, f"Fable が {a.timeout} 秒で書き終わらなかった", "材料が多い、または混んでいる", [f"--timeout を延ばしてもう一度 write を実行する"], human=False)
    out = p.stdout or ""
    if p.returncode != 0 or "<article" not in out:
        err = (p.stderr or out).strip()
        last = err.splitlines()[-1] if err else f"終了コード {p.returncode}、出力なし"
        fixes = ["もう一度 write を実行する"]
        if re.search(r"budget|上限", err, re.I):
            fixes = [f"--budget を上げる（今は ${a.budget}。費用がかかるので人の承認をもらう）"]
        elif re.search(r"log ?in|auth|credential|401", err, re.I):
            fixes = ["claude にログインし直す（ターミナルで claude を起動し /login。人の操作）"]
        elif re.search(r"model", err, re.I):
            fixes = [f"--model を変える（例: --model opus）", "使えるモデルは claude --help の --model の説明を見る"]
        raise Fail(E_WRITE, "Fable での仕様書の書き出しに失敗した", last, fixes)
    body, notes = clean_guide(out, book)
    (d / "guide_body.html").write_text(f"<!-- model: {a.model} -->\n{body}\n", encoding="utf-8")
    run_build(["--crawl", str(d)])  # 本文（guide_body.html）を枠に入れて book/guide.html にし、画面仕様書に入口を出す
    print(f"✔ 書きました: {book}/guide.html（{len(body) // 1000}k 文字）")
    for n in notes:
        print("  直したこと: " + n)
    print("  Fable は材料にない事実を足すことがある。数字・画面名・ボタン名を材料と照らし合わせること")
    print(f"次: {NAME} verify {d}")
    return OK


def cmd_verify(a) -> int:
    d = crawl_dir(a.dir)
    book = d / "book"
    if not (book / "index.html").exists():
        raise Fail(E_USAGE, "仕様書がまだ無い", f"{book}/index.html が無い", [f"{NAME} build {d}"], human=False)
    todo = sum(f.read_text(encoding="utf-8").count("要記入") for f in book.rglob("*.html"))
    shots = d / "verify"
    cfg = Path(tempfile.mkstemp(suffix=".json")[1])
    cfg.write_text(json.dumps({"book": str(book), "shots": str(shots)}))
    try:
        res = run_bu(SCRIPTS / "bu_verify.py", {"ASC_CONFIG": str(cfg)}, 300, first=True)
    finally:
        cfg.unlink()
    m = re.search(r"ASC_VERIFY=(\{.*\})", res)
    if not m:
        raise Fail(E_GENERAL, "見た目の確認が途中で落ちた", res.strip()[-400:], ["もう一度実行する"], human=False)
    r = json.loads(m.group(1))
    problems = r["problems"] + ([f"「要記入」が {todo} か所残っている"] if todo else [])
    print(f"確かめたページ: {', '.join(r['pages'])}\n撮った画像: {shots}/（{len(r['shots'])} 枚。幅 1440/390。OS をダークにした状態でも明るいままかを見ている）")
    if problems:
        print("\n✖ 見つかった問題:")
        for x in problems:
            print("  - " + x)
        print("\n直し方: はみ出し・画像は assets/book.css や scripts/build_book.py、要記入は descriptions.json を直して build し直す（スキルを直すときは人の承認をもらうこと）")
        return E_VERIFY
    print("✔ はみ出し・読めない画像・暗い背景・要記入は見つからなかった。撮った画像を目で見て、表の折り返しや重なりも確かめること")
    return OK


# ---------------------------------------------------------------------------
def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # エラー（stderr）と進み具合の表示の順番をそろえる
    if len(sys.argv) == 1 or sys.argv[1] in ("help", "-h", "--help"):
        print(HELP)
        return OK
    class Parser(argparse.ArgumentParser):
        def error(self, message):  # argparse の英語のエラーを、原因つきの Fail にする
            m = re.search(r"required: (.+)", message)
            why = f"必要な引数 {m.group(1)} が無い" if m else f"argparse の判定: {message}"
            raise Fail(E_USAGE, f"「{' '.join(sys.argv[1:])}」の引数が足りない、または間違っている", why, [f"{NAME} help で書き方を見る"], human=False)

    ap = Parser(prog=NAME, add_help=False)
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("doctor")
    d.add_argument("--url")
    d.add_argument("--no-connect", action="store_true", help="browser-use でつないでみるのを省く")
    c = sub.add_parser("crawl")
    c.add_argument("--url", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--resume", action="store_true")
    c.add_argument("--scope-prefix")
    c.add_argument("--route-param")
    c.add_argument("--variant-param", action="append", default=[])
    c.add_argument("--exclude", action="append", default=[])
    c.add_argument("--allow-route", action="append", default=[])
    c.add_argument("--extra-deny", action="append", default=[])
    c.add_argument("--hide", action="append", default=[])
    c.add_argument("--session-text", action="append", default=[])
    c.add_argument("--no-tabs", action="store_true")
    c.add_argument("--keep-query", action="store_true")
    c.add_argument("--no-id-collapse", action="store_true")
    c.add_argument("--batch", type=int, default=30)
    c.add_argument("--max-pages", type=int, default=300)
    c.add_argument("--max-depth", type=int, default=10)
    c.add_argument("--wait", type=float, default=1.0)
    for n in ("describe", "build", "verify"):
        sub.add_parser(n).add_argument("dir")
    w = sub.add_parser("write")
    w.add_argument("dir")
    w.add_argument("--model", default=GUIDE_MODEL)
    w.add_argument("--budget", type=float, default=8.0, help="claude -p の上限（ドル）")
    w.add_argument("--timeout", type=int, default=1800)
    if sys.argv[1] not in ("doctor", "crawl", "describe", "build", "write", "verify"):
        return report(Fail(E_USAGE, f"知らないコマンド「{sys.argv[1]}」", "使えるのは help / doctor / crawl / describe / build / write / verify", [f"{NAME} help で使い方を見る"], human=False))
    try:
        a = ap.parse_args()
        return {"doctor": cmd_doctor, "crawl": cmd_crawl, "describe": cmd_describe, "build": cmd_build, "write": cmd_write, "verify": cmd_verify}[a.cmd](a)
    except Fail as f:
        return report(f)
    except KeyboardInterrupt:
        return report(Fail(E_GENERAL, "途中で止めた", "Ctrl+C が押された", ["続きから回すなら crawl に --resume を付ける"], human=False))


if __name__ == "__main__":
    sys.exit(main())
