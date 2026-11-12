#!/usr/bin/env python3
"""Static font audit of 10 major Japanese sites.

One HTML request per site, up to 4 linked stylesheets, and HEAD probes for at
most 3 font binaries. No page crawling. Records font-family declarations,
@font-face rules, preload/preconnect hints, provider classification and font
response headers.
"""
import hashlib
import json
import re
import time
import urllib.parse
from urllib.parse import urljoin
from collections import Counter
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw" / "sites"
RAW.mkdir(parents=True, exist_ok=True)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA,
                  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                  "Accept-Language": "ja,en;q=0.8"})

SITES = [
    ("Yahoo! JAPAN", "portal", "https://www.yahoo.co.jp/"),
    ("NHK News", "news", "https://www3.nhk.or.jp/news/"),
    ("Asahi Shimbun", "news", "https://www.asahi.com/"),
    ("Rakuten Ichiba", "ecommerce", "https://www.rakuten.co.jp/"),
    ("Mercari", "marketplace", "https://jp.mercari.com/"),
    ("note", "blog platform", "https://note.com/"),
    ("Qiita", "tech community", "https://qiita.com/"),
    ("Zenn", "tech community", "https://zenn.dev/"),
    ("SmartHR Tech Blog", "corporate blog", "https://tech.smarthr.jp/"),
    ("CyberAgent Developers Blog", "corporate blog", "https://developers.cyberagent.co.jp/blog/"),
]

JP_SUFFIXES = {"co.jp", "ne.jp", "or.jp", "ac.jp", "go.jp", "lg.jp", "com.cn", "co.kr"}


def base_domain(host):
    parts = host.lower().split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in JP_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def brand(url):
    """Second-level label, a rough ownership signal (zenn.dev/zenn.studio)."""
    host = urllib.parse.urlparse(url if "//" in url else "https:" + url).netloc.lower()
    bd = base_domain(host)
    return bd.split(".")[0]


def provider_for(url, page_host):
    if not url:
        return "none"
    u = urllib.parse.urlparse(url if "//" in url else "https:" + url)
    host = u.netloc.lower()
    if "fonts.googleapis.com" in host or "fonts.gstatic.com" in host:
        return "Google Fonts"
    if "typekit.net" in host or "adobe.com" in host or "fonts.adobe" in host:
        return "Adobe Fonts"
    if base_domain(host) == base_domain(page_host):
        return "self-hosted"
    if brand(host) == brand(page_host):
        return "self-hosted (brand domain)"
    if any(x in host for x in ("cloudfront", "akamai", "fastly", "cdn")):
        return "external CDN"
    return "third-party"


def decode_css(content, content_type):
    import codecs
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if m:
        try:
            return content.decode(m.group(1), errors="replace")
        except LookupError:
            pass
    for enc in ("utf-8-sig", "utf-8", "cp932", "euc_jp"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def extract_faces(css, css_url, page_host):
    faces = []
    for m in re.finditer(r"@font-face\s*\{(.*?)\}", css, re.S | re.I):
        b = m.group(1)

        def prop(n):
            mm = re.search(rf"{n}\s*:\s*([^;}}]+)", b)
            return mm.group(1).strip() if mm else None

        src = prop("src") or ""
        urls = re.findall(r"url\(\s*['\"]?([^'\")]+)", src)
        urls = [urljoin(css_url, u.strip()) for u in urls if not u.strip().startswith("data:")]
        urls = [u if u.startswith(("http://", "https://", "//")) else urljoin(css_url, u)
                for u in urls]
        faces.append({
            "family": (prop("font-family") or "").strip("'\""),
            "style": prop("font-style"), "weight": prop("font-weight"),
            "display": prop("font-display"),
            "unicode_range": bool(prop("unicode-range")),
            "src_urls": urls,
            "src_hosts": sorted({urllib.parse.urlparse(
                u if "//" in u else "https:" + u).netloc for u in urls}),
            "providers": sorted({provider_for(u, page_host) for u in urls}),
            "source_css": css_url,
        })
    return faces


def font_families(css):
    vals = []
    for m in re.finditer(r"font-family\s*:\s*([^;}}]+)", css, re.I):
        v = re.sub(r"\s+", " ", m.group(1)).strip().strip("'\"")
        if not v or v.startswith("var(") or v in ("inherit", "initial", "unset"):
            continue
        vals.append(v)
    fams = []
    for v in vals:
        for p in v.split(","):
            p = p.strip().strip("'\"")
            if p and not p.startswith("var("):
                fams.append(p)
    return vals, fams


def head_font(url, page_host):
    try:
        r = S.head(url, timeout=25, allow_redirects=True)
        h = r.headers
        return {"url": url, "status": r.status_code, "final_url": r.url,
                "content_length": int(h["content-length"]) if h.get("content-length") else None,
                "content_type": h.get("content-type"), "server": h.get("server"),
                "cache_control": h.get("cache-control"),
                "access_control_allow_origin": h.get("access-control-allow-origin"),
                "last_modified": h.get("last-modified"), "etag": h.get("etag"),
                "via": h.get("via"), "x_cache": h.get("x-cache")}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "error": repr(e)[:200]}


def main():
    prev_map = {}
    jf = BASE / "major_sites.json"
    if jf.exists():
        prev_map = {p["name"]: p for p in json.loads(jf.read_text())}
    out = []
    for i, (name, genre, url) in enumerate(SITES):
        page_host = urllib.parse.urlparse(url).netloc
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        d = RAW / f"{i:02d}_{slug}"
        d.mkdir(exist_ok=True)
        rec = {"name": name, "genre": genre, "url": url,
               "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        css_all = []
        cached = d / "index.html"
        if cached.exists():
            content = cached.read_bytes()
            prev = prev_map.get(name, {})
            rec.update({"status": prev.get("status", 200),
                        "final_url": prev.get("final_url", url),
                        "html_bytes": len(content),
                        "response_headers": prev.get("response_headers", {}),
                        "html_from_cache": True})
            page_url = rec["final_url"]
        else:
            try:
                r = S.get(url, timeout=35, allow_redirects=True)
                content = r.content
                rec.update({"status": r.status_code, "final_url": r.url,
                            "html_bytes": len(content),
                            "response_headers": dict(r.headers)})
                cached.write_bytes(content)
                page_url = r.url
                if r.status_code != 200 or "html" not in r.headers.get("content-type", "").lower():
                    rec["error"] = f"status={r.status_code}"
                    out.append(rec)
                    print(f"{name}: bad status {r.status_code}")
                    continue
            except Exception as e:  # noqa: BLE001
                rec["error"] = repr(e)[:300]
                out.append(rec)
                print(f"{name}: fetch failed {e}")
                continue

        soup = BeautifulSoup(content, "html.parser")
        rec["title"] = soup.title.get_text(strip=True) if soup.title else ""

        # Inline styles
        inline = "\n".join(s.get_text() for s in soup.find_all("style"))
        css_all.append(("inline", "", inline))

        # Preload / preconnect hints
        preloads, preconnects = [], []
        for l in soup.find_all("link"):
            rel = " ".join(l.get("rel") or []).lower()
            href = l.get("href") or ""
            if "preload" in rel:
                preloads.append({"href": urljoin(r.url, href), "as": l.get("as"),
                                 "type": l.get("type"), "crossorigin": l.get("crossorigin")})
            if "preconnect" in rel or "dns-prefetch" in rel:
                preconnects.append({"href": href, "rel": rel})
        rec["preloads"] = preloads
        rec["preconnects"] = preconnects

        # Stylesheet links: same-origin first, then font services, max 4.
        links = []
        for l in soup.find_all("link"):
            rel = " ".join(l.get("rel") or []).lower()
            if "stylesheet" not in rel:
                continue
            href = l.get("href")
            if not href:
                continue
            full = urljoin(r.url, href)
            links.append(full)
        uniq = list(dict.fromkeys(links))
        font_svc = [u for u in uniq if any(h in u for h in
                    ("fonts.googleapis.com", "use.typekit.net", "p.typekit.net", "fonts.adobe.com"))]
        same = [u for u in uniq if u not in font_svc and
                base_domain(urllib.parse.urlparse(u).netloc) == base_domain(page_host)]
        chosen = (same[:2] + font_svc[:2] + [u for u in uniq if u not in same and u not in font_svc][:1])[:4]
        css_urls = chosen
        rec["stylesheet_links_total"] = len(uniq)
        rec["stylesheets_fetched"] = []
        for cu in chosen:
            try:
                cr = S.get(cu, timeout=25)
                body = cr.text
                (d / ("css_" + re.sub(r"[^a-zA-Z0-9]+", "_", cu)[-80:] + ".css")).write_text(body)
                css_all.append((cu, cu, body))
                rec["stylesheets_fetched"].append({
                    "url": cu, "status": cr.status_code, "bytes": len(cr.content),
                    "content_type": cr.headers.get("content-type"),
                    "content_encoding": cr.headers.get("content-encoding"),
                    "server": cr.headers.get("server")})
                time.sleep(0.2)
            except Exception as e:  # noqa: BLE001
                rec["stylesheets_fetched"].append({"url": cu, "error": repr(e)[:150]})
        rec["font_service_links"] = [u for u in uniq if any(h in u for h in
                                    ("fonts.googleapis", "typekit", "fonts.adobe"))]

        all_css = "\n".join(c for _, _, c in css_all)
        decls, fams = font_families(all_css)
        # include style="" attributes
        attr_styles = " ".join(t.get("style", "") for t in soup.find_all(style=True))
        if attr_styles:
            d2, f2 = font_families(attr_styles)
            decls += d2
            fams += f2
        rec["font_family_declaration_count"] = len(decls)
        rec["top_font_family_values"] = Counter(decls).most_common(12)
        rec["top_individual_families"] = Counter(fams).most_common(15)
        rec["unique_individual_families"] = len(set(fams))

        faces = []
        for src, cu, css in css_all:
            if "@font-face" in css:
                faces.extend(extract_faces(css, cu or r.url, page_host))
        rec["font_face_count"] = len(faces)
        rec["font_faces"] = faces
        rec["font_face_providers"] = dict(Counter(p for f in faces for p in f["providers"]))
        rec["font_face_hosts"] = dict(Counter(h for f in faces for h in f["src_hosts"]))

        # Adobe/Google script tags
        scripts = [s.get("src") for s in soup.find_all("script") if s.get("src")]
        rec["font_scripts"] = [s for s in scripts if any(
            k in s for k in ("typekit", "adobe", "fonts.googleapis"))]

        # Provider classification
        providers = set()
        for f in faces:
            providers.update(f["providers"])
        if any("fonts.googleapis" in u for u in uniq) or rec.get("font_scripts"):
            if any("fonts.googleapis" in u for u in uniq):
                providers.add("Google Fonts")
        if any("typekit" in u for u in uniq) or any("typekit" in (s or "") for s in scripts):
            providers.add("Adobe Fonts")
        rec["providers_detected"] = sorted(providers)
        rec["self_hosts_fonts"] = "self-hosted" in providers

        # Font request headers, max 3 distinct woff2.
        urls = []
        for f in faces:
            for u in f["src_urls"]:
                if u.lower().split("?")[0].endswith((".woff2", ".woff", ".otf", ".ttf")):
                    if u not in urls:
                        urls.append(u)
        for l in preloads:
            u = l.get("href")
            if u and u.lower().split("?")[0].endswith((".woff2", ".woff", ".otf", ".ttf")) and u not in urls:
                urls.append(u)
        rec["font_probes"] = []
        for u in urls[:3]:
            hh = head_font(u, page_host)
            hh["provider"] = provider_for(u, page_host)
            rec["font_probes"].append(hh)
            time.sleep(0.2)

        out.append(rec)
        print(f"{name:30s} faces={len(faces):3d} decls={len(decls):4d} "
              f"providers={rec['providers_detected']} patches={len(rec['font_probes'])}")
        time.sleep(1.0)

    (BASE / "major_sites.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))

    # compact CSV
    import csv
    with (BASE / "major_sites.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "genre", "url", "status", "font_face_count",
                    "font_family_declarations", "providers", "self_hosts",
                    "preload_font_count", "preconnect_font_count", "top_families"])
        for r in out:
            pre = [p for p in r.get("preloads", []) if (p.get("as") == "font" or
                   (p.get("href") or "").lower().split("?")[0].endswith((".woff2", ".woff")))]
            pc = [p for p in r.get("preconnects", []) if any(k in (p.get("href") or "") for k in
                  ("fonts.gstatic", "fonts.google", "typekit", "adobe"))]
            w.writerow([r["name"], r["genre"], r["url"], r.get("status"),
                        r.get("font_face_count", 0), r.get("font_family_declaration_count", 0),
                        ";".join(r.get("providers_detected", [])), r.get("self_hosts_fonts"),
                        len(pre), len(pc),
                        ";".join(f"{k} ({v})" for k, v in r.get("top_individual_families", [])[:5])])


if __name__ == "__main__":
    main()
