#!/usr/bin/env python3
"""Round 4, item 2a: which font weights do real pages actually render?

Round 3 priced every weight of Noto Sans JP (instance-then-GLC, "Arm A").
This script measures the demand side: for every usable corpus page it
re-fetches the HTML (robots.txt respected, nothing stored) and estimates,
for each visible character, the font weight it would render at.

The weight estimate is a deliberately simple model of the CSS cascade,
documented here so the numbers are read as approximations:
  * UA defaults: b/strong/h1-h6/th render bold (700); everything else
    inherits, root default 400.
  * <style> rules: only rules whose selector is a comma list of compound
    selectors (tag, .class, #id, tag.class) are honoured; for descendant
    selectors only the rightmost compound is used, except that a bare tag
    from a chain (".infobox div") is dropped -- honouring it page-wide
    measurably wrecks the estimate. Specificity:
    inline style > #id > .class > tag; later rules win ties.
  * font-weight values: normal=400, bold=700, numeric as-is (rounded to
    the nearest 100, clamped 100-900); bolder/lighter shift the inherited
    weight by +-200 (a simplification of the spec table).
  * Text scope matches fetch_corpus.py exactly (script/style/nav/footer/
    header/form etc. removed or skipped), so usage shares line up with
    the character sets the delivery studies subset.

Output: measure/out/weight_usage.json
Usage:  .venv/bin/python measure/weight_usage.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "web"))
from fetch_corpus import S, robots_allowed  # noqa: E402

# Text scope mirrors fetch_corpus.extract() exactly.
DECOMP = ["script", "style", "noscript", "nav", "footer", "header", "aside",
          "form", "svg", "iframe", "canvas", "template", "dialog"]
ROLE_RE = re.compile(r"^(navigation|banner|contentinfo|search|menu|menubar)$",
                     re.I)
CLASS_RE = re.compile(
    r"(^|[-_ ])(cookie|breadcrumb|sidebar|global-?nav|site-?footer|"
    r"site-?header|advert|adsbygoogle)($|[-_ ])", re.I)

STATS = HERE / "web" / "corpus_stats.json"
OUT = HERE / "out" / "weight_usage.json"

BOLD_TAGS = {"b", "strong", "h1", "h2", "h3", "h4", "h5", "h6", "th"}
FW_RE = re.compile(r"font-weight\s*:\s*([a-zA-Z0-9]+)")


def parse_weight_value(v: str, inherited: int) -> int | None:
    v = v.strip().lower()
    if v == "normal":
        return 400
    if v == "bold":
        return 700
    if v == "bolder":
        return min(900, inherited + 200)
    if v == "lighter":
        return max(100, inherited - 200)
    if v in ("inherit", "initial", "unset"):
        return inherited
    if v.isdigit():
        w = int(v)
        return max(100, min(900, round(w / 100) * 100))
    return None


def parse_style_rules(soup) -> list[tuple[int, str, str, int]]:
    """Return (specificity, kind, key, weight) in document order.
    kind: 'tag' | 'class' | 'id' | 'tagclass'. Only font-weight is kept,
    and only from rules with simple selectors (documented approximation);
    the declared value is stored raw and resolved against inheritance at
    match time via a second pass marker -- here we keep the keyword."""
    rules = []
    for style in soup.find_all("style"):
        css = style.get_text()
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
            sel, body = m.group(1), m.group(2)
            fw = FW_RE.search(body)
            if not fw:
                continue
            raw = fw.group(1)
            for one in sel.split(","):
                one = one.strip()
                # rightmost compound of a descendant/child selector chain;
                # a *bare tag* taken from a chain (e.g. ".infobox div")
                # would apply page-wide and wreck the estimate, so chained
                # selectors only contribute class/id/tag.class compounds.
                parts = [p for p in re.split(r"[\s>+~]+", one) if p]
                chained = len(parts) > 1
                one = parts[-1] if parts else ""
                one = one.split(":")[0]  # drop pseudo-classes
                if not one or one == "*":
                    continue
                if chained and re.fullmatch(r"[a-zA-Z][\w-]*", one):
                    continue
                mid = re.fullmatch(r"([a-zA-Z][\w-]*)?([.#])([\w-]+)", one)
                if one.startswith("#"):
                    rules.append((3, "id", one[1:], raw))
                elif mid and mid.group(2) == "#":
                    rules.append((3, "id", mid.group(3), raw))
                elif mid and mid.group(2) == "." and mid.group(1):
                    rules.append((2, "tagclass",
                                  f"{mid.group(1).lower()}.{mid.group(3)}", raw))
                elif one.startswith("."):
                    rules.append((2, "class", one[1:], raw))
                elif re.fullmatch(r"[a-zA-Z][\w-]*", one):
                    rules.append((1, "tag", one.lower(), raw))
    return rules


def rule_weight(el, rules, inherited: int) -> int:
    """Best-matching stylesheet weight for an element, else inherited."""
    best = None  # (specificity, order, raw)
    classes = set(el.get("class") or [])
    for i, (spec, kind, key, raw) in enumerate(rules):
        ok = False
        if kind == "tag":
            ok = el.name == key
        elif kind == "class":
            ok = key in classes
        elif kind == "id":
            ok = el.get("id") == key
        elif kind == "tagclass":
            tag, cls = key.split(".", 1)
            ok = el.name == tag and cls in classes
        if ok and (best is None or (spec, i) >= (best[0], best[1])):
            best = (spec, i, raw)
    if best is not None:
        w = parse_weight_value(best[2], inherited)
        if w is not None:
            return w
    return inherited


def element_weight(el, rules, inherited: int) -> int:
    w = inherited
    if el.name in BOLD_TAGS:
        w = 700
    w = rule_weight(el, rules, w)
    style = el.get("style") or ""
    fw = FW_RE.search(style)
    if fw:
        v = parse_weight_value(fw.group(1), w)
        if v is not None:
            w = v
    return w


def page_weights(html: bytes, url: str) -> Counter:
    soup = BeautifulSoup(html, "html.parser")
    rules = parse_style_rules(soup)  # before <style> is decomposed away
    for t in soup(DECOMP):
        t.decompose()
    for el in soup.find_all(attrs={"role": ROLE_RE}):
        el.decompose()
    for el in soup.find_all(class_=CLASS_RE):
        el.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    counts: Counter = Counter()
    # iterative walk carrying the inherited weight
    stack = [(root, 400)]
    while stack:
        el, inherited = stack.pop()
        w = element_weight(el, rules, inherited) if getattr(el, "name", None) else inherited
        for child in el.children:
            if isinstance(child, str):
                n = sum(1 for c in child if not c.isspace())
                if n:
                    counts[w] += n
            elif getattr(child, "name", None):
                stack.append((child, w))
    return counts


PARTIAL = HERE / "out" / "weight_usage_partial.json"


def main() -> int:
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    pages = [r for r in stats if r.get("unique_chars") and r.get("gf_estimate")]
    # Resumable: per-page results are cached, so an interrupted run can be
    # re-run and only fetches the pages it has not measured yet.
    cache: dict[str, dict] = {}
    if PARTIAL.exists():
        cache = {p["url"]: p for p in
                 json.loads(PARTIAL.read_text(encoding="utf-8"))}
    for rec in pages:
        url = rec["url"]
        if url in cache:
            continue
        allowed, _ = robots_allowed(url)
        if not allowed:
            print(f"SKIP robots {url}")
            continue
        try:
            r = S.get(url, timeout=30)
            if r.status_code != 200:
                print(f"SKIP status={r.status_code} {url}")
                continue
            counts = page_weights(r.content, url)
        except Exception as e:  # noqa: BLE001
            print(f"SKIP error {url}: {e!r}"[:140])
            continue
        total = sum(counts.values())
        cache[url] = {
            "url": url, "lang": rec["lang"], "genre": rec.get("genre"),
            "chars_by_weight": {str(k): v for k, v in sorted(counts.items())},
            "total_chars": total,
        }
        PARTIAL.parent.mkdir(exist_ok=True)
        PARTIAL.write_text(json.dumps(list(cache.values()),
                                      ensure_ascii=False),
                           encoding="utf-8")
        top = counts.most_common(3)
        print(f"{rec['lang']} total={total:6d} top={top} {url[:60]}")
        time.sleep(0.4)
    per_page = [cache[r["url"]] for r in pages if r["url"] in cache]

    def aggregate(rows):
        tot: Counter = Counter()
        for p in rows:
            tot.update({int(k): v for k, v in p["chars_by_weight"].items()})
        grand = sum(tot.values()) or 1
        return {"chars_by_weight": {str(k): tot[k] for k in sorted(tot)},
                "total_chars": sum(tot.values()),
                "share_pct": {str(k): round(100 * tot[k] / grand, 2)
                              for k in sorted(tot)}}

    out = {
        "provenance": {
            "method": "simple-cascade approximation; see module docstring",
            "pages_measured": len(per_page),
            "pages_in_corpus": len(pages),
            "pages_skipped": [r["url"] for r in pages
                              if r["url"] not in cache],
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "overall": aggregate(per_page),
        "by_lang": {lang: aggregate([p for p in per_page if p["lang"] == lang])
                    for lang in ("ja", "zh", "ko")},
        "pages": per_page,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out["overall"], ensure_ascii=False))
    for lang in ("ja", "zh", "ko"):
        print(lang, json.dumps(out["by_lang"][lang]["share_pct"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
