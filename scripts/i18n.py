#!/usr/bin/env python3
"""
app-spec-crawler / i18n.py
--------------------------
Translations for the generated documents. Standard library only.

English is the source language: code passes the English string to t(), and the
catalog scripts/locales/<lang>.json ({"English source": "translation"}) supplies
the other languages. A missing key falls back to the English source.

  t(lang, text, **kw)        UI strings
  localize_data(lang, s)     fixed phrases the crawler writes into pages.json /
                             safety_report.json (canonical English, or the
                             Japanese forms found in old crawls)
  normalize_confidence(v)    any spelling of a confidence value -> key
  confidence_label(lang, k)  key -> label in that language
"""
from __future__ import annotations

import json
import re
from pathlib import Path

LANGS = ("en", "ja", "zh", "es", "ko")
DEFAULT = "en"
LOCALES = Path(__file__).resolve().parent / "locales"

_NAMES = {"en": "English", "ja": "Japanese", "zh": "Simplified Chinese", "es": "Spanish", "ko": "Korean"}
_HTML_LANG = {"en": "en", "ja": "ja", "zh": "zh-Hans", "es": "es", "ko": "ko"}

_catalogs: dict[str, dict[str, str]] = {}


def language_name(lang: str) -> str:
    return _NAMES.get(lang, _NAMES[DEFAULT])


def html_lang(lang: str) -> str:
    return _HTML_LANG.get(lang, _HTML_LANG[DEFAULT])


def catalog(lang: str) -> dict[str, str]:
    """The catalog of one language ({} for English or when the file is missing)."""
    if lang not in _catalogs:
        path = LOCALES / f"{lang}.json"
        _catalogs[lang] = json.loads(path.read_text(encoding="utf-8")) if lang != DEFAULT and lang in LANGS and path.exists() else {}
    return _catalogs[lang]


def t(lang: str, text: str, **kw) -> str:
    """Translate the English source string `text` into `lang`, then fill {placeholders} if any are given."""
    out = text if lang == DEFAULT else catalog(lang).get(text, text)
    return out.format(**kw) if kw else out


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------
CONFIDENCE = ("verified", "inferred", "to_confirm")
CONFIDENCE_LABELS = {"verified": "Verified", "inferred": "Inferred", "to_confirm": "To confirm"}  # English source labels
_CONFIDENCE_LEGACY_JA = {"verified": "確認済", "inferred": "推定", "to_confirm": "要確認"}
_CONFIDENCE_EXTRA = {"confirmed": "verified", "assumed": "inferred", "unconfirmed": "to_confirm", "unknown": "to_confirm",
                     "to-confirm": "to_confirm", "toconfirm": "to_confirm"}
_conf_alias: dict[str, str] = {}


def confidence_label(lang: str, key: str) -> str:
    return t(lang, CONFIDENCE_LABELS[key]) if key in CONFIDENCE_LABELS else (key or "")


def normalize_confidence(value) -> str:
    """Key ("verified" / "inferred" / "to_confirm") for any accepted spelling, or "" when it is not recognized."""
    if not _conf_alias:
        for key in CONFIDENCE:
            _conf_alias[key] = key
            _conf_alias[key.replace("_", " ")] = key
            _conf_alias[CONFIDENCE_LABELS[key].lower()] = key
            _conf_alias[_CONFIDENCE_LEGACY_JA[key]] = key
            for lang in LANGS:
                _conf_alias[confidence_label(lang, key).strip().lower()] = key
        _conf_alias.update(_CONFIDENCE_EXTRA)
    return _conf_alias.get(str(value or "").strip().lower(), "")


# ---------------------------------------------------------------------------
# Crawler data: fixed phrases in pages.json / safety_report.json
# ---------------------------------------------------------------------------
# (canonical English form, legacy Japanese form). The crawler writes the English form; crawls made before the
# switch contain the Japanese one. More specific patterns come first. Placeholders a / b / i / n are numbers.
DATA_PHRASES: list[tuple[str, str]] = [
    # state labels
    ('Tab "{x}", continued ({a}–{b}px)', "タブ「{x}」の続き（{a}〜{b}px）"),
    ("Part {i}/{n} ({a}–{b}px)", "続き {i}/{n}（{a}〜{b}px）"),
    ('Tab "{x}"', "タブ「{x}」"),
    # state results
    ("In-page change", "画面内変化"),
    ("Continuation of a tall screen", "縦長の画面の続き"),
    ("Page navigation", "ページ遷移"),
    ("No change", "変化なし"),
    # reasons
    ("Blocked keyword: {x}", "禁止キーワード: {x}"),
    ("No label", "ラベル無し"),
    ("Not clicked (pages are opened by URL)", "未クリック（URL で開く方式）"),
    ("Out of scope", "スコープ外"),
    ("Excluded pattern: {x}", "除外パターン: {x}"),
    ("Risky URL keyword: {x}", "危険URLキーワード: {x}"),
    ("State-changing token in URL: {x}", "状態を変えるトークンが URL にある: {x}"),
    ("State-changing action: {x}", "状態を変える操作: {x}"),
    ("Duplicate of {x}", "{x} と重複"),
    # crawl method
    ("browser-use (opens pages by URL; clicks in-page tabs only)", "browser-use（URL で開く巡回・ページ内タブのみクリック）"),
    # written by the Playwright crawler (crawl.py)
    ("In-page change (expanded section, tab, menu and so on)", "画面内変化（展開/タブ/メニュー等）"),
    ("Modal/dialog shown", "モーダル/ダイアログ表示"),
    ("Element not found or hidden", "要素が見つからない/非表示"),
    ("Error: {x}", "エラー: {x}"),
    ("submit/reset element", "submit/reset 要素"),
    ("input element", "input 要素"),
    ("button without a type inside a form (= submit)", "form内のtype未指定button(=submit)"),
    ("does not match click-allow-pattern", "click-allow-pattern 不一致"),
    ("No label (purpose unclear)", "ラベルなし要素（用途不明）"),
]

_NUMERIC = {"a", "b", "i", "n"}


def _pattern(template: str) -> re.Pattern:
    parts = re.split(r"\{(\w+)\}", template)
    rx = ""
    for idx, part in enumerate(parts):
        rx += f"(?P<{part}>" + (r"\d+" if part in _NUMERIC else ".*?") + ")" if idx % 2 else re.escape(part)
    return re.compile(rx, re.S)


_DATA = [(en, ja, _pattern(en), _pattern(ja)) for en, ja in DATA_PHRASES]


def localize_data(lang: str, s):
    """Translate a fixed crawler phrase into `lang`. Anything that is not a known phrase is returned unchanged.

    A legacy Japanese form is first mapped to the canonical English form. For "ja" the result is exactly the
    legacy Japanese form, so books built from old Japanese crawls do not change."""
    if not s or not isinstance(s, str):
        return s
    for en, ja, rx_en, rx_ja in _DATA:
        m = rx_en.fullmatch(s) or rx_ja.fullmatch(s)
        if m:
            kw = m.groupdict()
            tpl = ja if lang == "ja" else t(lang, en)
            return tpl.format(**kw) if kw else tpl
    return s
