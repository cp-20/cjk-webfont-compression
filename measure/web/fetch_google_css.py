#!/usr/bin/env python3
"""Fetch Google Fonts CSS2 for CJK families and measure woff2 slices.

Raw CSS is saved verbatim. Slice sizes come from HEAD (with ranged GET
fallback) against the woff2 URLs; no size is inferred from CSS text.
"""
import csv
import json
import re
import statistics
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw" / "google_css"
RAW.mkdir(parents=True, exist_ok=True)

# A recent desktop Chrome UA: needed for Google Fonts to emit unicode-range
# sliced woff2 rather than legacy full TTF.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

FAMILIES = [
    # label, css2 family query
    ("Noto Sans JP", "Noto+Sans+JP:wght@400"),
    ("Noto Serif JP", "Noto+Serif+JP:wght@400"),
    ("M PLUS 1p", "M+PLUS+1p:wght@400"),
    ("Zen Kaku Gothic New", "Zen+Kaku+Gothic+New:wght@400"),
    ("Noto Sans SC", "Noto+Sans+SC:wght@400"),
    ("Noto Sans KR", "Noto+Sans+KR:wght@400"),
]

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "text/css,*/*;q=0.1"})


def fetch_css(query, slug, attempts=3):
    url = f"https://fonts.googleapis.com/css2?family={query}&display=swap"
    last = None
    for i in range(attempts):
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200:
                (RAW / f"{slug}.css").write_bytes(r.content)
                return url, r.text
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = repr(e)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"CSS fetch failed for {query}: {last}")


def head_size(url, attempts=3):
    """Return (status, final_url, content_length, method)."""
    last = None
    for i in range(attempts):
        try:
            r = S.head(url, timeout=40, allow_redirects=True)
            cl = r.headers.get("content-length")
            if r.status_code == 200 and cl is not None:
                return r.status_code, r.url, int(cl), "HEAD"
            last = r
            if r.status_code == 200 and cl is None:
                break
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(1.0 * (i + 1))
    # Ranged GET fallback for servers that omit content-length on HEAD.
    for i in range(attempts):
        try:
            r = S.get(url, timeout=40, allow_redirects=True,
                      headers={"Range": "bytes=0-0"})
            if r.status_code in (200, 206):
                cr = r.headers.get("content-range")
                if cr and "/" in cr:
                    return r.status_code, r.url, int(cr.rsplit("/", 1)[1]), "GET-range"
                if r.headers.get("content-length") and r.status_code == 200:
                    return r.status_code, r.url, int(r.headers["content-length"]), "GET"
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"size probe failed for {url}: {last}")


FACE_RE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)


def parse_faces(css):
    faces = []
    for m in FACE_RE.finditer(css):
        body = m.group(1)
        # Nearest preceding comment is Google's subset label (e.g. /* japanese */)
        before = css[: m.start()]
        cm = None
        for cm in re.finditer(r"/\*\s*([^*]+?)\s*\*/", before):
            pass
        subset = cm.group(1).strip() if cm else None

        def prop(name):
            pm = re.search(rf"{name}\s*:\s*([^;]+);", body)
            return pm.group(1).strip() if pm else None

        src = prop("src") or ""
        um = re.search(r"url\((https://[^)]+?\.woff2)\)", src)
        faces.append({
            "subset_comment": subset,
            "family": prop("font-family"),
            "style": prop("font-style"),
            "weight": prop("font-weight"),
            "unicode_range": prop("unicode-range"),
            "woff2_url": um.group(1) if um else None,
        })
    return faces


def parse_range_list(s):
    out = []
    if not s:
        return out
    for part in s.split(","):
        part = part.strip().upper().replace("U+", "")
        if "-" in part:
            a, b = part.split("-", 1)
            out.append((int(a, 16), int(b, 16)))
        else:
            out.append((int(part, 16), int(part, 16)))
    return out


def range_stats(ranges):
    if not ranges:
        return {"range_count": 0, "contiguous": False, "codepoints": 0, "span": 0, "gaps": 0}
    rs = sorted(ranges)
    merged = [list(rs[0])]
    for a, b in rs[1:]:
        if a <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    codepoints = sum(b - a + 1 for a, b in rs)
    span = max(b for _, b in rs) - min(a for a, _ in rs) + 1
    return {
        "range_count": len(rs),
        "contiguous": len(merged) == 1,
        "codepoints": codepoints,
        "span": span,
        "gaps": len(merged) - 1,
    }


def block_name(cp):
    if 0x3040 <= cp <= 0x309F:
        return "Hiragana"
    if 0x30A0 <= cp <= 0x30FF:
        return "Katakana"
    if 0x4E00 <= cp <= 0x9FFF:
        return "CJK Unified"
    if 0x3400 <= cp <= 0x4DBF:
        return "CJK Ext A"
    if 0xAC00 <= cp <= 0xD7AF:
        return "Hangul Syllables"
    if 0x1100 <= cp <= 0x11FF:
        return "Hangul Jamo"
    if 0x3000 <= cp <= 0x303F:
        return "CJK Symbols/Punct"
    if 0xFF00 <= cp <= 0xFFEF:
        return "Halfwidth/Fullwidth Forms"
    if 0x2000 <= cp <= 0x206F:
        return "General Punctuation"
    if 0x0000 <= cp <= 0x007F:
        return "Basic Latin"
    if 0x0080 <= cp <= 0x024F:
        return "Latin Supp/Ext"
    if 0x0370 <= cp <= 0x03FF:
        return "Greek"
    if 0x0400 <= cp <= 0x04FF:
        return "Cyrillic"
    if 0x2460 <= cp <= 0x24FF:
        return "Enclosed Alphanumerics"
    if 0x25A0 <= cp <= 0x25FF:
        return "Geometric Shapes"
    if 0x2600 <= cp <= 0x26FF:
        return "Misc Symbols"
    if 0x1F000 <= cp <= 0x1FAFF:
        return "Emoji/Supplemental"
    if 0xFE30 <= cp <= 0xFE4F:
        return "CJK Compat Forms"
    if 0xFE10 <= cp <= 0xFE1F:
        return "Vertical Forms"
    if 0x31F0 <= cp <= 0x31FF:
        return "Katakana Phonetic Ext"
    if 0x3200 <= cp <= 0x32FF:
        return "Enclosed CJK"
    if 0x3300 <= cp <= 0x33FF:
        return "CJK Compat"
    if 0xF900 <= cp <= 0xFAFF:
        return "CJK Compat Ideographs"
    if 0xFF61 <= cp <= 0xFF9F:
        return "Halfwidth Katakana"
    return "Other"


def main():
    all_faces = []
    family_summaries = []
    meta = {
        "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user_agent": UA,
        "css_endpoint": "https://fonts.googleapis.com/css2?family=<family>&display=swap",
    }

    for label, query in FAMILIES:
        slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        css_url, css = fetch_css(query, slug)
        faces = parse_faces(css)
        print(f"{label}: {len(faces)} faces from {css_url}")
        for idx, f in enumerate(faces):
            f["family_label"] = label
            f["index"] = idx
            f["css_url"] = css_url
            if not f["woff2_url"]:
                f["status"] = None
                f["content_length"] = None
                f["size_method"] = None
                f["final_url"] = None
                continue
            st, final, size, method = head_size(f["woff2_url"])
            f["status"] = st
            f["final_url"] = final
            f["content_length"] = size
            f["size_method"] = method
            rs = range_stats(parse_range_list(f["unicode_range"]))
            f.update(rs)
            f["blocks"] = sorted({block_name(a) for a, _ in parse_range_list(f["unicode_range"])})
            all_faces.append(f)
            print(f"  [{idx:02d}] {f['subset_comment'] or '?':>18} "
                  f"{f['weight']}/{f['style']} ranges={rs['range_count']} "
                  f"cps={rs['codepoints']:6d} {size/1024:8.1f} KiB")
            time.sleep(0.08)

        fam_faces = [f for f in all_faces if f["family_label"] == label]
        sizes = [f["content_length"] for f in fam_faces if f["content_length"]]
        rcounts = [f["range_count"] for f in fam_faces if f.get("range_count")]
        contiguous = sum(1 for f in fam_faces if f.get("contiguous"))
        cp_total = sum(f.get("codepoints", 0) for f in fam_faces)
        # union of codepoints across slices (overlaps counted once)
        cps = set()
        for f in fam_faces:
            for a, b in parse_range_list(f["unicode_range"]):
                cps.update(range(a, b + 1))
        family_summaries.append({
            "family": label,
            "css_url": css_url,
            "slices": len(fam_faces),
            "total_bytes": sum(sizes),
            "min_bytes": min(sizes),
            "median_bytes": statistics.median(sizes),
            "p90_bytes": statistics.quantiles(sizes, n=10)[8] if len(sizes) >= 10 else max(sizes),
            "max_bytes": max(sizes),
            "mean_bytes": round(statistics.mean(sizes), 1),
            "ranges_per_slice_min": min(rcounts),
            "ranges_per_slice_median": statistics.median(rcounts),
            "ranges_per_slice_max": max(rcounts),
            "slices_with_contiguous_range": contiguous,
            "sum_codepoints_across_slices": cp_total,
            "union_codepoints": len(cps),
            "overlap_codepoints": cp_total - len(cps),
        })

    out = {"meta": meta, "families": family_summaries, "slices": all_faces}
    (BASE / "google_slices.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))

    fields = ["family_label", "index", "subset_comment", "style", "weight",
              "unicode_range", "range_count", "contiguous", "codepoints", "span",
              "blocks", "content_length", "status", "size_method", "woff2_url"]
    with (BASE / "google_slices.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for f in all_faces:
            row = dict(f)
            row["blocks"] = ";".join(f.get("blocks") or [])
            w.writerow(row)

    print("\n=== FAMILY SUMMARY ===")
    for s in family_summaries:
        print(f"{s['family']:22s} slices={s['slices']:3d} total={s['total_bytes']/1024:8.1f} KiB "
              f"med={s['median_bytes']/1024:6.1f} p90={s['p90_bytes']/1024:6.1f} "
              f"max={s['max_bytes']/1024:6.1f} KiB ranges={s['ranges_per_slice_min']}-"
              f"{s['ranges_per_slice_max']} contig={s['slices_with_contiguous_range']}/{s['slices']} "
              f"union_cp={s['union_codepoints']}")


if __name__ == "__main__":
    main()
