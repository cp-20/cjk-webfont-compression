#!/usr/bin/env python3
"""Fetch a small multilingual page corpus once per page, respecting robots.txt.

Saves raw HTML bytes + response headers, then extracts visible text
(script/style/nav/footer/header/aside/form/svg removed) and per-page stats.
Also derives an estimate of Google Fonts woff2 bytes needed for the page's
unique characters using the measured unicode-range slices.
"""
import hashlib
import json
import re
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw" / "pages"
RAW.mkdir(parents=True, exist_ok=True)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.8,zh-CN;q=0.6,ko;q=0.5",
})

PAGES = [
    # --- Japanese: encyclopedia / news / government / literature / tech / blog
    ("ja", "encyclopedia", "https://ja.wikipedia.org/wiki/%E6%97%A5%E6%9C%AC%E8%AA%9E"),
    ("ja", "encyclopedia", "https://ja.wikipedia.org/wiki/%E6%BC%A2%E5%AD%97"),
    ("ja", "encyclopedia", "https://ja.wikipedia.org/wiki/%E6%9D%B1%E4%BA%AC"),
    ("ja", "news", "https://www3.nhk.or.jp/news/"),
    ("ja", "news", "https://www.asahi.com/"),
    ("ja", "news", "https://www.yomiuri.co.jp/"),
    ("ja", "news", "https://www.sankei.com/"),
    ("ja", "news", "https://www.nikkei.com/"),
    ("ja", "news", "https://www.itmedia.co.jp/"),
    ("ja", "news", "https://www.gizmodo.jp/"),
    ("ja", "government", "https://www.kantei.go.jp/"),
    ("ja", "government", "https://www.soumu.go.jp/"),
    ("ja", "government", "https://www.bunka.go.jp/"),
    ("ja", "government", "https://www.ndl.go.jp/"),
    ("ja", "government", "https://www.jma.go.jp/jma/index.html"),
    ("ja", "government", "https://www.metro.tokyo.lg.jp/"),
    ("ja", "government", "https://www.u-tokyo.ac.jp/ja/index.html"),
    ("ja", "government", "https://www.kyoto-u.ac.jp/ja"),
    ("ja", "literature", "https://www.aozora.gr.jp/cards/000148/files/789_14547.html"),
    ("ja", "literature", "https://www.aozora.gr.jp/cards/000081/files/456_15050.html"),
    ("ja", "tech", "https://qiita.com/"),
    ("ja", "tech", "https://zenn.dev/"),
    ("ja", "tech", "https://developer.mozilla.org/ja/docs/Web/CSS/font-family"),
    ("ja", "tech-blog", "https://developers.cyberagent.co.jp/blog/"),
    ("ja", "tech-blog", "https://tech.smarthr.jp/"),
    ("ja", "tech-blog", "https://blog.recruit.co.jp/"),
    ("ja", "blog", "https://note.com/"),
    ("ja", "social-bookmark", "https://b.hatena.ne.jp/"),
    ("ja", "ecommerce", "https://jp.mercari.com/"),
    ("ja", "ecommerce", "https://www.rakuten.co.jp/"),
    ("ja", "portal", "https://www.yahoo.co.jp/"),
    # --- Chinese comparison
    ("zh", "encyclopedia", "https://zh.wikipedia.org/wiki/%E6%B1%89%E5%AD%97"),
    ("zh", "government", "https://www.gov.cn/"),
    ("zh", "news", "https://www.people.com.cn/"),
    ("zh", "news", "https://www.xinhuanet.com/"),
    ("zh", "tech", "https://www.csdn.net/"),
    ("zh", "tech", "https://developer.mozilla.org/zh-CN/docs/Web/CSS/font-family"),
    ("zh", "community", "https://www.douban.com/"),
    # --- Korean comparison
    ("ko", "encyclopedia", "https://ko.wikipedia.org/wiki/%ED%95%9C%EA%B5%AD%EC%96%B4"),
    ("ko", "news", "https://www.yna.co.kr/"),
    ("ko", "government", "https://www.korea.kr/"),
    ("ko", "news", "https://news.naver.com/"),
    ("ko", "portal", "https://www.daum.net/"),
    ("ko", "blog", "https://brunch.co.kr/"),
]

_robots = {}


def robots_allowed(url):
    p = urllib.parse.urlparse(url)
    host = f"{p.scheme}://{p.netloc}"
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(host + "/robots.txt")
        status = None
        try:
            r = S.get(host + "/robots.txt", timeout=15)
            status = r.status_code
            (RAW / "robots").mkdir(exist_ok=True)
            fn = re.sub(r"[^a-zA-Z0-9]+", "_", p.netloc)
            (RAW / "robots" / f"{fn}.txt").write_bytes(r.content)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            elif 400 <= r.status_code < 500:
                rp.allow_all = True
            else:
                rp.disallow_all = True
        except Exception:  # noqa: BLE001
            status = None
            rp.allow_all = True  # network failed; page fetch will decide
        _robots[host] = (rp, status)
    rp, status = _robots[host]
    return rp.can_fetch(UA, url), status


def norm_text(s):
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
    lines = []
    for line in s.split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def extract(html, url):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header",
                     "aside", "form", "svg", "iframe", "canvas", "template",
                     "dialog"]):
        tag.decompose()
    for el in soup.find_all(attrs={"role": re.compile(
            r"^(navigation|banner|contentinfo|search|menu|menubar)$", re.I)}):
        el.decompose()
    for el in soup.find_all(class_=re.compile(
            r"(^|[-_ ])(cookie|breadcrumb|sidebar|global-?nav|site-?footer|"
            r"site-?header|advert|adsbygoogle)($|[-_ ])", re.I)):
        el.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = norm_text(main.get_text("\n"))
    title = soup.title.get_text(strip=True) if soup.title else ""
    return title, text, soup


def block(cp):
    if 0x3040 <= cp <= 0x309F: return "hiragana"
    if 0x30A0 <= cp <= 0x30FF: return "katakana"
    if 0x4E00 <= cp <= 0x9FFF: return "kanji"
    if 0x3400 <= cp <= 0x4DBF: return "kanji_extA"
    if 0xAC00 <= cp <= 0xD7AF: return "hangul"
    if 0x3000 <= cp <= 0x303F: return "cjk_punct"
    if 0xFF00 <= cp <= 0xFFEF: return "fullwidth"
    if cp < 0x80: return "ascii"
    if 0x2000 <= cp <= 0x206F: return "punct"
    return "other"


def main():
    slices = json.loads((BASE / "google_slices.json").read_text())
    fam_map = {
        "ja": "Noto Sans JP", "zh": "Noto Sans SC", "ko": "Noto Sans KR",
    }
    # cp -> [(slice index, bytes)] per family
    cover = {}
    for fam in {fam_map[k] for k in fam_map}:
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

    out = []
    for i, (lang, genre, url) in enumerate(PAGES):
        allowed, rob_status = robots_allowed(url)
        rec = {"lang": lang, "genre": genre, "url": url,
               "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "robots_txt_status": rob_status, "robots_allowed": allowed}
        if not allowed:
            rec["error"] = "disallowed by robots.txt"
            out.append(rec)
            print(f"SKIP robots: {url}")
            continue
        try:
            r = S.get(url, timeout=35, allow_redirects=True)
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)[:300]
            out.append(rec)
            print(f"FAIL {url}: {e}")
            continue
        rec.update({
            "status": r.status_code, "final_url": r.url,
            "response_headers": dict(r.headers),
            "html_bytes": len(r.content),
            "sha256": hashlib.sha256(r.content).hexdigest(),
        })
        slug = f"{i:02d}_{lang}_" + re.sub(r"[^a-z0-9]+", "_",
                                            urllib.parse.urlparse(url).netloc.lower()).strip("_")
        (RAW / f"{slug}.html").write_bytes(r.content)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", "").lower():
            rec["error"] = f"status={r.status_code} type={r.headers.get('content-type')}"
            out.append(rec)
            print(f"BAD {url}: {rec['error']}")
            continue
        try:
            title, text, soup = extract(r.content, url)
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"parse: {e!r}"
            out.append(rec)
            print(f"PARSEFAIL {url}: {e}")
            continue

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
            "text": kept,
        })

        fam = fam_map[lang]
        cmap = cover[fam]
        used = {ord(c) for c in utext}
        covered = used & cmap.keys()
        needed = {}
        for cp in covered:
            for idx, size in cmap[cp]:
                needed[idx] = size
        rec["gf_estimate"] = {
            "family": fam,
            "weight": 400,
            "chars_covered": len(covered),
            "chars_uncovered": len(used) - len(covered),
            "coverage_pct": round(100 * len(covered) / max(1, len(used)), 2),
            "slices_used": len(needed),
            "bytes_used": sum(needed.values()),
            "total_family_bytes": next(f["total_bytes"] for f in slices["families"]
                                       if f["family"] == fam),
        }
        out.append(rec)
        print(f"{i:02d} {lang} {genre:16s} {len(kept):7d}ch uniq={len(utext):4d} "
              f"gf~{sum(needed.values())/1024:7.1f}KiB ({len(needed):3d} slices) {url}")
        time.sleep(0.8)

    (BASE / "corpus.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nSaved {len(out)} records to corpus.json")


if __name__ == "__main__":
    main()
