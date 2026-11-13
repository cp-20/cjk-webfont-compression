#!/usr/bin/env python3
"""Round 4: extend the corpus for Korean (priority) and Chinese.

Round 3's cross-script claims rested on zh 7 usable pages / ko 4 usable
pages. This script fetches additional real pages with the *same*
methodology as fetch_corpus.py (robots.txt respected, visible text only,
Google Fonts estimate from the committed google_slices.json) and merges
stats-format records (no page text -- text_omitted, as in the committed
file) into corpus_stats.json.

Merge rules:
  * URL already recorded with a character set -> kept as-is (not refetched;
    the corpus is a fixed sample, not a live mirror).
  * URL recorded as an error (news.naver.com, www.daum.net) -> retried
    once; the record is replaced only if the retry yields a character set.
  * New URL -> appended, whether the fetch succeeds or fails (failures are
    recorded as error records, exactly like the existing naver/daum rows).

Usage: .venv/bin/python measure/web/fetch_corpus_r4.py
Writes: measure/web/corpus_stats.json (merged), and prints a summary.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from fetch_corpus import BASE, S, block, extract, robots_allowed

STATS_PATH = BASE / "corpus_stats.json"

CANDIDATES = [
    # --- Korean additions (round 3 usable: 4)
    ("ko", "encyclopedia", "https://ko.wikipedia.org/wiki/%ED%95%9C%EA%B8%80"),
    ("ko", "encyclopedia", "https://ko.wikipedia.org/wiki/%EC%84%9C%EC%9A%B8"),
    ("ko", "encyclopedia", "https://namu.wiki/w/%ED%95%9C%EA%B5%AD"),
    ("ko", "news", "https://www.hani.co.kr/"),
    ("ko", "news", "https://www.chosun.com/"),
    ("ko", "news", "https://www.joongang.co.kr/"),
    ("ko", "news", "https://www.etnews.com/"),
    ("ko", "news", "https://www.khan.co.kr/"),
    ("ko", "news", "https://www.hankyung.com/"),
    ("ko", "news", "https://www.donga.com/"),
    ("ko", "news", "https://www.ohmynews.com/"),
    ("ko", "government", "https://www.seoul.go.kr/"),
    ("ko", "government", "https://www.mois.go.kr/"),
    ("ko", "tech", "https://velog.io/"),
    ("ko", "tech-blog", "https://tech.kakao.com/blog/"),
    ("ko", "community", "https://www.clien.net/service/"),
    # --- Chinese additions (round 3 usable: 7)
    ("zh", "encyclopedia", "https://zh.wikipedia.org/wiki/%E4%B8%AD%E6%96%87"),
    ("zh", "encyclopedia", "https://zh.wikipedia.org/wiki/%E5%8C%97%E4%BA%AC"),
    ("zh", "news", "https://www.zaobao.com/"),
    ("zh", "news", "https://www.thepaper.cn/"),
    ("zh", "news", "https://www.jiemian.com/"),
    ("zh", "tech", "https://www.cnblogs.com/"),
    ("zh", "tech", "https://juejin.cn/"),
    ("zh", "blog", "https://www.jianshu.com/"),
    ("zh", "community", "https://www.v2ex.com/"),
    ("zh", "tech", "https://segmentfault.com/"),
]

# Error records in the committed corpus get one retry each.
RETRIES = [
    ("ko", "news", "https://news.naver.com/"),
    ("ko", "portal", "https://www.daum.net/"),
]

FAM_MAP = {"ja": "Noto Sans JP", "zh": "Noto Sans SC", "ko": "Noto Sans KR"}


def build_cover():
    slices = json.loads((BASE / "google_slices.json").read_text())
    cover = {}
    for fam in set(FAM_MAP.values()):
        d = {}
        for f in slices["slices"]:
            if f["family_label"] != fam or not f.get("content_length"):
                continue
            rs = []
            for part in (f["unicode_range"] or "").split(","):
                part = part.strip().upper().replace("U+", "")
                if not part:
                    continue
                if "-" in part:
                    a, b = part.split("-", 1)
                    rs.append((int(a, 16), int(b, 16)))
                else:
                    rs.append((int(part, 16), int(part, 16)))
            for a, b in rs:
                for cp in range(a, b + 1):
                    d.setdefault(cp, []).append((f["index"], f["content_length"]))
        cover[fam] = d
    totals = {f["family"]: f["total_bytes"] for f in slices["families"]}
    return cover, totals


def fetch_one(lang, genre, url, cover, totals):
    allowed, rob_status = robots_allowed(url)
    rec = {"lang": lang, "genre": genre, "url": url,
           "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "robots_txt_status": rob_status, "robots_allowed": allowed}
    if not allowed:
        rec["error"] = "disallowed by robots.txt"
        return rec
    r = None
    last_err = None
    for attempt in range(2):
        try:
            r = S.get(url, timeout=45, allow_redirects=True)
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2)
    if r is None:
        rec["error"] = repr(last_err)[:300]
        return rec
    rec.update({
        "status": r.status_code, "final_url": r.url,
        "response_headers": dict(r.headers),
        "html_bytes": len(r.content),
        "sha256": hashlib.sha256(r.content).hexdigest(),
    })
    if r.status_code != 200 or "html" not in r.headers.get("content-type", "").lower():
        rec["error"] = f"status={r.status_code} type={r.headers.get('content-type')}"
        return rec
    try:
        title, text, _soup = extract(r.content, url)
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"parse: {e!r}"
        return rec
    truncated = len(text) > 100_000
    kept = text[:100_000]
    utext = sorted({c for c in kept if not c.isspace()})
    counts = {}
    for c in utext:
        counts[block(ord(c))] = counts.get(block(ord(c)), 0) + 1
    rec.update({
        "title": title, "char_count": len(kept),
        "char_count_nonspace": sum(1 for c in kept if not c.isspace()),
        "unique_char_count": len(utext), "unique_chars": "".join(utext),
        "block_unique_counts": counts, "truncated": truncated,
    })
    fam = FAM_MAP[lang]
    cmap = cover[fam]
    used = {ord(c) for c in utext}
    covered = used & cmap.keys()
    needed = {}
    for cp in covered:
        for idx, size in cmap[cp]:
            needed[idx] = size
    rec["gf_estimate"] = {
        "family": fam, "weight": 400,
        "chars_covered": len(covered),
        "chars_uncovered": len(used) - len(covered),
        "coverage_pct": round(100 * len(covered) / max(1, len(used)), 2),
        "slices_used": len(needed),
        "bytes_used": sum(needed.values()),
        "total_family_bytes": totals[fam],
    }
    rec["text_omitted"] = True
    rec["text_chars"] = len(kept)
    return rec


def main() -> int:
    stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    by_url = {r["url"]: i for i, r in enumerate(stats)}
    cover, totals = build_cover()

    def usable(rec):
        return bool(rec.get("unique_chars")) and bool(rec.get("gf_estimate"))

    added, replaced, failed = [], [], []
    queue = [(c, False) for c in CANDIDATES] + [(c, True) for c in RETRIES]
    for (lang, genre, url), is_retry in queue:
        if url in by_url and usable(stats[by_url[url]]):
            print(f"KEEP (already recorded) {url}")
            continue
        rec = fetch_one(lang, genre, url, cover, totals)
        if usable(rec):
            if url in by_url:
                stats[by_url[url]] = rec
                replaced.append(url)
                print(f"REPLACED error record: {url} uniq={rec['unique_char_count']}")
            else:
                stats.append(rec)
                added.append(url)
                print(f"ADDED {lang} {genre:12s} uniq={rec['unique_char_count']:4d} "
                      f"gf~{rec['gf_estimate']['bytes_used']/1024:7.1f}KiB {url}")
        else:
            failed.append((url, rec.get("error", "?")[:120]))
            if url not in by_url:
                rec["text_omitted"] = True
                rec["text_chars"] = 0
                stats.append(rec)
                print(f"ADDED (error record) {url}: {rec.get('error')}")
            else:
                print(f"RETRY FAILED, keeping old record {url}: {rec.get('error')}")
        time.sleep(0.8)

    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    for lang in ("ja", "zh", "ko"):
        n_all = sum(1 for r in stats if r.get("lang") == lang)
        n_use = sum(1 for r in stats if r.get("lang") == lang and usable(r))
        print(f"{lang}: records={n_all} usable={n_use}")
    print(f"added={len(added)} replaced={len(replaced)} failed={len(failed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
