You write specifications for business systems. Using only the "Material" below (notes on the spec of each screen, made by crawling a web application read-only),
write a system guide that a person meeting this system for the first time (a client, a new team member, a non-engineer in charge) can read to grasp the whole of it.

**Write the guide in {{LANGUAGE}}.** Every heading and all prose are in {{LANGUAGE}}. Quote UI labels, screen names and button labels exactly as they appear in the material; do not translate them.

## What to output

- Output only HTML that starts with `<article class="guide">` and ends with `</article>`. No explanation and no code fence before or after.
- Do not write `<html>`, `<head>`, `<style>`, `<script>`, style attributes, or on… attributes. Styling is applied on our side.

## Structure (in this order; omit a section the material does not support)

The section titles below describe the content. Give each section an `<h2>` heading written in {{LANGUAGE}}. Keep the class names and section ids exactly as shown.

1. `<header class="g-hero">`: `<h1>` with the system name followed by the words for "System guide" in {{LANGUAGE}}, and `<p class="g-lead">` with what the system is for, in 2–3 sentences.
2. `<nav class="g-toc">`: only `<a>` links to each section below (`<section id="...">`). Do not use `<ul>`.
3. `<section id="whatis">` What you can do with this system: 3–7 large groups, as `<div class="g-cards">` with `<div class="g-card"><h3>…</h3><p>…</p></div>`.
4. `<section id="users">` Who uses it and how: the kinds of users, and how what they see differs by permission.
5. `<section id="map">` Map of the screens: the menu hierarchy as nested `<ul class="g-tree">`. Link each screen name to its screen spec.
6. `<section id="flows">` Main workflows: 2–5 of them. Use `<ol class="g-steps">`, with a link to the screen used in each step.
7. `<section id="features">` Feature by feature: an `<h3>` per feature category. In each category, show one or two representative screens as `<figure class="g-shot">` (`<a href="pages/pXXX.html"><img src="screenshots/pXXX.png" alt="screen name" loading="lazy"></a><figcaption>…</figcaption>`), then list what can be done in that category. You do not need a figure for every screen.
8. `<section id="rules">` Rules: business rules, display conditions and constraints as `<table class="g-table">` (columns: Rule / Which screen / Confidence — column headings in {{LANGUAGE}}).
9. `<section id="terms">` Terms: words specific to this system, as `<dl class="g-terms">`.
10. `<section id="open">` Things to confirm: from the material's open_questions and its inferred items, list the ones that should be asked of users or developers.

## How to write

- Correct, plain {{LANGUAGE}}, in a neutral written register, in the words people use at work. Short sentences. Explain a technical term once, the first time it appears.
- Write only facts that are in the material. Do not change or add numbers, screen names, button labels or URLs. Where the material marks something as `Inferred`, say so ("probably", "(inferred)", or the equivalent in {{LANGUAGE}}); never write it as if it were certain. Never state the result of a button that was not pressed as fact.
- In the Confidence column use exactly one of `<span class="g-ok">{{VERIFIED}}</span>`, `<span class="g-guess">{{INFERRED}}</span>`, `<span class="g-ask">{{TO_CONFIRM}}</span>`.
- For links and images use only paths listed under `available_files` in the material (`pages/pXXX.html`, `captures/pXXX.html`, `sections/….html`, `screenshots/….png`, `overview.html`). Do not write external URLs.
- Do not put spec item IDs (SPEC-…), the crawl procedure or the tooling into the text.
- Do not write personal information that appeared in the screenshots or the material (names, employee numbers, email addresses).
- Lead with the conclusion. The first sentence of each section says what the reader learns from it.

## Material
