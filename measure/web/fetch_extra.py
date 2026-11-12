#!/usr/bin/env python3
"""Fetch additional Korean pages, append to corpus.json, then recompute stats
for every record using the saved text (char_count = non-whitespace chars)."""
import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path

from fetch_corpus import BASE, RAW, S, UA, robots_allowed, extract, block

EXTRA = [
    ("ko", "encyclopedia", "https://ko.wikipedia.org/wiki/%ED%95%9C%EA%B8%80"),
    ("ko", "news", "https://www.hani.co.kr/"),
    ("ko", "news", "https://www.chosun.com/"),
    ("ko", "news", "https://www.joongang.co.kr/"),
    ("ko", "news", "https://www.etnews.com/"),
]


def stats(text):
    ns = sum(1 for c in text if not c.isspace())
    utext = sorted({c for c in text if not c.isspace()})
    counts = {}
    for c in utext:
        counts[block(ord(c))] = counts.get(block(ord(c)), 0) + 1
    return ns, utext, counts


def main():
    data = json.loads((BASE / "corpus.json").read_text())
    start = len(data)
    for j, (lang, genre, url) in enumerate(EXTRA):
        allowed, rob = robots_allowed(url)
        rec = {"lang": lang, "genre": genre, "url": url,
               "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "robots_txt_status": rob, "robots_allowed": allowed}
        if not allowed:
            rec["error"] = "disallowed by robots.txt"
            data.append(rec)
            continue
        try:
            r = S.get(url, timeout=35, allow_redirects=True)
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)[:300]
            data.append(rec)
            continue
        rec.update({"status": r.status_code, "final_url": r.url,
                    "response_headers": dict(r.headers),
                    "html_bytes": len(r.content),
                    "sha256": hashlib.sha256(r.content).hexdigest()})
        slug = f"{start+j:02d}_{lang}_" + re.sub(
            r"[^a-z0-9]+", "_", urllib.parse.urlparse(url).netloc.lower()).strip("_")
        (RAW / f"{slug}.html").write_bytes(r.content)
        if r.status_code != 200:
            rec["error"] = f"status={r.status_code}"
            data.append(rec)
            continue
        title, text, _ = extract(r.content, url)
        kept = text[:100_000]
        rec.update({"title": title, "text": kept, "truncated": len(text) > 100_000})
        data.append(rec)
        print(f"{start+j:02d} {lang} {genre:14s} {len(kept):7d} raw {url}")
        time.sleep(0.8)

    # Recompute stats from saved text for all records.
    for rec in data:
        if "text" not in rec:
            continue
        ns, utext, counts = stats(rec["text"])
        rec["char_count"] = ns
        rec["raw_text_length"] = len(rec["text"])
        rec["unique_char_count"] = len(utext)
        rec["unique_chars"] = "".join(utext)
        rec["block_unique_counts"] = counts
        rec["usable_text"] = ns >= 300

    (BASE / "corpus.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"total records={len(data)} usable_ja={sum(1 for r in data if r.get('lang')=='ja' and r.get('usable_text'))} "
          f"usable_zh={sum(1 for r in data if r.get('lang')=='zh' and r.get('usable_text'))} "
          f"usable_ko={sum(1 for r in data if r.get('lang')=='ko' and r.get('usable_text'))}")


if __name__ == "__main__":
    main()
